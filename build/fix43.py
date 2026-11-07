"""Position slots. After the flop, with nobody having bet on the street, the opponent model kept one counter
(street, 0, 0) for two different decisions: the opponent opening the street out of position, and the opponent
answering our check in position. A practice bot that always checks out of position and always bets after our
check (f19) made us read its checks as weak and its bets as strong, and beat cand49 in 27 of 32 long matches.
The counter is now split by position, per street, and backed off onto the shared counter: slot 6 when we hold the
button (the opponent opens), slot 7 when the opponent answers our check.
usage: fix43.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''    K_POOL, K_SPEC = 6.0, 4.0
''', '''    K_POOL, K_SPEC, K_SLOT = 6.0, 4.0, 4.0
''')
cut('''    def _dist(self, st, lvl, sz):''', '''    def _dist(self, st, lvl, sz, slot=None):''')
cut('''            p = (spec + self.K_SPEC * p) / (spec.sum() + self.K_SPEC)
        return p
''', '''            p = (spec + self.K_SPEC * p) / (spec.sum() + self.K_SPEC)
        if slot is not None:
            c = self.counts.get((30 + st, lvl, slot))
            if c is not None:
                p = (c + self.K_SLOT * p) / (c.sum() + self.K_SLOT)
        return p
''')
cut('''    def dist(self, st, lvl, sz):
        key = (st, min(lvl, 3), sz)
        p = self.cache.get(key)
        if p is None:
            p = self.cache[key] = self._dist(st, lvl, sz)
        return p

    def add(self, st, lvl, sz, action):
        lvl = min(lvl, 3)
        for key in ((1 if st else 0, lvl, sz), (10 + st, lvl, sz)):
''', '''    def dist(self, st, lvl, sz, slot=None):
        key = (st, min(lvl, 3), sz, slot)
        p = self.cache.get(key)
        if p is None:
            p = self.cache[key] = self._dist(st, lvl, sz, slot)
        return p

    def add(self, st, lvl, sz, action, slot=None):
        lvl = min(lvl, 3)
        keys = [(1 if st else 0, lvl, sz), (10 + st, lvl, sz)]
        if slot is not None:
            keys.append((30 + st, lvl, slot))
        for key in keys:
''')
cut('''        lvl, sz = h.raises, h.sz
        p = self.opp.dist(st, lvl, sz)
''', '''        lvl, sz = h.raises, h.sz
        slot = (6 if h.button else 7) if lvl == 0 and st > 0 else None  # opens, or answers our check
        p = self.opp.dist(st, lvl, sz, slot)
''')
cut('''        self.opp.add(st, lvl, sz, a)
''', '''        self.opp.add(st, lvl, sz, a, slot)
''')
cut('''        p = self.opp.dist(st, h.raises, h.sz)
''', '''        p = self.opp.dist(st, h.raises, h.sz, None if h.raises else 7)  # out of position: it answers our check
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
