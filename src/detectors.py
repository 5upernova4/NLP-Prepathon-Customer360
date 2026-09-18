"""Tier 0, third half: the cheap detectors.

Each emits a Signal only when it actually fires. Across the practice scenarios
roughly 8% of live events trip anything, and only those wake the LLM tier --
that gate is the whole reason this is affordable.

The governing rule, stated precisely because it is easy to get wrong:
**no detector uses an absolute amount threshold.** Amounts are read
relationally -- against this customer's own fitted baseline, or against another
amount inside the same window -- never as "large means interesting". Ranking
scenario 1's live events by size puts both red herrings in the top seven and
scatters the real signals from rank 3 to rank 27. Size is close to useless here
and that is clearly deliberate on the organisers' part.

What separates signal from noise is novelty, cadence and corroboration.
Novelty TRIGGERS; it does not conclude. Bare first-in-category runs at about
2/3 precision (the resort refund and the electronics purchase are both novel
and both red herrings), so a novel category wakes the agents and nothing more.
The discrimination happens at the correlation step, where two independent
sources have to point at the same hypothesis.
"""
from __future__ import annotations

import datetime as dt

from .features import FeatureStore
from .schemas import Event, Signal

SWEEP_WINDOW_SECONDS = 6 * 3600
SWEEP_MATCH_RATIO = 0.90
SHORTFALL_RATIO = 0.85          # arrived < 85% of expected
DRAWDOWN_RATIO = 0.35           # 35% off peak balance
SILENCE_MULTIPLE = 3.0          # x the customer's own historical max gap
HEALTH_SPEND_MULTIPLE = 4.0     # x this customer's own median card transaction
HEALTH_CATEGORIES = ("healthcare", "pharmacy")


