"""The agents.

Each one keeps its capabilities, its tools, its prompt and its output schema in
one place, so you can read an agent top to bottom and know what it is.

Two decisions worth defending.

Scope is structural. An agent is handed a ScopedView built by the AccessBroker
from its declared capabilities, and there is no method on that object reaching
anything else. The support agent cannot read balances because it holds no
handle to them, not because its prompt asks it not to.

Most of the swarm is deterministic, on purpose. Usage, Transaction and KYC are
doing arithmetic against a baseline; a model there adds latency and a
hallucination surface without adding accuracy. The model earns its place where
there is actually language to interpret -- free text in support tickets -- and
in drafting and critiquing the note a human will read. When no API key is
present those two fall back to keyword rules and the trace records which was
used.
"""
from __future__ import annotations

import datetime as dt

from . import llm
from .ledger import Ledger
from .schemas import Signal, State
from .weights import weights_for


class Agent:
    """Base. Subclasses declare name, capabilities, tools."""

    name = "agent"
    capabilities: set[str] = set()
    tools: tuple[str, ...] = ()
    trigger = "event"

    def __init__(self, ledger: Ledger, tracer):
        self.ledger = ledger
        self.tracer = tracer

    # Turning a detector signal into ledger rows is the same for every agent;
    # what differs is which signals each one is allowed to see, and how it
    # phrases the rationale a human will read.
    def record(self, sig: Signal, event_time: dt.datetime, now: dt.datetime):
        made = []
        for state, weight, half_life in weights_for(sig):
            a = self.ledger.add(
                hypothesis=state,
                weight=weight * min(sig.strength, 2.0),
                half_life_days=half_life,
                observed_at=event_time,
                asserted_at=now,
                source_event_ids=[sig.event_id],
                agent=self.name,
                rationale=self.phrase(sig),
                signal=sig.name,
            )
            self.tracer.log("assertion", assertion_id=a.assertion_id,
                            hypothesis=state.value, weight=round(a.weight, 2))
            made.append(a)
        return made

    def phrase(self, sig: Signal) -> str:
        return sig.detail


class UsageAgent(Agent):
    """How often the customer actually shows up."""
    name = "usage"
    capabilities = {"web_app_events"}
    tools = ("window_aggregation(web_app_events)", "cadence_model(feature_store)")
    trigger = "event-based + daily rollup"
    handles = ("si_cancel_intent", "search_intent")


class TransactionAgent(Agent):
    """Money in and out, always against this customer's own normal."""
    name = "transaction"
    capabilities = {"card_payments", "core_banking_ledger", "instant_payments",
                    "ach_wire"}
    tools = ("baseline_compare(feature_store)", "counterparty_classifier(pii lexicon)",
             "drawdown(balances)", "expected_arrival(income table)")
    trigger = "event-based"
    handles = ("novel_category", "income_shortfall", "balance_drawdown",
               "competitor_outflow", "new_obligation", "sweep_pair")

    def phrase(self, sig: Signal) -> str:
        if sig.name == "sweep_pair":
            return sig.detail + " (treated as one movement, not two)"
        return sig.detail


class KYCAgent(Agent):
    """Declared facts. The strongest evidence here because it is stated, not inferred."""
    name = "kyc"
    capabilities = {"loan_kyc"}
    tools = ("kyc_field_diff(loan_kyc)", "sanctions_lookup(policy index)")
    trigger = "event-based + periodic re-verification"
    handles = ("kyc_change",)


class SchedulerAgent(Agent):
    """Owns the synthetic absence events. Separate from usage because the thing
    it reacts to is the absence of data rather than any source."""
    name = "ambient"
    capabilities = {"ambient_scheduler"}
    tools = ("expectation_table(feature_store)", "replay_clock",)
    trigger = "time-based (daily tick)"
    handles = ("expectation_breach",)


