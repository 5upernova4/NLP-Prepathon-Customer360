"""
Scratch analysis of the three practice scenarios.

Point of this script: before designing anything, work out what the signal
actually looks like in this data, because the obvious design (score each event,
alert on the big ones) turns out to be backwards.

Run: python3 notebooks/explore_stream.py
"""
import json, collections, statistics as st
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "customer_360_dataset"
SCENARIOS = ["scenario_01", "scenario_02", "scenario_03"]
T = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load(scenario):
    base = ROOT / scenario
    hist = [json.loads(l) for l in open(base / "history_seed.jsonl")]
    live = [json.loads(l) for l in open(base / "live_stream.jsonl")]
    gt = json.load(open(base / "ground_truth.json"))
    ents = json.load(open(base / "entities.json"))
    return hist, live, gt, ents


def amount(e):
    return e["payload"].get("amount")


# ---------------------------------------------------------------- experiment 1
def amount_vs_signal():
    """Does transaction size predict whether an event matters?

    Rank every live event with an amount by size, then see where the
    ground-truth signal events and red herrings land in that ranking.
    """
    print("\n" + "=" * 72)
    print("1. IS AMOUNT A USEFUL PRIOR?")
    print("=" * 72)
    for s in SCENARIOS:
        _, live, gt, _ = load(s)
        sig, red = set(gt["signal_events"]), set(gt["red_herring_events"])
        with_amt = [e for e in live if isinstance(amount(e), (int, float))]
        ranked = sorted(with_amt, key=amount, reverse=True)
        n = len(ranked)
        pos = {e["event_id"]: i + 1 for i, e in enumerate(ranked)}

        sig_ranks = sorted(pos[i] for i in sig if i in pos)
        red_ranks = sorted(pos[i] for i in red if i in pos)
        print(f"\n{s}  ({n} live events carry an amount)")
        print(f"   signal events rank by size : {sig_ranks}")
        print(f"   red herrings rank by size  : {red_ranks}")

        # what would "alert on the top-5 largest" catch?
        top5 = {e["event_id"] for e in ranked[:5]}
        print(f"   top-5-by-amount alerting   : {len(top5 & sig)} signals, {len(top5 & red)} red herrings")
        if sig_ranks and red_ranks:
            print(f"   -> median signal rank {st.median(sig_ranks):.0f}, "
                  f"median red-herring rank {st.median(red_ranks):.0f}")


# ---------------------------------------------------------------- experiment 2
def category_novelty():
    """How often does the life event announce itself as a brand-new MCC?"""
    print("\n" + "=" * 72)
    print("2. NOVEL-CATEGORY TEST")
    print("=" * 72)
    for s in SCENARIOS:
        hist, live, gt, _ = load(s)
        sig = set(gt["signal_events"])
        seen = {e["payload"].get("mcc_category") for e in hist
                if e["source_system"] == "card_payments"}
        seen.discard(None)
        firsts = []
        running = set(seen)
        for e in sorted(live, key=lambda e: e["event_time"]):
            if e["source_system"] != "card_payments":
                continue
            c = e["payload"].get("mcc_category")
            if c and c not in running:
                running.add(c)
                firsts.append((e["event_id"], e["event_time"][:10], c,
                               amount(e), e["event_id"] in sig))
        print(f"\n{s}  baseline categories: {sorted(seen)}")
        for eid, when, cat, amt, is_sig in firsts:
            tag = "SIGNAL " if is_sig else "        "
            print(f"   {tag}{when}  first-ever '{cat}'  ${amt}  ({eid})")
        hits = sum(1 for *_, is_sig in firsts if is_sig)
        print(f"   -> {hits}/{len(firsts)} first-in-category events are ground-truth signals")


# ---------------------------------------------------------------- experiment 3
def silence():
    """Absence of events. Nothing fires here, which is the whole problem."""
    print("\n" + "=" * 72)
    print("3. SILENCE — THE SIGNAL THAT EMITS NO EVENT")
    print("=" * 72)
    for s in SCENARIOS:
        hist, live, _, _ = load(s)
        cfg = json.load(open(ROOT / s / "replay_config.json"))
        end = T(cfg["simulated_end"])

        def gaps(evs):
            t = sorted(T(e["event_time"]) for e in evs
                       if e["source_system"] in ("card_payments", "web_app_events"))
            return [(b - a).total_seconds() / 86400 for a, b in zip(t, t[1:])], t

        hg, _ = gaps(hist)
        lg, lt = gaps(live)
        trailing = (end - lt[-1]).total_seconds() / 86400 if lt else 0
        print(f"\n{s}")
        print(f"   history : max gap {max(hg):.1f}d, p95 {sorted(hg)[int(len(hg)*.95)]:.1f}d, mean {st.mean(hg):.2f}d")
        print(f"   live    : max gap {max(lg):.1f}d")
        print(f"   trailing silence to simulated_end: {trailing:.0f} days "
              f"({trailing / max(hg):.0f}x the historical max gap)")


