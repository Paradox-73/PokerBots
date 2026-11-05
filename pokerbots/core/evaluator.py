"""Fast N-card poker hand evaluator (bit tricks + 2^NUM_RANKS lookup tables).

Idea
----
Every card is mapped to one bit in a packed int: bit (suit * NUM_RANKS + rank).
OR-ing (summing) the cards of a hand gives one rank-bitmask per suit.  From
the per-suit masks we get, with a handful of AND/OR operations:

  m_any = ranks present at least once     (OR of all suits)
  m2    = ranks present at least twice    (OR of pairwise ANDs)
  m3    = ranks present at least 3 times  (OR of triple ANDs)
  m4    = ranks present 4 times           (AND of all suits)

Small tables indexed by a 13-bit mask give popcount, highest bit, the packed
top-k ranks and the best straight.  The final score is

  score = category_value << 20 | five 4-bit kicker ranks

so a plain integer comparison orders hands; equal ints are exact ties.
The same code works for any number of cards (5, 6, 7, 8, 9, ...): it always
returns the value of the best 5-card hand, because each category candidate is
computed from the masks and the maximum is taken.  Category strength order is
read from rules.CATEGORY_ORDER, so variants that reorder categories work.

Two implementations share the tables:
  evaluate(cards)            scalar, pure Python ints (~3-5 us per hand)
  evaluate_batch(cards_2d)   NumPy, one call for thousands of hands
"""

from itertools import combinations

import numpy as np

from pokerbots.core import rules

NR = rules.NUM_RANKS
NS = rules.NUM_SUITS
RMASK = (1 << NR) - 1
SHIFT = 20

if rules.HAND_SIZE != 5:
    raise NotImplementedError("evaluator assumes 5-card hands (rules.HAND_SIZE)")
if NR > 16:
    raise NotImplementedError("evaluator packs ranks in 4 bits (<= 16 ranks)")

# internal category ids (fixed); their strength comes from rules.CATEGORY_ORDER
CATEGORY_NAMES = ("high_card", "pair", "two_pair", "trips", "straight",
                  "flush", "full_house", "quads", "straight_flush")
(HIGH, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS,
 STRAIGHT_FLUSH) = range(9)
CAT_VALUE = [rules.CATEGORY_ORDER.index(n) for n in CATEGORY_NAMES]
_CV = [v << SHIFT for v in CAT_VALUE]          # pre-shifted category values


def _build_tables():
    size = 1 << NR
    popcount = [0] * size
    highbit = [0] * size        # mask containing only the highest set bit
    highrank = [0] * size       # index of the highest set bit
    top = [[0] * size for _ in range(6)]   # top[k][m] = packed top-k ranks
    straight = [0] * size       # 0 = none, else (high rank index + 1)
    windows = [(((1 << 5) - 1) << (hi - 4), hi) for hi in range(4, NR)]
    wheel = ((1 << (NR - 1)) | 0b1111) if rules.ACE_LOW_STRAIGHT else None
    for m in range(size):
        ranks = [r for r in range(NR - 1, -1, -1) if m >> r & 1]
        popcount[m] = len(ranks)
        if ranks:
            highrank[m] = ranks[0]
            highbit[m] = 1 << ranks[0]
        for k in range(1, 6):
            v = 0
            for r in ranks[:k]:
                v = (v << 4) | r
            v <<= 4 * (k - min(k, len(ranks)))
            top[k][m] = v
        best = 0
        if wheel is not None and m & wheel == wheel:
            best = 3 + 1
        for w, hi in windows:
            if m & w == w:
                best = hi + 1
        straight[m] = best
    return popcount, highbit, highrank, top, straight


(_POP, _HB, _HR, _TOP, _STR) = _build_tables()
_TOP1, _TOP2, _TOP3, _TOP5 = _TOP[1], _TOP[2], _TOP[3], _TOP[5]

