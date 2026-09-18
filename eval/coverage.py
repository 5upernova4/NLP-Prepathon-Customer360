"""How much of the ground-truth signal does Tier 0 actually catch, and at what cost?

Two numbers matter and they pull against each other. Recall: of the events the
ground truth marks as signal, how many trip a detector. Wake rate: what fraction
of all live events trip anything at all, because every one of those is a
specialist agent waking up.

The architecture claims roughly 8% of events reach the expensive tier. This is
where that claim is checked, from committed code rather than a scratch script.

    python3 eval/coverage.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.detectors import DetectorBank            # noqa: E402
from src.features import FeatureStore             # noqa: E402
from src.ingest import load_scenario              # noqa: E402


def one(root: Path):
    pipe, _, cfg = load_scenario(root)
    gt = json.loads((root / "ground_truth.json").read_text())
    signal_ids = set(gt["signal_events"])
    herring_ids = set(gt["red_herring_events"])

    # Split by EVENT TIME, not by ingest position. in_event_time_order() re-sorts
    # the log, so a late-arriving live event can sort back before the last
    # history event; splitting on a count of ingest order would quietly feed it
    # into the baseline instead of testing against it. Scenario 1 has exactly
    # one such arrival, and the error would flatter us.
    ordered = pipe.log.in_event_time_order()
    start = cfg["_simulated_start"]
    history = [e for e in ordered if e.event_time < start]
    live = [e for e in ordered if e.event_time >= start]

    store = FeatureStore()
    for e in history:
        store.update(e)
    store.freeze_baseline()

    bank = DetectorBank(store)
    fired: dict[str, list[str]] = {}
    for e in live:
        store.update(e)
        signals = bank.run(e)
        if signals:
            fired[e.event_id] = [s.name for s in signals]

    caught = set(fired) & signal_ids
    herrings_fired = set(fired) & herring_ids
    return {
        "scenario": gt["scenario_id"],
        "live_events": len(live),
        "events_firing": len(fired),
        "wake_rate": len(fired) / len(live) if live else 0.0,
        "signals_total": len(signal_ids),
        "signals_caught": len(caught),
        "missed": sorted(signal_ids - set(fired)),
        "herrings_total": len(herring_ids),
        "herrings_firing": len(herrings_fired),
    }


def main():
    root = Path(__file__).resolve().parent.parent / "customer_360_dataset"
    rows = [one(root / d.name) for d in sorted(root.iterdir())
            if d.is_dir() and d.name.startswith("scenario_")]

    print(f"{'scenario':32s} {'live':>5s} {'fire':>5s} {'wake%':>6s} "
          f"{'recall':>8s} {'herrings':>9s}")
    print("-" * 72)
    tot_live = tot_fire = tot_sig = tot_caught = 0
    for r in rows:
        print(f"{r['scenario']:32s} {r['live_events']:5d} {r['events_firing']:5d} "
              f"{r['wake_rate']*100:5.1f}% "
              f"{r['signals_caught']:3d}/{r['signals_total']:<4d} "
              f"{r['herrings_firing']:4d}/{r['herrings_total']:<4d}")
        tot_live += r["live_events"]
        tot_fire += r["events_firing"]
        tot_sig += r["signals_total"]
        tot_caught += r["signals_caught"]
    print("-" * 72)
    print(f"{'total':32s} {tot_live:5d} {tot_fire:5d} "
          f"{tot_fire/tot_live*100:5.1f}% {tot_caught:3d}/{tot_sig:<4d}")

    print("\nSignal events no detector fires on:")
    for r in rows:
        for m in r["missed"]:
            print(f"  {r['scenario']:32s} {m}")

    print("\nRed herrings that DO trip a detector (firing is fine; acting on it "
          "is not -\n  see the false-positive checks in eval/score.py):")
    for r in rows:
        if r["herrings_firing"]:
            print(f"  {r['scenario']:32s} {r['herrings_firing']} of "
                  f"{r['herrings_total']}")


if __name__ == "__main__":
    main()
