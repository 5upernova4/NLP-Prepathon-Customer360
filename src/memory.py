"""Memory, and the access broker that scopes it.

Three tiers, per the problem statement's taxonomy:

  working    the live state of ONE customer right now -- the open case, the
             window under review, what the swarm has concluded this pass.
             Discarded when the case resolves.
  episodic   per-customer history of what happened and what was done about it,
             including every HITL approve/reject/modify. This is how the
             system gets smarter about THIS customer.
  semantic   cross-customer patterns and policy: offer eligibility, compliance
             rules, cohort baselines, the merchant -> class lexicon. Shared,
             read-only to agents, owned by nobody.

Two design decisions worth stating.

ACCESS IS BROKERED AT THE DATA LAYER. An agent receives a ScopedView built
from its declared capability set. An agent without brokerage scope has no
method that can reach brokerage data -- it is not instructed to avoid it. This
is the difference between a control and a request, and it also caps the blast
radius of a poisoned retrieval to a single customer.

EPISODIC RECALL IS FILTERED, NOT DUMPED. Xiong et al. (2025) show that agents
exhibit 'experience-following': when an input resembles a retrieved memory, the
output copies that memory's output. With ~8% signal density, roughly nine in
ten stored precedents say no_significant_event / no_action, so an unfiltered
precedent bank would actively teach the system to do nothing. Recall therefore
requires a hypothesis match, not merely similarity.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .schemas import Action, HITL, State

# Which source systems each capability unlocks. Enforced when the view is
# built, so an out-of-scope read is structurally impossible.
CAPABILITY_SOURCES: dict[str, set[str]] = {
    "usage": {"web_app_events"},
    "transactions": {"core_banking_ledger", "card_payments", "ach_wire",
                     "instant_payments"},
    "support": {"support_logs"},
    "kyc": {"loan_kyc"},
    "brokerage": {"trading_brokerage"},
    "ambient": {"ambient_scheduler"},
}


@dataclass
class EpisodicRecord:
    at: dt.datetime
    state: State
    action: Action
    hitl: HITL
    outcome: str | None
    evidence_ids: list[str]
    note: str = ""


@dataclass
class WorkingMemory:
    """Scoped strictly to one customer and one open case."""
    customer_id: str
    window_start: dt.datetime | None = None
    window_end: dt.datetime | None = None
    swarm_findings: dict[str, list[str]] = field(default_factory=dict)
    open_case: str | None = None

    def publish(self, agent: str, finding: str) -> None:
        self.swarm_findings.setdefault(agent, []).append(finding)

    def clear(self) -> None:
        self.swarm_findings.clear()
        self.open_case = None


class SemanticMemory:
    """Cross-customer, read-only to agents."""

    OFFER_ELIGIBILITY = {
        State.NEW_CHILD: ("childcare_savings_or_insurance_plan", 0.0),
        State.WEALTH_GROWTH: ("investment_product_offer", 0.0),
        State.JOB_CHANGE: ("credit_line_increase_offer", 0.0),
        State.RETIREMENT: ("retirement_planning_offer", 0.0),
    }
    SUPPORT_SUBTYPES = {
        State.MEDICAL_HARDSHIP: "medical_hardship_payment_plan",
        State.FINANCIAL_DISTRESS: "hardship_payment_plan",
        State.JOB_LOSS: "income_disruption_forbearance",
    }
    RETENTION_SUBTYPES = {
        State.CHURN_RISK: "premium_retention_offer_and_fee_waiver",
    }

    @classmethod
    def action_subtype(cls, state: State, action: Action) -> str | None:
        if action == Action.OFFER:
            hit = cls.OFFER_ELIGIBILITY.get(state)
            return hit[0] if hit else None
        if action == Action.SUPPORT:
            return cls.SUPPORT_SUBTYPES.get(state)
        if action == Action.RETENTION:
            return cls.RETENTION_SUBTYPES.get(state)
        if action == Action.RM_ESCALATION:
            return "relationship_manager_review"
        if action == Action.FRAUD_HOLD:
            return "account_review_hold"
        return None


class EpisodicMemory:
    """Per-customer, and the retrieval is deliberately narrow."""

    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self._records: list[EpisodicRecord] = []

    def write(self, rec: EpisodicRecord) -> None:
        self._records.append(rec)

    def recall(self, hypothesis: State, before: dt.datetime,
               limit: int = 3) -> list[EpisodicRecord]:
        """Hypothesis-matched recall, not nearest-neighbour recall.

        Records that concluded no_significant_event are excluded outright:
        they are the overwhelming majority and following them is precisely the
        degradation Xiong et al. describe.
        """
        hits = [r for r in self._records
                if r.at < before
                and r.state == hypothesis
                and r.state != State.NO_SIGNIFICANT_EVENT]
        return sorted(hits, key=lambda r: -r.at.timestamp())[:limit]

    def hitl_history(self) -> list[EpisodicRecord]:
        return [r for r in self._records
                if r.hitl in (HITL.HUMAN_APPROVED, HITL.HUMAN_REJECTED,
                              HITL.HUMAN_MODIFIED)]

    def __len__(self) -> int:
        return len(self._records)


class ScopedView:
    """What an agent actually receives. Built from its capability set.

    There is no method here that reaches a source outside `allowed`. An agent
    holding only {'support'} cannot construct a query for brokerage data --
    not because it was told not to, but because the object it holds has no
    such surface.
    """

    def __init__(self, customer_id: str, events: list, capabilities: set[str]):
        self.customer_id = customer_id
        self._capabilities = set(capabilities)
        self._allowed = set()
        for cap in self._capabilities:
            self._allowed |= CAPABILITY_SOURCES.get(cap, set())
        self._events = [e for e in events if e.source_system in self._allowed]

    @property
    def capabilities(self) -> set[str]:
        return set(self._capabilities)

    def events(self, since: dt.datetime | None = None,
               until: dt.datetime | None = None) -> list:
        out = self._events
        if since:
            out = [e for e in out if e.event_time >= since]
        if until:
            out = [e for e in out if e.event_time <= until]
        return out

    def can_read(self, source_system: str) -> bool:
        return source_system in self._allowed

    def __repr__(self) -> str:
        return (f"<ScopedView {self.customer_id} caps={sorted(self._capabilities)} "
                f"{len(self._events)} events visible>")


class AccessBroker:
    """Builds ScopedViews. The only place a capability set turns into data."""

    def __init__(self, customer_id: str, events: list):
        self.customer_id = customer_id
        self._events = events
        self.grants: list[tuple[str, set[str], int]] = []

    def view_for(self, agent_name: str, capabilities: set[str]) -> ScopedView:
        v = ScopedView(self.customer_id, self._events, capabilities)
        self.grants.append((agent_name, set(capabilities), len(v.events())))
        return v
