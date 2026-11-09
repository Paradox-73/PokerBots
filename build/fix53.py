"""Limp-raisers: once the big blind has raised most of our limps, the solver no longer forces the limp-then-fold.

The solver's big blind raises a limp 37% of the time, and its button folds 60% of its limping range to a raise to 10.
The veto in pick() drops any option the solver plays under 10%, and the solver folds under 10% of the time with 88%
of button hands, so against a big blind that raises every limp the bot still limped and then folded: 77 of 78
limps in one 1,000-hand match, 380 chips per match more lost than to the same bot without the raise (se 90, 120
matches). Once the big blind has raised at least 60% of at least 5 of our limps:
1. a hand the solver would not open (it raises it under 10% of the time) may fold instead of limping, and its limp
   is priced as the better of folding and calling a raise to 10 against the raising range, not as a fold;
2. our own model alone answers the raise.
Hands the solver opens keep its advice. Letting every hand fold made the bot fold hands the solver opens, and letting
every limp be priced for the call made it limp hands it used to open; both lost points to the two rivals written
from the organisers' documents alone, which raise almost every limp.
Needs fix49.py (the big blind's answers to our limps have their own counter, slot 8).
usage: fix53.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''    def decide(self, req):
''', '''    def limp_raiser(self):
        c = self.opp.counts.get((30, 0, 8))  # the big blind's answers to our limps
        return c is not None and c.sum() >= 5 and c[RS:].sum() >= 0.6 * c.sum()

    def decide(self, req):
''')
cut('''        if "call" in legal:
            ev = self.value(eq, P + tc, behind, st, ip) - tc  # behind is already the stack after calling
            if st == 0 and h.button and h.raises == 0:  # a limp lets the big blind raise
                r = o.dist(0, 0, 0, 8)[RS:].sum()
                ev = (1 - r) * ev + r * -tc
''', '''        # A big blind that raised most of our limps is not the one the solver's button play answers (it raises 37%).
        lr = st == 0 and h.button and h.bets[0] <= 2 and h.raises <= 1 and self.view is not None and self.limp_raiser()
        only_limp = lr and h.raises == 0 and self.view[2] < VETO_P  # a hand the solver would not open
        if "call" in legal:
            ev = self.value(eq, P + tc, behind, st, ip) - tc  # behind is already the stack after calling
            if st == 0 and h.button and h.raises == 0:  # a limp lets the big blind raise
                r = o.dist(0, 0, 0, 8)[RS:].sum()
                # the better of folding and calling a raise to 10 against its raising range
                cont = max(-tc, self.value(window(0, r), 20, behind - 8, st, ip) - 8 - tc) if only_limp else -tc
                ev = (1 - r) * ev + r * cont
''')
cut('''                options.append((self.ev_raise(st, ip, req, to, window), "raise", to))
        return self.pick(options, P, req)
''', '''                options.append((self.ev_raise(st, ip, req, to, window), "raise", to))
        if lr and h.raises == 1:
            self.view = None  # our own model answers its raise
        elif only_limp:
            self.view = [1.0, *self.view[1:]]  # folding open instead of a forced limp
        return self.pick(options, P, req)
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
