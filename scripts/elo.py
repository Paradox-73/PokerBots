"""Fit Elo ratings from match results (scripts/field_matrix.py rows), mc fixed at 1500.

    python scripts/elo.py field.jsonl hero.jsonl

A forfeited match is left out: it says nothing about strength.  Ratings maximise the likelihood of the match points; a
small pull toward 1500 keeps a bot that won every match at a finite rating, so ratings
at the extremes are lower bounds.
"""

import collections
import json
import math
import sys

ANCHOR = "mc"
PRIOR_GAMES = 1.0     # pseudo-matches against an equal-rated opponent, half won


def load(paths):
    scores = collections.defaultdict(lambda: [0.0, 0])
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for r in map(json.loads, f):
                if r["a"] == r["b"] or r["forfeit"] is not None:
                    continue
                pts = 1.0 if r["chips"] > 0 else 0.5 if r["chips"] == 0 else 0.0
                key = (r["a"], r["b"])
                scores[key][0] += pts
                scores[key][1] += 1
    return scores


def fit(scores, steps=4000):
    names = sorted({n for pair in scores for n in pair})
    rating = dict.fromkeys(names, 1500.0)
    scale = math.log(10) / 400
    for step in range(steps):
        grad = dict.fromkeys(names, 0.0)
        games = dict.fromkeys(names, PRIOR_GAMES)
        for (a, b), (won, n) in scores.items():
            expect = 1 / (1 + 10 ** ((rating[b] - rating[a]) / 400))
            grad[a] += won - n * expect
            grad[b] -= won - n * expect
            games[a] += n
            games[b] += n
        for name in names:
            grad[name] += PRIOR_GAMES * (0.5 - 1 / (1 + 10 ** ((1500 - rating[name]) / 400)))
            rating[name] += grad[name] / (scale * games[name]) * 0.5
    shift = 1500 - rating.get(ANCHOR, 1500)
    return {n: r + shift for n, r in rating.items()}


def main():
    scores = load(sys.argv[1:])
    played = collections.Counter()
    for (a, b), (_, n) in scores.items():
        played[a] += n
        played[b] += n
    for rank, (name, r) in enumerate(sorted(fit(scores).items(), key=lambda kv: -kv[1]), 1):
        print("%2d %-12s %6.0f  (%d matches)" % (rank, name, r, played[name]))


if __name__ == "__main__":
    main()
