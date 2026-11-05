"""Measure a bot against opponents over duplicate deals, with the noise.

    python scripts/compare.py equity --against tag nit base.py --matches 20 --jobs 4

Each match is 200 duplicate deals with its own seed, and the same seeds are used
for every run, so two versions meet the same cards. A `name.py` opponent is run
as a script, which is how a saved older version is tested; `rival:folder` runs
someone else's bot in the Docker sandbox. Results: match wins,
mean chips per hand, and the 95% interval of that mean across matches.
"""

import argparse
import math
import os
import sys
import time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pokerbots.field  # noqa: E402,F401
from pokerbots.engine.match import play_match  # noqa: E402


def sandboxed(opp):
    """`rival:path/to/folder` runs that folder's bot.py in the no-network Docker sandbox."""
    if not opp.startswith("rival:"):
        return None
    folder = os.path.abspath(opp[len("rival:"):]).replace("\\", "/")
    if os.environ.get("POKER_NO_DOCKER"):  # trusted frozen rivals on a machine without Docker access
        return "cmd:%s -I -u %s/bot.py" % (sys.executable, folder)
    return ('cmd:docker run -i --rm --network none --read-only --cpus 1 --memory 1g '
            '--memory-swap 1g -v "%s:/bot:ro" -w /bot pokerbots-sandbox:3.11 python -u bot.py'
            % folder)


def one_match(task):
    hero, opp, seed, deals, opp_bank, bank = task
    spec = sandboxed(opp) or (opp if opp.endswith(".py") else "inproc:" + opp)
    res = play_match("inproc:" + hero, spec, deals=deals, seed=seed, time_bank=bank,
                     opp_time_bank=opp_bank)
    return opp, res.match_points[0], res.chips[0] / max(1, res.hands_played), \
        res.time_used[0], res.forfeit


def label(opp):
    return os.path.basename(opp.rstrip("/"))


def summarise(opp, all_rows):
    """Strength figures use only matches both bots finished: a forfeit is not a result."""
    rows = [r for r in all_rows if r[4] is None]
    hero_lost = sum(r[4] == 0 for r in all_rows)
    opp_lost = sum(r[4] == 1 for r in all_rows)
    tail = "  bank max %5.1fs  FORFEITS hero %d opp %d" % (max(r[3] for r in all_rows),
                                                           hero_lost, opp_lost)
    n = len(rows)
    if not n:
        return "%-22s no finished matches%s" % (label(opp), tail)
    points = sum(r[1] for r in rows)
    rates = [r[2] for r in rows]
    mean = sum(rates) / n
    var = sum((x - mean) ** 2 for x in rates) / max(1, n - 1)
    half = 1.96 * math.sqrt(var / n)
    return ("%-22s finished %3d  points %5.1f  chips/hand %+7.2f +- %5.2f%s"
            % (label(opp), n, points, mean, half, tail))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hero")
    ap.add_argument("--against", nargs="+", required=True)
    ap.add_argument("--matches", type=int, default=20)
    ap.add_argument("--deals", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=5000)
    ap.add_argument("--bank", type=float, default=None, help="time bank; Stage 2 is 150")
    ap.add_argument("--opp-bank", type=float, default=None, help="opponent's own time bank")
    args = ap.parse_args()
    tasks = [(args.hero, opp, args.seed + i, args.deals, args.opp_bank, args.bank)
             for opp in args.against for i in range(args.matches)]
    start = time.time()
    with Pool(args.jobs) as pool:
        rows = pool.map(one_match, tasks, chunksize=1)
    for opp in args.against:
        print(summarise(opp, [r for r in rows if r[0] == opp]), flush=True)
    print("%d hands in %.0f s" % (len(tasks) * args.deals * 2, time.time() - start))


if __name__ == "__main__":
    main()
