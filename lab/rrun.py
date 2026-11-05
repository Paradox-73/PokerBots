"""Round robin in the two-leg format with the organisers' engine (kit2/engine.py): every pair once per seed.
usage: rrun.py OUT.jsonl JOBS STAGE SEEDS NAME=BOT...   (rows as legrun.py: a = first-named bot of the pair)
Pairs already in OUT (same a, b, stage, seed with a result) are skipped, so a stopped run can restart."""
import concurrent.futures as cf
import itertools
import json
import os
import re
import subprocess
import sys

H = os.path.expanduser("~/synergy_pokerbots")
PY = H + "/.venv/bin/python"
ENGINE = H + "/kit2/engine.py"
LINE_A = re.compile(r"^\s+A\s+\S+\s+net\s+([+-]?\d+)\s+time used\s+([\d.]+) s.*notices\s+(\d+)", re.M)
out, jobs, stage = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
lo, hi = map(int, sys.argv[4].split("-"))
bots = [a.split("=", 1) for a in sys.argv[5:]]
done = set()
if os.path.exists(out):
    for r in map(json.loads, open(out)):
        if r.get("chips") is not None:
            done.add((r["a"], r["b"], r["stage"], r["seed"]))


def play(a, b, seed):  # as legrun.play, with both bots as arguments
    p = subprocess.run([PY, "-I", ENGINE, a[1], b[1], "--stage", str(stage), "--seed", str(seed),
                        "--log-dir", "", "--python", PY], capture_output=True, text=True, timeout=1200)
    m = LINE_A.search(p.stdout)
    fo = re.search(r"^.*[Ff]orfeit.*$", p.stdout, re.M)
    row = {"a": a[0], "b": b[0], "stage": stage, "seed": seed,
           "chips": int(m.group(1)) if m else None, "time": float(m.group(2)) if m else None,
           "notices": int(m.group(3)) if m else None, "forfeit": fo.group(0).strip() if fo else None}
    if m is None:
        row["error"] = (p.stdout[-300:] + p.stderr[-300:]).strip()
    return row


tasks = [(a, b, s) for s in range(lo, hi + 1) for a, b in itertools.combinations(bots, 2)
         if (a[0], b[0], stage, s) not in done]
with cf.ThreadPoolExecutor(jobs) as ex, open(out, "a") as f:
    for fu in cf.as_completed([ex.submit(play, *t) for t in tasks]):
        f.write(json.dumps(fu.result()) + "\n")
        f.flush()
print("RRUNDONE", out, len(tasks))
