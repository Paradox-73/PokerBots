"""a code review fixes.
W (W=1): window() took the whole bucket where a slice of the opponent's range ends and dropped the bucket where it
   starts, both toward weaker hands, so preflop (16 buckets) the bot overstated its equity when called or re-raised
   (8c8sKh vs an open to 8: 0.543 used, 0.419 simulated); the best preflop option changed in 9% of replayed decisions.
   The slice is now read off the cumulative curve, interpolated inside buckets.
G8 (G8=1): a bet far cheaper than the tree size it maps to (a min-raise read as the tree's pot-size open, a 2-chip
   bet read as a third of the pot) took the solver's folds for the larger bet: 103 preflop classes folded to a
   min-raise with 0.38-0.49 equity (calling gains 1.7 +- 0.75 chips per spot). No solver check when the real price
   is under 0.8 of the node's price.
usage: [W=1] [G8=1] fix34.py IN_BOT OUT_BOT"""
import os
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


if os.environ.get("W") == "1":
    cut('''        def window(lo, hi):
            i = int(np.searchsorted(cw, min(hi, 1.0) * tot))
            i = min(i, len(cw) - 1)
            if lo <= 0:
                return float(cwe[i] / max(cw[i], 1e-12))
            j = min(int(np.searchsorted(cw, lo * tot)), len(cw) - 1)
            if cw[i] - cw[j] < 1e-9:
                return float(cwe[i] / max(cw[i], 1e-12))
            return float((cwe[i] - cwe[j]) / (cw[i] - cw[j]))''', '''        xs, ys = np.concatenate(([0.0], cw)), np.concatenate(([0.0], cwe))

        def window(lo, hi):
            # Equity against the [lo, hi] slice of the range (strongest first), interpolated inside buckets.
            a, b = sorted((min(max(lo, 0.0), 1.0) * tot, min(max(hi, 0.0), 1.0) * tot))
            if b - a < 1e-9 * tot:
                a, b = max(0.0, a - 1e-6 * tot), min(tot, b + 1e-6 * tot)
            return float((np.interp(b, xs, ys) - np.interp(a, xs, ys)) / max(b - a, 1e-12))''')
if os.environ.get("G8") == "1":
    cut('''        node = solver.abstract_node(req)
        if node is None:
            return None
''', '''        node = solver.abstract_node(req)
        if node is None:
            return None
        # A bet far cheaper than the tree size it was mapped to (a min-raise read as a pot-size raise, a 2-chip bet
        # read as a third of the pot): the solver's folds there do not apply.
        real, tree = req["to_call"] / (req["pot"] + req["to_call"]), node.to_call() / max(1, node.pot + node.to_call())
        if req["to_call"] > 0 and real < 0.8 * tree:
            return None
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
