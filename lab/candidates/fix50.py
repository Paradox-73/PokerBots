"""Limp-raisers: the solver's preflop button play stops binding once the big blind has raised most of our limps.

The solver's big blind raises a limp 37% of the time, and its button folds 60% of its limping range to a raise to 10.
The veto in pick() drops any option the solver plays under 10%, and the solver folds under 10% of the time with 88%
of button hands, so against a big blind that raises every limp the bot still limped and then folded: 77 of 78
limps in one 1,000-hand match, 380 chips per match more lost than to the same bot without the raise (se 90, 120
matches). Once the big blind has raised at least 60% of at least 5 of our limps:
1. at the button's first action folding is always open, and the limp is priced as the better of folding and
   calling a raise to 10 against its raising range, instead of as a fold;
2. the answer to its raise is our own model's alone.
Needs fix49.py (the big blind's answers to our limps have their own counter, slot 8).
Not shipped (cand79). Against the limp raiser it scored +916 chips per long match over cand72 (se 115), and against a
copy of cand72 that raises every limp it won 71 of 120 matches where cand72 won 58. But against the two rivals
written from the organisers' documents alone, which raise almost every limp, it lost 10 match points in 64 short
matches (se 4.3), the gate set before the result: it limped hands it used to open (results/limp_round_9nov.txt).
usage: fix50.py IN_BOT OUT_BOT"""
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
        lr = st == 0 and h.button and h.bets[0] <= 2 and h.raises <= 1 and self.limp_raiser()
        if "call" in legal:
            ev = self.value(eq, P + tc, behind, st, ip) - tc  # behind is already the stack after calling
            if st == 0 and h.button and h.raises == 0:  # a limp lets the big blind raise
                r = o.dist(0, 0, 0, 8)[RS:].sum()
                # the better of folding and calling a raise to 10 against its raising range
                cont = max(-tc, self.value(window(0, r), 20, behind - 8, st, ip) - 8 - tc) if lr else -tc
                ev = (1 - r) * ev + r * cont
''')
cut('''                options.append((self.ev_raise(st, ip, req, to, window), "raise", to))
        return self.pick(options, P, req)
''', '''                options.append((self.ev_raise(st, ip, req, to, window), "raise", to))
        if lr and self.view is not None:  # first action: folding stays open; against its raise: our model alone
            self.view = [1.0, *self.view[1:]] if h.raises == 0 else None
        return self.pick(options, P, req)
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
