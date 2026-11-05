"""Monte Carlo equity (vectorised with NumPy).

equity = P(win) + 0.5 * P(tie) for `hole` against one opponent whose hole
cards are either uniformly random or drawn from a weighted range, with the
board completed at random.  `dead` cards (the public discards) are never
dealt.  A random opponent holds as many cards as `hole` (3 before the
discard, 2 after); 3-card hands are valued by the best 2 they could keep
(see evaluator.hand_value), which overstates both sides equally.

All functions return (equity, rollouts_used).
"""

import time

import numpy as np

from pokerbots.core import rules
from pokerbots.core import evaluator
from pokerbots.core.evaluator import hand_value_batch

_DECK = np.arange(rules.DECK_SIZE, dtype=np.int64)


def _remaining(known):
    mask = np.ones(rules.DECK_SIZE, dtype=bool)
    mask[list(known)] = False
    return _DECK[mask]


def _draw(rng, n, deck_size, k):
    """n rows of k distinct indices into range(deck_size)."""
    keys = rng.random((n, deck_size))
    if k == deck_size:
        return np.argsort(keys, axis=1)
    return np.argpartition(keys, k - 1, axis=1)[:, :k]


def _showdown(hole, board, opp_hole, board_fill):
    n = opp_hole.shape[0]
    hero_h = np.broadcast_to(np.asarray(hole, dtype=np.int64), (n, len(hole)))
    if len(board):
        known = np.broadcast_to(np.asarray(board, dtype=np.int64), (n, len(board)))
        full_board = np.concatenate([known, board_fill], axis=1)
    else:
        full_board = board_fill
    hv = hand_value_batch(hero_h, full_board)
    ov = hand_value_batch(opp_hole, full_board)
    return float((hv > ov).sum() + 0.5 * (hv == ov).sum())


def equity_vs_random(hole, board=(), n=1000, rng=None, dead=()):
    rng = rng if rng is not None else np.random.default_rng()
    hole, board = list(hole), list(board)
    deck = _remaining(hole + board + list(dead))
    need = rules.BOARD_CARDS - len(board)
    h = len(hole)
    idx = _draw(rng, n, len(deck), h + need)
    drawn = deck[idx]
    score = _showdown(hole, board, drawn[:, :h], drawn[:, h:])
    return score / n, n


class Range:
    """Weighted list of opponent hole-card combos.

    combos:  int array (C, HOLE_CARDS)
    weights: float array (C,), any non-negative scale
    """

    def __init__(self, combos, weights=None):
        self.combos = np.asarray(combos, dtype=np.int64)
        if weights is None:
            weights = np.ones(len(self.combos))
        self.weights = np.asarray(weights, dtype=float)

    def live(self, dead):
        """Weights with combos blocked by `dead` cards set to zero."""
        if not dead:
            return self.weights
        dead_mask = np.zeros(rules.DECK_SIZE, dtype=bool)
        dead_mask[list(dead)] = True
        blocked = dead_mask[self.combos].any(axis=1)
        return np.where(blocked, 0.0, self.weights)


def equity_vs_range(hole, board, opp_range, n=1000, rng=None, dead=()):
    rng = rng if rng is not None else np.random.default_rng()
    hole, board = list(hole), list(board)
    known = hole + board + list(dead)
    w = opp_range.live(known)
    total = w.sum()
    if total <= 0:
        return equity_vs_random(hole, board, n, rng, dead)
    pick = rng.choice(len(w), size=n, p=w / total)
    opp = opp_range.combos[pick]
    deck = _remaining(known)
    need = rules.BOARD_CARDS - len(board)
    if need == 0:
        fill = np.zeros((n, 0), dtype=np.int64)
    else:
        pos = np.full(rules.DECK_SIZE, -1, dtype=np.int64)
        pos[deck] = np.arange(len(deck))
        keys = rng.random((n, len(deck)))
        rows = np.arange(n)[:, None]
        keys[rows, pos[opp]] = 2.0        # opponent's cards can't hit the board
        fill = deck[np.argpartition(keys, need - 1, axis=1)[:, :need]]
    return _showdown(hole, board, opp, fill) / n, n


def equity_timed(hole, board, budget_s, opp_range=None, batch=250,
                 max_rollouts=4000, min_rollouts=100, rng=None, dead=(),
                 opp_discard=None, policy_weights=None, hand_weight=None):
    """Run batches until `budget_s` seconds are spent or max_rollouts reached.
    With `opp_discard` (after the discard) uses equity_vs_discarder."""
    rng = rng if rng is not None else np.random.default_rng()
    start = time.perf_counter()
    total, used = 0.0, 0
    while used < max_rollouts:
        if used >= min_rollouts and time.perf_counter() - start >= budget_s:
            break
        if opp_discard is not None:
            eq, k = equity_vs_discarder(hole, board, opp_discard, dead, batch, rng,
                                        policy_weights, hand_weight)
        elif opp_range is None:
            eq, k = equity_vs_random(hole, board, batch, rng, dead)
        else:
            eq, k = equity_vs_range(hole, board, opp_range, batch, rng, dead)
        total += eq * k
        used += k
    return total / used, used


