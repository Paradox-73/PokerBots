"""Who reaches the lock line first?  Reads running chip totals from field_matrix.py.

    python scripts/lock_race.py paths.jsonl --hero range

The line at a hand is the most that check-folding every remaining hand can lose.  A side
reaches it when its lead passes the line.  Reported per opponent: how often each side got
there first, the median hand it happened, the spread of hand results before either side
locked, and the match points that followed.
"""

import argparse
import collections
import json
import statistics


def line(left):
    return (left + 1) // 2 * 2 + left // 2


def first_cross(path):
    """(side, hand): side +1 if we reached the line first, -1 if they did, 0 if neither."""
    total = len(path)
    for i, net in enumerate(path):
        left = total - i - 1
        if net > line(left):
            return 1, i + 1
        if -net > line(left):
            return -1, i + 1
    return 0, total


def spread(path, stop):
    steps = [b - a for a, b in zip([0] + path[:stop - 1], path[:stop])]
    return statistics.pstdev(steps) if len(steps) > 1 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--hero", default="range")
    args = ap.parse_args()
    rows = collections.defaultdict(list)
    for name in args.files:
        with open(name, encoding="utf-8") as f:
            for r in map(json.loads, f):
                if r["a"] == args.hero and r["forfeit"] is None:
                    rows[(r["b"], r["deals"] * 2)].append(r["path"])
    print("%-10s %5s %4s | %-15s %-15s %-8s | %-6s %-6s" % (
        "opponent", "hands", "n", "we first @hand", "they first @hand", "neither", "spread", "points"))
    for (opp, hands), paths in sorted(rows.items()):
        marks = [first_cross(p) for p in paths]
        ours = [h for s, h in marks if s > 0]
        theirs = [h for s, h in marks if s < 0]
        points = sum(1.0 if p[-1] > 0 else 0.5 if p[-1] == 0 else 0.0 for p in paths)
        sd = statistics.mean(spread(p, h) for p, (_, h) in zip(paths, marks))
        print("%-10s %5d %4d | %3d @ %-9s %3d @ %-9s %-8d | %6.1f %5.1f" % (
            opp, hands, len(paths), len(ours), int(statistics.median(ours)) if ours else "-",
            len(theirs), int(statistics.median(theirs)) if theirs else "-",
            len(paths) - len(ours) - len(theirs), sd, points))


if __name__ == "__main__":
    main()