# packed single-card values
_PACK = [1 << ((c % NS) * NR + (c // NS)) for c in range(NR * NS)]
_PAIRS = list(combinations(range(NS), 2))
_TRIPLES = list(combinations(range(NS), 3))
_QUADS = list(combinations(range(NS), 4))
_SUIT_SHIFTS = [s * NR for s in range(NS)]

# numpy copies of the tables
_POP_NP = np.array(_POP, dtype=np.int64)
_HB_NP = np.array(_HB, dtype=np.int64)
_HR_NP = np.array(_HR, dtype=np.int64)
_TOP1_NP = np.array(_TOP1, dtype=np.int64)
_TOP2_NP = np.array(_TOP2, dtype=np.int64)
_TOP3_NP = np.array(_TOP3, dtype=np.int64)
_TOP5_NP = np.array(_TOP5, dtype=np.int64)
_STR_NP = np.array(_STR, dtype=np.int64)
_PACKED_FITS = NR * NS <= 62
_PACK_NP = np.array(_PACK, dtype=np.int64) if _PACKED_FITS else None
_CARD_RANK_BIT = np.array([1 << (c // NS) for c in range(NR * NS)], dtype=np.int64)
_CARD_SUIT = np.array([c % NS for c in range(NR * NS)], dtype=np.int64)


# ------------------------------------------------------------------ scalar
def _score(suits):
    m_any = 0
    for s in suits:
        m_any |= s
    m2 = 0
    for a, b in _PAIRS:
        m2 |= suits[a] & suits[b]
    m3 = 0
    if m2:
        for a, b, c in _TRIPLES:
            m3 |= suits[a] & suits[b] & suits[c]
    m4 = 0
    if m3:
        for q in _QUADS:
            x = RMASK
            for s in q:
                x &= suits[s]
            m4 |= x

    best = _CV[HIGH] | _TOP5[m_any]
    st = _STR[m_any]
    if st:
        v = _CV[STRAIGHT] | st << 16
        if v > best:
            best = v
    for sm in suits:
        if _POP[sm] >= 5:
            sf = _STR[sm]
            v = (_CV[STRAIGHT_FLUSH] | sf << 16) if sf else (_CV[FLUSH] | _TOP5[sm])
            if v > best:
                best = v
            if sf:   # flush is also present; candidate for odd orderings
                v = _CV[FLUSH] | _TOP5[sm]
                if v > best:
                    best = v
    if m2:
        p1 = _HB[m2]
        v = _CV[PAIR] | _HR[p1] << 16 | _TOP3[m_any & ~p1] << 4
        if v > best:
            best = v
        rest = m2 & ~p1
        if rest:
            p2 = _HB[rest]
            v = (_CV[TWO_PAIR] | _HR[p1] << 16 | _HR[p2] << 12
                 | _TOP1[m_any & ~(p1 | p2)] << 8)
            if v > best:
                best = v
        if m3:
            t = _HB[m3]
            v = _CV[TRIPS] | _HR[t] << 16 | _TOP2[m_any & ~t] << 8
            if v > best:
                best = v
            rest = m2 & ~t
            if rest:
                v = _CV[FULL_HOUSE] | _HR[t] << 16 | _HR[_HB[rest]] << 12
                if v > best:
                    best = v
            if m4:
                q = _HB[m4]
                v = _CV[QUADS] | _HR[q] << 16 | _TOP1[m_any & ~q] << 12
                if v > best:
                    best = v
    return best


def evaluate(cards):
    """Value of the best 5-card hand among `cards` (any count >= 5)."""
    p = 0
    for c in cards:
        p |= _PACK[c]
    return _score([(p >> sh) & RMASK for sh in _SUIT_SHIFTS])


# ------------------------------------------------------------------- batch
def _suit_masks_batch(cards):
    if _PACKED_FITS:
        p = _PACK_NP[cards].sum(axis=1)       # cards are distinct -> sum == OR
        return [(p >> sh) & RMASK for sh in _SUIT_SHIFTS]
    bits = _CARD_RANK_BIT[cards]
    suit = _CARD_SUIT[cards]
    return [np.where(suit == s, bits, 0).sum(axis=1) for s in range(NS)]


def evaluate_batch(cards):
    """cards: int array (n_hands, n_cards).  Returns int64 array (n_hands,)."""
    cards = np.asarray(cards, dtype=np.int64)
    suits = _suit_masks_batch(cards)
    m_any = suits[0].copy()
    for s in suits[1:]:
        m_any |= s
    m2 = np.zeros_like(m_any)
    for a, b in _PAIRS:
        m2 |= suits[a] & suits[b]
    m3 = np.zeros_like(m_any)
    for a, b, c in _TRIPLES:
        m3 |= suits[a] & suits[b] & suits[c]
    m4 = np.zeros_like(m_any)
    for q in _QUADS:
        x = suits[q[0]].copy()
        for s in q[1:]:
            x &= suits[s]
        m4 |= x

    best = _CV[HIGH] | _TOP5_NP[m_any]
    # straight
    st = _STR_NP[m_any]
    best = np.where(st > 0, np.maximum(best, _CV[STRAIGHT] | st << 16), best)
    # flush / straight flush (any suit may qualify)
    for sm in suits:
        has = _POP_NP[sm] >= 5
        if not has.any():
            continue
        sf = _STR_NP[sm]
        fl = _CV[FLUSH] | _TOP5_NP[sm]
        cand = np.where(sf > 0, np.maximum(_CV[STRAIGHT_FLUSH] | sf << 16, fl), fl)
        best = np.where(has, np.maximum(best, cand), best)
    # pair / two pair
    p1 = _HB_NP[m2]
    hr1 = _HR_NP[p1]
    cand = _CV[PAIR] | hr1 << 16 | _TOP3_NP[m_any & ~p1] << 4
    best = np.where(m2 != 0, np.maximum(best, cand), best)
    rest = m2 & ~p1
    p2 = _HB_NP[rest]
    cand = (_CV[TWO_PAIR] | hr1 << 16 | _HR_NP[p2] << 12
            | _TOP1_NP[m_any & ~(p1 | p2)] << 8)
    best = np.where(rest != 0, np.maximum(best, cand), best)
    # trips / full house
    t = _HB_NP[m3]
    hrt = _HR_NP[t]
    cand = _CV[TRIPS] | hrt << 16 | _TOP2_NP[m_any & ~t] << 8
    best = np.where(m3 != 0, np.maximum(best, cand), best)
    rest = m2 & ~t
    cand = _CV[FULL_HOUSE] | hrt << 16 | _HR_NP[_HB_NP[rest]] << 12
    best = np.where((m3 != 0) & (rest != 0), np.maximum(best, cand), best)
    # quads
    q = _HB_NP[m4]
    cand = _CV[QUADS] | _HR_NP[q] << 16 | _TOP1_NP[m_any & ~q] << 12
    best = np.where(m4 != 0, np.maximum(best, cand), best)
    return best


# ------------------------------------------------------- hole/board helpers
def hand_value(hole, board):
    """Showdown value honouring rules.HAND_COMPOSITION (e.g. Omaha 2+3).

    Before the discard (more than rules.KEEP_CARDS hole cards) this is the best
    value over every set of cards the player could keep."""
    if len(hole) > rules.KEEP_CARDS:
        return max(hand_value(k, board) for k in combinations(hole, rules.KEEP_CARDS))
    comp = rules.HAND_COMPOSITION
    if comp is None:
        return evaluate(list(hole) + list(board))
    nh, nb = comp
    return max(evaluate(list(h) + list(b))
               for h in combinations(hole, nh) for b in combinations(board, nb))


def hand_value_batch(hole, board):
    """hole: (n, H) array, board: (n, B) array -> (n,) values."""
    hole = np.asarray(hole, dtype=np.int64)
    board = np.asarray(board, dtype=np.int64)
    if hole.shape[1] > rules.KEEP_CARDS:
        best = None
        for ki in combinations(range(hole.shape[1]), rules.KEEP_CARDS):
            v = hand_value_batch(hole[:, list(ki)], board)
            best = v if best is None else np.maximum(best, v)
        return best
    comp = rules.HAND_COMPOSITION
    if comp is None:
        return evaluate_batch(np.concatenate([hole, board], axis=1))
    nh, nb = comp
    best = None
    for hi in combinations(range(hole.shape[1]), nh):
        for bi in combinations(range(board.shape[1]), nb):
            v = evaluate_batch(np.concatenate([hole[:, list(hi)], board[:, list(bi)]], axis=1))
            best = v if best is None else np.maximum(best, v)
    return best


def category_of(score):
    """Category name of a score, e.g. 'two_pair'."""
    return rules.CATEGORY_ORDER[int(score) >> SHIFT]
