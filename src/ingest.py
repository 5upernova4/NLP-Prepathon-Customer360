"""Tier 0, first half: get events into the log correctly.

Deterministic. No model touches anything in this path. Four stages:

  normalise      schema check, PII tokenisation, merchant -> semantic class
  de-duplicate   collapse one money movement reported by two systems
  event-time     order by when it happened, never by when it arrived
  immutable log  append-only, replayable, the system's only source of truth

The de-duplication stage exists because of a specific thing in the data:
scenario 1 reports one $12,000 movement twice, once as ach_wire/
outbound_transfer and once as core_banking_ledger/withdrawal, one second
apart. Summing naively invents a $24,000 crisis.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .pii import PIIVault, classify_counterparty, classify_merchant, mask_payload
from .schemas import Event, parse_time

# Worst lateness observed in the practice data is 48h; 72 gives headroom
# without letting a window stay open indefinitely.
ALLOWED_LATENESS_HOURS = 72

# Two reports of the same movement land within seconds and match on amount.
DEDUPE_WINDOW_SECONDS = 5


class ImmutableLog:
    """Append-only event log. Replayable; nothing is ever edited in place."""

    def __init__(self):
        self._events: list[Event] = []
        self._seen: set[str] = set()

    def append(self, e: Event) -> None:
        if e.event_id in self._seen:
            return
        self._seen.add(e.event_id)
        self._events.append(e)

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self._events)

    def in_event_time_order(self) -> list[Event]:
        return sorted(self._events, key=lambda e: e.event_time)

    def up_to(self, t: dt.datetime) -> list[Event]:
        return [e for e in self.in_event_time_order() if e.event_time <= t]


class Normaliser:
    """Schema check, tokenisation, semantic classing."""

    def __init__(self, vault: PIIVault):
        self.vault = vault

    def __call__(self, raw: dict) -> Event:
        e = Event.from_raw(raw)
        p = e.payload
        if e.source_system == "card_payments":
            e.semantic_class = classify_merchant(p.get("merchant_name"),
                                                 p.get("mcc_category"))
        elif e.source_system in ("ach_wire", "instant_payments"):
            e.semantic_class = classify_counterparty(p.get("counterparty_name"))
        elif e.source_system == "core_banking_ledger":
            e.semantic_class = p.get("transaction_type")
        else:
            e.semantic_class = e.event_type
        e.payload = mask_payload(p, self.vault)
        return e


class Deduplicator:
    """Collapse the same money movement reported by two source systems.

    Fingerprint is (account, rounded amount, direction-agnostic) inside a short
    window. Direction-agnostic is deliberate: the wire is reported as an
    outbound transfer and the ledger as a withdrawal, which are the same event
    described from two sides.
    """

    def __init__(self, window_seconds: int = DEDUPE_WINDOW_SECONDS):
        self.window = window_seconds
        self._recent: list[tuple[dt.datetime, tuple, str]] = []
        self.collapsed: list[tuple[str, str]] = []

    def is_duplicate(self, e: Event) -> str | None:
        amt = e.amount()
        if amt is None:
            return None
        key = (e.account_id, round(abs(amt), 2))
        cutoff = e.event_time - dt.timedelta(seconds=self.window)
        self._recent = [(t, k, i) for t, k, i in self._recent if t >= cutoff]
        for t, k, first_id in self._recent:
            if k == key and e.source_system:
                self.collapsed.append((first_id, e.event_id))
                return first_id
        self._recent.append((e.event_time, key, e.event_id))
        return None


class EventTimeBuffer:
    """Ordering by event_time with a watermark and bounded lateness.

    The watermark is used ONLY to decide when a window is safe to close. It is
    deliberately NOT used to drive the ambient scheduler -- see scheduler.py
    for why that distinction is load-bearing rather than pedantic.
    """

    def __init__(self, allowed_lateness_hours: int = ALLOWED_LATENESS_HOURS):
        self.allowed = dt.timedelta(hours=allowed_lateness_hours)
        self.watermark: dt.datetime | None = None
        self.late_arrivals: list[Event] = []

    def observe(self, e: Event) -> bool:
        """Record the event; return True if it arrived late enough that any
        already-emitted conclusion covering its window needs revisiting."""
        mark = e.ingestion_time - self.allowed
        self.watermark = mark if self.watermark is None else max(self.watermark, mark)
        is_late = self.watermark is not None and e.event_time < self.watermark
        if e.lateness_hours > 1:
            self.late_arrivals.append(e)
        return is_late


class Pipeline:
    """Normalise -> dedupe -> buffer -> immutable log."""

    def __init__(self, vault: PIIVault | None = None):
        self.vault = vault or PIIVault()
        self.normalise = Normaliser(self.vault)
        self.dedupe = Deduplicator()
        self.buffer = EventTimeBuffer()
        self.log = ImmutableLog()
        self.duplicate_ids: dict[str, str] = {}

    def ingest(self, raw: dict) -> Event | None:
        e = self.normalise(raw)
        dup_of = self.dedupe.is_duplicate(e)
        if dup_of:
            self.duplicate_ids[e.event_id] = dup_of
            return None
        self.buffer.observe(e)
        self.log.append(e)
        return e

    def ingest_file(self, path: Path) -> int:
        n = 0
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line and self.ingest(json.loads(line)) is not None:
                    n += 1
        return n


def load_scenario(root: Path) -> tuple[Pipeline, dict, dict]:
    """Load one scenario: history first (baseline), then the live stream."""
    pipe = Pipeline()
    entities = json.loads((root / "entities.json").read_text())
    config = json.loads((root / "replay_config.json").read_text())
    pipe.ingest_file(root / "history_seed.jsonl")
    n_hist = len(pipe.log)
    pipe.ingest_file(root / "live_stream.jsonl")
    config["_history_count"] = n_hist
    config["_simulated_start"] = parse_time(config["simulated_start"])
    config["_simulated_end"] = parse_time(config["simulated_end"])
    return pipe, entities, config
