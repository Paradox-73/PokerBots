"""Sleeps 0.3 s per decision (exhausts a small time bank)."""
import json
import sys
import time

for line in iter(sys.stdin.readline, ""):
    msg = json.loads(line)
    if msg["type"] == "action_request":
        time.sleep(0.3)
        act = "call" if "call" in msg["legal_actions"] else "check"
        print(json.dumps({"type": "action", "action": act}), flush=True)
    elif msg["type"] == "discard_request":
        print(json.dumps({"type": "discard", "card": msg["hole_cards"][0]}), flush=True)
