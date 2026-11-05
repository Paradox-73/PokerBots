"""Simulate the full tournament from sampled match results (scripts/field_matrix.py).

    python scripts/simulate_tournament.py field.jsonl hero.jsonl --runs 2000

Stage 1: 6 rounds of Swiss, or a round robin below 64 entrants.  The top 32 go on.
Stage 2: round robin of 1000-hand matches with scores reset.  Ranking is match
points, then capped chips per hand.  A 1000-hand result is a sampled 1000-hand match
where one exists, else the sum of sampled 400-hand results, 2.5 matches' worth.
Entrants of one type share that type's samples, so identical-type matches come from
its self-play rows.
"""

import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pokerbots.core import rules  # noqa: E402

HERO = "HERO"
# shares of the field by type, summing to 100; entrants are mostly simple equity
# bots, which is a judgement about who enters, not a measurement
FIELD = {"mc": 18, "tosslow": 9, "tag": 8, "tight": 8, "lag": 6, "smallball": 6, "potodds": 5,
         "tagbig": 5, "starter": 8, "random": 3, "call": 3, "shove": 3, "maniac": 3,
         "minraise": 3, "passive": 2, "scared": 2, "jammer": 2, "barrel": 2, "nit": 2,
         "balanced": 3, "exploiter": 2, "loose": 3, "fold": 1}
MIXES = {
    "typical": FIELD,
    # many strong AI-written bots: the real rivals plus the best simple ones
    "solver_heavy": {"rival_a": 14, "rival_b": 14, "cfr2": 14, "cfr": 8, "rival_c": 8, "locker": 12,
                     "rival_a2": 12, "rival_b2": 10, "balanced": 4, "exploiter": 4},
    # solver_heavy without rival_a and its twin, so rival_a as hero does not face its own copies
    "strong_no_rival_a": {"rival_b": 18, "cfr2": 18, "cfr": 10, "rival_c": 10, "locker": 16,
                       "rival_b2": 14, "balanced": 7, "exploiter": 7},
    # mostly first-draft bots
    "weak": {"starter": 25, "random": 12, "call": 12, "mc": 15, "tosslow": 15, "passive": 6,
             "scared": 5, "fold": 3, "loose": 7},
    # shovers and maniacs, where variance is highest
    "wild": {"shove": 14, "jammer": 14, "maniac": 14, "minraise": 10, "barrel": 10, "lag": 12,
             "loose": 10, "nit": 8, "exploiter": 8},
    # everyone has read the same advice
    "tight_field": {"tight": 22, "tag": 20, "tagbig": 14, "potodds": 14, "nit": 10, "smallball": 10,
                    "mc": 10},
}
STAGE1_ROUNDS = 6
STAGE2_SIZE = 32
SMALL_FIELD = 64
CAP1, CAP2 = rules.MATCH_CHIP_CAP, 1000
HANDS1, HANDS2 = 400, 1000


def load(paths, hero_name):
    samples = collections.defaultdict(list)     # (a, b, hands) -> a's chips per match
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for row in map(json.loads, f):
                if row["forfeit"] is not None:
                    continue
                chips, hands = row["chips"], row["deals"] * 2
                # a hero that is also a field type keeps its rows under its own name too,
                # and its self-play rows also stand for hero against that field type
                names = {n: {n, HERO} if n == hero_name else {n} for n in (row["a"], row["b"])}
                pairs = {(a, b) for a in names[row["a"]] for b in names[row["b"]]}
                for a, b in pairs:
                    samples[(a, b, hands)].append(chips)
                    samples[(b, a, hands)].append(-chips)
    return samples


def missing_pairs(samples, field):
    """Every pair this mix can draw that has no results: guessing them would decide the answer."""
    types = [HERO] + sorted(field)
    return [(a, b) for i, a in enumerate(types) for b in types[i:]
            if (a, b, HANDS1) not in samples and not (a == b == HERO)]


