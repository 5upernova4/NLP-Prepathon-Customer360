"""The ambient scheduler -- absence as a first-class event.

This is the mechanism scenario 3 exists to test, and it is the part most
likely to be missing from a naive implementation.

David Chen's last card transaction or app session is 9 March; the window runs
to 15 April. That is 36 days of nothing against a historical maximum gap of 2
days -- eighteen times the largest silence he has ever produced. In those 36
days exactly four events arrive: salary in at 08:00 and $4,900 straight back
out at 09:15, twice over. The account has become a pipe.

No event-driven trigger can fire on that, because there is no event. So a
scheduled tick does it instead: compare the expected-arrival table against what
actually landed, and when an expectation lapses, write a synthetic
`expectation_breach` event into the same immutable log. From that point the
ordinary machinery handles it -- detectors run, agents wake, assertions get
written. Absence becomes something the event-driven system can see.

ONE DETAIL IS LOAD-BEARING and it is easy to get backwards. The tick is driven
by the REPLAY CLOCK, not by watermark advance. The natural streaming instinct
is to arm a timer and fire it when the watermark passes -- which is how Flink
and Beam do it. That design deadlocks here: watermarks only advance when events
arrive, this customer emits nothing for 36 days, so the watermark stalls at the
last activity and the timer never fires. The mechanism built to catch the
silence would itself be silent. An absence detector cannot depend on the
arrival of events.
"""
from __future__ import annotations

import datetime as dt

from .features import FeatureStore
from .schemas import Event

SILENCE_MULTIPLE = 3.0      # x this customer's own historical max gap
GRACE_DAYS = 2              # tolerance before an expected arrival counts as missed


class AmbientScheduler:
    """Daily tick on the replay clock. Emits synthetic breach events."""

    def __init__(self, store: FeatureStore, customer_id: str):
        self.store = store
        self.customer_id = customer_id
        self._emitted: set[str] = set()
        self._counter = 0

    def tick(self, now: dt.datetime, seen_types_since: dict[str, dt.datetime]) -> list[Event]:
        """Run one day's checks. Returns synthetic events to inject."""
        out: list[Event] = []
        out.extend(self._check_expected_arrivals(now, seen_types_since))
        out.extend(self._check_engagement_silence(now))
        return out

    # ------------------------------------------------------------- mechanisms
    def _check_expected_arrivals(self, now, seen) -> list[Event]:
        """Did everything that was due actually arrive?

        Scenario 1's income story is five observations, not three: salary at
        $3,800 twelve times, then $1,400 of benefits twice, then NOTHING on
        20 March and 3 April. A system that reacts to deposits sees three
        events; a system that knows what it expected sees five, and the two
        silent ones are the ones that matter.
        """
        out = []
        for kind, exp in self.store.expectations.items():
            if not exp.period_days:
                continue
            last = seen.get(kind, exp.last_seen)
            due = last + dt.timedelta(days=exp.period_days)
            overdue = (now - due).days
            if overdue < GRACE_DAYS + exp.tolerance_days:
                continue
            key = f"{kind}:{due.date()}"
            if key in self._emitted:
                continue
            self._emitted.add(key)
            out.append(self._synth(
                now, "expectation_breach",
                detail=(f"expected '{kind}' (${exp.amount:.0f} every "
                        f"{exp.period_days:.0f}d, {exp.observations} observations) "
                        f"was due {due.date()} and has not arrived "
                        f"({overdue}d overdue)"),
                strength=min(2.0, 0.6 + overdue / 20),
                kind=kind, due=due.isoformat(), overdue_days=overdue))
        return out

    def _check_engagement_silence(self, now) -> list[Event]:
        """Has the customer simply stopped showing up?

        Measured against their OWN historical maximum gap, not a global
        constant -- a customer who logs in twice a year is not churning when
        they skip a week.
        """
        base = getattr(self.store, "baseline_max_gap_days", None)
        if not base:
            return []
        silence = self.store.silence_days(now)
        if silence < base * SILENCE_MULTIPLE:
            return []
        bucket = int(silence // 7)
        key = f"silence:{bucket}"
        if key in self._emitted:
            return []
        self._emitted.add(key)
        return [self._synth(
            now, "expectation_breach",
            detail=(f"{silence:.0f} days with no card or app activity, against a "
                    f"historical maximum gap of {base:.1f}d "
                    f"({silence/base:.0f}x this customer's own largest silence)"),
            strength=min(2.2, 0.8 + silence / base / 8),
            kind="engagement_silence", silence_days=round(silence, 1),
            baseline_max_gap_days=round(base, 2))]

    def _synth(self, now: dt.datetime, event_type: str, **payload) -> Event:
        self._counter += 1
        return Event(
            event_id=f"SYN_{self._counter:05d}",
            event_time=now,
            ingestion_time=now,
            customer_id=self.customer_id,
            account_id=None,
            source_system="ambient_scheduler",
            event_type=event_type,
            payload=payload,
            synthetic=True,
            semantic_class=event_type,
        )
