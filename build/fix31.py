"""a code review fixes, applied on top of fix30.py builds.
B (always): the call EV passed `behind - tc` to value(), but `behind` = min(my_stack, opp_stack) is already the
   stack left after calling (facing a bet, opp_stack = my_stack - to_call), so the call was subtracted twice and
   future streets were dropped when that went to 0 or below. 51 of 1422 recorded decisions facing a bet changed.
A (ALLIN_FREE=1): facing an all-in the solver check stays on, and it vetoed calls the bot's own read of this
   opponent's shoving range rated +EV (16 of 23 replayed spots, incl. a river straight and an overpair). With A
   there is no solver check when the opponent has no chips left. Risky: the check also stops calls the bot
   overrates, so it ships only if the general field says so.
usage: [ALLIN_FREE=1] fix31.py IN_BOT OUT_BOT"""
import os
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''            ev = self.value(eq, P + tc, behind - tc, st, ip) - tc''',
    '''            ev = self.value(eq, P + tc, behind, st, ip) - tc  # behind is already the stack after calling''')
if os.environ.get("ALLIN_FREE") == "1":
    cut('''    if solver is None or solver.hand is None:
        return None
    try:''', '''    if solver is None or solver.hand is None:
        return None
    if req.get("to_call", 0) > 0 and req.get("opp_stack", 1) == 0:  # facing an all-in: our own read of its range
        return None
    try:''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
