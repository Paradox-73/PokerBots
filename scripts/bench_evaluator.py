"""Benchmark the evaluator and Monte Carlo equity.

    python scripts/bench_evaluator.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from pokerbots.core import evaluator, rules  # noqa: E402
from pokerbots.core.cards import str_to_cards  # noqa: E402
from pokerbots.core.equity import equity_vs_random, equity_vs_range  # noqa: E402
from pokerbots.bots.common import top_range  # noqa: E402


def timeit(fn, reps):
    fn()
    t = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t) / reps


def main():
    rng = np.random.default_rng(0)
    for k in (5, 7, 9):
        hands = np.argsort(rng.random((200000, rules.DECK_SIZE)), axis=1)[:, :k]
        lst = hands[:50000].tolist()
        s = timeit(lambda: [evaluator.evaluate(h) for h in lst], 3) / len(lst)
        b = timeit(lambda: evaluator.evaluate_batch(hands), 3) / len(hands)
        print("%d-card  scalar %.2f us/hand   batch %.3f us/hand" % (k, s * 1e6, b * 1e6))
    hole = str_to_cards("Ah,Kd")
    flop = str_to_cards("Qs,7h,2c")
    rngs = top_range(0.3)
    cases = [
        ("1000 rollouts vs random, preflop", lambda: equity_vs_random(hole, [], 1000, rng)),
        ("1000 rollouts vs random, flop", lambda: equity_vs_random(hole, flop, 1000, rng)),
        ("1000 rollouts vs top-30% range, preflop", lambda: equity_vs_range(hole, [], rngs, 1000, rng)),
        ("1000 rollouts vs top-30% range, flop", lambda: equity_vs_range(hole, flop, rngs, 1000, rng)),
    ]
    for name, fn in cases:
        print("%-42s %.2f ms" % (name, timeit(fn, 50) * 1000))


if __name__ == "__main__":
    main()
