"""What each signal is worth, and to which hypothesis.

This file is the honest centre of the system. Everything else is machinery;
this is the judgement. Weights are log-likelihood ratios, hand-set from
reasoning about the domain and then adjusted until the three practice
scenarios came out right. They are not learned, and three scenarios is not a
calibration set. If this system is wrong on a scenario I have not seen, it will
almost certainly be wrong here rather than in the plumbing.

Half-lives are in days and answer the "should an 18-month-old churn flag still
count" question without an expiry job: it still counts, it just counts for
almost nothing, and the row stays on the ledger for the audit.

Two rules I tried to hold to while tuning:

  Nothing single-sourced reaches `high` on its own. A novel merchant category
  is worth 1.3; a declared KYC change is worth 2.6. Getting past the high
  cutoff takes corroboration, which is what the correlation step supplies.

  Red herrings are defused by class, not by size. A first-ever `travel` charge
  and a first-ever `healthcare` charge are both novel; only one of them means
  anything, so novelty is scored per semantic class rather than as one number.
"""
from __future__ import annotations

from .schemas import State

# Log-odds each hypothesis starts at. Everything begins slightly against, so
# the system has to be given a reason rather than talked out of one.
PRIOR = -1.0

# signal name -> [(state, weight, half_life_days), ...]
SIGNAL_WEIGHTS: dict[str, list[tuple[State, float, float]]] = {
    "income_shortfall": [],      # scored below, by which instrument arrived
    "health_spend": [
        (State.MEDICAL_HARDSHIP, 0.75, 220),
        (State.FINANCIAL_DISTRESS, 0.2, 180),
    ],
    "balance_drawdown": [
        (State.FINANCIAL_DISTRESS, 1.0, 150),
        (State.MEDICAL_HARDSHIP, 0.7, 150),
    ],
    "competitor_outflow": [
        (State.CHURN_RISK, 2.0, 220),
    ],
    "sweep_pair": [
        # a near-equal in-and-out is ONE movement. On its own that is neutral;
        # it matters because it stops the pair being read as an exfiltration.
        # Weight sits at zero deliberately - see orchestrator.
    ],
    "si_cancel_intent": [
        (State.CHURN_RISK, 1.7, 200),
    ],
    "support_ticket": [],        # scored by the support agent after reading it
    "search_intent": [],         # scored below, by what was actually typed
    "kyc_change": [],            # scored below, by which field changed
    "novel_category": [],        # scored below, by semantic class
    "new_obligation": [],        # scored below, by what the obligation is
    "expectation_breach": [],    # scored below, by what failed to arrive
}

# Novel category is worth different things depending on what the category is.
# A first-ever healthcare charge says something. A first-ever hotel refund says
# nothing, and treating it as signal is how you fire an investment offer at a
# cancelled holiday.
NOVEL_CATEGORY: dict[str, list[tuple[State, float, float]]] = {
    "healthcare": [(State.MEDICAL_HARDSHIP, 1.3, 200)],
    "pharmacy": [(State.MEDICAL_HARDSHIP, 0.9, 150)],
    "baby_products": [(State.NEW_CHILD, 1.5, 300)],
    "clothing": [],              # only meaningful via the merchant, below
    "electronics": [],
    "lodging": [],
    "travel": [],
    "education": [],
    "groceries": [],
}

# The merchant name carries more than the MCC does. "Mothercare" is filed under
# clothing and is obviously a baby purchase; scoring it by MCC alone loses that.
MERCHANT_CLASS: dict[str, list[tuple[State, float, float]]] = {
    "baby_retail": [(State.NEW_CHILD, 1.4, 300)],
    "healthcare_provider": [(State.MEDICAL_HARDSHIP, 1.2, 200)],
    "pharmacy": [(State.MEDICAL_HARDSHIP, 0.9, 150)],
    "childcare": [(State.NEW_CHILD, 1.6, 400)],
    "education_institution": [],
    "competitor_institution": [(State.CHURN_RISK, 1.2, 220)],
}

NEW_OBLIGATION: dict[str, list[tuple[State, float, float]]] = {
    # A new monthly childcare commitment is nearly as strong as a declared
    # dependants change: nobody sets up a recurring daycare payment
    # speculatively. Weighted to let it carry the decision on its own once the
    # softer baby signals are already on the ledger, which is what buys the
    # lead time -- waiting for the KYC update costs a week.
    "daycare_payment": [(State.NEW_CHILD, 2.5, 400)],
    "mortgage_payment": [(State.RELOCATION, 1.2, 400)],
    "rent_payment": [(State.RELOCATION, 1.0, 400)],
}

# What failed to arrive, and what that implies.
BREACH: dict[str, list[tuple[State, float, float]]] = {
    "salary_credit": [
        (State.JOB_LOSS, 1.4, 180),
        (State.FINANCIAL_DISTRESS, 0.9, 180),
    ],
    "engagement_silence": [
        (State.CHURN_RISK, 1.6, 160),
    ],
    "rent_payment": [(State.CHURN_RISK, 0.8, 200)],
    "gym_membership": [(State.CHURN_RISK, 0.9, 200)],
    "utilities": [(State.CHURN_RISK, 0.8, 200)],
}