class Tournament:
    def __init__(self, samples, rng, field):
        self.samples, self.rng = samples, rng
        self.types = [HERO] + [t for t, n in field.items() for _ in range(n)]

    def draw(self, a, b, scale):
        pair = (self.types[a], self.types[b])
        long_pool = self.samples.get(pair + (HANDS2,))
        if scale != 1 and long_pool:
            return self.rng.choice(long_pool)
        pool = self.samples[pair + (HANDS1,)]
        if scale == 1:
            return self.rng.choice(pool)
        return self.rng.choice(pool) + self.rng.choice(pool) + 0.5 * self.rng.choice(pool)

    def play(self, a, b, scale, cap, table):
        net = self.draw(a, b, scale)
        pts = 1.0 if net > 0 else 0.0 if net < 0 else 0.5
        clipped = max(-cap, min(cap, net))
        table[a][0] += pts
        table[b][0] += 1.0 - pts
        table[a][1] += clipped
        table[b][1] -= clipped
        return net

    def ranked(self, table, members):
        return sorted(members, key=lambda e: (-table[e][0], -table[e][1], self.rng.random()))

    def stage1(self):
        entrants = list(range(len(self.types)))
        table = {e: [0.0, 0.0] for e in entrants}
        met = set()
        if len(entrants) < SMALL_FIELD:
            for i, a in enumerate(entrants):
                for b in entrants[i + 1:]:
                    self.play(a, b, 1, CAP1, table)
            return self.ranked(table, entrants)[:STAGE2_SIZE]
        for _ in range(STAGE1_ROUNDS):
            order = self.ranked(table, entrants)
            while len(order) > 1:
                a = order.pop(0)
                b = next((x for x in order if (a, x) not in met), order[0])
                order.remove(b)
                met.update(((a, b), (b, a)))
                self.play(a, b, 1, CAP1, table)
            if order:
                table[order[0]][0] += 1.0
        return self.ranked(table, entrants)[:STAGE2_SIZE]

    def stage2(self, finalists, losses):
        table = {e: [0.0, 0.0] for e in finalists}
        for i, a in enumerate(finalists):
            for b in finalists[i + 1:]:
                net = self.play(a, b, 2.5, CAP2, table)
                if a == 0 or b == 0:
                    other = self.types[b if a == 0 else a]
                    hero_net = net if a == 0 else -net
                    losses[other][0] += 1
                    losses[other][1] += hero_net < 0
        return self.ranked(table, finalists)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--hero", default="equity")
    ap.add_argument("--runs", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--scale", type=float, default=1.0, help="multiply the field's size")
    ap.add_argument("--mix", default="typical", choices=sorted(MIXES))
    ap.add_argument("--list-missing", action="store_true", help="list pairs with no data and stop")
    args = ap.parse_args()
    samples = load(args.files, args.hero)
    field = {t: max(1, round(n * args.scale)) for t, n in MIXES[args.mix].items()}
    absent = missing_pairs(samples, field)
    if args.list_missing or absent:
        print("mix %s: %d pairs have no 400-hand data" % (args.mix, len(absent)))
        for pair in absent:
            print("  missing %s %s" % pair)
        sys.exit(0 if args.list_missing else 1)
    rng = random.Random(args.seed)
    places = collections.Counter()
    losses = collections.defaultdict(lambda: [0, 0])
    qualified = 0
    for _ in range(args.runs):
        t = Tournament(samples, rng, field)
        finalists = t.stage1()
        if 0 not in finalists:
            places["out"] += 1
            continue
        qualified += 1
        order = t.stage2(finalists, losses)
        places[order.index(0) + 1] += 1
    first = places[1] / args.runs
    top3 = sum(places[p] for p in (1, 2, 3)) / args.runs
    print("mix %s, entrants %d, runs %d: first %.1f%%, top 3 %.1f%%, reached finals %.1f%%"
          % (args.mix, sum(field.values()) + 1, args.runs, 100 * first, 100 * top3,
             100 * qualified / args.runs))
    print("finals match losses by opponent type (lost / played):")
    for name, (played, lost) in sorted(losses.items(), key=lambda kv: -kv[1][1]):
        print("  %-10s %6d / %6d  %5.1f%%" % (name, lost, played, 100 * lost / max(1, played)))


if __name__ == "__main__":
    main()
