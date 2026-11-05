"""Compare two versions match by match on the same deals (field_matrix.py rows).

    python scripts/paired.py base.jsonl candidate.jsonl --hero range

Pairs rows by opponent and seed.  For each opponent it reports the gain per hand in chips
before any lock, with a 95% interval across pairs, and the match points of each side.
"""

import argparse
import collections
import json
import math

from lock_race import first_cross


def load(path, hero):
    rows = {}
    with open(path, encoding="utf-8") as f:
        for r in map(json.loads, f):
            if r["a"] == hero and r["forfeit"] is None:
                rows[(r["b"], r["deals"], r["seed"])] = r["path"]
    return rows


def edge(path):
    stop = first_cross(path)[1]
    return path[stop - 1] / stop


def points(path):
    return 1.0 if path[-1] > 0 else 0.5 if path[-1] == 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("candidate")
    ap.add_argument("--hero", default="range")
    args = ap.parse_args()
    base, cand = load(args.base, args.hero), load(args.candidate, args.hero)
    groups = collections.defaultdict(list)
    for key in sorted(set(base) & set(cand)):
        groups[key[:2]].append(key)
    print("%-10s %5s %4s | %8s %8s | %-18s" % ("opponent", "hands", "n", "pts base", "pts cand", "edge gain"))
    for (opp, deals), keys in sorted(groups.items()):
        gains = [edge(cand[k]) - edge(base[k]) for k in keys]
        n = len(gains)
        mean = sum(gains) / n
        half = 1.96 * math.sqrt(sum((g - mean) ** 2 for g in gains) / max(1, n - 1) / n)
        print("%-10s %5d %4d | %8.1f %8.1f | %+6.2f +- %5.2f" % (
            opp, deals * 2, n, sum(points(base[k]) for k in keys),
            sum(points(cand[k]) for k in keys), mean, half))


if __name__ == "__main__":
    main()
