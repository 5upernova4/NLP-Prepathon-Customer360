#!/usr/bin/env python3
"""Run the desk over one scenario, or all of them.

    python3 run.py customer_360_dataset/scenario_01
    python3 run.py --all
"""
import argparse
import os
import sys

from src.orchestrator import Desk
from src.trace import Tracer


def run_one(path, outdir):
    name = os.path.basename(path.rstrip("/"))
    tracer = Tracer()
    desk = Desk(path, tracer=tracer)
    desk.run()

    dest = os.path.join(outdir, name)
    out = desk.emit(os.path.join(dest, "inferred_events.json"))
    from pathlib import Path
    tracer.dump(Path(dest) / "trace.json")

    s = desk.stats
    print(f"{name}: {len(desk.checkpoints)} checkpoints  "
          f"events={s['events']} signals={s['signals']} "
          f"synthetic={s['synthetic']} deduped={s['deduped']} "
          f"wake-days={s['wakes']} revocations={s['revocations']} "
          f"llm={s['llm_calls']}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dataset", default="customer_360_dataset")
    ap.add_argument("--out", default="runs")
    a = ap.parse_args()

    if a.all:
        paths = sorted(os.path.join(a.dataset, d) for d in os.listdir(a.dataset)
                       if d.startswith("scenario_"))
    elif a.scenario:
        paths = [a.scenario]
    else:
        ap.error("give a scenario directory or --all")

    for p in paths:
        run_one(p, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
