"""Rebuild submission/bot.py and the upload zip from the committed inputs and check both md5 sums.
Inputs: build/ev_bot.py (the EV bot) and solver/bot/ (abstraction.py, strategy.py with the trained table, bot.py).
Text edits only, no training or matches; a few seconds on one core.
usage: python build/rebuild_all.py [WORK_DIR, default build/out]"""
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, "build")
WORK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(B, "out")
BOT_MD5 = "f0ddf15aa0d1b9651e5e9f117ca60dc6"  # submission/bot.py as uploaded
ZIP_MD5 = "8e895671d6bb4d12ad5df8d4d44fed1a"  # dist/submission.zip as uploaded
FLAGS = ("LEVEL0", "PRE1", "ALLIN_FREE", "E1", "R1", "W", "G8")  # options read by the fix scripts

# (script, arguments before IN OUT, environment, test build whose bot.py equals this step's output byte for byte)
STEPS = [
    ("build_veto.py", [os.path.join(B, "ev_bot.py"), os.path.join(ROOT, "solver", "bot"), "fcr", "0"], {}, "cand14"),
    ("cleanup.py", [], {}, "cand19"),
    ("fix20.py", [], {}, "cand20"),
    ("fix29.py", [], {}, "cand29"),
    ("fix30.py", [], {}, "cand30"),
    ("fix31.py", [], {}, ""),
    ("fix32.py", [], {"E1": "1"}, "cand36"),
    ("fix34.py", [], {"W": "1"}, ""),
    ("fix33.py", [], {}, "cand41"),
    ("fix38.py", [], {}, "cand49"),
    ("fix40.py", [], {}, "cand50"),
    ("fix43.py", [], {}, "cand55"),
    ("fix44.py", [], {}, ""),
    ("fix45.py", [], {}, "cand72"),
    ("fix49.py", [], {}, ""),
    ("fix53.py", [], {}, "cand83"),
]


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


os.makedirs(WORK, exist_ok=True)
env = {k: v for k, v in os.environ.items() if k not in FLAGS}  # only the flags listed above apply
cur = None
for i, (script, pre, flags, cand) in enumerate(STEPS):
    out = os.path.join(WORK, "b%02d_%s" % (i, script))
    args = [sys.executable, os.path.join(B, script)] + pre + ([cur] if cur else [])
    if script == "build_veto.py":
        args += [out, "0.1"]  # OUT then VETO_P; BLEND, LOCK_MIN and RUNOUT_CAP stay at their defaults
    else:
        args += [out]
    subprocess.run(args, check=True, env=dict(env, **flags), stdout=subprocess.DEVNULL)
    cur = out
    print("%-14s %-8s %s %s" % (script, " ".join("%s=%s" % kv for kv in flags.items()), md5(out), cand))

shutil.copyfile(cur, os.path.join(WORK, "bot.py"))
zip_path = os.path.join(WORK, "submission.zip")
subprocess.run([sys.executable, os.path.join(B, "mkzip.py"), cur, zip_path], check=True, stdout=subprocess.DEVNULL)
bot_ok, zip_ok = md5(cur) == BOT_MD5, md5(zip_path) == ZIP_MD5
print("bot.py", md5(cur), "OK" if bot_ok else "DIFFERS from %s" % BOT_MD5)
print("zip   ", md5(zip_path), "OK" if zip_ok else "DIFFERS from %s" % ZIP_MD5)
print("same bytes as submission/bot.py:", open(cur, "rb").read() == open(os.path.join(ROOT, "submission", "bot.py"), "rb").read())
sys.exit(0 if bot_ok and zip_ok else 1)
