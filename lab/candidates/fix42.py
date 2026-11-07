"""Position slots. Postflop, with nobody having bet on the street, the opponent model kept one counter
(street, 0, 0) for two different decisions: the opponent opening the street out of position, and the opponent
answering our check in position. A bot that always checks out of position and always bets after our check
(f19) made us read its checks as weak and its bets as strong: it beat cand49 in 7 of 8 long and 8 of 8 short
matches. The counter is now split by position, per street, backed off onto the shared one (slot 6: we hold the
button, so the opponent opens; slot 7: the opponent answers our check). Applies to a fix41 build; SIZE 0 turns
fix41's size slots off, leaving only the position slots.
usage: fix42.py IN_BOT OUT_BOT [SIZE]"""
import sys

src = open(sys.argv[1], newline="").read()
SIZE = int(sys.argv[3]) if len(sys.argv) > 3 else 1


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


if not SIZE:
    cut('''    return None if not 0.6 < ratio <= 1.2 else 4 if ratio <= 0.8 else 5
''', '''    return None
''')
cut('''        if slot is not None and st >= SLOT_FROM:
            c = self.counts.get((20 + stc, lvl, slot))
''', '''        if slot is not None and st >= SLOT_FROM:
            c = self.counts.get(self.slot_key(st, lvl, slot))
''')
cut('''        if slot is not None and st >= SLOT_FROM:
            keys.append((21 if st else 20, lvl, slot))
''', '''        if slot is not None and st >= SLOT_FROM:
            keys.append(self.slot_key(st, lvl, slot))
''')
cut('''    def dist(self, st, lvl, sz, slot=None):''', '''    @staticmethod
    def slot_key(st, lvl, slot):
        # position slots (6, 7) are kept per street; size slots (4, 5) are pooled over the streets
        return (30 + st, lvl, slot) if slot >= 6 else (21 if st else 20, lvl, slot)

    def dist(self, st, lvl, sz, slot=None):''')
cut('''        lvl, sz, slot = h.raises, h.sz, h.slot
''', '''        lvl, sz, slot = h.raises, h.sz, h.slot
        if lvl == 0 and st > 0:
            slot = 6 if h.button else 7
''')
cut('''        p = self.opp.dist(st, h.raises, h.sz, h.slot)
''', '''        p = self.opp.dist(st, h.raises, h.sz, h.slot if h.raises else 7)  # out of position: it answers our check
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written, size slots", "on" if SIZE else "off")
