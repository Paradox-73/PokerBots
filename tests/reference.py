"""Deliberately naive reference evaluator (standard Hold'em ranking only)."""

from collections import Counter
from itertools import combinations

from pokerbots.core import rules

NS = rules.NUM_SUITS


def rank5(cards):
    ranks = sorted((c // NS for c in cards), reverse=True)
    suits = [c % NS for c in cards]
    flush = len(set(suits)) == 1
    uniq = sorted(set(ranks), reverse=True)
    straight_hi = None
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_hi = uniq[0]
        elif uniq == [12, 3, 2, 1, 0]:
            straight_hi = 3
    counts = Counter(ranks)
    groups = sorted(counts.items(), key=lambda rc: (rc[1], rc[0]), reverse=True)
    shape = [c for _, c in groups]
    order = [r for r, _ in groups]
    if straight_hi is not None and flush:
        return (8, [straight_hi])
    if shape == [4, 1]:
        return (7, order)
    if shape == [3, 2]:
        return (6, order)
    if flush:
        return (5, ranks)
    if straight_hi is not None:
        return (4, [straight_hi])
    if shape == [3, 1, 1]:
        return (3, order)
    if shape == [2, 2, 1]:
        return (2, order)
    if shape == [2, 1, 1, 1]:
        return (1, order)
    return (0, ranks)


def best_rank(cards):
    return max(rank5(c) for c in combinations(cards, 5))
