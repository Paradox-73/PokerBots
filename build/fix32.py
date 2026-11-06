"""Fixes for re-raising over big bets, found with logged matches against value-overbet test opponents
(ob_audit.py on leaklogs4/: after a flop or turn bet of at least 1.2x the pot, our re-raises lost 70 chips per spot
on the turn (se 21, n 43) and 28 on the flop; the bettor folded to them 19% of the time).
E1 (E1=1): eps_agg is learnt as the share of the opponent's shown aggressive hands that were below the action's slice,
   but narrow() used it as a per-hand weight. For an action taken a fraction m of the time, a weight e leaves a weak
   share of e(1-m) / (e(1-m) + m): with e 0.15 and m 0.1 that is 57%, where the measured share is 15%. The weight
   is now the one that reproduces the measured share, w*m / ((1-m)(1-w)), and never more than before, so only
   actions taken less than about 46% of the time are read more tightly.
R1 (R1=1): facing a flop, turn or river bet of more than 1.2x the pot before it, raise only with eq >= 0.68, the bar
   sizes() already sets for our own shoves far above the pot.
usage: [E1=1] [R1=1] fix32.py IN_BOT OUT_BOT"""
import os
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


if os.environ.get("E1") == "1":
    cut('''            thr = 1.0 - p[a:].sum()
            e = self.opp.eps_agg(st)
            L = e + (1 - e) * sig(x, thr)''', '''            thr = 1.0 - p[a:].sum()
            w = self.opp.eps_agg(st)  # measured share of its shown aggressive hands that were below the slice
            m = min(max(1.0 - thr, 1e-3), 1 - 1e-3)
            e = min(w, w * m / ((1 - m) * (1 - w)))  # the weight that gives that share after this action
            L = e + (1 - e) * sig(x, thr)''')
if os.environ.get("R1") == "1":
    cut('''        if "raise" in legal:
            for to in self.sizes(req, eq):''', '''        # A bet of over 1.2x the pot is rarely folded to a re-raise, and the hands that call it beat a medium one.
        if "raise" in legal and (st == 0 or tc <= 1.2 * (P - tc) or eq >= 0.68):
            for to in self.sizes(req, eq):''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
