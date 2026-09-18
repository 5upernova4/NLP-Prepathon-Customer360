"""Observability: OTel-style spans over every agent run, tool call and retrieval.

PS 6.5 asks for enough detail to reconstruct the full decision path after the
fact, including the prompts and tool calls behind any given action -- not just
a final summary. Every ledger row carries the span id that produced it, so an
assertion can be walked back to the agent invocation, its inputs and its
output.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import itertools
import json
from pathlib import Path
from typing import Any


class Tracer:
    def __init__(self):
        self.spans: list[dict] = []
        self._ids = itertools.count(1)
        self._stack: list[str] = []

    @contextlib.contextmanager
    def span(self, name: str, kind: str = "internal", **attrs: Any):
        span_id = f"SPAN_{next(self._ids):05d}"
        rec = {
            "span_id": span_id,
            "parent": self._stack[-1] if self._stack else None,
            "name": name,
            "kind": kind,
            "start": dt.datetime.now(dt.timezone.utc).isoformat(),
            "attributes": dict(attrs),
            "events": [],
        }
        self.spans.append(rec)
        self._stack.append(span_id)
        t0 = dt.datetime.now(dt.timezone.utc)
        try:
            yield rec
        except Exception as exc:
            rec["error"] = repr(exc)
            raise
        finally:
            self._stack.pop()
            rec["duration_ms"] = round(
                (dt.datetime.now(dt.timezone.utc) - t0).total_seconds() * 1000, 3)

    def current(self) -> str | None:
        return self._stack[-1] if self._stack else None

    def log(self, message: str, **attrs: Any) -> None:
        if self._stack:
            for s in reversed(self.spans):
                if s["span_id"] == self._stack[-1]:
                    s["events"].append({"message": message, **attrs})
                    return

    # ------------------------------------------------------------- reporting
    def metrics(self) -> dict:
        by_kind: dict[str, list[float]] = {}
        for s in self.spans:
            by_kind.setdefault(s["kind"], []).append(s.get("duration_ms", 0.0))
        return {
            "span_count": len(self.spans),
            "by_kind": {k: {"n": len(v), "total_ms": round(sum(v), 2)}
                        for k, v in sorted(by_kind.items())},
            "errors": sum(1 for s in self.spans if "error" in s),
        }

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.spans, indent=2))
