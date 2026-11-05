"""Search for the bot that beats ours the most: an exploitability estimate that does
not depend on guessing the field.

    python scripts/best_response.py out.jsonl --rounds 40 --matches 10 --jobs 4

A hunter is a set of style numbers.  Random styles are tried first, then small changes
to the best one so far.  Every style is scored on the same deals, and the winner is
measured again on deals the search never saw, because the best of many noisy scores
is flattered by luck.
"""

import argparse
import json
import math
import os
import random
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pokerbots.field as field  # noqa: E402
from pokerbots.bots.common import preflop_percentile  # noqa: E402
from pokerbots.bots.simple import bet_to  # noqa: E402
from pokerbots.core.types import Action, CHECK, RAISE  # noqa: E402
from pokerbots.engine.match import play_match  # noqa: E402

RANGES = {"open_pct": (0.0, 0.9), "shove_pct": (0.3, 1.01), "raise_at": (0.5, 0.95),
          "size": (0.25, 2.0), "call_edge": (-0.1, 0.25), "bluff": (0.0, 0.4),
          "big_bet": (0.3, 2.0), "big_bet_eq": (0.5, 0.95)}


class Hunter(field.SimpleEquity):
    """Opens and reshoves by hand rank, bets by equity, and folds to big bets unless strong."""
    name = "hunter"
    style = {"open_pct": 0.5, "shove_pct": 1.01, "raise_at": 0.7, "size": 0.75, "call_edge": 0.0,
             "bluff": 0.0, "big_bet": 2.0, "big_bet_eq": 0.5}

    def act(self, view):
        s = self.style
        legal = view.legal
        if view.street == 0:
            pct = preflop_percentile(view.hole)
            if RAISE in legal and view.to_call > 1 and pct >= s["shove_pct"]:
                return Action.raise_to(view.max_raise)
            if RAISE in legal and view.to_call <= 1 and pct >= s["open_pct"]:
                return Action.raise_to(bet_to(view, s["size"]))
        eq = self.strength(view)
        price = view.to_call / max(1, view.pot + view.to_call)
        big = view.to_call >= s["big_bet"] * max(1, view.pot - view.to_call)
        if big and eq < s["big_bet_eq"]:
            return Action.fold()
        if RAISE in legal and (eq >= s["raise_at"] or self.rng.random() < s["bluff"]):
            return Action.raise_to(bet_to(view, s["size"]))
        if view.to_call == 0:
            return Action.check() if CHECK in legal else Action.call()
        return Action.call() if eq >= price + s["call_edge"] else Action.fold()


field.EXTRA[Hunter.name] = Hunter


def evaluate(task):
    style, seed, deals = task
    Hunter.style = style
    res = play_match("inproc:hunter", "inproc:range", deals=deals, seed=seed)
    return res.match_points[0], res.chips[0] / max(1, res.hands_played), res.forfeit


def score(pool, style, seeds, deals):
    rows = pool.map(evaluate, [(style, s, deals) for s in seeds], chunksize=1)
    n = len(rows)
    mean = sum(r[1] for r in rows) / n
    sd = math.sqrt(sum((r[1] - mean) ** 2 for r in rows) / max(1, n - 1))
    return sum(r[0] for r in rows) / n, mean, 1.96 * sd / math.sqrt(n)


def random_style(rng):
    return {k: rng.uniform(lo, hi) for k, (lo, hi) in RANGES.items()}


def nudge(style, rng):
    out = dict(style)
    for k in rng.sample(sorted(RANGES), 3):
        lo, hi = RANGES[k]
        out[k] = min(hi, max(lo, out[k] + rng.gauss(0, 0.15 * (hi - lo))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--rounds", type=int, default=40)
    ap.add_argument("--matches", type=int, default=10)
    ap.add_argument("--confirm", type=int, default=40)
    ap.add_argument("--deals", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    rng = random.Random(1)
    seeds = list(range(60000, 60000 + args.matches))
    best, best_score = None, None
    with Pool(args.jobs) as pool, open(args.out, "a", encoding="utf-8") as log:
        for i in range(args.rounds):
            style = random_style(rng) if i < args.rounds // 2 or best is None else nudge(best, rng)
            points, chips, half = score(pool, style, seeds, args.deals)
            log.write(json.dumps({"round": i, "points": points, "chips": chips, "style": style}) + "\n")
            log.flush()
            if best_score is None or (points, chips) > best_score:
                best, best_score = style, (points, chips)
        fresh = list(range(70000, 70000 + args.confirm))
        points, chips, half = score(pool, best, fresh, args.deals)
    result = {"best": best, "search_points": best_score[0], "search_chips": best_score[1],
              "fresh_matches": args.confirm, "fresh_point_rate": points,
              "fresh_chips_per_hand": chips, "fresh_half_interval": half}
    with open(args.out, "a", encoding="utf-8") as log:
        log.write(json.dumps({"result": result}) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
