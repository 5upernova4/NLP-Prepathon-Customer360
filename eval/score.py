"""Scoring harness: inferred_events.json vs ground_truth.json.

PS 8.1 offers credit for building this, and the reason to want it is simpler
than the credit: the thresholds in this system are hand-set, and I would
rather find out they are wrong from a script than from the leaderboard.

It scores the artifact the evaluator scores -- the emitted checkpoint file --
so it depends on nothing inside src/. Any implementation that writes a
schema-conformant inferred_events.json can be scored by it.

Five things are measured, because the ground-truth files carry five kinds of
claim:

  state        did we name the right inferred_state at this checkpoint
  band         did we reach the right confidence at the right time -- scored
               with direction, because 'too early' and 'too late' are
               different failures and averaging them hides both
  action       did we commit to the right bounded action, and subtype
  hitl         did we route it correctly
  lead time    did the action fire within ideal_action_lead_time_days of when
               it should have, rather than merely appearing by the checkpoint
  red herrings did a forbidden action fire inside a false-positive window

Usage:
    python3 eval/score.py runs/scenario_01/inferred_events.json \
                          customer_360_dataset/scenario_01
    python3 eval/score.py --all runs/          # every scenario at once
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

BANDS = {"low": 0, "medium": 1, "high": 2}


def T(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_events(scenario_dir: Path) -> dict[str, dt.datetime]:
    """event_id -> event_time, for resolving false-positive windows."""
    out: dict[str, dt.datetime] = {}
    for name in ("history_seed.jsonl", "live_stream.jsonl"):
        f = scenario_dir / name
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                out[e["event_id"]] = T(e["event_time"])
    return out


def assessment_at(checkpoints: list[dict], when: dt.datetime) -> dict | None:
    """The system's belief as of `when`.

    Takes the latest checkpoint at or before the time asked about. A system
    that writes densely can answer any as_of_time; one that writes three rows
    and hopes they line up cannot, and this is where that shows.
    """
    eligible = [c for c in checkpoints if T(c["as_of_time"]) <= when]
    if not eligible:
        return None
    return max(eligible, key=lambda c: T(c["as_of_time"]))


def first_time_action(checkpoints: list[dict], action: str,
                      before: dt.datetime) -> dt.datetime | None:
    hits = [T(c["as_of_time"]) for c in checkpoints
            if c.get("action") == action and T(c["as_of_time"]) <= before]
    return min(hits) if hits else None


def score_scenario(inferred_path: Path, scenario_dir: Path) -> dict:
    gt = json.loads((scenario_dir / "ground_truth.json").read_text())
    emitted = json.loads(inferred_path.read_text())
    if isinstance(emitted, dict):                 # tolerate {"checkpoints": [...]}
        emitted = emitted.get("checkpoints", [])
    events = load_events(scenario_dir)

    rows, tally = [], {"state": [0, 0], "band": [0, 0], "action": [0, 0],
                       "subtype": [0, 0], "hitl": [0, 0], "lead": [0, 0]}

    for exp in gt["checkpoints"]:
        when = T(exp["as_of_time"])
        got = assessment_at(emitted, when)
        row = {"as_of_time": exp["as_of_time"], "missing": got is None}

        def mark(key: str, ok: bool | None):
            if ok is None:
                return
            tally[key][1] += 1
            tally[key][0] += int(ok)

        if got is None:
            row["note"] = "no checkpoint at or before this time"
            for k in ("state", "band", "action"):
                mark(k, False)
            rows.append(row)
            continue

        exp_state = exp["expected_inferred_state"]
        got_state = got.get("inferred_state")
        row["state"] = f"{got_state} vs {exp_state}"
        mark("state", got_state == exp_state)

        exp_band, got_band = exp["expected_confidence_band"], got.get("confidence_band")
        drift = BANDS.get(got_band, -1) - BANDS.get(exp_band, -1)
        row["band"] = (f"{got_band} vs {exp_band}"
                       + ("" if drift == 0 else
                          f"  ({'OVER-confident' if drift > 0 else 'UNDER-confident'} "
                          f"by {abs(drift)})"))
        mark("band", drift == 0)

        exp_action, got_action = exp["expected_action"], got.get("action")
        row["action"] = f"{got_action} vs {exp_action}"
        mark("action", got_action == exp_action)

        if exp.get("expected_action_subtype"):
            row["subtype"] = f"{got.get('action_subtype')} vs {exp['expected_action_subtype']}"
            mark("subtype", got.get("action_subtype") == exp["expected_action_subtype"])

        if exp.get("expected_hitl_status"):
            row["hitl"] = f"{got.get('hitl_status')} vs {exp['expected_hitl_status']}"
            mark("hitl", got.get("hitl_status") == exp["expected_hitl_status"])

        lead = exp.get("ideal_action_lead_time_days")
        if lead is not None and exp_action != "no_action":
            fired = first_time_action(emitted, exp_action, when)
            if fired is None:
                row["lead"] = f"never fired {exp_action} by this checkpoint"
                mark("lead", False)
            else:
                days = (when - fired).total_seconds() / 86400
                ok = days >= lead - 0.5
                row["lead"] = (f"fired {days:.1f}d before checkpoint "
                               f"(ideal >= {lead}d) -> {'ok' if ok else 'LATE'}")
                mark("lead", ok)
        rows.append(row)

    # ------------------------------------------------------ red-herring checks
    fp_rows, fp_pass = [], 0
    for chk in gt.get("false_positive_checks", []):
        eid = chk["event_id"]
        t0 = events.get(eid)
        forbidden = set(chk["must_not_trigger_action"])
        if t0 is None:
            fp_rows.append({"event_id": eid, "result": "event_id not found"})
            continue
        t1 = t0 + dt.timedelta(hours=chk.get("window_hours", 72))
        violations = [c for c in emitted
                      if t0 <= T(c["as_of_time"]) <= t1
                      and c.get("action") in forbidden]
        ok = not violations
        fp_pass += int(ok)
        fp_rows.append({
            "event_id": eid,
            "forbidden": sorted(forbidden),
            "result": "clean" if ok else
                      f"VIOLATED by {[v['action'] for v in violations]}",
        })

    return {
        "scenario": gt.get("scenario_id", scenario_dir.name),
        "checkpoints": rows,
        "tally": tally,
        "false_positives": fp_rows,
        "fp_pass": fp_pass,
        "fp_total": len(gt.get("false_positive_checks", [])),
        "emitted_count": len(emitted),
    }


def render(res: dict) -> str:
    L = [f"\n{'='*74}", f"{res['scenario']}   ({res['emitted_count']} checkpoints emitted)",
         "=" * 74]
    for r in res["checkpoints"]:
        L.append(f"\n  as_of {r['as_of_time']}")
        if r.get("missing"):
            L.append(f"     !! {r['note']}")
            continue
        for k in ("state", "band", "action", "subtype", "hitl", "lead"):
            if k in r:
                L.append(f"     {k:8s} {r[k]}")
    if res["false_positives"]:
        L.append("\n  red-herring checks")
        for f in res["false_positives"]:
            L.append(f"     {f['event_id']}  {f['result']}")
    L.append("\n  " + "-" * 70)
    for k, (hit, n) in res["tally"].items():
        if n:
            L.append(f"  {k:8s} {hit}/{n}   {hit/n:.0%}")
    if res["fp_total"]:
        L.append(f"  {'no-FP':8s} {res['fp_pass']}/{res['fp_total']}   "
                 f"{res['fp_pass']/res['fp_total']:.0%}")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inferred", nargs="?", help="path to inferred_events.json")
    ap.add_argument("scenario", nargs="?", help="scenario directory")
    ap.add_argument("--all", metavar="RUNS_DIR",
                    help="score every scenario under RUNS_DIR")
    ap.add_argument("--dataset", default="customer_360_dataset")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    pairs: list[tuple[Path, Path]] = []
    if a.all:
        runs = Path(a.all)
        for d in sorted(runs.iterdir()) if runs.exists() else []:
            f = d / "inferred_events.json"
            sc = Path(a.dataset) / d.name
            if f.exists() and sc.exists():
                pairs.append((f, sc))
        if not pairs:
            print(f"no scored runs found under {runs}/ "
                  f"(expected <scenario>/inferred_events.json)", file=sys.stderr)
            return 2
    elif a.inferred and a.scenario:
        pairs.append((Path(a.inferred), Path(a.scenario)))
    else:
        ap.print_help()
        return 2

    results = [score_scenario(f, s) for f, s in pairs]
    if a.json:
        print(json.dumps(results, indent=2))
        return 0
    for r in results:
        print(render(r))

    agg: dict[str, list[int]] = {}
    for r in results:
        for k, (hit, n) in r["tally"].items():
            cur = agg.setdefault(k, [0, 0])
            cur[0] += hit
            cur[1] += n
    fp_hit = sum(r["fp_pass"] for r in results)
    fp_tot = sum(r["fp_total"] for r in results)
    if len(results) > 1:
        print(f"\n{'='*74}\nACROSS {len(results)} SCENARIOS\n{'='*74}")
        for k, (hit, n) in agg.items():
            if n:
                print(f"  {k:8s} {hit}/{n}   {hit/n:.0%}")
        if fp_tot:
            print(f"  {'no-FP':8s} {fp_hit}/{fp_tot}   {fp_hit/fp_tot:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
