"""Mistakes that are wrong whatever the opponent holds, found in engine match logs (bot A = ours).
On the river, with both discards known, every two-card hand the opponent could hold is scored:
  river_fold_nuts    we folded a hand that beats or ties every possible opponent hand
  river_call_dead    we called a bet with a hand that loses to every possible opponent hand
  river_bet_dead_called  we bet or raised a hand that loses to every possible holding and got called
                     (a bluff can be right; counted only to see how often bluffs are called)
  turn_fold_lock     we folded on the turn a hand that wins or ties on every river against every holding
usage: audit.py BOT_PY MATCH_LOG..."""
import collections
import importlib.util
import re
import sys

import numpy as np

spec = importlib.util.spec_from_file_location("botmod", sys.argv[1])
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

LINE = re.compile(r"^L(\d) #(\d+)\s+button (\w) \| (\w): ([^|]*?)  (\w): ([^|]*?) \| board ([^|]*?) "
                  r"(?:\| discards (\w):(\S+) (\w):(\S+) )?\| (.*) \| (fold|showdown)")
ALL = np.arange(52)


def values(board):
    return B.eval_boards(np.array([board]))[0]  # value of every two-card hand on this 5-card board


def opp_pairs(dead):
    live = [c for c in range(52) if c not in dead]
    return [B.PIDX[a, b] for i, a in enumerate(live) for b in live[i + 1:]]


count = collections.Counter()
examples = collections.defaultdict(list)
for path in sys.argv[2:]:
    for raw in open(path):
        m = LINE.match(raw.rstrip("\n"))
        if not m or not m.group(9):
            continue
        g = m.groups()
        cards = {g[3]: [B.cid(c) for c in g[4].split()], g[5]: [B.cid(c) for c in g[6].split()]}
        disc = {g[8]: B.cid(g[9]), g[10]: B.cid(g[11])}
        board = [B.cid(c) for c in g[7].split()]
        if len(board) < 4:
            continue
        acts = g[12].split()
        keep = [c for c in cards["A"] if c != disc["A"]]
        ours = B.PIDX[keep[0], keep[1]]
        dead = set(cards["A"]) | {disc["B"]}
        street, tokens = None, []
        for t in acts:
            if t.endswith(":"):
                street = t[:-1]
            else:
                tokens.append((street, t))
        for i, (st, t) in enumerate(tokens):
            if t[0] != "A":
                continue
            prev = next((u for s2, u in reversed(tokens[:i]) if s2 == st and u[0] == "B"), "")
            facing = prev[1:2] == "r"
            if st == "river" and len(board) == 5:
                v = values(board)
                opp = opp_pairs(dead | set(board))
                best, worst = max(v[opp]), min(v[opp])
                if t[1] == "f" and facing and v[ours] >= best:
                    count["river_fold_nuts"] += 1
                    examples["river_fold_nuts"].append((path, g[0], g[1]))
                if t[1] == "c" and facing and v[ours] < worst:
                    count["river_call_dead"] += 1
                    examples["river_call_dead"].append((path, g[0], g[1]))
                if t[1] == "r" and v[ours] < worst and any(u[0] == "B" and u[1] == "c" for s2, u in tokens[i + 1:] if s2 == "river"):
                    count["river_bet_dead_called"] += 1
                count["river_decisions"] += 1
            if st == "turn" and t[1] == "f" and facing:
                lock = True
                for r in range(52):
                    if r in dead or r in board[:4]:
                        continue
                    bd = board[:4] + [r]
                    v = values(bd)
                    opp = opp_pairs(dead | set(bd))
                    if v[ours] < max(v[opp]):
                        lock = False
                        break
                if lock:
                    count["turn_fold_lock"] += 1
                    examples["turn_fold_lock"].append((path, g[0], g[1]))
                count["turn_folds"] += 1
print(dict(count))
for k, ex in examples.items():
    print(k, ex[:5])
