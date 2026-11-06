"""Write test opponents that punish limping: each relays the engine's messages to a base bot and, as big blind
facing a small-blind limp, always raises to 4 big blinds instead of checking. Everything else is the base bot.
Tests the level-0 counter split (fix30 LEVEL0): a bot that reads "big blind raises my limp" from a counter
shared with the opponent's button opens keeps limping into it. usage: iso_gen.py OUT_DIR NAME=BASE_BOT.py ..."""
import os
import sys

TEMPLATE = r'''import json, os, random, subprocess, sys
BASE = %r
child = subprocess.Popen([sys.executable, BASE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         cwd=os.path.dirname(BASE), text=True, bufsize=1)
rng = random.Random(11)


def raise_to(req, mult):
    amt = int(max(req["min_raise"], min(req["max_raise"], round(req["opp_bet"] * mult))))
    return json.dumps({"type": "action", "action": "raise", "amount": amt}) + "\n"


def rewrite(req, reply):
    # big blind facing a limp (nothing to call, preflop, raise legal): always raise to 4 big blinds
    if req["street"] == "preflop" and req["to_call"] == 0 and "raise" in req["legal_actions"]:
        return raise_to_amt(req, 8)
    return reply


def raise_to_amt(req, amt):
    amt = int(max(req["min_raise"], min(req["max_raise"], amt)))
    return json.dumps({"type": "action", "action": "raise", "amount": amt}) + "\n"


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
