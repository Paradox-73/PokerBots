"""No solver veto when the real bet is much cheaper than the bet the solver answered.

The solver's tree has no bet below a third of the pot after the flop, no raise of a bet below 0.75 pot, and no
preflop open below 6. map_raise replays any smaller bet as the smallest tree size, so the solver's fold / call /
raise split answers a dearer bet, and pick()'s veto (drop an option the solver plays under 10%) forced folds that
our own model rated as clear wins. A copy of the bot that bets the minimum instead of checking beat the shipped bot
by 316 chips per 1000-hand match (se 96, 60 matches). When the real price to call is under 0.8 of the price the
solver answered, the view is left out and our own model decides, as it already does off the tree. The same check
covers a bet between two tree sizes that map_raise maps up to the larger one.
usage: fix45.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        if req.get("opp_stack", 0) > 0.2 * (req["pot"] + req["to_call"]) and all(a in ("f", "c") for a in node.actions):
            return None
''', '''        if req.get("opp_stack", 0) > 0.2 * (req["pot"] + req["to_call"]) and all(a in ("f", "c") for a in node.actions):
            return None
        # A bet smaller than any tree size was replayed as the smallest one: the split answers a dearer bet.
        if req["to_call"] > 0:
            ab_call = node.bets[1 - node.player] - node.bets[node.player]
            if req["to_call"] / (req["pot"] + req["to_call"]) < 0.8 * ab_call / max(1, node.pot + ab_call):
                return None
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
