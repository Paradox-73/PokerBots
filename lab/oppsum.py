"""Per-opponent record of one version from legrun rows: matches, wins, ties, capped chips per match (clipped to
+-400 in Stage 1, +-1000 in Stage 2) with its standard error, forfeits by either side, engine notices, slowest
time over both legs. A repeated (opponent, stage, seed) row is counted once.  usage: oppsum.py NAME ROWS.jsonl..."""
import collections, json, statistics, sys
name, files = sys.argv[1], sys.argv[2:]
rows = {}
for fn in files:
    for line in open(fn):
        r = json.loads(line)
        if r.get("a") == name and r.get("chips") is not None:
            rows[(r["stage"], r["b"], r["seed"])] = r
by = collections.defaultdict(list)
for (st, b, _), r in sorted(rows.items()):
    by[(st, b)].append(r)
tot = collections.Counter()
for (st, b), rs in sorted(by.items(), key=lambda kv: (-kv[0][0], kv[0][1])):
    cap = 1000 if st == 2 else 400
    cp = [max(-cap, min(cap, r["chips"])) for r in rs]
    se = statistics.stdev(cp) / len(cp) ** 0.5 if len(cp) > 1 else 0.0
    w = sum(r["chips"] > 0 for r in rs) + 0.5 * sum(r["chips"] == 0 for r in rs)
    tot[(st, "n")] += len(rs); tot[(st, "w")] += w
    tot[(st, "f")] += sum(bool(r["forfeit"]) for r in rs); tot[(st, "x")] += sum(r["notices"] or 0 for r in rs)
    print("S%d %-12s matches %3d  wins %5.1f  capped/match %+6.0f (se %3.0f)  forfeits %d  notices %d  slowest %5.1f s"
          % (st, b, len(rs), w, statistics.mean(cp), se, sum(bool(r["forfeit"]) for r in rs),
             sum(r["notices"] or 0 for r in rs), max(r["time"] for r in rs)))
for st in (2, 1):
    if tot[(st, "n")]:
        print("S%d all: %d matches, %.1f wins, %d forfeits, %d notices" % (st, tot[(st, "n")], tot[(st, "w")],
              tot[(st, "f")], tot[(st, "x")]))
