# Committed output

Produced by `python3 run.py --all`. Committed so the emitted artifact can be
inspected without running anything.

    inferred_events.json        what the evaluator scores, in the required schema
    inferred_events_audit.json  the same rows plus the posterior and the ranked
                                evidence behind each one, with cited event ids
    trace.json                  spans for every agent run, tool call and model call

Regenerate with `python3 run.py --all`; the files are overwritten in place.
Numbers reported in docs/evaluation.md come from exactly this output.
