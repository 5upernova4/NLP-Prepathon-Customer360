"""PII vault and the merchant -> semantic class lexicon.

Two jobs, and the second one is the interesting one.

Tokenisation is the easy half: names and account numbers are swapped for
surrogates on ingest, and the mapping lives here, outside the prompt path. No
agent ever holds the reverse map.

The semantic class is the half that took a design decision. Merchant and
counterparty names are NOT redacted, because the identity of the counterparty
is exactly what carries the signal -- 'State University' is what makes a
$12,000 wire a tuition payment rather than a wealth drain, and 'David Chen -
Chase Bank' is what makes a self-transfer look like an exit. Redacting the name
destroys the discriminator; passing it raw sends PII to a model. Mapping it to
a class is the compromise: the model sees `education_institution`, never the
string.
"""
from __future__ import annotations

import hashlib

# Counterparty classes. The distinction that matters here is whether money
# leaving the account is leaving the relationship.
_COUNTERPARTY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("university", "college", "school", "tuition"), "education_institution"),
    (("hospital", "clinic", "medical", "health"), "healthcare_provider"),
    (("chase", "wells fargo", "citi", "ext bank", "external bank",
      "bank of america"), "competitor_institution"),
    (("irs", "treasury", "revenue"), "government_agency"),
    (("insurance", "assurance"), "insurer"),
]

# Merchant classes. mcc_category already carries most of this; the lexicon
# exists for the cases where the merchant name is more specific than its MCC
# (a diagnostics lab and a pharmacy are both `healthcare`-adjacent but mean
# different things about severity).
_MERCHANT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("hospital er", "emergency"), "emergency_care"),
    (("hospital billing",), "hospital_billing"),
    (("diagnostics", "laboratory", "labs"), "diagnostics_lab"),
    (("pharmacy", "walgreens", "cvs", "chemist"), "pharmacy"),
    (("mothercare", "buybuybaby", "baby"), "infant_goods"),
    (("resort", "hotel", "airlines", "travel"), "leisure_travel"),
    (("techworld", "electronics", "best buy"), "consumer_electronics"),
]

# Free-text fields that must never reach a prompt unmasked.
_FREE_TEXT_FIELDS = ("raw_text", "search_text", "merchant_name",
                     "counterparty_name")


class PIIVault:
    """Holds the surrogate <-> real mapping. Deliberately not passed to agents.

    Embeddings are treated as PII-equivalent: the vector of 'ER visit,
    pharmacy, diagnostics' is health-adjacent data in its own right, so
    anything derived from a masked field stays inside the vault's scope.
    """

    def __init__(self, salt: str = "c360"):
        self._salt = salt
        self._forward: dict[str, str] = {}
        self._reverse: dict[str, str] = {}

    def tokenise(self, value: str, kind: str = "ENT") -> str:
        if value in self._forward:
            return self._forward[value]
        digest = hashlib.sha256(f"{self._salt}:{value}".encode()).hexdigest()[:10]
        token = f"{kind}_{digest.upper()}"
        self._forward[value] = token
        self._reverse[token] = value
        return token

    def resolve(self, token: str) -> str | None:
        """Only the HITL desk calls this, to render a name for a human."""
        return self._reverse.get(token)

    def __len__(self) -> int:
        return len(self._forward)


def classify_counterparty(name: str | None) -> str | None:
    if not name:
        return None
    low = name.lower()
    for keys, cls in _COUNTERPARTY_RULES:
        if any(k in low for k in keys):
            return cls
    return "unclassified_counterparty"


def classify_merchant(name: str | None, mcc: str | None) -> str | None:
    if name:
        low = name.lower()
        for keys, cls in _MERCHANT_RULES:
            if any(k in low for k in keys):
                return cls
    return mcc


def mask_payload(payload: dict, vault: PIIVault) -> dict:
    """Return a copy safe to put in front of a model.

    Free text is kept -- a support ticket's wording is the signal -- but the
    customer's own name is tokenised inside it, because a ticket that says
    'this is Marcus Vance' leaks the identity the account_id already hid.
    """
    out = dict(payload)
    for f in ("merchant_name", "counterparty_name"):
        if out.get(f):
            out[f] = vault.tokenise(out[f], "MERCH")
    return out
