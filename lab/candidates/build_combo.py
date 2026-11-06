"""Build a combined candidate from cand29 (expects cand29/bot.py and cand20t/bot.py beside the fix scripts): F3 and B always, plus the named optional fixes, applied in a fixed order
(fix30 -> fix31 -> fix32 -> fix24b -> table); every fix script asserts its anchors, so a clash stops the build.
usage: build_combo.py OUT_BOT [F1] [F2] [A] [E1] [R1] [MAP | MAPC] [ROUND] [W] [G8] [TABLE]
  F1 level-0 counter split, F2 preflop counted once (fix30); A no solver check facing an all-in (fix31);
  E1 aggressive-range weight from the weak share, R1 re-raise over a > 1.2x pot bet only with eq >= 0.68 (fix32);
  MAP bet-size mapping fixes (fix24b), MAPC the same plus no check when nothing is to call; TABLE preflop table of cand20t, ROUND solver features rounded as in training (fix33), W window interpolated inside buckets, G8 no solver check below 0.8 of the node price (fix34)"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
out, parts = sys.argv[1], set(sys.argv[2:])
known = {"F1", "F2", "A", "E1", "R1", "MAP", "MAPC", "TABLE", "ROUND", "W", "G8"}
assert parts <= known, parts - known
assert not {"MAP", "MAPC"} <= parts
tmp = out + ".step"
cur = os.path.join(HERE, "cand29", "bot.py")


def run(args, env):
    global cur
    subprocess.run([sys.executable] + args + [cur, tmp], check=True, env=dict(os.environ, **env), stdout=subprocess.DEVNULL)
    shutil.move(tmp, out)
    cur = out


run([os.path.join(HERE, "fix30.py")], {"LEVEL0": "1" if "F1" in parts else "0", "PRE1": "1" if "F2" in parts else "0"})
run([os.path.join(HERE, "fix31.py")], {"ALLIN_FREE": "1" if "A" in parts else "0"})
if parts & {"E1", "R1"}:
    run([os.path.join(HERE, "fix32.py")], {"E1": "1" if "E1" in parts else "0", "R1": "1" if "R1" in parts else "0"})
if parts & {"MAP", "MAPC"}:
    run([os.path.join(HERE, "fix24b.py")], {"CHECK_ONLY_FACING": "1" if "MAPC" in parts else "0"})
if parts & {"W", "G8"}:
    run([os.path.join(HERE, "fix34.py")], {"W": "1" if "W" in parts else "0", "G8": "1" if "G8" in parts else "0"})
if "ROUND" in parts:
    run([os.path.join(HERE, "fix33.py")], {})
if "TABLE" in parts:
    run([os.path.join(HERE, "copy_table.py"), os.path.join(HERE, "cand20t", "bot.py")], {})
print(out, "= cand29 + F3 B", " ".join(sorted(parts)))
