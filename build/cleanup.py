"""Remove code that no longer runs under the two-leg rules: the lead lock and the score-aware
all-in call (USE_LOCK is False and match_call is never called), the match-score counters they
read, and two unused imports. usage: cleanup.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()
head, sep, rest = src.partition("\nSOLVER_ABSTRACTION = r'''")  # only the main part is edited
assert sep


def cut(old, new=""):
    global head
    assert head.count(old) == 1, old
    head = head.replace(old, new)


cut('''frequencies come from counters on this opponent, seeded with priors.
''', '''frequencies come from counters on this opponent, seeded with priors.
A precomputed equilibrium strategy (the solver section below) follows every
hand, and a move it would almost never make in that spot is dropped.
''')
cut("import math\n")
cut("import random\n")
cut("USE_LOCK = False  # a leg cannot see the other leg's chips, so a lead is never safe to fold out\n")
cut('''        self.bank = 60000
        self.net = 0
        self.sq = 0.0  # sum of squared hand results, for the match variance
''')
cut('''    def win_prob(self, net):
        """Chance of ending the match ahead from `net` after this hand: the remaining hands
        add a shrunk estimate of our edge per hand, with this match's spread."""
        h = self.h
        left = self.total - h.id
        if left <= 0:
            return 1.0 if net > 0 else 0.5 if net == 0 else 0.0
        mean = self.net / (h.id + 40.0)
        sd = max(10.0, (self.sq / max(1, h.id)) ** 0.5) * left ** 0.5
        return 0.5 * (1.0 + math.erf((net + mean * left) / (sd * 2 ** 0.5)))

    def match_call(self, options, eq, req):
        """An all-in call settles the hand, so score it by the match it leaves: a favourite
        passes on coin flips, an underdog takes them. Chips decide when both score alike."""
        spent = 200 - req["my_stack"]
        stake = spent + req["to_call"]  # stacks start equal, so a won all-in pays what it risks
        fold = self.win_prob(self.net - spent)
        call = eq * self.win_prob(self.net + stake) + (1 - eq) * self.win_prob(self.net - stake)
        if abs(call - fold) < 0.002:
            return options
        keep = "call" if call > fold else "fold"
        return [o for o in options if o[1] == keep or o[1] not in ("call", "fold")]

''')
cut('''    def lock_budget(self):
        """Chips this hand may risk once folding out the match still wins it; None = no limit.

        The win is locked only if it is in doubt, or the chip cap leaves nothing more to earn.
        """
        h = self.h
        left = self.total - h.id
        cost = left // 2 * 3 + (left % 2) * (2 if h.button else 1)
        budget = self.net - cost - 1
        if not USE_LOCK or budget < h.commit[0] or budget >= 200:
            return None
        mean = self.net / max(1, h.id)
        sd = max(20.0, (self.sq / max(1, h.id)) ** 0.5)
        safe = (self.net + max(0.0, mean) * left) / (sd * max(1, left) ** 0.5)
        cap = 400 if self.total <= 400 else 1000  # Rulebook 8.3 tie-break cap (provisional)
        return budget if safe < 2.0 or budget > cap else None

''')
cut('''    def pick(self, options, P, req):
        h = self.h
        budget = self.lock_budget()
        if budget is not None:
            safe = []
            for ev, act, amt in options:
                add = req["to_call"] if act == "call" else amt - req["my_bet"] if act == "raise" else 0
                if act in ("fold", "check") or h.commit[0] + add <= budget:
                    safe.append((ev, act, amt))
            options = safe
        view = self.view''', '''    def pick(self, options, P, req):
        view = self.view''')
cut('''        h = self.h
        self.net += msg.get("net", 0)
        self.sq += msg.get("net", 0) ** 2
        if h is None:''', '''        h = self.h
        if h is None:''')
for name in ("math.", "random.", "USE_LOCK", "lock_budget", "win_prob", "match_call", "self.net", "self.sq", "self.bank"):
    assert name not in head.replace("np.random.", ""), name
out = head + sep + rest
compile(out, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(out)
print(sys.argv[2], "written,", len(src) - len(out), "bytes removed")
