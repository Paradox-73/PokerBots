"""Two-leg results per opponent and paired against the first version (same opponent, stage, seed).
usage: legsum.py STAGE BASE V...   (reads leg_<v>.jsonl)"""
import collections, json, math, os, sys
stage = int(sys.argv[1]); cap = 400 if stage == 1 else 1000
lo, hi = map(int, os.environ.get("SEEDS", "0-999999").split("-"))  # e.g. SEEDS=33-48 scores only those deals
def load(v):
    out = {}
    for r in map(json.loads, open("leg_%s.jsonl" % v)):
        # an opponent timing out on a busy test server says nothing about our bot, so that match is dropped
        if r["stage"] == stage and r["chips"] is not None and not (r["forfeit"] or "").startswith("B forfeited") and lo <= r["seed"] <= hi:
            out[(r["b"], r["seed"])] = r
    return out
def pts(x):
    return 1.0 if x > 0 else 0.5 if x == 0 else 0.0
vs = sys.argv[2:]
data = {v: load(v) for v in vs}
common = set.intersection(*(set(d) for d in data.values()))
opps = sorted({k[0] for k in common})
print("stage %d, %d matches per version on common seeds" % (stage, len(common)))
print("%-12s" % "opponent" + "".join("%18s" % v for v in vs))
for o in opps:
    ks = [k for k in common if k[0] == o]
    print("%-12s" % o + "".join("%9.1f/%-2d %+6.0f" % (sum(pts(data[v][k]["chips"]) for k in ks), len(ks),
          sum(max(-cap, min(cap, data[v][k]["chips"])) for k in ks) / len(ks)) for v in vs))
base = vs[0]
for v in vs:
    d = [pts(data[v][k]["chips"]) - pts(data[base][k]["chips"]) for k in common]
    c = [max(-cap, min(cap, data[v][k]["chips"])) - max(-cap, min(cap, data[base][k]["chips"])) for k in common]
    n = len(d); m = sum(d) / max(1, n); mc = sum(c) / max(1, n)
    se = (sum((x - m) ** 2 for x in d) / max(1, n - 1)) ** 0.5 * math.sqrt(n) if n > 1 else 0
    sec = (sum((x - mc) ** 2 for x in c) / max(1, n - 1)) ** 0.5 / math.sqrt(n) if n > 1 else 0
    f = sum(1 for k in common if data[v][k]["forfeit"]); nt = sum(data[v][k]["notices"] or 0 for k in common)
    tmax = max(data[v][k]["time"] for k in common) if common else 0
    print("%-8s points %6.1f  vs %s %+5.1f (se %.1f)  capped/match vs %s %+6.1f (se %.1f)  forfeit lines %d  notices %d  max time %.1f s"
          % (v, sum(pts(data[v][k]["chips"]) for k in common), base, sum(d), se, base, mc, sec, f, nt, tmax))
