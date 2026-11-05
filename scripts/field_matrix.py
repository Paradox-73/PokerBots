"""Sample match results between practice opponents, for tournament simulation.

    python scripts/field_matrix.py results.jsonl --all --matches 8        # every pair
    python scripts/field_matrix.py hero.jsonl --hero range --matches 12   # one bot vs all
    python scripts/field_matrix.py r.jsonl --hero tag mc --against rival:folder

Rows are appended as they finish and finished rows are skipped, so a stopped run
can be restarted.  Each row keeps the first bot's running chip total by hand.
"""

import argparse
import itertools
import json
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pokerbots.field  # noqa: E402,F401
from pokerbots.bots import bot_names  # noqa: E402
from pokerbots.engine.match import play_match  # noqa: E402
from scripts.compare import label, sandboxed  # noqa: E402


def field_names():
    return [n for n in bot_names() if n not in ("equity", "range", "mirror")]


def one_match(task):
    a, b, seed, deals, opp_bank, bank = task
    res = play_match(sandboxed(a) or "inproc:" + a, sandboxed(b) or "inproc:" + b, deals=deals,
                     seed=seed, time_bank=bank, opp_time_bank=opp_bank)
    return {"a": label(a), "b": label(b), "seed": seed, "deals": deals, "chips": res.chips[0],
            "hands": res.hands_played, "forfeit": res.forfeit, "time": round(res.time_used[0], 1),
            "path": res.path}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--hero", nargs="+")
    ap.add_argument("--against", nargs="+", default=None)
    ap.add_argument("--matches", type=int, default=8)
    ap.add_argument("--deals", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=30000)
    ap.add_argument("--bank", type=float, default=None, help="time bank; Stage 2 is 150")
    ap.add_argument("--opp-bank", type=float, default=None, help="opponent's own time bank")
    args = ap.parse_args()
    names = args.against or field_names()
    pairs = [(h, n) for h in args.hero for n in names] if args.hero else \
        list(itertools.combinations_with_replacement(names, 2))
    done = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            done = {(r["a"], r["b"], r["seed"]) for r in map(json.loads, f)}
    tasks = [(a, b, args.seed + i, args.deals, args.opp_bank, args.bank) for a, b in pairs
             for i in range(args.matches) if (label(a), label(b), args.seed + i) not in done]
    with Pool(args.jobs) as pool, open(args.out, "a", encoding="utf-8") as out:
        for row in pool.imap_unordered(one_match, tasks):
            out.write(json.dumps(row) + "\n")
            out.flush()
    print("wrote %d rows" % len(tasks))
    # a forfeit row is kept for the record, and elo.py, lock_eval.py and
    # simulate_tournament.py leave it out of every strength figure


if __name__ == "__main__":
    main()
