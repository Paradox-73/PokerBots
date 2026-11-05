"""Write test opponents that re-raise small: each relays the engine's messages to a base bot and
rewrites its re-raises to the minimum, and at the deepest raise levels turns half its calls into
minimum re-raises. cand19 replays such raises as all-ins in its solver check (the leak cand20
fixes), so a paired cand19/cand20 test against these shows whether that leak costs chips.
usage: minrr_gen.py OUT_DIR NAME=BASE_BOT.py ..."""
import os
import sys

TEMPLATE = r'''import json, os, random, subprocess, sys
BASE = %r
child = subprocess.Popen([sys.executable, BASE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         cwd=os.path.dirname(BASE), text=True, bufsize=1)
rng = random.Random(7)


def rewrite(req, reply):
    try:
        act = json.loads(reply).get("action")
    except ValueError:
        return reply
    if "raise" not in req["legal_actions"] or req["to_call"] <= 0:
        return reply
    pre = req["street"] == "preflop"
    if pre and req["raises_left"] == 3:  # the small blind's first move is an open, not a re-raise
        return reply
    deep = req["raises_left"] <= (1 if pre else 2)
    if act == "raise" or (deep and act == "call" and rng.random() < 0.5):
        return json.dumps({"type": "action", "action": "raise", "amount": req["min_raise"]}) + "\n"
    return reply


for line in sys.stdin:
    child.stdin.write(line)
    child.stdin.flush()
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    kind = msg.get("type")
    if kind not in ("action_request", "discard_request"):
        continue
    reply = child.stdout.readline()
    if kind == "action_request":
        reply = rewrite(msg, reply)
    sys.stdout.write(reply)
    sys.stdout.flush()
child.stdin.close()
'''

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
for arg in sys.argv[2:]:
    name, base = arg.split("=", 1)
    path = os.path.join(out, name + ".py")
    src = TEMPLATE % os.path.abspath(base)
    compile(src, path, "exec")
    open(path, "w").write(src)
    print(path)
