"""From a code review of the postflop equity engine: on the flop, narrow() reads each opponent action as a slice of its 3-card hands ranked by
best keep (T_order), but range_view() sorted the kept-pair weights by pair strength, so window() sliced a different
set of hands than the action model describes (top 15% equity gap up to 0.24 while the discard model is unsure).
The flop view now slices the triple order, each triple's equity averaged over its keep probabilities.
usage: fix35.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()
old = '''            if h.st == 1:
                eqs = h.E @ pw / pw.sum()
                best = int(np.argmax(eqs))
                e = h.E[best]
            else:
                e = h.E[0]
            order = np.argsort(-h.S)
            w, e = pw[order], e[order]'''
new = '''            if h.st == 1:
                eqs = h.E @ pw / pw.sum()
                best = int(np.argmax(eqs))
                # flop actions are slices of the triple order (narrow), so slice the range the same way
                tw = h.W3[:, None] * h.Pk
                order = h.T_order[::-1]
                w = tw.sum(1)[order]
                e = ((tw * h.E[best][PT]).sum(1) / np.maximum(tw.sum(1), 1e-300))[order]
            else:
                order = np.argsort(-h.S)
                w, e = pw[order], h.E[0][order]'''
assert src.count(old) == 1
src = src.replace(old, new)
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
