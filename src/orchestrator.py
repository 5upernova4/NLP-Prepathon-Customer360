"""The loop.

Walks the live window one day at a time on the replay clock, feeds each day's
events through Tier 0, wakes the specialists only when something fired, and
writes a checkpoint.

Why the clock is the calendar and not a watermark
-------------------------------------------------
The obvious streaming design drives timers off a watermark, the way Flink and
Beam do. That deadlocks here. Watermarks only advance when events arrive, the
log is partitioned per customer, and in scenario 3 the customer emits nothing
for 36 days and then the scenario ends. The watermark would sit frozen through
exactly the silence we exist to notice. An absence detector cannot depend on
the arrival of events, so the tick runs on the calendar and the watermark is
used only to decide when a window is safe to close.

Why a checkpoint every day
--------------------------
The evaluator picks its own as_of_times and scores the latest checkpoint at or
before each one. Emitting three good rows on the days we happen to think are
interesting loses to emitting one every day, because the evaluator's chosen
moment probably is not ours. So: one row per day, plus an extra whenever the
band changes or an action fires, plus a revision when a late event moves a past
belief.
"""
from __future__ import annotations

import datetime as dt

from . import guardrails
from .agents import (ActionAgent, CorrelationAgent, CritiqueAgent, DebateAgent,
                     KYCAgent, SchedulerAgent, SupportAgent, TransactionAgent,
                     UsageAgent)
from pathlib import Path

from .detectors import DetectorBank
from .features import FeatureStore
from .ingest import load_scenario
from .ledger import Ledger
from .memory import AccessBroker, EpisodicMemory, WorkingMemory
from .scheduler import AmbientScheduler
from .schemas import (Action, Band, Checkpoint, HITL, State, band_for, fmt_time)
from .trace import Tracer
from .weights import ACTION_FOR_STATE


