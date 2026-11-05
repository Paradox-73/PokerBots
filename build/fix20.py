"""Three fixes from the code review, each an exact one-place edit. usage: fix20.py IN_BOT OUT_BOT

1. Solver check off when the solver's tree has the opponent all-in but the real opponent still has
   chips. The tree offers only an all-in at deep raise levels, so a small re-raise is replayed as a
   shove; the solver then folds almost everything and the check deleted every other option.
2. Discard names the card by identity, not by its position in the request's hole_cards list.
3. Preflop, the big blind's check closes the street, so its value no longer includes a bet that
   cannot come."""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        if node is None:
            return None
        street = sb.STREET[req["street"]]''', '''        if node is None:
            return None
        # A raise the tree had no size for was replayed as an all-in: the solver's split is then
        # its answer to a shove, not to this bet.
        if req.get("opp_stack", 0) > 0 and all(a in ("f", "c") for a in node.actions):
            return None
        street = sb.STREET[req["street"]]''')
cut('''        return {"type": "discard", "card": hole[2 - keep]}  # keeps[i] drops hole[2 - i]''',
    '''        drop = h.hole[2 - keep]  # keeps[i] drops hole[2 - i] of the new_hand order
        return {"type": "discard", "card": next((c for c in hole if cid(c) == drop), hole[2 - keep])}''')
cut('''        h = self.h
        if ip:
            return self.value(eq, P, behind, st, True)''', '''        h = self.h
        if ip or st == 0:  # preflop a check is the big blind's, and it ends the street
            return self.value(eq, P, behind, st, ip)''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
