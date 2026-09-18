# Agentic Customer 360 — Proactive Intervention Desk

Inter IIT Tech Meet 15.0 · Prepathon · Natural Language Processing (Agentic AI)
Akshat Agrawal, IIT (BHU) Varanasi

An ambient system that reads a customer's live event stream, keeps track of what
they are going through, and commits to one intervention — or to an explicit,
equally traceable decision not to act.

It is not a chatbot. Nothing here waits for a human to ask a question.

## Run it

No API key needed. The system runs end to end offline; the two model-dependent
agents fall back to keyword rules and the trace records which path each call
took.

```bash
python3 run.py --all                                          # writes runs/<scenario>/
python3 eval/score.py --all runs/ --dataset customer_360_dataset
python3 eval/coverage.py
```

Set `ANTHROPIC_API_KEY` to enable the model path for support-text reading and
message drafting.

## Results on the three practice scenarios

| | |
|---|---|
| inferred_state | 8/8 |
| confidence_band | 8/8 |
| action | 7/8 |
| action_subtype | 3/3 |
| hitl_status | 3/3 |
| lead time | 2/3 |
| no false positive on a red herring | 4/4 |

Tier 0 catches 26 of 27 ground-truth signal events while waking the agent tier
on 9.4% of live events. The two misses and the fitted-threshold problem are
written up honestly in [docs/evaluation.md](docs/evaluation.md).

## Where things are

| Path | What's in it |
|---|---|
| `docs/solution.md` | The 3-page solution document |
| `docs/architecture.svg` | System architecture diagram |
| `docs/evaluation.md` | Test results, failure modes, what's fragile |
| `research/research-log.md` | What I read, what I took from it, which decision it changed |
| `src/` | The system |
| `eval/` | Scoring harness and detector coverage |
| `notebooks/explore_stream.py` | The data exploration the design came out of |
| `midterm/` | 15 Sep snapshot, kept as submitted |

## How the code is laid out

```
src/
  schemas.py      enums the evaluator scores against, plus Event/Signal/Assertion/Checkpoint
  ingest.py       normalise, dedupe, order by event time, append-only log
  pii.py          tokenisation and the merchant -> semantic class lexicon
  features.py     per-customer baseline and running aggregates
  detectors.py    the cheap deterministic tests
  scheduler.py    the daily tick that notices what did NOT happen
  weights.py      what each signal is worth, and to which hypothesis
  ledger.py       the evidence ledger and the posterior
  agents.py       the agents, each with its capabilities, tools and prompt
  guardrails.py   hard stops, the state x action policy matrix, tool boundaries
  memory.py       working / episodic / semantic memory and the access broker
  orchestrator.py the loop
  trace.py        spans
```

`weights.py` is where the judgement lives. Everything else is machinery.

## The dataset

Three practice scenarios under `customer_360_dataset/`. Events carry both
`event_time` and `ingestion_time`, and these deliberately disagree — late and
out-of-order arrival is part of the problem, not noise to be smoothed away.

## Submission

Mid-term (15 Sep): preliminary research, architecture, one-page report — in
`midterm/`, left as submitted.
End-term (19 Sep): everything above.
