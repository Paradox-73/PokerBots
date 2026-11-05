"""Write test opponents that open every postflop bet at the minimum: each relays the engine's messages
to a base bot and rewrites its first bet of a street (nothing to call) to min_raise. The solver tree's
smallest bet is a third of the pot, so such bets are mapped onto a bet several times their price.
usage: minbet_gen.py OUT_DIR NAME=BASE_BOT.py ..."""
import os
import sys

TEMPLATE = r'''import json, os, subprocess, sys
BASE = %r
child = subprocess.Popen([sys.executable, BASE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         cwd=os.path.dirname(BASE), text=True, bufsize=1)
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
    if kind == "action_request" and msg["street"] != "preflop" and msg["to_call"] == 0:
        try:
            if json.loads(reply).get("action") == "raise":
                reply = json.dumps({"type": "action", "action": "raise", "amount": msg["min_raise"]}) + "\n"
        except ValueError:
            pass
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
