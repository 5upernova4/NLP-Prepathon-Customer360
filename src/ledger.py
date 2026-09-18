"""The evidence ledger.

This is the shared state board from the problem statement with one change:
it is append-only, and a finding is a row with a number on it rather than a
sentence. Agents write rows; nobody edits a row.

The reason it is shaped this way is that four separate requirements turn out
to be the same requirement.

  explain a decision    ->  rank the rows by contribution; they already cite
                            the events they rest on
  decay old memory      ->  the half-life term in Assertion.contribution()
  absorb a late event   ->  append with its real observed_at and recompute
                            the posterior for that as_of_time
  retract a red herring ->  set revoked_by and recompute

One structure, four problems. An LLM asked to re-read a state blob and report
its confidence solves none of them reproducibly, and cannot be audited after
the fact.
"""
from __future__ import annotations

import datetime as dt
import itertools

from .schemas import Assertion, State, band_for
from .weights import PRIOR


class Ledger:
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.rows: list[Assertion] = []
        self._ids = itertools.count(1)

    # ------------------------------------------------------------------ write
    def add(self, hypothesis: State, weight: float, half_life_days: float,
            observed_at: dt.datetime, asserted_at: dt.datetime,
            source_event_ids: list[str], agent: str, rationale: str,
            direction: str = "supports", signal: str | None = None) -> Assertion:
        a = Assertion(
            assertion_id=f"A{next(self._ids):04d}",
            customer_id=self.customer_id,
            hypothesis=hypothesis,
            direction=direction,
            weight=weight,
            observed_at=observed_at,
            asserted_at=asserted_at,
            half_life_days=half_life_days,
            source_event_ids=list(source_event_ids or []),
            agent=agent,
            rationale=rationale,
            signal=signal,
        )
        self.rows.append(a)
        return a

    def revoke(self, row: Assertion, by_agent: str, reason: str) -> str:
        """Withdraw a row because a later event explained it away.

        Not a delete. The trace still shows the system believed this and why,
        which is exactly what an audit of a fraud hold needs to see.
        """
        marker = f"REV:{by_agent}"
        row.revoked_by = marker
        row.rationale += f"  [revoked by {by_agent}: {reason}]"
        return marker

    # ------------------------------------------------------------------- read
    def live(self, at: dt.datetime) -> list[Assertion]:
        return [r for r in self.rows if not r.revoked_by and r.observed_at <= at]

    def posterior(self, hypothesis: State, at: dt.datetime) -> float:
        """Sum the live rows, discounting repeats of the same kind.

        Adding every row at face value assumes the pieces of evidence are
        conditionally independent, and they plainly are not: a pharmacy charge
        and a hospital bill are the same underlying fact observed twice. Summed
        naively, two benefits credits and two large medical charges push the
        posterior past the high cutoff weeks before the ground truth says the
        picture is clear, which is exactly the over-confidence this problem
        punishes.

        So within one (hypothesis, detector) group the strongest row counts in
        full, the second counts half, the third a third. Corroboration across
        DIFFERENT detectors is undiscounted, which is the behaviour we want --
        it is independent sources agreeing that should move a belief, not the
        same source repeating itself.
        """
        groups: dict[str, list[float]] = {}
        for r in self.live(at):
            if r.hypothesis != hypothesis:
                continue
            groups.setdefault(r.signal or r.agent, []).append(r.contribution(at))

        total = PRIOR
        for contributions in groups.values():
            contributions.sort(key=abs, reverse=True)
            for i, c in enumerate(contributions):
                total += c / (i + 1)
        return total

    def ranked(self, at: dt.datetime) -> list[tuple[State, float]]:
        seen = {r.hypothesis for r in self.live(at)}
        out = [(h, self.posterior(h, at)) for h in seen]
        out.sort(key=lambda t: -t[1])
        return out

    def leader(self, at: dt.datetime):
        """(state, posterior, runner_up_or_None)."""
        r = self.ranked(at)
        if not r:
            return State.NO_SIGNIFICANT_EVENT, PRIOR, None
        return r[0][0], r[0][1], (r[1] if len(r) > 1 else None)

    def band(self, at: dt.datetime):
        _, score, _ = self.leader(at)
        return band_for(score)

    # -------------------------------------------------------------------- why
    def explain(self, hypothesis: State, at: dt.datetime, limit: int = 6) -> list[dict]:
        """Why we believe this, ranked by how much each row actually moved the
        number. This is the explanation a reviewer sees. It is not produced by
        asking a model what it just did -- it falls out of the arithmetic."""
        scored = [(r, r.contribution(at)) for r in self.live(at)
                  if r.hypothesis == hypothesis]
        scored.sort(key=lambda t: -abs(t[1]))

        # Show a human the strongest row from each kind of evidence, not the
        # same detector five times. The daily silence check re-fires every day
        # it stays quiet, which is right for scoring and unreadable in a note.
        seen: set[str] = set()
        deduped = []
        for r, c in scored:
            key = r.signal or r.agent
            if key in seen:
                continue
            seen.add(key)
            deduped.append((r, c))
        scored = deduped

        return [{
            "contribution": round(c, 3),
            "observed_at": r.observed_at.strftime("%Y-%m-%d"),
            "agent": r.agent,
            "why": r.rationale,
            "cites": r.source_event_ids,
        } for r, c in scored[:limit]]

    def agents_supporting(self, hypothesis: State, at: dt.datetime) -> set[str]:
        return {r.agent for r in self.live(at) if r.hypothesis == hypothesis}