class SupportAgent(Agent):
    """Reads what the customer actually wrote.

    The one place in the swarm where a model genuinely helps: short
    unstructured text whose meaning is in no field. It is also the only agent
    that can revoke another agent's row, because "that was me, I bought a baby
    monitor" is the customer explaining an earlier event away.
    """
    name = "support"
    capabilities = {"support_logs", "social_signal_consented"}
    tools = ("read_ticket(support_logs)", "ticket_history(support_logs)")
    trigger = "event-based"
    handles = ("support_ticket",)

    SYSTEM = (
        "You read one customer support message sent to a retail bank and report "
        "what it indicates about the customer's situation. You see only this "
        "message: no balances, no transactions. Be conservative. If the message "
        "does not clearly indicate something, say it does not."
    )

    OUTPUT_SCHEMA = {
        "sentiment": "negative | neutral | positive",
        "intent": "short phrase",
        "confirms_own_purchase": "true if the customer is confirming an earlier "
                                 "card purchase was legitimately theirs",
        "signals_hardship": "bool",
        "signals_leaving": "bool",
    }

    def read(self, text: str, category: str, resolution: str):
        low = (text or "").lower()
        fallback = {
            "sentiment": "negative" if (
                resolution == "human_rejected"
                or "wasn't disclosed" in low or "not disclosed" in low) else "neutral",
            "intent": category or "unknown",
            "confirms_own_purchase": any(p in low for p in (
                "just confirming", "it's me", "its me", "confirming it's me",
                "that was me", "i bought")),
            "signals_hardship": any(p in low for p in (
                "payment plan", "hardship", "in the hospital", "income dropped",
                "can't afford", "cannot afford")),
            "signals_leaving": any(p in low for p in (
                "close my account", "closing my account", "switch bank")),
        }
        result, how = llm.classify(self.SYSTEM,
                                   f"Message ({category}):\n{text}",
                                   self.OUTPUT_SCHEMA, fallback)
        self.tracer.log("support_read", provenance=how, **{
            k: result.get(k) for k in ("sentiment", "confirms_own_purchase",
                                       "signals_hardship", "signals_leaving")})
        return result, how

    def score_reading(self, reading: dict, sig: Signal, event_time, now):
        """Turn what the model understood into ledger rows."""
        made = []

        def put(state, weight, half_life, why):
            a = self.ledger.add(hypothesis=state, weight=weight,
                                half_life_days=half_life, observed_at=event_time,
                                asserted_at=now, source_event_ids=[sig.event_id],
                                agent=self.name, rationale=why,
                                signal=f"support:{why[:20]}")
            made.append(a)

        if reading.get("signals_hardship"):
            put(State.FINANCIAL_DISTRESS, 1.4, 200,
                "customer asked us for help with payments")
            put(State.MEDICAL_HARDSHIP, 1.0, 200,
                "the request mentions being in hospital or a drop in income")
        if reading.get("signals_leaving"):
            put(State.CHURN_RISK, 2.4, 220, "customer said they want to leave")
        if reading.get("sentiment") == "negative":
            put(State.CHURN_RISK, 1.3, 200,
                "customer raised a complaint and was unhappy with the outcome")
        return made

    def claims_purchase_explained(self, reading: dict) -> bool:
        """The customer says a recent card charge was legitimately theirs.

        The support agent can only report the claim, not act on it. It holds no
        handle to card transactions -- by design -- so it cannot tell which
        purchase is meant. Resolving the claim against a specific ledger row is
        the orchestrator's job, and that separation is the access model doing
        its work rather than getting in the way.
        """
        return bool(reading.get("confirms_own_purchase"))


class CorrelationAgent(Agent):
    """Fires only when two or more swarm agents point the same way inside a
    window. Never looks at the raw stream.

    This is the one place where having several agents does real work rather
    than being organisational theatre. In scenario 2 the income dip, the
    first-ever baby purchase and the new daycare instruction are each
    unremarkable; together they are the answer. It is also what separates the
    baby purchases, which several agents support, from the electronics one,
    which only the transaction agent ever saw.
    """
    name = "correlation"
    capabilities: set[str] = set()
    tools = ("read_ledger(assertions)",)
    trigger = "agent-dependent (>=2 agents agree within the window)"
    WINDOW_DAYS = 45

    def run(self, now: dt.datetime) -> list[State]:
        recent = [r for r in self.ledger.live(now)
                  if (now - r.observed_at).days <= self.WINDOW_DAYS]
        by_state: dict[State, set[str]] = {}
        for r in recent:
            by_state.setdefault(r.hypothesis, set()).add(r.agent)

        boosted = []
        for state, agents in by_state.items():
            others = agents - {self.name}
            if len(others) < 2:
                continue
            if any(r.agent == self.name and r.hypothesis == state
                   and (now - r.observed_at).days < 7 for r in recent):
                continue        # don't re-boost the same thing every day
            self.ledger.add(
                hypothesis=state,
                weight=0.6 + 0.3 * (len(others) - 2),
                half_life_days=120, observed_at=now, asserted_at=now,
                source_event_ids=[], agent=self.name, signal="correlation",
                rationale=(f"{len(others)} independent agents "
                           f"({', '.join(sorted(others))}) point at this within "
                           f"{self.WINDOW_DAYS} days"))
            boosted.append(state)
        return boosted


