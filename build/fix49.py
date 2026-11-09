"""Two opponent-model counting bugs, both preflop.

1. One counter held two preflop spots: the opponent's first action as button and its big-blind option after our
   limp both read and wrote the key (street 0, level 0, size 0) with no slot. The limp EV in decide() read that key
   as "how often the big blind raises a limp", but most of its data was the opponent's own button opens, so it
   measured the opponent's open-raise rate. Each spot now has its own slot (8: big blind after our limp, 9: button
   open), backed off onto the shared key as the postflop slots are.
2. Preflop, the pooled key and the street key are the same data, so every preflop observation was applied twice
   and the prior counted for about 1.7 observations instead of 6. Preflop now uses the pooled key once.
usage: fix49.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        spec = self.counts.get((10 + st, lvl, sz))
''', '''        spec = self.counts.get((10 + st, lvl, sz)) if st else None  # preflop the pooled key is this key
''')
cut('''        slot = (6 if h.button else 7) if lvl == 0 and st > 0 else None  # opens, or answers our check
''', '''        # postflop: opens (6) or answers our check (7); preflop: big blind after our limp (8) or button open (9)
        slot = ((6 if h.button else 7) if st > 0 else (8 if h.button else 9)) if lvl == 0 else None
''')
cut('''                r = o.dist(0, 0, 0)[RS:].sum()
''', '''                r = o.dist(0, 0, 0, 8)[RS:].sum()
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
