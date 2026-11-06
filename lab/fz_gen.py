"""Size-fuzzer variants of the f15 attacker: its extra bet takes a uniformly random size between the
smallest and largest legal raise, drawn once per decision, so every size the target might misread is tried.
f15 then keeps offering it whenever its own fold-rate estimate makes it pay.
usage: fz_gen.py F15_BOT OUT_DIR      writes OUT_DIR/{fz,fzf,fzb}/bot.py
  fz   turn and river, value only (>= 62% equity against the calling range)
  fzf  also on the flop
  fzb  turn and river, no equity floor (bluffs whenever the estimate says they pay)"""
import os
import sys

base = open(sys.argv[1], newline="").read()
SIZE = '        to = req["max_raise"] - NJ_LEAVE\n'
FUZZ = ('        if getattr(self, "fz", (None,))[0] is not req:  # fuzzer: one random size per decision\n'
        '            self.fz = (req, int(req["min_raise"] + self.rng.random() * (req["max_raise"] - req["min_raise"] + 1)))\n'
        '        to = min(self.fz[1], req["max_raise"])\n')
FLOP = ('        if STREET[req["street"]] < 2 or', '        if STREET[req["street"]] < 1 or')
BLUFF = ('NJ_MIN_EQ = 0.62 ', 'NJ_MIN_EQ = 0.0 ')
for name, extra in (("fz", []), ("fzf", [FLOP]), ("fzb", [BLUFF])):
    src = base
    for old, new in [(SIZE, FUZZ)] + extra:
        assert src.count(old) == 1, (name, old)
        src = src.replace(old, new)
    compile(src, name, "exec")
    os.makedirs(os.path.join(sys.argv[2], name), exist_ok=True)
    open(os.path.join(sys.argv[2], name, "bot.py"), "w", newline="").write(src)
    print(name, "written")
