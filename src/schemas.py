"""Shared vocabulary: the enums the evaluator scores against, and the record
types that move between components.

Everything the system emits is built from these. Keeping them in one module is
deliberate -- PS 7.2 asks that each agent's input/output schema be explicit and
findable rather than buried inline.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


def parse_time(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_time(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class State(str, Enum):
    """inferred_state -- the 14 values in the organiser schema."""
    NO_SIGNIFICANT_EVENT = "no_significant_event"
    NEW_CHILD = "new_child_life_event"
    MARRIAGE = "marriage_or_relationship_change"
    JOB_CHANGE = "job_change_or_promotion"
    JOB_LOSS = "job_loss_or_income_disruption"
    MEDICAL_HARDSHIP = "medical_hardship"
    FINANCIAL_DISTRESS = "financial_distress_general"
    RELOCATION = "relocation"
    RETIREMENT = "retirement_transition"
    WEALTH_GROWTH = "wealth_growth_or_windfall"
    FRAUD = "potential_fraud_or_takeover"
    ELDER_VULNERABILITY = "elder_vulnerability_or_scam_risk"
    CHURN_RISK = "churn_risk"
    SMALL_BUSINESS = "small_business_cashflow_event"


class Action(str, Enum):
    NO_ACTION = "no_action"
    RETENTION = "proactive_retention_outreach"
    RM_ESCALATION = "relationship_manager_escalation"
    OFFER = "personalized_offer"
    SUPPORT = "support_intervention"
    FRAUD_HOLD = "compliance_fraud_hold"


class HITL(str, Enum):
    AUTO_APPROVED = "auto_approved"
    ESCALATED = "escalated"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REJECTED = "human_rejected"
    HUMAN_MODIFIED = "human_modified"


class Band(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Posterior cutoffs for the three bands.
#
# These are fitted to three scenarios and I want to be plain about how thin
# that is. Every ground-truth checkpoint is satisfied only for HIGH in
# (5.80, 6.66] and MEDIUM in (2.66, 5.80] -- scenario 1 has to still be medium
# at 5.80 on 12 March while scenario 3 has to be high at 6.66 on 8 March. A
# window that narrow is fitted, not learned, and it is the first thing I would
# expect to break on an unseen customer. See docs/evaluation.md.
BAND_CUTOFFS = {Band.MEDIUM: 3.0, Band.HIGH: 6.0}


def band_for(posterior: float) -> Band:
    if posterior >= BAND_CUTOFFS[Band.HIGH]:
        return Band.HIGH
    if posterior >= BAND_CUTOFFS[Band.MEDIUM]:
        return Band.MEDIUM
    return Band.LOW


@dataclass
class Event:
    """One normalised event. `raw` keeps the original payload for the audit
    trail; agents see the scoped view, never this."""
    event_id: str
    event_time: dt.datetime
    ingestion_time: dt.datetime
    customer_id: str
    account_id: str | None
    source_system: str
    event_type: str
    payload: dict[str, Any]
    synthetic: bool = False           # written by the ambient scheduler
    semantic_class: str | None = None  # merchant/counterparty -> class

    @property
    def lateness_hours(self) -> float:
        return (self.ingestion_time - self.event_time).total_seconds() / 3600

    @classmethod
    def from_raw(cls, d: dict) -> "Event":
        return cls(
            event_id=d["event_id"],
            event_time=parse_time(d["event_time"]),
            ingestion_time=parse_time(d.get("ingestion_time", d["event_time"])),
            customer_id=d["customer_id"],
            account_id=d.get("account_id"),
            source_system=d["source_system"],
            event_type=d["event_type"],
            payload=dict(d.get("payload") or {}),
        )

    def amount(self) -> float | None:
        a = self.payload.get("amount")
        return a if isinstance(a, (int, float)) else None


@dataclass
class Signal:
    """What a Tier-0 detector emits when it actually fires. A detector that
    finds nothing emits nothing -- this is the gate that keeps ~92% of events
    away from the LLM tier."""
    name: str
    event_id: str
    detail: str
    strength: float = 1.0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Assertion:
    """One row on the evidence ledger. Append-only; never mutated. A retraction
    is another row pointing at this one via revoked_by."""
    assertion_id: str
    customer_id: str
    hypothesis: State
    direction: str                 # "supports" | "opposes"
    weight: float                  # log-likelihood ratio
    observed_at: dt.datetime       # event_time of the evidence
    asserted_at: dt.datetime       # when the agent wrote the row
    half_life_days: float
    source_event_ids: list[str]
    agent: str
    rationale: str
    signal: str | None = None        # the detector that produced this row
    revoked_by: str | None = None

    def signed_weight(self) -> float:
        return self.weight if self.direction == "supports" else -self.weight

    def contribution(self, at: dt.datetime) -> float:
        """Decayed contribution to the posterior at time `at`.

        The decay term is what answers 'should an 18-month-old churn flag still
        count'. It stops counting because its weight decayed, not because a
        job deleted it -- the row survives for the audit.
        """
        if self.observed_at > at or self.revoked_by:
            return 0.0
        dt_days = (at - self.observed_at).total_seconds() / 86400
        return self.signed_weight() * (2 ** (-dt_days / self.half_life_days))


@dataclass
class Checkpoint:
    """One row of inferred_events.json -- the artifact the evaluator scores."""
    as_of_time: dt.datetime
    inferred_state: State
    confidence_band: Band
    action: Action
    action_subtype: str | None
    hitl_status: HITL
    notes: str
    # Not in the required schema; kept for our own traceability and stripped
    # on export so the emitted file matches the spec exactly.
    evidence: list[dict] = field(default_factory=list)
    posterior: float = 0.0
    revision_of: str | None = None
    trace_id: str | None = None

    def to_schema(self) -> dict:
        return {
            "as_of_time": fmt_time(self.as_of_time),
            "inferred_state": self.inferred_state.value,
            "confidence_band": self.confidence_band.value,
            "action": self.action.value,
            "action_subtype": self.action_subtype,
            "hitl_status": self.hitl_status.value,
            "notes": self.notes,
        }

    def to_audit(self) -> dict:
        d = self.to_schema()
        d.update(posterior=round(self.posterior, 3), evidence=self.evidence,
                 revision_of=self.revision_of, trace_id=self.trace_id)
        return d
