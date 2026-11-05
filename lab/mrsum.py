"""Paired cand19 vs cand20 summary from FILE_A FILE_B (legrun rows): same opponent, stage and seed only.
Per stage: matches won, points (1 per win, 0.5 per tie), capped chip difference per match and its se."""
import json
import sys

def load(p):
    return {(r["b"], r["stage"], r["seed"]): r for r in map(json.loads, open(p)) if not r.get("forfeit")}

a, b = load(sys.argv[1]), load(sys.argv[2])
pt = lambda c: 1.0 if c > 0 else 0.5 if c == 0 else 0.0
for st, cap in ((2, 1000), (1, 400)):
    keys = sorted(k for k in a if k in b and k[1] == st)
    if not keys:
        continue
    for opp in sorted({k[0] for k in keys}):
        ks = [k for k in keys if k[0] == opp]
        print("S%d %-10s n %2d  A %4.1f mean %+5.0f   B %4.1f mean %+5.0f" % (st, opp, len(ks),
              sum(pt(a[k]["chips"]) for k in ks), sum(a[k]["chips"] for k in ks) / len(ks),
              sum(pt(b[k]["chips"]) for k in ks), sum(b[k]["chips"] for k in ks) / len(ks)))
    d = [max(-cap, min(cap, b[k]["chips"])) - max(-cap, min(cap, a[k]["chips"])) for k in keys]
    dp = [pt(b[k]["chips"]) - pt(a[k]["chips"]) for k in keys]
    n = len(d)
    se = lambda x: (sum((v - sum(x) / n) ** 2 for v in x) / max(1, n - 1) * n) ** 0.5
    print("S%d all n %d  points B-A %+.1f (se %.1f)  capped/match B-A %+.1f (se %.1f)" % (
        st, n, sum(dp), se(dp), sum(d) / n, se(d) / n))