# Typed intent. Cheap to read and unusually direct.
SEARCH_INTENT: list[tuple[tuple[str, ...], list[tuple[State, float, float]]]] = [
    (("hardship", "payment plan", "defer", "forbearance"),
     [(State.FINANCIAL_DISTRESS, 1.2, 120), (State.MEDICAL_HARDSHIP, 0.9, 120)]),
    (("child education", "education savings", "child savings", "529"),
     [(State.NEW_CHILD, 1.1, 200)]),
    (("close account", "switch bank", "transfer out"),
     [(State.CHURN_RISK, 1.6, 160)]),
    (("home loan", "mortgage", "moving"),
     [(State.RELOCATION, 1.0, 200)]),
    (("retirement", "pension"),
     [(State.RETIREMENT, 1.2, 300)]),
]

# Income arriving light means different things depending on what arrived.
# Salary that simply shrank is ambiguous between a pay cut and parental leave.
# Salary REPLACED by a benefits or disability credit is a medical story, and
# reading it as job loss is what sent scenario 1 to the wrong hypothesis on my
# first run.
INCOME_SHORTFALL: dict[str, list[tuple[State, float, float]]] = {
    "benefits_credit": [
        (State.MEDICAL_HARDSHIP, 1.0, 220),
        (State.JOB_LOSS, 0.35, 180),
        (State.FINANCIAL_DISTRESS, 0.45, 180),
    ],
    "salary_credit": [
        (State.JOB_LOSS, 0.55, 180),
        (State.FINANCIAL_DISTRESS, 0.5, 180),
        # partial-pay parental leave looks exactly like this from the ledger,
        # so it counts towards new_child and lets other evidence break the tie
        (State.NEW_CHILD, 0.7, 180),
    ],
}


# Declared facts. The strongest evidence in the stream because it is stated
# rather than inferred, which is also why the debate rule prefers it.
KYC_CHANGE: dict[str, list[tuple[State, float, float]]] = {
    "dependents_change": [(State.NEW_CHILD, 2.6, 900)],
    "marital_status_change": [(State.MARRIAGE, 2.6, 900)],
    "address_change": [(State.RELOCATION, 2.2, 700)],
}


def weights_for(signal) -> list[tuple[State, float, float]]:
    """Turn one detector Signal into ledger rows. Empty list means 'noted, but
    it does not move any hypothesis on its own'."""
    n = signal.name
    p = signal.payload or {}

    if n == "novel_category":
        by_merchant = MERCHANT_CLASS.get(p.get("semantic_class") or "", [])
        if by_merchant:
            return by_merchant
        return NOVEL_CATEGORY.get(p.get("mcc") or "", [])

    if n == "new_obligation":
        return NEW_OBLIGATION.get(p.get("kind") or "", [])

    if n == "expectation_breach":
        return BREACH.get(p.get("kind") or "", [])

    if n == "search_intent":
        q = (p.get("query") or "").lower()
        for needles, w in SEARCH_INTENT:
            if any(x in q for x in needles):
                return w
        return []

    if n == "income_shortfall":
        return INCOME_SHORTFALL.get(p.get("instrument") or "salary_credit", [])

    if n == "kyc_change":
        return KYC_CHANGE.get(p.get("event_subtype") or "", [])

    return SIGNAL_WEIGHTS.get(n, [])


# Which action a confirmed state justifies, once confidence is high enough.
# Below `high` the answer is no_action - see orchestrator.decide().
ACTION_FOR_STATE: dict[State, tuple[str, str]] = {
    State.MEDICAL_HARDSHIP: ("support_intervention", "medical_hardship_payment_plan"),
    State.FINANCIAL_DISTRESS: ("support_intervention", "hardship_payment_plan"),
    State.JOB_LOSS: ("support_intervention", "income_disruption_support"),
    State.NEW_CHILD: ("personalized_offer", "childcare_savings_or_insurance_plan"),
    State.MARRIAGE: ("personalized_offer", "joint_account_or_planning"),
    State.RELOCATION: ("personalized_offer", "home_loan_or_relocation_support"),
    State.RETIREMENT: ("personalized_offer", "retirement_income_planning"),
    State.WEALTH_GROWTH: ("personalized_offer", "investment_or_savings_product"),
    State.CHURN_RISK: ("relationship_manager_escalation",
                       "premium_retention_offer_and_fee_waiver"),
    State.FRAUD: ("compliance_fraud_hold", "account_review"),
    State.ELDER_VULNERABILITY: ("compliance_fraud_hold", "vulnerability_review"),
    State.SMALL_BUSINESS: ("personalized_offer", "working_capital_line"),
}
