"""Play one duplicate match between two bots and print the summary.

    python scripts/run_match.py equity tag --deals 200 --seed 1
    python scripts/run_match.py inproc:equity inproc:call --deals 50
    python scripts/run_match.py path/to/player.py equity
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pokerbots.engine.match import play_match  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bot_a")
    ap.add_argument("bot_b")
    ap.add_argument("--deals", type=int, default=200, help="duplicate deals (2 hands each)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--time-bank", type=float, default=None)
    ap.add_argument("--log-dir", default=None, help="write each bot's stderr here")
    args = ap.parse_args()
    t = time.time()
    res = play_match(args.bot_a, args.bot_b, deals=args.deals, seed=args.seed,
                     time_bank=args.time_bank, log_dir=args.log_dir)
    print(res.summary())
    print("wall time %.1fs" % (time.time() - t))


if __name__ == "__main__":
    main()
