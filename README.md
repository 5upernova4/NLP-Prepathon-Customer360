# Agentic Customer 360 — Proactive Intervention Desk

Inter IIT Tech Meet 15.0 · Prepathon · **Natural Language Processing (Agentic AI)**

An ambient multi-agent system that continuously reads a live, out-of-order,
multi-source customer event stream, maintains an evolving per-customer state
(including an inferred *current life phase*), and commits to a specific,
traceable intervention decision — or an explicit, equally traceable no-action.

> This is not a chatbot. No agent in this system waits for a human prompt.

---

## Repository map

| Path | What's in it |
|---|---|
| `midterm/` | Mid-term submission bundle (15 Sep): research doc, architecture diagram, one-page report |
| `research/` | Running research log — every paper, blog and talk consulted, with what was taken from it and which design decision it informed |
| `notebooks/` | Exploratory analysis of the provided scenarios — what the signal actually looks like in this data |
| `customer_360_dataset/` | Organiser-provided practice scenarios (synthetic). Schema in `README_dataset_schema.md` |
| `src/` | Implementation — agents, memory, ingestion, guardrails, HITL, observability |
| `eval/` | Scoring harness: inferred-events output vs. sample ground truth |

## Deliverables → where they live

| Deliverable (PS §7) | Weight | Status | Location |
|---|---|---|---|
| Research log | 30% | 🟡 mid-term draft | `midterm/`, `research/` |
| Codebase | 25% | ⚪ end-term | `src/` |
| Architectural novelty | 20% | 🟡 mid-term draft | `midterm/diagrams/` |
| Non-negotiables (observability, traceability, guardrails, explainability) | 15% | ⚪ end-term | `src/` |
| Documentation & architecture diagram | 10% | 🟡 mid-term draft | `midterm/` |

## Submission timeline

- **Mid-term — 15 Sep EoD:** preliminary research doc, preliminary system architecture, one-page findings report.
- **End-term — 19 Sep EoD:** all deliverables compiled into this repository, submitted via the Google Form.

## The dataset

Three practice scenarios under `customer_360_dataset/`, each containing:

```
entities.json        customer + account reference data
history_seed.jsonl   baseline history preceding the live window
live_stream.jsonl    the live stream, consumed in event_time order
replay_config.json   pacing / time boundaries for timed replay
ground_truth.json    practice-only answer key (withheld for the graded scenarios)
instructions.md      per-scenario caveats
```

Events carry both `event_time` (when it happened) and `ingestion_time` (when it
arrived). These deliberately disagree — late and out-of-order arrival is part of
the problem, not noise to be smoothed away.

## Reproducing the exploratory analysis

```bash
python3 notebooks/explore_stream.py
```

## Evaluation output

The system emits its inferred state, confidence and committed action per
timestep in the organiser-specified **inferred-events schema** — this file is
the artifact evaluators score against hidden ground truth, so emitting it
correctly is a hard requirement, not optional logging.