# ------------------------------------------- how players choose what to keep
_KEEPS = np.array(((1, 2), (0, 2), (0, 1)), dtype=np.int64)   # kept cards, by index discarded
_CATEGORY = 1 << evaluator.SHIFT
_STRAIGHT_VALUE = rules.CATEGORY_ORDER.index("straight") * _CATEGORY
FLUSH_DRAW_BONUS = int(0.7 * _CATEGORY)
OPEN_ENDED_BONUS = int(0.5 * _CATEGORY)
GUTSHOT_BONUS = int(0.2 * _CATEGORY)


def _straight_draw_table():
    """Bonus per 13-bit rank mask: open-ended, gutshot, or none."""
    table = np.zeros(1 << rules.NUM_RANKS, dtype=np.int64)
    masks = np.arange(1 << rules.NUM_RANKS)
    wheel = [0, 1, 2, 3, rules.NUM_RANKS - 1]
    windows = [sum(1 << r for r in range(low, low + 5))
               for low in range(rules.NUM_RANKS - 4)] + [sum(1 << r for r in wheel)]
    for w in windows:
        hits = np.zeros(len(masks), dtype=np.int64)
        for bit in range(rules.NUM_RANKS):
            if w >> bit & 1:
                hits += masks >> bit & 1
        table[hits == 4] = GUTSHOT_BONUS
    for low in range(1, rules.NUM_RANKS - 4):
        run = sum(1 << r for r in range(low, low + 4))
        table[(masks & run) == run] = OPEN_ENDED_BONUS
    return table


_STRAIGHT_DRAW = _straight_draw_table()


def keep_score(kept, flop):
    """How much a player likes keeping `kept` (n, 2) on `flop` (n, 3): its made hand,
    raised for a flush or straight draw unless it is already a straight or better."""
    made = hand_value_batch(kept, flop)
    cards = np.concatenate([kept, flop], axis=1)
    ranks, suits = cards // rules.NUM_SUITS, cards % rules.NUM_SUITS
    mask = np.bitwise_or.reduce(1 << ranks, axis=1)
    most_suited = (suits[:, :, None] == np.arange(rules.NUM_SUITS)).sum(axis=1).max(axis=1)
    bonus = np.maximum(_STRAIGHT_DRAW[mask], np.where(most_suited == 4, FLUSH_DRAW_BONUS, 0))
    return np.where(made < _STRAIGHT_VALUE, made + bonus, made)


def best_kept(three, flop):
    """The two cards each (n, 3) hand keeps on its (n, 3) flop."""
    scores = np.stack([keep_score(three[:, k], flop) for k in _KEEPS], axis=1)
    return three[np.arange(len(three))[:, None], _KEEPS[scores.argmax(axis=1)]]


def strength_weights(values, pressure):
    """Sample weights that lean toward strong opponent hands as `pressure` rises above
    zero, and toward weak ones below zero.  None means every sample counts equally."""
    if abs(pressure) < 1e-6:
        return None
    rank = np.argsort(np.argsort(values, kind="stable"), kind="stable") / max(1, len(values) - 1)
    return (0.02 + rank) ** pressure if pressure > 0 else (1.02 - rank) ** -pressure


