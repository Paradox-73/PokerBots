"""Limp-raisers: the solver's preflop button play stops binding once the big blind has raised most of our limps.

The solver's big blind raises a limp 37% of the time, and its button folds 60% of its limping range to a raise to 10.
The veto in pick() drops any option the solver plays under 10%, and the solver folds under 10% of the time with 88%
of button hands, so against a big blind that raises every limp the bot still limped and then folded: 77 of 78
limps in one 1,000-hand match, 380 chips per match more lost than to the same bot without the raise (se 90, 120
matches). Both rivals written from the organisers' documents alone raise almost every limp too. Once the big blind
has raised at least 60% of at least 5 of our limps, folding is always open at the button's first action, and our own
model alone answers its raise. The limp keeps its price from decide(): a raise is counted as a fold, so against such
a big blind the button opens or folds instead of limping. (Pricing the limp as the better of folding and calling the
raise made the bot limp hands it used to open, and it lost 10 match points in 64 short matches to those two rivals.)
Needs fix49.py (the big blind's answers to our limps have their own counter, slot 8).
Not shipped (cand81). Against the same two rivals it scored -5.0 match points in 64 short matches (se 4.8), and a
logged match showed it folding hands the solver opens; build/fix53.py lets only hands the solver would not open
fold (results/limp_round_9nov.txt).
usage: fix51.py IN_BOT OUT_BOT"""
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
cut('''                options.append((self.ev_raise(st, ip, req, to, window), "raise", to))
        return self.pick(options, P, req)
''', '''                options.append((self.ev_raise(st, ip, req, to, window), "raise", to))
        # A big blind that raised most of our limps is not the one the solver's button play answers (it raises 37%):
        # folding stays open at the first action, and our own model alone answers its raise.
        if st == 0 and h.button and h.bets[0] <= 2 and h.raises <= 1 and self.view is not None and self.limp_raiser():
            self.view = [1.0, *self.view[1:]] if h.raises == 0 else None
        return self.pick(options, P, req)
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
