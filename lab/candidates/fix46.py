"""No preflop all-in while it is more than three pots: such a shove came only from the top few hands.

sizes() offered the all-in only when it is at most three pots or equity is at least 0.68. Preflop the pot is 3 or 4
chips, so every open-shove was one of the strongest 3-4% of hands (52 of 52 logged had equity 0.60 or more). An
opponent that calls an all-in only with the very top of its range loses the blinds to such a shove instead of a
stack: a copy of the control bot with that one rule gained 96 capped chips per long match over the control against
cand55 (se 37, 60 matches). Preflop the strong hands now raise to the normal sizes, and the all-in stays offered once
it is at most three pots. After the flop nothing changes.
usage: fix46.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        # A shove far above the pot needs a real hand: fold-rate estimates there are thin,
        # and the callers it meets are the ones that beat a medium hand.
        out = {hi} if hi - b <= 3 * P or eq >= 0.68 else set()
''', '''        # A shove far above the pot needs a real hand: fold-rate estimates there are thin,
        # and the callers it meets are the ones that beat a medium hand. Preflop not even then:
        # it would show the top few hands and win only the blinds from anyone who reads that.
        out = {hi} if hi - b <= 3 * P or (eq >= 0.68 and st > 0) else set()
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
