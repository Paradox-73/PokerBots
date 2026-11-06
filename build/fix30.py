"""Three opponent-model fixes from a code review (state tracking itself was found exact on 11,457 replayed decisions).
F3 (always): a call the opponent could not raise over (street raise cap reached, or we are all-in) was read as
   "chose not to raise", cutting the top of its range by up to 70% and logging a slow-play lesson.
F1 (LEVEL0=1): the level-0 counter held two decisions: acting first, and acting after our check or limp. The limp
   EV and the out-of-position check EV read the merged rate (e.g. P(big blind raises our limp) 0.58, true 0.36).
   Level 0 now uses size slot 1 for "acts after our check/limp" and 0 for "acts first" (the prior ignores the slot).
F2 (PRE1=1): preflop the pooled key and the street key hold the same counts, so each preflop action was counted
   twice (one fold moved P(fold) from 0.30 to 0.52). Preflop now uses the pooled key only.
usage: [LEVEL0=1] [PRE1=1] fix30.py IN_BOT OUT_BOT"""
import os
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        elif h.bets[1] < h.bets[0]:  # a call
            e = self.opp.eps_pas(st)
            L = e + (1 - e) * sig(x, p[FOLD]) * (1 - 0.7 * sig(x, thr_r))
            h.events.append((st, 1, thr_r, x))''', '''        elif h.bets[1] < h.bets[0]:  # a call
            e = self.opp.eps_pas(st)
            # At the raise cap, or with us all-in (stacks start at 200), calling was its only way to continue.
            can_raise = h.raises + (st == 0) < 4 and h.commit[0] < 200
            L = e + (1 - e) * sig(x, p[FOLD]) * (1 - 0.7 * sig(x, thr_r) * can_raise)
            if can_raise:
                h.events.append((st, 1, thr_r, x))''')
if os.environ.get("LEVEL0") == "1":
    cut('''        lvl, sz = h.raises, h.sz
        p = self.opp.dist(st, lvl, sz)''', '''        lvl, sz = h.raises, h.sz
        if lvl == 0:  # two decisions at level 0: slot 1 = acting after our check or limp, slot 0 = acting first
            sz = int(h.button == (st == 0))
        p = self.opp.dist(st, lvl, sz)''')
    cut('''                r = o.dist(0, 0, 0)[RS:].sum()''', '''                r = o.dist(0, 0, 1)[RS:].sum()''')
    cut('''            return self.value(eq, P, behind, st, ip)
        p = self.opp.dist(st, h.raises, h.sz)
        b = float(p[RS:].sum())''', '''            return self.value(eq, P, behind, st, ip)
        p = self.opp.dist(st, 0, 1)  # out of position: the opponent acts after our check
        b = float(p[RS:].sum())''')
if os.environ.get("PRE1") == "1":
    cut('''        spec = self.counts.get((10 + st, lvl, sz))''',
        '''        spec = self.counts.get((10 + st, lvl, sz)) if st else None  # preflop: the same counts as the pool''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
