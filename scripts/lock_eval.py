"""Replay lock-in on recorded matches, so both rules are judged on identical cards.

    python scripts/lock_eval.py hero.jsonl --hero equity

A match locks at the first hand where the lead exceeds the most that check-folding
every remaining hand can lose.  From there the result is taken as a win, and the
final chips as the lead minus 1.5 chips per remaining hand, the average cost of
check-folding.  `margin` requires that much lead on top, which keeps tie-break chips
at the price of locking later.
"""

import argparse
import collections
import json


def worst(left):
    return (left + 1) // 2 * 2 + left // 2


def replay(path, margin):
    total = len(path)
    for i, net in enumerate(path):
        left = total - i - 1
        if net > worst(left) + margin:
            return max(1, net - round(1.5 * left))
    return path[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--hero", default="equity")
    ap.add_argument("--cap", type=int, default=400)
    args = ap.parse_args()
    rows = collections.defaultdict(list)
    for name in args.files:
        with open(name, encoding="utf-8") as f:
            for r in map(json.loads, f):
                if r["a"] == args.hero and r["forfeit"] is None:
                    rows[r["b"]].append(r["path"])
    print("%-10s %4s %7s | %-14s | %-14s | %-14s" % ("opponent", "n", "", "no lock", "lock", "lock+cap"))
    grand = collections.Counter()
    for opp, paths in sorted(rows.items()):
        cells = []
        for margin in (None, 0, args.cap):
            finals = [p[-1] if margin is None else replay(p, margin) for p in paths]
            points = sum(1.0 if x > 0 else 0.5 if x == 0 else 0.0 for x in finals)
            capped = sum(max(-args.cap, min(args.cap, x)) for x in finals) / len(finals)
            cells.append("%5.1f %+7.1f" % (points, capped))
            grand[(margin, "p")] += points
            grand[(margin, "c")] += capped * len(finals)
        print("%-10s %4d %7s | %-14s | %-14s | %-14s" % (opp, len(paths), "", *cells))
    n = sum(len(p) for p in rows.values())
    for margin, label in ((None, "no lock"), (0, "lock"), (args.cap, "lock+cap")):
        print("%-9s points %.1f of %d, mean capped chips %+.1f"
              % (label, grand[(margin, "p")], n, grand[(margin, "c")] / max(1, n)))


if __name__ == "__main__":
    main()