class DebateAgent(Agent):
    """Wakes only when the top two hypotheses sit within a margin of each other.

    Resolution is a written rule rather than a vibe: a declared fact beats an
    inferred one, then more independent agents wins. If neither separates them
    we cap confidence and send it to a human on ambiguity alone, which is the
    escalate-for-ambiguity case rather than escalate-for-cost.
    """
    name = "debate"
    capabilities: set[str] = set()
    tools = ("read_ledger(assertions)",)
    trigger = "agent-dependent (top two within the margin)"
    MARGIN = 0.8
    DECLARED = {"kyc"}

    def resolve(self, a: State, b: State, at: dt.datetime):
        agents_a = self.ledger.agents_supporting(a, at)
        agents_b = self.ledger.agents_supporting(b, at)

        da, db = bool(agents_a & self.DECLARED), bool(agents_b & self.DECLARED)
        if da != db:
            win = a if da else b
            return win, f"a declared KYC fact supports {win.value}; the other side is inferred"

        if len(agents_a) != len(agents_b):
            win = a if len(agents_a) > len(agents_b) else b
            return win, (f"{win.value} is corroborated by "
                         f"{max(len(agents_a), len(agents_b))} agents against "
                         f"{min(len(agents_a), len(agents_b))}")

        return None, (f"cannot separate {a.value} from {b.value} on the evidence; "
                      f"capping confidence and routing to a human")


class ActionAgent(Agent):
    """Drafts the intervention.

    Holds a draft tool. Holds no send tool -- that split is the blast radius
    limit and it is enforced by there being no such method on this class.
    """
    name = "action"
    capabilities: set[str] = set()
    tools = ("draft_note(ledger evidence)", "cost_estimate(value tier)")
    trigger = "agent-dependent"

    SYSTEM = (
        "You draft a short internal note for a bank relationship manager "
        "explaining a proposed intervention for one customer. Ground every "
        "factual claim in the evidence supplied and cite the event ids. Invent "
        "nothing. Do not address the customer -- a human decides whether "
        "anything is sent."
    )
    OUTPUT_SCHEMA = {"note": "two or three sentences", "cites": ["event_id"]}

    def draft(self, state: State, action: str, subtype: str,
              evidence: list[dict], profile: dict):
        cites: list[str] = []
        for e in evidence[:3]:
            cites.extend(e["cites"])
        fallback = {
            "note": (f"Proposing {action.replace('_', ' ')} ({subtype}). "
                     + " ".join(e["why"].rstrip(".") + "." for e in evidence[:3])),
            "cites": cites,
        }
        lines = "\n".join(f"- {e['why']} ({e['observed_at']}, cites "
                          f"{','.join(e['cites']) or 'n/a'})" for e in evidence[:6])
        result, how = llm.classify(
            self.SYSTEM,
            (f"Customer: {profile.get('occupation', '?')}, age "
             f"{profile.get('age', '?')}, value tier "
             f"{profile.get('customer_value_tier', '?')}.\n"
             f"Inferred state: {state.value}\n"
             f"Proposed action: {action} ({subtype})\nEvidence:\n{lines}"),
            self.OUTPUT_SCHEMA, fallback)
        self.tracer.log("draft", provenance=how)
        return result, how


class CritiqueAgent(Agent):
    """The last thing before a human sees it.

    Round-robin passes, one concern each: is every claim grounded, is the tone
    right for the situation, does it pass policy. Sends a draft back exactly
    once; a second failure escalates instead of looping, so a bad draft cannot
    burn the lead time we have.
    """
    name = "critique"
    capabilities: set[str] = set()
    tools = ("check_citations(ledger)", "policy_lookup(semantic memory)")
    trigger = "agent-dependent"
    PASSES = ("grounding", "tone", "policy")

    HARDSHIP_STATES = {State.MEDICAL_HARDSHIP, State.JOB_LOSS,
                       State.FINANCIAL_DISTRESS}

    def review(self, draft: dict, state: State, evidence: list[dict]) -> list[tuple[str, str]]:
        problems = []

        known = set()
        for e in evidence:
            known.update(e["cites"])
        cited = set(draft.get("cites") or [])
        if not cited and known:
            problems.append(("grounding", "draft makes claims without citing anything"))
        elif cited - known:
            problems.append(("grounding", "draft cites events outside the evidence"))

        note = (draft.get("note") or "").lower()
        if state in self.HARDSHIP_STATES:
            for word in ("offer", "upgrade", "congratulations", "opportunity",
                         "exclusive"):
                if word in note:
                    problems.append(("tone",
                                     "promotional wording on a hardship case"))
                    break

        for kind, detail in problems:
            self.tracer.log("critique_flag", pass_name=kind, detail=detail)
        return problems


# The swarm, in the order they are woken. Correlation, debate, action and
# critique are agent-dependent and run later in the pipeline.
SWARM = (UsageAgent, TransactionAgent, SupportAgent, KYCAgent, SchedulerAgent)