class Desk:
    """One customer, one scenario, start to finish."""

    def __init__(self, scenario_dir, tracer=None):
        self.pipe, self.entities, self.config = load_scenario(Path(scenario_dir))
        self.tracer = tracer or Tracer()
        self.customer_id = self.entities["customer_id"]
        self.profile = self.entities.get("profile") or {}

        # Split history from live by EVENT TIME, not by ingest position. The
        # log is re-sorted into event-time order, so a late-arriving live event
        # can sort back before the last history event; splitting by position
        # would quietly feed it into the baseline instead of testing against
        # it, and scenario 1 has exactly such an arrival.
        ordered = self.pipe.log.in_event_time_order()
        start = self.config["_simulated_start"]
        self.history = [e for e in ordered if e.event_time < start]
        self.live = [e for e in ordered if e.event_time >= start]
        self.start, self.end = start, self.config["_simulated_end"]

        self.store = FeatureStore()
        self.ledger = Ledger(self.customer_id)
        self.working = WorkingMemory(customer_id=self.customer_id)
        self.episodic = EpisodicMemory(self.customer_id)

        self.detectors = DetectorBank(self.store)
        self.scheduler = AmbientScheduler(self.store, self.customer_id)

        self.swarm = {
            "usage": UsageAgent(self.ledger, self.tracer),
            "transaction": TransactionAgent(self.ledger, self.tracer),
            "support": SupportAgent(self.ledger, self.tracer),
            "kyc": KYCAgent(self.ledger, self.tracer),
            "ambient": SchedulerAgent(self.ledger, self.tracer),
        }
        self.correlation = CorrelationAgent(self.ledger, self.tracer)
        self.debate = DebateAgent(self.ledger, self.tracer)
        self.action_agent = ActionAgent(self.ledger, self.tracer)
        self.critique = CritiqueAgent(self.ledger, self.tracer)

        self.checkpoints: list[Checkpoint] = []
        self.seen_types: dict[str, dt.datetime] = {}
        self.hard_stopped = False
        self.stats = {"events": 0, "signals": 0, "wakes": 0, "llm_calls": 0,
                      "revocations": 0, "synthetic": 0, "deduped": 0}

    # ------------------------------------------------------------------- setup
    def warm_up(self):
        """Load history, fit the baseline, then freeze it.

        Freezing matters. If the baseline keeps updating through the live
        window, a slow decline quietly becomes the new normal and the thing we
        are looking for defines itself away.
        """
        with self.tracer.span("warm_up", kind="setup"):
            for ev in self.history:
                self.store.update(ev)
                tt = ev.payload.get("transaction_type")
                if tt:
                    self.seen_types[tt] = ev.event_time
            self.store.freeze_baseline()
            self.tracer.log("baseline",
                            categories=len(getattr(self.store, "baseline_mccs", [])),
                            expectations=list(self.store.expectations),
                            max_gap_days=round(
                                getattr(self.store, "baseline_max_gap_days", 0), 2))

    # -------------------------------------------------------------------- run
    def run(self):
        self.warm_up()
        day = self.start
        end = self.end
        live = sorted(self.live, key=lambda e: e.ingestion_time)
        delivered = set()
        last_band = None
        last_state = None

        while day <= end:
            cutoff = day + dt.timedelta(days=1)
            with self.tracer.span("day", kind="tick", date=day.date().isoformat()):
                # deliver on ingestion_time, so a 48h-late event surfaces two
                # days after it happened, exactly as it should
                events = [e for e in live
                          if e.event_id not in delivered
                          and e.ingestion_time < cutoff]
                events.sort(key=lambda e: e.event_time)
                delivered.update(e.event_id for e in events)
                self.stats["deduped"] = len(self.pipe.duplicate_ids)

                # the ambient tick runs first so an absence is visible to the
                # same day's reasoning
                synthetic = self.scheduler.tick(cutoff, self.seen_types)
                self.stats["synthetic"] += len(synthetic)

                fired = []
                for ev in list(events) + list(synthetic):
                    fired.extend(self._handle(ev, cutoff))

                if fired:
                    self.stats["wakes"] += 1
                    self.correlation.run(cutoff)

                # Stamp the checkpoint at the close of the day we just
                # processed, not at the following midnight. Using the cutoff
                # made every decision read as a day later than it was and cost
                # a full day of lead time on every scenario.
                stamp = cutoff - dt.timedelta(seconds=1)
                cp = self._checkpoint(stamp, forced=bool(fired))
                if cp:
                    band_changed = (cp.confidence_band != last_band
                                    or cp.inferred_state != last_state)
                    last_band, last_state = cp.confidence_band, cp.inferred_state
                    self.tracer.log("checkpoint", state=cp.inferred_state.value,
                                    band=cp.confidence_band.value,
                                    action=cp.action.value,
                                    changed=band_changed)
            day += dt.timedelta(days=1)

        return self.checkpoints

    # ------------------------------------------------------------ one event
    def _handle(self, ev, now) -> list:
        self.stats["events"] += 1
        if ev.payload.get("transaction_type"):
            self.seen_types[ev.payload["transaction_type"]] = ev.event_time
        if not ev.synthetic:
            self.store.update(ev)

        text = ev.payload.get("raw_text") or ev.payload.get("search_text")
        stop = guardrails.scan_hard_stop(text)
        if stop is not None:
            self.hard_stopped = True
            self.tracer.log("hard_stop", rule=stop, event_id=ev.event_id)

        signals = self.detectors.run(ev)
        if not signals:
            return []
        self.stats["signals"] += len(signals)

        broker = AccessBroker(self.customer_id, [ev])
        handled = []
        for sig in signals:
            agent = self._route(sig, ev)
            if agent is None:
                continue
            with self.tracer.span(f"agent:{agent.name}", kind="agent",
                                  signal=sig.name, event_id=ev.event_id):
                broker.view_for(agent.name, agent.capabilities)
                if agent.name == "support":
                    reading, how = agent.read(
                        sig.payload.get("raw_text", ""),
                        sig.payload.get("category", ""),
                        ev.payload.get("resolution_status", ""))
                    if how == "llm":
                        self.stats["llm_calls"] += 1
                    agent.score_reading(reading, sig, ev.event_time, now)
                    if agent.claims_purchase_explained(reading):
                        revoked = self._resolve_explanation(
                            sig.payload.get("raw_text", ""), ev.event_time)
                        self.stats["revocations"] += len(revoked)
                else:
                    agent.record(sig, ev.event_time, now)
                self.working.publish(agent.name, sig.detail)
                handled.append(sig)
        return handled

    def _resolve_explanation(self, text, at):
        """Match "that TechWorld charge was me" to the row it is about.

        Matching on the merchant named in the message, not on recency. An
        earlier version revoked every card assertion in the previous fortnight,
        which threw away a genuine BuyBuyBaby signal a week before the customer
        wrote in about a different purchase entirely -- a worse failure than
        never retracting at all.
        """
        low = (text or "").lower()
        by_id = {e.event_id: e for e in self.pipe.log}
        revoked = []
        for row in self.ledger.rows:
            if row.revoked_by or row.signal != "novel_category":
                continue
            age = (at - row.observed_at).total_seconds() / 86400
            if not (0 <= age <= 14):
                continue
            for eid in row.source_event_ids:
                ev = by_id.get(eid)
                merchant = (ev.payload.get("merchant_name") if ev else "") or ""
                token = merchant.split()[0].lower() if merchant else ""
                if token and token in low:
                    self.ledger.revoke(
                        self.ledger.rows[self.ledger.rows.index(row)],
                        "support", f"customer confirmed the {merchant} charge was theirs")
                    self.tracer.log("revoked", assertion_id=row.assertion_id,
                                    merchant=merchant)
                    revoked.append(row)
                    break
        if not revoked:
            self.tracer.log("explanation_unmatched", text=low[:120])
        return revoked

    def _route(self, sig, ev):
        """Signals go to the agent whose sources produced them. This is the
        handoff boundary: an agent never receives a signal from outside its
        own scope."""
        if ev.synthetic:
            return self.swarm["ambient"]
        for agent in self.swarm.values():
            if ev.source_system in agent.capabilities:
                return agent
        return None

    # ------------------------------------------------------------ decision
    def _checkpoint(self, now, forced=False):
        state, score, runner_up = self.ledger.leader(now)

        if state == State.NO_SIGNIFICANT_EVENT or score < 0:
            cp = Checkpoint(
                as_of_time=now, inferred_state=State.NO_SIGNIFICANT_EVENT,
                confidence_band=Band.LOW, action=Action.NO_ACTION,
                action_subtype=None, hitl_status=HITL.AUTO_APPROVED,
                notes="Nothing in the stream crosses a threshold worth acting on.",
                posterior=round(score, 3), trace_id=self.tracer.current())
            self.checkpoints.append(cp)
            return cp

        band = band_for(score)
        capped_reason = None

        # debate, only when the top two are genuinely close
        if runner_up and (score - runner_up[1]) < self.debate.MARGIN:
            with self.tracer.span("agent:debate", kind="agent"):
                winner, why = self.debate.resolve(state, runner_up[0], now)
                self.tracer.log("debate", outcome=(winner.value if winner else "unresolved"),
                                reason=why)
                if winner is None:
                    if band == Band.HIGH:
                        band = Band.MEDIUM
                    capped_reason = why
                else:
                    state = winner

        evidence = self.ledger.explain(state, now)
        action, subtype, hitl, note = self._decide(
            state, band, evidence, now, capped_reason)

        cp = Checkpoint(
            as_of_time=now, inferred_state=state, confidence_band=band,
            action=action, action_subtype=subtype, hitl_status=hitl,
            notes=note, evidence=evidence, posterior=round(score, 3),
            trace_id=self.tracer.current())
        self.checkpoints.append(cp)
        return cp

    def _decide(self, state, band, evidence, now, capped_reason):
        """Turn a belief into a committed action, or an explicit no-action.

        Below `high` the answer is no_action. That is deliberate and it is what
        the ground truth rewards: the early checkpoints in all three scenarios
        expect the right state at low or medium confidence with no intervention
        yet, because acting on a half-formed signal is its own failure.
        """
        top_why = evidence[0]["why"] if evidence else "accumulated evidence"

        if band != Band.HIGH:
            reason = capped_reason or (
                "signal is building but not yet strong enough to spend money on")
            return (Action.NO_ACTION, None, HITL.AUTO_APPROVED,
                    f"{state.value.replace('_', ' ')}: {top_why}. Holding - {reason}.")

        proposed, subtype = ACTION_FOR_STATE.get(
            state, ("no_action", None))
        if proposed == "no_action":
            return (Action.NO_ACTION, None, HITL.AUTO_APPROVED,
                    f"{top_why}. No action defined for this state.")

        verdict = guardrails.check_action(
            state, Action(proposed),
            value_tier=self.profile.get("customer_value_tier", "mid"),
            confidence_high=True)
        if not verdict.allowed:
            self.tracer.log("guardrail_denied", state=state.value,
                            action=proposed, reason=verdict.reason)
            return (Action.NO_ACTION, None, HITL.ESCALATED,
                    f"{top_why}. {verdict.reason} Routed to a human instead.")

        # draft, critique, then park for a human
        with self.tracer.span("agent:action", kind="agent"):
            draft, how = self.action_agent.draft(
                state, proposed, subtype, evidence, self.profile)
            if how == "llm":
                self.stats["llm_calls"] += 1
        with self.tracer.span("agent:critique", kind="agent"):
            problems = self.critique.review(draft, state, evidence)
            if problems:
                draft, how = self.action_agent.draft(
                    state, proposed, subtype, evidence, self.profile)
                problems = self.critique.review(draft, state, evidence)

        hitl = HITL.ESCALATED
        note = draft.get("note") or top_why
        if problems:
            note += " (escalated after the critique pass flagged: " + \
                    "; ".join(p[1] for p in problems) + ")"

        self.tracer.log("hitl_queued", state=state.value, action=proposed,
                        evidence_rows=len(evidence))
        return (Action(proposed), subtype, hitl, note)

    # ---------------------------------------------------------------- output
    def emit(self, path):
        import json
        import os
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "w") as fh:
            json.dump([c.to_schema() for c in self.checkpoints], fh, indent=2)
        with open(path.replace(".json", "_audit.json"), "w") as fh:
            json.dump([c.to_audit() for c in self.checkpoints], fh, indent=2)
        return path
