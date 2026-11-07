"""Size slots. A 0.66-pot bet and a pot-sized bet fall in the same size bucket (0.6 to 1.2 of the pot), so the
opponent model gave both the same fold rate. Real opponents fold clearly more to the bigger one (flop first bets:
f7 0.42 vs 0.55, cand20 0.44 vs 0.57, f17 0.49 vs 0.77, from 144 logged matches), so bluffs always took the cheaper
size and value bets the dearer one, and an opponent could read our hand from the size. Inside that bucket the
model now keeps one more counter per size (slot 4 up to 0.8 of the pot, slot 5 above), backed off onto the shared
counter, so each size learns its own answer rate. FROM_STREET 1 = flop onward; 0 = preflop too.
usage: fix41.py IN_BOT OUT_BOT [FROM_STREET]"""
import sys

src = open(sys.argv[1], newline="").read()
FROM = int(sys.argv[3]) if len(sys.argv) > 3 else 1


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''def sz_bucket(ratio):
    return 0 if ratio <= 0.6 else 1 if ratio <= 1.2 else 2 if ratio <= 3.0 else 3
''', '''def sz_bucket(ratio):
    return 0 if ratio <= 0.6 else 1 if ratio <= 1.2 else 2 if ratio <= 3.0 else 3


SLOT_FROM = %d  # first street with size slots


def sz_slot(ratio):
    """Finer key inside bucket 1: opponents fold more to a pot-sized bet than to a 0.66-pot one."""
    return None if not 0.6 < ratio <= 1.2 else 4 if ratio <= 0.8 else 5
''' % FROM)
cut('''    K_POOL, K_SPEC = 6.0, 4.0
''', '''    K_POOL, K_SPEC, K_SLOT = 6.0, 4.0, 4.0
''')
cut('''    def _dist(self, st, lvl, sz):''', '''    def _dist(self, st, lvl, sz, slot=None):''')
cut('''            p = (spec + self.K_SPEC * p) / (spec.sum() + self.K_SPEC)
        return p
''', '''            p = (spec + self.K_SPEC * p) / (spec.sum() + self.K_SPEC)
        if slot is not None and st >= SLOT_FROM:
            c = self.counts.get((20 + stc, lvl, slot))
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
        if slot is not None and st >= SLOT_FROM:
            keys.append((21 if st else 20, lvl, slot))
        for key in keys:
''')
cut('''        self.raises = 0  # voluntary raises on this street
        self.sz = 0
''', '''        self.raises = 0  # voluntary raises on this street
        self.sz = 0
        self.slot = None
''')
cut('''        self.raises = 0
        self.sz = 0
''', '''        self.raises = 0
        self.sz = 0
        self.slot = None
''')
cut('''            self.sz = sz_bucket(ratio)
''', '''            self.sz = sz_bucket(ratio)
            self.slot = sz_slot(ratio)
''')
cut('''        lvl, sz = h.raises, h.sz
        p = self.opp.dist(st, lvl, sz)
''', '''        lvl, sz, slot = h.raises, h.sz, h.slot
        p = self.opp.dist(st, lvl, sz, slot)
''')
cut('''        self.opp.add(st, lvl, sz, a)
''', '''        self.opp.add(st, lvl, sz, a, slot)
''')
cut('''        p = self.opp.dist(st, h.raises, h.sz)
''', '''        p = self.opp.dist(st, h.raises, h.sz, h.slot)
''')
cut('''        p = self.opp.dist(st, h.raises + 1, sz_bucket(ratio))
''', '''        p = self.opp.dist(st, h.raises + 1, sz_bucket(ratio), sz_slot(ratio))
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written, SLOT_FROM", FROM)
