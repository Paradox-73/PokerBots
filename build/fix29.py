"""Two fixes for a bet of all-in minus a few chips, found by a test opponent built to beat the bot:
1. ev_raise read the fold rate of its own re-raise from the size bucket of the extra chips alone, so a
   shove that costs the opponent 2 more chips after a 188-chip bet was given a 30% fold chance (the
   small-raise prior) and was made with ~30%-equity hands. A raise that costs the opponent under 10%
   of the final pot now has its fold rate scaled down in proportion, the rest counted as calls.
2. The solver check was off whenever a bet mapped onto the tree's all-in node while the bettor still had
   chips (meant for small re-raises read as shoves). A bet that leaves the bettor under a fifth of the
   pot behind is a shove in all but name, so the solver's answer to a shove now stands.
usage: fix29.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        f, c, r = float(p[FOLD]), float(p[PASS]), float(p[RS:].sum())
        allin = to >= req["max_raise"]''', '''        f, c, r = float(p[FOLD]), float(p[PASS]), float(p[RS:].sum())
        price = faced / max(1.0, P + add + faced)
        if price < 0.1:  # a raise that costs the opponent almost nothing to call is not folded to
            f, c = f * price / 0.1, c + f * (1 - price / 0.1)
        allin = to >= req["max_raise"]''')
cut('''        if req.get("opp_stack", 0) > 0 and all(a in ("f", "c") for a in node.actions):
            return None''', '''        # A bet that leaves the bettor under a fifth of the pot behind is a shove in all but name.
        if req.get("opp_stack", 0) > 0.2 * (req["pot"] + req["to_call"]) and all(a in ("f", "c") for a in node.actions):
            return None''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