# ---------------------------------------------------------------- experiment 4
def income_cadence():
    """Model expected salary arrivals from history, then check the live window."""
    print("\n" + "=" * 72)
    print("4. EXPECTED-ARRIVAL MODEL FOR INCOME")
    print("=" * 72)
    for s in SCENARIOS:
        hist, live, _, _ = load(s)
        sal = [e for e in hist if e["payload"].get("transaction_type") == "salary_credit"]
        if len(sal) < 3:
            continue
        times = [T(e["event_time"]) for e in sal]
        period = st.median((b - a).days for a, b in zip(times, times[1:]))
        amt = st.median(amount(e) for e in sal)
        print(f"\n{s}  baseline: ${amt:.0f} every {period:.0f} days ({len(sal)} observations)")

        cursor = times[-1]
        live_ledger = [e for e in live if e["source_system"] == "core_banking_ledger"]
        end = T(json.load(open(ROOT / s / "replay_config.json"))["simulated_end"])
        while cursor + dt.timedelta(days=period) <= end:
            cursor += dt.timedelta(days=period)
            window = [e for e in live_ledger
                      if abs((T(e["event_time"]) - cursor).days) <= 2
                      and e["payload"].get("amount", 0) > 0
                      and "credit" in str(e["payload"].get("transaction_type", ""))]
            if not window:
                print(f"   {cursor.date()}  EXPECTED ${amt:.0f} -> nothing arrived  [MISS]")
            else:
                got = window[0]
                a = amount(got)
                kind = got["payload"]["transaction_type"]
                delta = (a - amt) / amt * 100
                flag = "  [SHORTFALL]" if delta < -15 else ""
                sub = "  [SUBSTITUTED]" if kind != "salary_credit" else ""
                print(f"   {cursor.date()}  expected ${amt:.0f} -> ${a} as {kind} "
                      f"({delta:+.0f}%){flag}{sub}")


# ---------------------------------------------------------------- experiment 5
def commitments():
    """Recurring obligations are a set. Watch the set change."""
    print("\n" + "=" * 72)
    print("5. STANDING-INSTRUCTION SET DIFF")
    print("=" * 72)
    for s in SCENARIOS:
        hist, live, _, _ = load(s)
        def si(evs):
            return collections.Counter(
                e["payload"].get("transaction_type") for e in evs
                if e["event_type"] in ("standing_instruction",)
                or e["payload"].get("transaction_type") in
                ("mortgage_payment", "rent_payment", "gym_membership", "utilities", "daycare_payment"))
        h, l = si(hist), si(live)
        added = set(l) - set(h)
        stopped = set(h) - set(l)
        print(f"\n{s}")
        print(f"   historical commitments: {dict(h)}")
        print(f"   live commitments      : {dict(l)}")
        if added:   print(f"   -> NEW obligations   : {sorted(added)}")
        if stopped: print(f"   -> LAPSED obligations: {sorted(stopped)}")
        # last observed date per commitment, to catch cancellation mid-window
        last = {}
        for e in sorted(live, key=lambda e: e["event_time"]):
            k = e["payload"].get("transaction_type")
            if k in h or k in l:
                last[k] = e["event_time"][:10]
        print(f"   last seen in live window: {last}")


# ---------------------------------------------------------------- experiment 6
def sweeps_and_pairs():
    """Cross-source correlations inside short windows."""
    print("\n" + "=" * 72)
    print("6. PAIRED / SWEPT MOVEMENTS")
    print("=" * 72)
    for s in SCENARIOS:
        _, live, _, _ = load(s)
        money = [e for e in live if isinstance(amount(e), (int, float))]
        money.sort(key=lambda e: e["event_time"])
        print(f"\n{s}")
        for a, b in [(a, b) for i, a in enumerate(money) for b in money[i + 1:i + 4]]:
            dtm = (T(b["event_time"]) - T(a["event_time"])).total_seconds()
            if dtm > 3600 * 6:
                continue
            ratio = min(amount(a), amount(b)) / max(amount(a), amount(b))
            if ratio > 0.9 and amount(a) > 1000:
                print(f"   {a['event_time'][:16]} {a['payload'].get('transaction_type') or a['event_type']:24s} ${amount(a)}")
                print(f"   {b['event_time'][:16]} {b['payload'].get('transaction_type') or b['event_type']:24s} ${amount(b)}   "
                      f"(+{dtm/60:.0f} min, {ratio:.0%} of the first)")


# ---------------------------------------------------------------- experiment 7
def lateness():
    print("\n" + "=" * 72)
    print("7. OUT-OF-ORDER ARRIVALS")
    print("=" * 72)
    for s in SCENARIOS:
        hist, live, gt, _ = load(s)
        sig = set(gt["signal_events"])
        for e in hist + live:
            lag = (T(e["ingestion_time"]) - T(e["event_time"])).total_seconds()
            if lag > 3600:
                mark = "  <-- IS A GROUND-TRUTH SIGNAL EVENT" if e["event_id"] in sig else ""
                print(f"   {s} {e['event_id']} arrives {lag/3600:.0f}h late "
                      f"({e['source_system']}/{e['event_type']}, "
                      f"{e['payload'].get('merchant_name', '')}){mark}")


if __name__ == "__main__":
    amount_vs_signal()
    category_novelty()
    silence()
    income_cadence()
    commitments()
    sweeps_and_pairs()
    lateness()
