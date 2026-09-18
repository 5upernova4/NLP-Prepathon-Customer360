"""Guardrails that are ENFORCED rather than requested.

The problem statement is blunt that a prompt-level instruction is not a
guardrail, so nothing here is a prompt. Three mechanisms:

  hard-stop scanner   deterministic keyword classes that bypass every agent
                      and land directly on the human desk
  policy matrix       a table lookup over (inferred_state, action), evaluated
                      in code before an action can be constructed
  blast radius        tools are split draft/send; no agent holds a send tool

The policy entry that matters most is medical_hardship -> personalized_offer,
denied outright. Marcus Vance is drawing down savings to pay hospital bills. A
system that reads a large balance movement and pitches him a product has
failed in a way no amount of good intent fixes. That is not a threshold a model
can argue past -- it is a lookup that returns DENY before any offer object
exists.
"""
from __future__ import annotations

from dataclasses import dataclass

from .schemas import Action, State

HARD_STOP_PATTERNS: dict[str, tuple[str, ...]] = {
    "legal_threat": ("lawsuit", "legal action", "attorney", "lawyer", "sue you",
                     "litigation", "small claims", "regulator", "ombudsman"),
    "self_harm": ("suicide", "kill myself", "end my life", "self harm",
                  "hurt myself"),
    "account_takeover": ("didn't authorize", "did not authorize", "not me",
                         "someone accessed", "hacked", "stolen card",
                         "unauthorized transaction"),
    "sanctions": ("ofac", "sanctioned", "embargo"),
}

# (state, action) pairs that are DENIED regardless of confidence.
DENIED: set[tuple[State, Action]] = {
    (State.MEDICAL_HARDSHIP, Action.OFFER),
    (State.FINANCIAL_DISTRESS, Action.OFFER),
    (State.JOB_LOSS, Action.OFFER),
    (State.ELDER_VULNERABILITY, Action.OFFER),
    # Freezing an account on a life event is a category error; fraud holds
    # require a fraud hypothesis, not merely unusual money movement.
    (State.MEDICAL_HARDSHIP, Action.FRAUD_HOLD),
    (State.NEW_CHILD, Action.FRAUD_HOLD),
    (State.RETIREMENT, Action.FRAUD_HOLD),
    (State.WEALTH_GROWTH, Action.FRAUD_HOLD),
}

# Actions that may never execute without a human, whatever the confidence.
ALWAYS_HITL: set[Action] = {
    Action.FRAUD_HOLD, Action.RM_ESCALATION, Action.OFFER,
}

# Spend ceiling by customer value tier. Exceeding one forces escalation rather
# than silently reducing the offer -- a system that shrinks a gesture to stay
# under its own limit is making a pricing decision nobody authorised.
SPEND_CEILINGS = {"high": 500.0, "mid": 250.0, "low": 100.0}


@dataclass
class GuardrailVerdict:
    allowed: bool
    reason: str
    force_hitl: bool = False
    hard_stop: str | None = None


def scan_hard_stop(text: str | None) -> str | None:
    """Deterministic keyword classes. Runs on every piece of customer text,
    before any agent sees it."""
    if not text:
        return None
    low = text.lower()
    for label, keys in HARD_STOP_PATTERNS.items():
        if any(k in low for k in keys):
            return label
    return None


def check_action(state: State, action: Action, *, value_tier: str = "mid",
                 cost: float = 0.0, confidence_high: bool = False
                 ) -> GuardrailVerdict:
    """The policy matrix. Evaluated in code before an action is constructed."""
    if action == Action.NO_ACTION:
        return GuardrailVerdict(True, "no action requires no authority")

    if (state, action) in DENIED:
        return GuardrailVerdict(
            False,
            f"policy matrix denies {action.value} while inferred_state is "
            f"{state.value}", force_hitl=False)

    ceiling = SPEND_CEILINGS.get(value_tier, SPEND_CEILINGS["mid"])
    if cost > ceiling:
        return GuardrailVerdict(
            True,
            f"cost ${cost:.0f} exceeds the ${ceiling:.0f} ceiling for a "
            f"'{value_tier}' tier customer -- escalating rather than resizing",
            force_hitl=True)

    if action in ALWAYS_HITL:
        return GuardrailVerdict(
            True, f"{action.value} always requires a human checkpoint",
            force_hitl=True)

    if not confidence_high:
        return GuardrailVerdict(
            True, "confidence below the autonomous threshold", force_hitl=True)

    return GuardrailVerdict(True, "within autonomous bounds")


class ToolBoundary:
    """Blast radius. An agent can draft; it cannot send or spend.

    This is structural rather than instructed: the send tool does not exist on
    any agent's toolset, so there is no call for a model to emit.
    """

    DRAFT_ONLY = {"draft_message", "draft_offer", "estimate_cost",
                  "lookup_eligibility", "query_ledger", "retrieve_policy"}
    REQUIRES_HUMAN = {"send_message", "apply_credit", "freeze_account",
                      "book_rm_meeting"}

    @classmethod
    def check(cls, tool: str) -> GuardrailVerdict:
        if tool in cls.REQUIRES_HUMAN:
            return GuardrailVerdict(
                False, f"'{tool}' is outside every agent's blast radius; it is "
                       f"executable only by a human from the HITL desk")
        if tool in cls.DRAFT_ONLY:
            return GuardrailVerdict(True, "draft-scope tool")
        return GuardrailVerdict(False, f"unknown tool '{tool}' refused by default")
