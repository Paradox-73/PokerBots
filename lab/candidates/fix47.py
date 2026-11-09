"""No all-in while it is more than three pots, on any street: such a shove came only from strong hands.

sizes() offered the all-in when it is at most three pots, or at any size when equity is at least 0.68. So every
shove far above the pot was a strong hand (91% of 400 logged all-ins had equity 0.70 or more), and an opponent that
calls an all-in only with the very top of its range folds everything else and gives up just the pot. A copy of a
control bot with that one rule took 822 chips per long match more from cand55 than the control did (se 124, 60
matches). Now strong hands bet up to 1.5 pots like any other hand, and the all-in is offered only once it is at most
three pots, where every hand can choose it by expected value.
Not shipped (cand74). Head to head against a plain copy of cand72, paired with cand72's own result on the same 120
long-match deal sets: +3.0 match points (se 7.0). With build/fix49.py added (cand76) it won 75 of 120 matches against
a copy of cand72 that calls an all-in with equity 0.30 or more, where cand72 won all 120: the big all-in is what
beats loose callers (results/allin_round_8nov.txt).
usage: fix47.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        # A shove far above the pot needs a real hand: fold-rate estimates there are thin,
        # and the callers it meets are the ones that beat a medium hand.
        out = {hi} if hi - b <= 3 * P or eq >= 0.68 else set()
''', '''        # No shove far above the pot: only strong hands made it, so it told the opponent what we held.
        out = {hi} if hi - b <= 3 * P else set()
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