def range_equity(hole, board, n, rng, dead=(), opp_discard=None, pressure=0.0):
    """Equity of each way to play `hole`, against sampled opponents and runouts.

    Three hole cards on the flop: a list of 3, entry i being the equity after
    discarding hole[i].  Otherwise a list of 1.  The opponent keeps its best two of
    three, or fits the discard it showed; `pressure` narrows it by final strength."""
    hole, board = list(hole), list(board)
    known = hole + board + list(dead) + ([] if opp_discard is None else [opp_discard])
    deck = _remaining(known)
    need = rules.BOARD_CARDS - len(board)
    opp_cards = rules.HOLE_CARDS if len(hole) == rules.HOLE_CARDS else rules.KEEP_CARDS
    drawn = deck[_draw(rng, n, len(deck), opp_cards + need)]
    opp, fill = drawn[:, :opp_cards], drawn[:, opp_cards:]
    known_board = np.broadcast_to(np.asarray(board, dtype=np.int64), (n, len(board)))
    full = np.concatenate([known_board, fill], axis=1)
    flop = full[:, :3]
    if opp_cards == rules.HOLE_CARDS:
        opp = best_kept(opp, flop)
    opp_values = hand_value_batch(opp, full)
    weights = strength_weights(opp_values, pressure)
    if opp_discard is not None:
        shown = np.full((n, 1), opp_discard, dtype=np.int64)
        kept_score = keep_score(opp, flop)
        fits = (kept_score >= keep_score(np.concatenate([opp[:, :1], shown], axis=1), flop)) \
            & (kept_score >= keep_score(np.concatenate([opp[:, 1:], shown], axis=1), flop))
        fit_weight = np.where(fits, 1.0, 0.3)
        weights = fit_weight if weights is None else weights * fit_weight
    hero = np.broadcast_to(np.asarray(hole, dtype=np.int64), (n, len(hole)))
    if len(hole) == 2:
        options = [hero]
    elif board:
        options = [hero[:, k] for k in _KEEPS]
    else:
        options = [best_kept(hero, flop)]
    equities = []
    for cards in options:
        values = hand_value_batch(cards, full)
        score = (values > opp_values) + 0.5 * (values == opp_values)
        equities.append(float(score.mean() if weights is None
                              else (score * weights).sum() / weights.sum()))
    return equities


# ------------------------------------------------- after the public discard
DISCARD_POLICIES = ("best_made", "lowest_rank")
DEFAULT_POLICY_WEIGHTS = {"best_made": 0.5, "lowest_rank": 0.2}


def discard_consistency(kept, discard, flop):
    """Which discard policies would throw `discard` from kept + [discard].

    kept: (n, 2), discard: (n,) or int, flop: 3 cards.  Returns a dict
    policy -> bool array (n,):
      best_made    keeping `kept` makes the best hand with the flop
      lowest_rank  the discard's rank is not above either kept card's
    """
    kept = np.asarray(kept, dtype=np.int64)
    n = kept.shape[0]
    d = np.broadcast_to(np.asarray(discard, dtype=np.int64), (n,))[:, None]
    fl = np.broadcast_to(np.asarray(flop, dtype=np.int64), (n, len(flop)))
    v_keep = hand_value_batch(kept, fl)
    v_a = hand_value_batch(np.concatenate([kept[:, :1], d], axis=1), fl)
    v_b = hand_value_batch(np.concatenate([kept[:, 1:], d], axis=1), fl)
    ns = rules.NUM_SUITS
    return {"best_made": v_keep >= np.maximum(v_a, v_b),
            "lowest_rank": d[:, 0] // ns <= kept.min(axis=1) // ns}


def equity_vs_discarder(hole, board, opp_discard, dead, n=1000, rng=None,
                        policy_weights=None, hand_weight=None):
    """Equity after the discard against an opponent who threw `opp_discard`.

    The opponent's 2 kept cards are sampled at random, then each sample is
    weighted by how likely it was to produce that discard: a mixture where
    policy p is followed with probability policy_weights[p] and otherwise
    the discard is one of the 3 cards at random:
        sum(w[p] * [p would discard it]) + (1 - sum(w)) / 3
    and optionally by hand_weight(three_cards (n, 3)) -> (n,), e.g. a preflop
    range.  `dead` must include both discards.  Returns (equity, n)."""
    rng = rng if rng is not None else np.random.default_rng()
    hole, board = list(hole), list(board)
    deck = _remaining(hole + board + list(dead))
    need = rules.BOARD_CARDS - len(board)
    drawn = deck[_draw(rng, n, len(deck), 2 + need)]
    kept, fill = drawn[:, :2], drawn[:, 2:]
    pw = DEFAULT_POLICY_WEIGHTS if policy_weights is None else policy_weights
    cons = discard_consistency(kept, opp_discard, board[:3])
    w = np.full(n, max(0.0, 1.0 - sum(pw.values())) / 3.0)
    for p, ok in cons.items():
        w += pw.get(p, 0.0) * ok
    if hand_weight is not None:
        three = np.concatenate([kept, np.full((n, 1), opp_discard, dtype=np.int64)], axis=1)
        w = w * hand_weight(three)
    hero = np.broadcast_to(np.asarray(hole, dtype=np.int64), (n, len(hole)))
    full = np.concatenate([np.broadcast_to(np.asarray(board, dtype=np.int64), (n, len(board))),
                           fill], axis=1) if need else np.broadcast_to(
        np.asarray(board, dtype=np.int64), (n, len(board)))
    hv, ov = hand_value_batch(hero, full), hand_value_batch(kept, full)
    score = (hv > ov) + 0.5 * (hv == ov)
    total = w.sum()
    return (float((w * score).sum() / total) if total > 0 else float(score.mean())), n
