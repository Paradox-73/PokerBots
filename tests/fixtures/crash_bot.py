"""Crashes on its first decision."""
import sys

for line in iter(sys.stdin.readline, ""):
    if '"action_request"' in line:
        raise SystemExit(3)
