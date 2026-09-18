"""Tier 0, second half: the incremental feature store.

Updated on every event. No LLM in this path -- these are the running
aggregates the cheap detectors read, and the baseline against which 'unusual'
is defined per customer rather than per population.

The expected-arrival table is the piece that matters most. For every recurring
stream (salary, rent, gym, utilities) it holds an observed period and amount
fitted from history. That table is what lets the system notice something that
did NOT happen, which is the only way scenario 3 is catchable at all.
"""
from __future__ import annotations

import collections
import datetime as dt
import statistics as st

from .schemas import Event

RECURRING_TYPES = {
    "salary_credit", "benefits_credit", "mortgage_payment", "rent_payment",
    "gym_membership", "utilities", "daycare_payment",
}
ENGAGEMENT_SOURCES = ("card_payments", "web_app_events")


class Expectation:
    """One recurring stream's fitted arrival model."""

    def __init__(self, kind: str, times: list[dt.datetime], amounts: list[float]):
        self.kind = kind
        self.observations = len(times)
        self.last_seen = max(times)
        gaps = [(b - a).days for a, b in zip(sorted(times), sorted(times)[1:])]
        self.period_days = st.median(gaps) if gaps else None
        self.amount = st.median(amounts) if amounts else None
        # Tolerance widens with observed jitter; a stream seen 12 times at
        # exactly 14 days gets a tight window, a noisy one gets a loose one.
        self.tolerance_days = max(2, int(st.pstdev(gaps)) + 1) if len(gaps) > 1 else 3

    def next_due(self, after: dt.datetime) -> dt.datetime | None:
        if not self.period_days:
            return None
        t = self.last_seen
        while t <= after:
            t += dt.timedelta(days=self.period_days)
        return t

    def __repr__(self) -> str:
        return (f"<Expectation {self.kind} ${self.amount:.0f}/"
                f"{self.period_days:.0f}d n={self.observations}>")


class FeatureStore:
    """Per-customer running state. Everything here is incremental."""

    def __init__(self):
        self.mcc_histogram: collections.Counter = collections.Counter()
        self.counterparty_classes: collections.Counter = collections.Counter()
        self.balances: dict[str, float] = {}
        self.balance_peak: dict[str, float] = {}
        self.standing_instructions: set[str] = set()
        self.engagement_times: list[dt.datetime] = []
        self.last_engagement: dt.datetime | None = None
        self.txn_times: dict[str, list[dt.datetime]] = collections.defaultdict(list)
        self.txn_amounts: dict[str, list[float]] = collections.defaultdict(list)
        self.expectations: dict[str, Expectation] = {}
        self.event_count = 0
        self._card_amounts: list[float] = []
        self._frozen = False

    # ------------------------------------------------------------------ write
    def update(self, e: Event) -> None:
        self.event_count += 1
        p = e.payload

        if e.source_system in ENGAGEMENT_SOURCES:
            self.engagement_times.append(e.event_time)
            self.last_engagement = (e.event_time if self.last_engagement is None
                                    else max(self.last_engagement, e.event_time))

        if e.source_system == "card_payments" and p.get("mcc_category"):
            self.mcc_histogram[p["mcc_category"]] += 1
            if not self._frozen and e.amount() is not None:
                self._card_amounts.append(abs(e.amount()))

        if e.semantic_class and e.source_system in ("ach_wire", "instant_payments"):
            self.counterparty_classes[e.semantic_class] += 1

        if "balance_after" in p and e.account_id:
            bal = p["balance_after"]
            self.balances[e.account_id] = bal
            self.balance_peak[e.account_id] = max(
                self.balance_peak.get(e.account_id, bal), bal)

        tt = p.get("transaction_type")
        if tt:
            self.txn_times[tt].append(e.event_time)
            amt = e.amount()
            if amt is not None:
                self.txn_amounts[tt].append(abs(amt))
            if tt in RECURRING_TYPES:
                self.standing_instructions.add(tt)

    def freeze_baseline(self) -> None:
        """Fit the expected-arrival table from history, then stop refitting.

        Refitting during the live window would let a stream that is lapsing
        quietly widen its own tolerance until the lapse looks normal -- the
        baseline has to be the customer's ordinary behaviour, not their
        behaviour during the event being detected.
        """
        for kind, times in self.txn_times.items():
            if kind in RECURRING_TYPES and len(times) >= 3:
                self.expectations[kind] = Expectation(
                    kind, times, self.txn_amounts.get(kind, []))
        self._frozen = True
        self.baseline_mccs = set(self.mcc_histogram)
        self.baseline_median_card = (st.median(self._card_amounts)
                                     if self._card_amounts else None)
        self.baseline_sis = set(self.standing_instructions)
        gaps = self._engagement_gaps()
        self.baseline_max_gap_days = max(gaps) if gaps else 1.0
        self.baseline_mean_gap_days = st.mean(gaps) if gaps else 1.0

    # ------------------------------------------------------------------- read
    def _engagement_gaps(self) -> list[float]:
        ts = sorted(self.engagement_times)
        return [(b - a).total_seconds() / 86400 for a, b in zip(ts, ts[1:])]

    def silence_days(self, at: dt.datetime) -> float:
        if not self.last_engagement:
            return 0.0
        return (at - self.last_engagement).total_seconds() / 86400

    def is_novel_mcc(self, mcc: str | None) -> bool:
        return bool(mcc) and mcc not in getattr(self, "baseline_mccs", set())

    def drawdown_ratio(self, account_id: str) -> float:
        peak = self.balance_peak.get(account_id)
        cur = self.balances.get(account_id)
        if not peak or cur is None or peak <= 0:
            return 0.0
        return max(0.0, (peak - cur) / peak)

    def snapshot(self) -> dict:
        return {
            "events_seen": self.event_count,
            "mcc_histogram": dict(self.mcc_histogram),
            "balances": dict(self.balances),
            "standing_instructions": sorted(self.standing_instructions),
            "expectations": {k: repr(v) for k, v in self.expectations.items()},
        }
