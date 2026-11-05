"""Matches in the new two-leg format with the organisers' engine (kit2/engine.py), many in parallel.
usage: legrun.py OUT.jsonl JOBS STAGE SEEDS HERO_NAME=HERO_BOT OPP_NAME=OPP_BOT...
  SEEDS like 1-16. Appends one JSON row per match: a, b, stage, seed, chips (A's net over both
  legs), time (A's seconds over both legs), notices, forfeit (engine's forfeit line or None)."""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys

H = os.path.expanduser("~/synergy_pokerbots")
PY = H + "/.venv/bin/python"
ENGINE = H + "/kit2/engine.py"
out, jobs, stage = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
lo, hi = map(int, sys.argv[4].split("-"))
hero_name, hero = sys.argv[5].split("=", 1)
opps = [a.split("=", 1) for a in sys.argv[6:]]
LINE_A = re.compile(r"^\s+A\s+\S+\s+net\s+([+-]?\d+)\s+time used\s+([\d.]+) s.*notices\s+(\d+)", re.M)


def play(opp_name, opp, seed):
    p = subprocess.run([PY, "-I", ENGINE, hero, opp, "--stage", str(stage), "--seed", str(seed),
                        "--log-dir", "", "--python", PY], capture_output=True, text=True, timeout=1200)
    m = LINE_A.search(p.stdout)
    fo = re.search(r"^.*[Ff]orfeit.*$", p.stdout, re.M)
    row = {"a": hero_name, "b": opp_name, "stage": stage, "seed": seed,
           "chips": int(m.group(1)) if m else None, "time": float(m.group(2)) if m else None,
           "notices": int(m.group(3)) if m else None, "forfeit": fo.group(0).strip() if fo else None}
    if m is None:
        row["error"] = (p.stdout[-300:] + p.stderr[-300:]).strip()
    return row


with cf.ThreadPoolExecutor(jobs) as ex, open(out, "a") as f:
    futs = [ex.submit(play, n, o, s) for s in range(lo, hi + 1) for n, o in opps]
    for fu in cf.as_completed(futs):
        f.write(json.dumps(fu.result()) + "\n")
        f.flush()
print("LEGRUNDONE", out)
