"""fix24.py ported to builds that carry fix29 (its solver_view anchor line).
Three solver-check mapping fixes from the solver review. usage: fix24.py IN_BOT OUT_BOT
1. A bet far below the tree's size (a min bet read as a third of the pot) asked the solver about a
   bet costing several times more: no solver check when the real price is under half the tree's.
2. Where the tree's only raise is all-in, its raise share judges a shove only: other raise sizes
   are no longer dropped by it (the view carries a 4th entry, 1.0 at such nodes).
3. The view sums the table row before the play-time 4% cut, which split raise sizes fell under.
With CHECK_ONLY_FACING=1 also: no solver check when nothing is to call (bet/check choices)."""
import os
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        if req.get("opp_stack", 0) > 0.2 * (req["pot"] + req["to_call"]) and all(a in ("f", "c") for a in node.actions):
            return None
        street = sb.STREET[req["street"]]
        bucket, _ = solver.features(street, [sb.A.card_id(c) for c in req["board"]])
        p = solver.strategy.probs(node, bucket)''', '''        if req.get("opp_stack", 0) > 0.2 * (req["pot"] + req["to_call"]) and all(a in ("f", "c") for a in node.actions):
            return None
        # A bet far below the tree's size here (a min bet read as a third of the pot): the solver's
        # answer is to a bet that costs several times more.
        tc = req.get("to_call", 0)
        if tc > 0 and node.to_call() > 0:
            if tc / (req["pot"] + tc) < 0.5 * node.to_call() / (node.pot + node.to_call()):
                return None
        street = sb.STREET[req["street"]]
        bucket, _ = solver.features(street, [sb.A.card_id(c) for c in req["board"]])
        # the table row itself: the solver's own 4% cut at play time can split raise sizes under VETO_P
        strat, na = solver.strategy, len(node.actions)
        o = strat.offsets[node.id] + bucket * na
        p = strat.table[o:o + na].astype(np.float64)
        p = p / p.sum() if p.sum() > 0 else np.full(na, 1.0 / na)''')
cut('''        view[kind] += float(q)
    return view''', '''        view[kind] += float(q)
    # 4th entry: the tree's only raise here is all-in, so its raise share judges a shove only
    view.append(float(all(a in ("f", "c", "a") for a in node.actions)))
    return view''')
cut('''            kept = [o for o in options if KIND[o[1]] not in VETO_KINDS or view[KIND[o[1]]] >= VETO_P]''',
    '''            kept = [o for o in options if KIND[o[1]] not in VETO_KINDS or view[KIND[o[1]]] >= VETO_P
                    or (o[1] == "raise" and view[3] and o[2] < req["max_raise"])]''')
if os.environ.get("CHECK_ONLY_FACING") == "1":
    cut('''        if view is not None and STREET[req["street"]] >= VETO_MIN_STREET:''',
        '''        if view is not None and STREET[req["street"]] >= VETO_MIN_STREET and req["to_call"] > 0:''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
