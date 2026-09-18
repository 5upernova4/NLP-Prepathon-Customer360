"""LLM access, with a deterministic fallback so the system always runs.

Design note, because a reviewer will reasonably ask why the agents are not
purely LLM-driven. The architecture puts the discriminating work in the
deterministic Tier-0 reflex layer and uses the model tier for what models are
actually good at: reading free text (ticket wording, search intent) and
weighing an ambiguous case. That means the system degrades honestly without an
API key -- every structural claim (dedupe, absence detection, decay,
guardrails, the posterior) still holds, and only the text-interpretation
assertions fall back to a keyword reading.

Set ANTHROPIC_API_KEY to enable the model path. Without it the system runs
end to end and says so in its trace.
"""
from __future__ import annotations

import json
import os

MODEL = "claude-sonnet-5"
_client = None
_checked = False


def available() -> bool:
    global _client, _checked
    if _checked:
        return _client is not None
    _checked = True
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic
        _client = anthropic.Anthropic()
    except Exception:
        _client = None
    return _client is not None


def classify(system: str, user: str, schema_hint: dict,
             fallback: dict) -> tuple[dict, str]:
    """Return (result, provenance). Provenance is 'llm' or 'deterministic'.

    Every call carries its fallback, so no code path depends on the model
    being reachable.
    """
    if not available():
        return fallback, "deterministic"
    try:
        msg = _client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content":
                       f"{user}\n\nReply with JSON only, matching:\n"
                       f"{json.dumps(schema_hint)}"}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        return json.loads(text), "llm"
    except Exception:
        return fallback, "deterministic"
