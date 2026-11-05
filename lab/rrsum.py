"""Round-robin table from rrun.py rows: match points (1 win, 0.5 tie), capped chips, forfeit lines,
and each bot's record against every other. usage: rrsum.py ROWS.jsonl [CAP]"""
import collections
import json
import sys

cap = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
pts, chips, n = collections.Counter(), collections.Counter(), collections.Counter()
h2h = collections.defaultdict(lambda: [0.0, 0])
forf = collections.Counter()  # forfeit lines by pair; chips are the engine's result either way
for r in map(json.loads, open(sys.argv[1])):
    if r.get("chips") is None:
        continue
    a, b, c = r["a"], r["b"], r["chips"]
    if r.get("forfeit"):
        forf[(a, b)] += 1
    pa = 1.0 if c > 0 else 0.5 if c == 0 else 0.0
    pts[a] += pa; pts[b] += 1 - pa
    k = max(-cap, min(cap, c))
    chips[a] += k; chips[b] -= k
    n[a] += 1; n[b] += 1
    h2h[(a, b)][0] += pa; h2h[(a, b)][1] += 1
    h2h[(b, a)][0] += 1 - pa; h2h[(b, a)][1] += 1
order = sorted(pts, key=lambda x: (-pts[x], -chips[x]))
print("%-12s %7s %5s %9s" % ("bot", "points", "of", "capped"))
for x in order:
    print("%-12s %7.1f %5d %+9d" % (x, pts[x], n[x], chips[x]))
print("forfeit lines by pair:", dict(forf) or "none")
print("\nwins of row bot vs column bot")
print(" " * 12 + "".join("%10s" % y[:9] for y in order))
for x in order:
    print("%-12s" % x + "".join("%10s" % ("-" if x == y else "%.1f/%d" % tuple(h2h[(x, y)]) if h2h[(x, y)][1] else "") for y in order))
