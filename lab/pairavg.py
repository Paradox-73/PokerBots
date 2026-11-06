"""Paired comparison of two bots from legrun rows, using every repeat: rows with the same (opponent, stage, seed)
are averaged first (repeats come from re-runs), then version B minus version A is taken on the keys both have.
usage: [OPP=a,b] [SEEDS=lo-hi] pairavg.py A_ROWS.jsonl[,MORE.jsonl] A_NAME B_ROWS.jsonl[,MORE.jsonl] B_NAME
(A_NAME/B_NAME pick the hero column "a" in the rows)"""
import collections
import json
import os
import sys

lo, hi = map(int, os.environ.get("SEEDS", "0-999999").split("-"))
opps = set(os.environ["OPP"].split(",")) if os.environ.get("OPP") else None
CAP = {1: 400, 2: 1000}


def load(paths, hero):
    acc = collections.defaultdict(list)
    for p in paths.split(","):
        for r in map(json.loads, open(p)):
            if r.get("a") != hero or r.get("chips") is None or r.get("forfeit") or not lo <= r["seed"] <= hi:
                continue
            if opps and r["b"] not in opps:
                continue
            c = max(-CAP[r["stage"]], min(CAP[r["stage"]], r["chips"]))
            acc[(r["b"], r["stage"], r["seed"])].append((c, 1.0 if c > 0 else 0.5 if c == 0 else 0.0))
    return {k: (sum(c for c, _ in v) / len(v), sum(p for _, p in v) / len(v), len(v)) for k, v in acc.items()}


A, B = load(sys.argv[1], sys.argv[2]), load(sys.argv[3], sys.argv[4])
for st in (2, 1):
    keys = sorted(k for k in A if k in B and k[1] == st)
    if not keys:
        continue
    for opp in sorted({k[0] for k in keys}):
        ks = [k for k in keys if k[0] == opp]
        da = [B[k][0] - A[k][0] for k in ks]
        print("S%d %-10s seeds %3d  rows A %3d B %3d  wins A %5.1f B %5.1f  capped A %+5.0f B %+5.0f  B-A %+5.0f" % (
            st, opp, len(ks), sum(A[k][2] for k in ks), sum(B[k][2] for k in ks), sum(A[k][1] for k in ks),
            sum(B[k][1] for k in ks), sum(A[k][0] for k in ks) / len(ks), sum(B[k][0] for k in ks) / len(ks), sum(da) / len(ks)))
    n = len(keys)
    d = [B[k][0] - A[k][0] for k in keys]
    dp = [B[k][1] - A[k][1] for k in keys]
    m, mp = sum(d) / n, sum(dp) / n
    se = (sum((x - m) ** 2 for x in d) / max(1, n - 1) / n) ** .5
    sep = (sum((x - mp) ** 2 for x in dp) / max(1, n - 1) / n) ** .5
    print("S%d all %d seeds: points B-A %+.1f (se %.1f)  capped/match B-A %+.1f (se %.1f)" % (st, n, mp * n, sep * n, m, se))
