"""Strategy helpers shared by bots: starting-hand strength, ranges, made hands."""

from itertools import combinations

import numpy as np

from pokerbots.core import rules
from pokerbots.core.equity import Range
from pokerbots.core.evaluator import category_of, hand_value

_NS = rules.NUM_SUITS
CATEGORY_RANK = {name: i for i, name in enumerate(rules.CATEGORY_ORDER)}


def hand_class(hole):
    """Suit-isomorphism class key: ranks high to low plus a suit code.

    Suffix 's' = all one suit, 'r' = all different, or (3 cards, two share a
    suit) 'a'/'b'/'c' = the 1st/2nd/3rd card is the odd suit out.  2 cards: 's'/'o'."""
    cs = sorted(hole, key=lambda c: (-(c // _NS), c))
    rk = [c // _NS for c in cs]
    suits = [c % _NS for c in cs]
    key = "".join(rules.RANKS[r] for r in rk)
    ns = len(set(suits))
    if len(cs) == 2:
        return key if rk[0] == rk[1] else key + ("s" if ns == 1 else "o")
    if ns == 1:
        return key + "s"
    if ns == len(cs):
        return key + "r"
    odd = next(i for i in range(3) if suits.count(suits[i]) == 1)
    return key + "abc"[rk.index(rk[odd])]


def _load_table():
    if rules.HOLE_CARDS != 3:
        return None
    try:
        from pokerbots.bots.preflop_table import HOLE_CARDS, PREFLOP_EQUITY, RANKS
    except ImportError:
        return None
    ok = RANKS == rules.RANKS and HOLE_CARDS == rules.HOLE_CARDS
    return PREFLOP_EQUITY if ok else None


PREFLOP_EQUITY = _load_table()

# every starting-hand combo with its strength percentile (0 = worst, 1 = best)
if PREFLOP_EQUITY is not None:
    ALL_COMBOS = np.array(list(combinations(range(rules.DECK_SIZE), rules.HOLE_CARDS)),
                          dtype=np.int64)
    _eq = np.array([PREFLOP_EQUITY[hand_class(c)] for c in ALL_COMBOS.tolist()])
    _SORTED_EQ = np.sort(_eq)
    # midrank percentile so equal-strength combos share a value
    COMBO_PCT = (np.searchsorted(_SORTED_EQ, _eq, side="left")
                 + np.searchsorted(_SORTED_EQ, _eq, side="right")) / 2.0 / len(_eq)
else:
    ALL_COMBOS = None
    COMBO_PCT = None


def preflop_percentile(hole):
    """Strength percentile of a starting hand; falls back to a crude formula."""
    if PREFLOP_EQUITY is not None:
        eq = PREFLOP_EQUITY[hand_class(hole)]
        lo = np.searchsorted(_SORTED_EQ, eq, side="left")
        hi = np.searchsorted(_SORTED_EQ, eq, side="right")
        return float((lo + hi) / 2.0 / len(_SORTED_EQ))
    ranks = sorted((c // _NS for c in hole), reverse=True)
    score = sum(ranks) / (len(ranks) * (rules.NUM_RANKS - 1))
    if len(set(ranks)) < len(ranks):
        score += 0.25
    if len(set(c % _NS for c in hole)) == 1:
        score += 0.05
    return min(1.0, score)


def top_range(fraction, softness=0.04):
    """Range of roughly the strongest `fraction` of starting hands.

    Soft edge (logistic) so the range is never empty and is robust to model
    error.  Returns None when no preflop table exists (use vs-random)."""
    if ALL_COMBOS is None:
        return None
    fraction = min(1.0, max(0.02, fraction))
    cut = 1.0 - fraction
    w = 1.0 / (1.0 + np.exp(-(COMBO_PCT - cut) / softness))
    return Range(ALL_COMBOS, w)


def made_hand(hole, board):
    """(category rank of hole+board, category rank of board alone, uses_hole).

    uses_hole is True when the hole cards improve on the board by itself."""
    if not board:
        return 0, 0, False
    mine = hand_value(hole, board)
    cat = CATEGORY_RANK[category_of(mine)]
    if rules.HAND_COMPOSITION is not None:
        return cat, 0, True
    bv = hand_value([], board)
    return cat, CATEGORY_RANK[category_of(bv)], mine > bv


def flush_draw(hole, board):
    """True if hole+board has exactly 4 cards of one suit (incl. a hole card)."""
    for s in range(_NS):
        n = sum(1 for c in list(hole) + list(board) if c % _NS == s)
        if n == 4 and any(c % _NS == s for c in hole):
            return True
    return False


if ALL_COMBOS is not None:
    # percentile of a sorted 3-card hand, looked up by its three card ids
    _PCT_CUBE = np.zeros((rules.DECK_SIZE,) * rules.HOLE_CARDS, dtype=np.float32)
    _PCT_CUBE[tuple(ALL_COMBOS.T)] = COMBO_PCT


def range_weight(fraction, softness=0.04):
    """top_range's weights as a function of starting hands (n, 3) -> (n,),
    for weighting sampled hands.  None without a preflop table."""
    if ALL_COMBOS is None:
        return None
    cut = 1.0 - min(1.0, max(0.02, fraction))

    def weight(hands):
        pct = _PCT_CUBE[tuple(np.sort(hands, axis=1).T)]
        return 1.0 / (1.0 + np.exp(-(pct - cut) / softness))
    return weight
