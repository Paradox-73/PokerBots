"""Hardening only; no decision in a valid game changes.

1. One BLAS thread. At import, numpy's OpenBLAS starts one worker thread per visible core, and each reserves
   about 40 MB of address space (VmPeak 672 MB on a 14-core host against 140 MB with one thread). Under an
   address-space cap such as 1 GB on a host with about 23 or more cores, or under a thread cap, the import fails
   and the bot dies before its first reply: a forfeit of every match. The variables must be set before numpy
   loads; the embedded solver's own setting ran too late.
2. The read loop survives any line: a byte that is not UTF-8 becomes U+FFFD, and a line json cannot parse for
   any reason (deep nesting raises RecursionError, not ValueError) is skipped.
3. The emergency replies after an exception cannot raise themselves. A request without legal_actions or with
   empty hole_cards used to end the process from inside the except block. The discard fallback now names the
   lowest-ranked card, as the engine's own correction would.
usage: fix44.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''import base64
import json
import sys
import time
import zlib

import numpy as np
''', '''import base64
import json
import os
import sys
import time
import zlib

# One vCPU: without this, numpy's BLAS starts a thread per visible core at import, each reserving address space.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np
''')
cut('''    bank = bot.time_left
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
''', '''    bank = bot.time_left
    try:  # a byte that is not UTF-8 becomes U+FFFD instead of ending the read loop
        sys.stdin.reconfigure(errors="replace")
    except Exception:
        pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:  # not JSON, or nested too deep to parse
            continue
''')
cut('''            print("error:", repr(exc), file=sys.stderr)
            if t == "action_request":
                reply = panic_action(msg)
            elif t == "discard_request":
                reply = {"type": "discard", "card": msg["hole_cards"][0]}
''', '''            print("error:", repr(exc), file=sys.stderr)
            try:
                if t == "action_request":
                    reply = panic_action(msg)
                elif t == "discard_request":
                    reply = {"type": "discard", "card": min(msg["hole_cards"], key=lambda c: RANKS.find(str(c)[:1]))}
            except Exception:  # the request itself is broken; any well-formed reply avoids a forfeit
                reply = {"type": "action", "action": "fold"} if t == "action_request" else {"type": "discard", "card": "2s"}
''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
