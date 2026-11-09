"""The all-in is always offered, and expected value decides it like any other size.

sizes() offered a shove far above the pot only with equity of at least 0.68, so such a shove was always a strong
hand (91% of 400 logged all-ins had equity 0.70 or more). An opponent that calls an all-in only with the very top of
its range folds everything else and gives up just the pot: a copy of a control bot with that one rule took 822 chips
per long match more from cand55 than the control did (se 124, 60 matches). Without the gate, ev_raise prices the
shove with the opponent's own answers to our shoves: size bucket 3 (over three pots) holds only shoves, so against
an opponent that folds them the strong hands take a smaller size it calls, and a weak hand can take the pot; against
one that calls them the strong hands keep shoving and weak hands do not.
Rejected (cand75): head to head against a plain copy of cand72, paired with cand72's own result on the same 120
long-match deal sets, -28.0 match points (se 7.6); with build/fix49.py added (cand77), -23.0 (se 7.4)
(results/allin_round_8nov.txt).
usage: fix48.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        # A shove far above the pot needs a real hand: fold-rate estimates there are thin,
        # and the callers it meets are the ones that beat a medium hand.
        out = {hi} if hi - b <= 3 * P or eq >= 0.68 else set()
''', '''        # The shove is always an option: ev_raise prices it with the opponent's answers to our shoves.
        out = {hi}
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
