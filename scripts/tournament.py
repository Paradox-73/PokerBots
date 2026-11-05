"""Swiss tournament between local bots, mirroring the official Stage 1 format.

    python scripts/tournament.py --bots random call tag equity --rounds 3 --deals 200
    python scripts/tournament.py --inproc ...        # faster, no subprocesses

Pairing each round: sort by (match points, capped chips/hand), pair the top
unpaired bot with the highest-ranked opponent it has not met yet; an odd bot
out gets a bye (1 match point, 0 chips).  Ranking: match points, then capped
chips per hand (the official tie-break).
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pokerbots.bots import bot_names  # noqa: E402
import pokerbots.field  # noqa: E402,F401
from pokerbots.engine.match import play_match  # noqa: E402


class Entry:
    def __init__(self, name):
        self.name = name
        self.mp = 0.0
        self.capped = 0
        self.chips = 0
        self.hands = 0
        self.opponents = set()
        self.forfeits = 0
        self.time_max = 0.0

    @property
    def cph(self):
        return self.capped / max(1, self.hands)

    def key(self):
        return (-self.mp, -self.cph, self.name)


def swiss_pairs(entries):
    order = sorted(entries, key=Entry.key)
    unpaired = list(order)
    pairs, bye = [], None
    if len(unpaired) % 2:
        # lowest-ranked bot that has not had a bye yet gets it
        for e in reversed(unpaired):
            if "BYE" not in e.opponents:
                bye = e
                break
        bye = bye or unpaired[-1]
        unpaired.remove(bye)
    while unpaired:
        a = unpaired.pop(0)
        partner = next((b for b in unpaired if b.name not in a.opponents), unpaired[0])
        unpaired.remove(partner)
        pairs.append((a, partner))
    return pairs, bye


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", nargs="+", default=bot_names())
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--deals", type=int, default=200, help="duplicate deals per pairing")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--inproc", action="store_true", help="run bots in-process")
    ap.add_argument("--jobs", type=int, default=1, help="matches run in parallel")
    args = ap.parse_args()

    entries = [Entry(b) for b in args.bots]
    spec = (lambda n: "inproc:" + n) if args.inproc else (lambda n: n)
    t0 = time.time()
    for rnd in range(1, args.rounds + 1):
        pairs, bye = swiss_pairs(entries)
        print("\n=== Round %d ===" % rnd)
        if bye:
            bye.mp += 1.0
            bye.opponents.add("BYE")
            print("%s gets a bye" % bye.name)

        def run(idx_pair):
            idx, (a, b) = idx_pair
            seed = args.seed * 1000 + rnd * 50 + idx
            return play_match(spec(a.name), spec(b.name), deals=args.deals, seed=seed,
                              names=[a.name, b.name])

        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            results = list(ex.map(run, enumerate(pairs)))
        for (a, b), res in zip(pairs, results):
            mp = res.match_points
            for i, e in enumerate((a, b)):
                e.mp += mp[i]
                e.capped += res.capped(i)
                e.chips += res.chips[i]
                e.hands += res.hands_played
                e.time_max = max(e.time_max, res.time_used[i])
                e.opponents.add((b, a)[i].name)
                if res.forfeit == i:
                    e.forfeits += 1
            print(res.summary())
            print("-")

    print("\n=== Final standings (%d rounds, %d duplicate deals/pairing, %.0fs) ==="
          % (args.rounds, args.deals, time.time() - t0))
    print("%-4s %-10s %5s %12s %12s %9s %8s" % ("#", "bot", "MP", "capped c/h", "chips c/h",
                                               "max bank", "forfeit"))
    for i, e in enumerate(sorted(entries, key=Entry.key), 1):
        print("%-4d %-10s %5.1f %+12.2f %+12.2f %8.2fs %8d"
              % (i, e.name, e.mp, e.cph, e.chips / max(1, e.hands), e.time_max, e.forfeits))


if __name__ == "__main__":
    main()