class DetectorBank:
    """All Tier-0 detectors. Stateless except for what the FeatureStore holds."""

    def __init__(self, store: FeatureStore):
        self.store = store
        self._recent_money: list[Event] = []

    def run(self, e: Event) -> list[Signal]:
        out: list[Signal] = []
        for fn in (self._novel_category, self._health_spend, self._sweep_pair,
                   self._drawdown,
                   self._si_diff, self._income_shortfall, self._competitor_transfer,
                   self._support_distress, self._search_intent, self._kyc_change,
                   self._expectation_breach):
            try:
                s = fn(e)
            except Exception:
                s = None
            if s:
                out.extend(s if isinstance(s, list) else [s])
        return out

    # ------------------------------------------------------------- detectors
    def _novel_category(self, e: Event) -> Signal | None:
        """First-ever merchant category. Wakes the agents; concludes nothing."""
        if e.source_system != "card_payments":
            return None
        mcc = e.payload.get("mcc_category")
        if not self.store.is_novel_mcc(mcc):
            return None
        return Signal("novel_category", e.event_id,
                      f"first-ever '{mcc}' against {sum(self.store.mcc_histogram.values())} "
                      f"historical card transactions",
                      payload={"mcc": mcc, "semantic_class": e.semantic_class})

    def _health_spend(self, e: Event) -> Signal | None:
        """Heavy medical spend, whether or not the category is still novel.

        novel_category fires once and then goes quiet, so on its own it misses
        the part of scenario 1 that actually matters: an $8,500 hospital bill
        three weeks after the first ER visit, by which point healthcare is no
        longer a new category. Sized against this customer's own median card
        transaction rather than a fixed number, so it means the same thing for
        someone who normally spends $60 and someone who normally spends $600.
        """
        if e.source_system != "card_payments":
            return None
        mcc = e.payload.get("mcc_category")
        amt = e.amount()
        if mcc not in HEALTH_CATEGORIES or amt is None:
            return None
        median = getattr(self.store, "baseline_median_card", None)
        if not median or abs(amt) < median * HEALTH_SPEND_MULTIPLE:
            return None
        return Signal("health_spend", e.event_id,
                      f"${abs(amt):,.0f} of {mcc} spend, "
                      f"{abs(amt)/median:.0f}x this customer's typical card transaction",
                      strength=min(2.0, 0.7 + abs(amt) / (median * 40)),
                      payload={"mcc": mcc, "amount": abs(amt)})

    def _sweep_pair(self, e: Event) -> Signal | None:
        """Near-equal out-and-in inside a short window = ONE movement.

        Scenario 1: $10,000 out of savings and $10,000 into checking, one
        second apart. Read as two events it looks like exfiltration and trips a
        fraud hold on someone who is paying hospital bills.
        """
        amt = e.amount()
        if amt is None:
            return None
        cutoff = e.event_time - dt.timedelta(seconds=SWEEP_WINDOW_SECONDS)
        self._recent_money = [x for x in self._recent_money if x.event_time >= cutoff]
        hit = None
        for prior in self._recent_money:
            pa = prior.amount()
            if pa is None or prior.account_id == e.account_id:
                continue
            ratio = min(abs(pa), abs(amt)) / max(abs(pa), abs(amt))
            if ratio >= SWEEP_MATCH_RATIO:
                hit = prior
                break
        self._recent_money.append(e)
        if not hit:
            return None
        return Signal("sweep_pair", e.event_id,
                      f"near-equal movement across accounts within "
                      f"{(e.event_time - hit.event_time).total_seconds()/60:.0f} min "
                      f"-- one drawdown, not two events",
                      payload={"paired_with": hit.event_id})

    def _drawdown(self, e: Event) -> Signal | None:
        """Balance off its own peak. Relational, not a dollar threshold."""
        if "balance_after" not in e.payload or not e.account_id:
            return None
        r = self.store.drawdown_ratio(e.account_id)
        if r < DRAWDOWN_RATIO:
            return None
        return Signal("balance_drawdown", e.event_id,
                      f"{e.account_id} is {r:.0%} below its own peak balance",
                      strength=min(2.0, r / DRAWDOWN_RATIO),
                      payload={"ratio": round(r, 3)})

    def _si_diff(self, e: Event) -> list[Signal]:
        """Recurring obligations are a set; watch the set change.

        A NEW obligation (daycare) and a CANCELLED one (rent, gym) mean
        opposite things, so they are separate signals.
        """
        out = []
        tt = e.payload.get("transaction_type")
        base = getattr(self.store, "baseline_sis", set())
        if tt and tt in {"daycare_payment"} and tt not in base:
            out.append(Signal("new_obligation", e.event_id,
                              f"new recurring commitment '{tt}' not in baseline",
                              payload={"kind": tt}))
        if e.payload.get("feature_or_page") == "manage_standing_instructions_cancel":
            out.append(Signal("si_cancel_intent", e.event_id,
                              "customer visited the cancel-standing-instructions page"))
        return out

    def _income_shortfall(self, e: Event) -> Signal | None:
        """Expected income arrived light, or arrived as something else."""
        tt = e.payload.get("transaction_type")
        if tt not in ("salary_credit", "benefits_credit"):
            return None
        exp = self.store.expectations.get("salary_credit")
        amt = e.amount()
        if not exp or not exp.amount or amt is None:
            return None
        ratio = abs(amt) / exp.amount
        if ratio >= SHORTFALL_RATIO and tt == "salary_credit":
            return None
        sub = " and as a different instrument" if tt != "salary_credit" else ""
        return Signal("income_shortfall", e.event_id,
                      f"income arrived at {ratio:.0%} of the ${exp.amount:.0f} "
                      f"baseline{sub}",
                      strength=min(2.0, (1 - ratio) * 2.5),
                      payload={"ratio": round(ratio, 3), "instrument": tt})

    def _competitor_transfer(self, e: Event) -> Signal | None:
        """Money leaving toward a competitor institution.

        The semantic class is doing the work: an identical amount to
        `education_institution` is a tuition payment and means nothing.
        """
        if e.semantic_class != "competitor_institution":
            return None
        return Signal("competitor_outflow", e.event_id,
                      "outbound transfer to a competitor institution",
                      payload={"class": e.semantic_class})

    def _support_distress(self, e: Event) -> Signal | None:
        """Any support message, opened OR resolved.

        Reading only ticket_created misses both of the interesting support
        events in this dataset: the customer explaining that a flagged purchase
        was theirs, and our own rejection of a fee complaint. Both arrive as
        ticket_resolved, and both change what we should believe.
        """
        if e.source_system != "support_logs":
            return None
        if e.event_type not in ("ticket_created", "ticket_resolved",
                                "call_transcript"):
            return None
        status = e.payload.get("resolution_status") or ""
        verb = "opened" if e.event_type == "ticket_created" else status or "closed"
        return Signal("support_ticket", e.event_id,
                      f"support contact ({e.payload.get('category')}, {verb})",
                      payload={"category": e.payload.get("category"),
                               "raw_text": e.payload.get("raw_text", ""),
                               "resolution_status": status,
                               "event_type": e.event_type})

    def _search_intent(self, e: Event) -> Signal | None:
        if e.event_type != "search_query":
            return None
        q = (e.payload.get("search_text") or "").lower()
        if not q:
            return None
        return Signal("search_intent", e.event_id, f"in-app search: '{q}'",
                      payload={"query": q})

    def _kyc_change(self, e: Event) -> Signal | None:
        if e.source_system != "loan_kyc":
            return None
        return Signal("kyc_change", e.event_id,
                      f"{e.event_type}: {e.payload.get('old_value')} -> "
                      f"{e.payload.get('new_value')}",
                      payload=dict(e.payload))

    def _expectation_breach(self, e: Event) -> Signal | None:
        """Synthetic events written by the ambient scheduler (see scheduler.py)."""
        if not e.synthetic or e.event_type != "expectation_breach":
            return None
        return Signal("expectation_breach", e.event_id,
                      e.payload.get("detail", "an expected arrival did not occur"),
                      strength=e.payload.get("strength", 1.0),
                      payload=dict(e.payload))
