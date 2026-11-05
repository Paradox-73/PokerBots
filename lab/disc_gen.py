"""Write test opponents that discard by the starter kit's rule (drop the lowest rank) instead of their
own choice: each relays the engine's messages to a base bot and replaces only its discard reply.
The engine's discard_result then tells the base bot which two cards it really kept.
usage: disc_gen.py OUT_DIR NAME=BASE_BOT.py ..."""
import os
import sys

TEMPLATE = r'''import json, os, subprocess, sys
BASE = %r
RANKS = "23456789TJQKA"
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
    if kind == "discard_request":
        worst = min(msg["hole_cards"], key=lambda c: RANKS.index(c[0]))
        reply = json.dumps({"type": "discard", "card": worst}) + "\n"
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
