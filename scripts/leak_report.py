"""Show where a bot's chips go against one opponent, and its real edge per hand.

    python scripts/leak_report.py rival:path/to/folder --matches 12 --opp-bank 400

Only hands before either side reached the lock line count (scripts/lock_race.py): after
that one side folds on purpose, so those chips say nothing about skill.  Hands are grouped
by ending and street and by the last aggressor.  A forfeited match is left out.
"""

import argparse
import collections
import math
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pokerbots.field  # noqa: E402,F401
from pokerbots.bots import EXTRA  # noqa: E402
from pokerbots.bots.range_bot import RangeBot  # noqa: E402
from pokerbots.core import rules  # noqa: E402
from pokerbots.core.types import FOLD, RAISE  # noqa: E402
from pokerbots.engine.match import play_match  # noqa: E402
from scripts.compare import sandboxed  # noqa: E402
from scripts.lock_race import first_cross  # noqa: E402


class Logged(RangeBot):
    name = "logged"
    last = None

    def __init__(self, seed=None):
        super().__init__(seed)
        self.rows = []
        Logged.last = self

    def on_hand_end(self, view, my_delta):
        super().on_hand_end(view, my_delta)
        acts = [e for e in view.history if e.kind == "act"]
        raises = [e for e in acts if e.action == RAISE]
        aggressor = "none" if not raises else "us" if raises[-1].seat == view.my_seat else "them"
        end = acts[-1] if acts else None
        if end is not None and end.action == FOLD:
            who = "we fold" if end.seat == view.my_seat else "they fold"
            street = rules.STREET_NAMES[end.street]
        else:
            who = "showdown won" if my_delta > 0 else "showdown lost" if my_delta < 0 else "split"
            street = "-"
        self.rows.append(((who, street, aggressor), my_delta,
                          "button" if view.is_button else "big blind"))


EXTRA[Logged.name] = Logged


def one(task):
    opp, seed, deals, bank = task
    spec = sandboxed(opp) or "inproc:" + opp
    res = play_match("inproc:logged", spec, deals=deals, seed=seed, opp_time_bank=bank)
    stop = first_cross(res.path)[1]
    return res.forfeit, Logged.last.rows[:stop]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("opponent")
    ap.add_argument("--matches", type=int, default=12)
    ap.add_argument("--deals", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=96000)
    ap.add_argument("--opp-bank", type=float, default=None)
    args = ap.parse_args()
    tasks = [(args.opponent, args.seed + i, args.deals, args.opp_bank) for i in range(args.matches)]
    with Pool(args.jobs) as pool:
        results = pool.map(one, tasks, chunksize=1)
    total = collections.defaultdict(lambda: [0, 0])
    by_seat = collections.defaultdict(lambda: [0, 0])
    rates = []
    hands = 0
    for forfeit, rows in results:
        if forfeit is not None:
            continue
        hands += len(rows)
        rates.append(sum(r[1] for r in rows) / max(1, len(rows)))
        for key, delta, seat in rows:
            total[key][0] += 1
            total[key][1] += delta
            by_seat[seat][0] += 1
            by_seat[seat][1] += delta
    n = len(rates)
    mean = sum(rates) / max(1, n)
    half = 1.96 * math.sqrt(sum((x - mean) ** 2 for x in rates) / max(1, n - 1) / max(1, n))
    print("%d finished matches of %d, %d hands before any lock" % (n, len(results), hands))
    print("edge before any lock: %+.2f +- %.2f chips per hand" % (mean, half))
    for seat, (count, chips) in sorted(by_seat.items()):
        print("  %-10s %6d hands %+8d chips %+7.2f per hand" % (seat, count, chips, chips / max(1, count)))
    print("%-14s %-8s %-6s %7s %9s %8s" % ("ending", "street", "last", "hands", "chips", "per hand"))
    for key, (count, chips) in sorted(total.items(), key=lambda kv: kv[1][1]):
        print("%-14s %-8s %-6s %7d %+9d %+8.1f" % (*key, count, chips, chips / max(1, count)))


if __name__ == "__main__":
    main()
