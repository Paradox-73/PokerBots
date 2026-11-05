"""Game abstraction shared by the trainer (solver/train.py) and the bot.

Three parts, each used identically at training time and at play time:

  * cards     - card ids, the 1326 two-card holdings, a vectorised evaluator that
                ranks every holding on many boards at once (rank_boards).
  * features  - what a player knows about its own cards on each street, reduced
                to a bucket id:
                  preflop  exact suit-isomorphic class of the 3 hole cards (1755)
                  flop     strength S and volatility V of the best 2-card keep
                           (percentile against all holdings over fixed runouts)
                  turn     mean and spread over river cards of the hand strength
                           against the opponent's plausible kept holdings
                  river    hand strength against those holdings
                The opponent's plausible holdings after the discard are the ones
                it would rationally keep given the card it threw away.
  * betting   - a fixed bet abstraction (fold, check/call, a few pot fractions,
                all-in) laid out as a DAG of public states: the full action
                sequence inside a street, and at a street start only the pot and
                who made the last bet of the previous street.

Card id = rank * 4 + suit, rank 0 = deuce, suits in the order "shdc".
"""

from itertools import combinations, permutations

import numpy as np

RANKS, SUITS = "23456789TJQKA", "shdc"
STACK, SB, BB = 200, 1, 2
MAX_RAISES = 4                      # bets + raises per street; the big blind counts preflop
PREFLOP, FLOP, TURN, RIVER = range(4)
STREET_NAMES = ("preflop", "flop", "turn", "river")

# ------------------------------------------------------------------ bet abstraction
# Pot fractions offered by raise depth (bets/raises already made on the street;
# preflop starts at 1 because of the big blind).  All-in is always offered too.
PRE_SIZES = {1: (1.0, 2.0), 2: (0.75,), 3: ()}
POST_SIZES = {0: (0.33, 0.66, 1.0), 1: (0.75,), 2: (), 3: ()}
ALLIN_SNAP = 0.6                    # a size above this share of the all-in amount is dropped

# ------------------------------------------------------------------ feature constants
FLOP_RUNOUTS = 48                   # turn+river runouts used to score flop keeps
KEEP_MARGIN = 0.02                  # slack when judging which holdings were rationally kept
# Buckets per street: preflop classes, flop (S bins x V bins), turn (mean x spread), river.
FLOP_GRID, TURN_GRID, RIVER_BINS = (64, 8), (32, 6), 192
N_BUCKETS = (None, FLOP_GRID[0] * FLOP_GRID[1], TURN_GRID[0] * TURN_GRID[1], RIVER_BINS)


def card_id(text):
    return RANKS.index(text[0]) * 4 + SUITS.index(text[1])


def card_name(c):
    return RANKS[c >> 2] + SUITS[c & 3]


# ================================================================== holdings
PA, PB = (a.astype(np.int64) for a in np.triu_indices(52, 1))   # 1326 holdings, PA < PB
NH = PA.size
PID = np.zeros((52, 52), dtype=np.int64)      # holding id of a card pair (diagonal unused)
PID[PA, PB] = PID[PB, PA] = np.arange(NH)
HAS = np.zeros((52, NH), dtype=bool)          # HAS[c, h]: holding h contains card c
HAS[PA, np.arange(NH)] = HAS[PB, np.arange(NH)] = True

# ================================================================== evaluator
# Score = category << 20 | kickers, compared as plain integers.  Works for any
# board size; ranks every holding against each board in one pass.


def _mask_tables():
    size = 1 << 13
    hi, top2, top3, top5, straight, flush = (np.zeros(size, dtype=np.int64) for _ in range(6))
    for m in range(1, size):
        ranks = [r for r in range(12, -1, -1) if m >> r & 1]
        hi[m] = ranks[0]
        t = ranks[:5] + [0] * 5
        top2[m] = t[0] << 4 | t[1]
        top3[m] = t[0] << 8 | t[1] << 4 | t[2]
        top5[m] = t[0] << 16 | t[1] << 12 | t[2] << 8 | t[3] << 4 | t[4]
        high = next((h + 1 for h in range(12, 3, -1) if (m >> (h - 4)) & 31 == 31), 0)
        if not high and m & 0x100F == 0x100F:          # A-2-3-4-5
            high = 4
        straight[m] = high
        if len(ranks) >= 5:
            flush[m] = (8 << 20 | high) if high else (5 << 20 | top5[m])
    return hi, top2, top3, top5, straight, flush


HI, TOP2, TOP3, TOP5, STRAIGHT, FLUSH = _mask_tables()
_POW2 = 1 << np.arange(13)
_PAIR_RANKS = np.zeros((NH, 13), dtype=np.int64)
np.add.at(_PAIR_RANKS, (np.arange(NH), PA >> 2), 1)
np.add.at(_PAIR_RANKS, (np.arange(NH), PB >> 2), 1)
_PAIR_SUIT_BITS = np.array([((PA & 3) == s) * (1 << (PA >> 2)) + ((PB & 3) == s) * (1 << (PB >> 2))
                            for s in range(4)])


def rank_boards(boards):
    """Score of every holding on each board: (n_boards, 1326), -1 where they overlap."""
    boards = np.asarray(boards, dtype=np.int64).reshape(-1, np.shape(boards)[-1])
    n = len(boards)
    cnt = np.zeros((n, 13), dtype=np.int64)
    np.add.at(cnt, (np.repeat(np.arange(n), boards.shape[1]), (boards >> 2).ravel()), 1)
    c = cnt[:, None, :] + _PAIR_RANKS                       # (n, 1326, 13) rank counts
    m1, m2, m3, m4 = ((c >= k) @ _POW2 for k in (1, 2, 3, 4))
    p = HI[m2]
    rest = m2 & ~(1 << p)
    p2 = HI[rest]
    t = HI[m3]
    rest_t = m2 & ~(1 << t)
    q = HI[m4]
    v = TOP5[m1]
    v = np.where(m2 != 0, 1 << 20 | p << 12 | TOP3[m1 & ~(1 << p)], v)
    v = np.where(rest != 0, 2 << 20 | p << 8 | p2 << 4 | HI[m1 & ~(1 << p) & ~(1 << p2)], v)
    v = np.where(m3 != 0, 3 << 20 | t << 8 | TOP2[m1 & ~(1 << t)], v)
    v = np.where(STRAIGHT[m1] != 0, 4 << 20 | STRAIGHT[m1], v)
    v = np.where((m3 != 0) & (rest_t != 0), 6 << 20 | t << 4 | HI[rest_t], v)
    v = np.where(m4 != 0, 7 << 20 | q << 4 | HI[m1 & ~(1 << q)], v)
    suits = boards & 3
    for i in range(n):
        counts = np.bincount(suits[i], minlength=4)
        s = int(counts.argmax())
        if counts[s] >= 3:                                  # a flush needs 3 suited board cards
            board_bits = int(np.bitwise_or.reduce(1 << (boards[i][suits[i] == s] >> 2)))
            v[i] = np.maximum(v[i], FLUSH[board_bits | _PAIR_SUIT_BITS[s]])
    v[HAS[boards].any(axis=1)] = -1
    return v


def percentiles(scores):
    """Per row, each valid holding's strength percentile among the valid ones (midrank)."""
    n = scores.shape[0]
    shifted = scores + (np.arange(n, dtype=np.int64)[:, None] << 25)
    flat = np.sort(shifted, axis=None)
    lo = np.searchsorted(flat, shifted, "left") - np.arange(n)[:, None] * NH
    hi = np.searchsorted(flat, shifted, "right") - np.arange(n)[:, None] * NH
    invalid = (scores < 0).sum(axis=1, keepdims=True)
    valid = NH - invalid
    pct = ((lo + hi) * 0.5 - invalid) / valid
    return np.where(scores >= 0, pct, 0.0)


# ================================================================== preflop classes
def _class_key(combo):
    """Ranks high to low plus the suit pattern, minimised over orderings of equal ranks."""
    cs = sorted(combo, key=lambda x: -(x >> 2))
    ranks = tuple(x >> 2 for x in cs)
    patterns = []
    for perm in permutations(cs):
        if tuple(x >> 2 for x in perm) == ranks:
            relabel = {}
            patterns.append(tuple(relabel.setdefault(x & 3, len(relabel)) for x in perm))
    return ranks, min(patterns)


def _preflop_classes():
    """Class id (0..1754) for every sorted 3-card combo, keyed by suit isomorphism."""
    keys = {}
    cube = np.zeros((52, 52, 52), dtype=np.int16)
    for combo in combinations(range(52), 3):
        cube[combo] = keys.setdefault(_class_key(combo), len(keys))
    return cube, len(keys)


_PRE_CUBE, N_PREFLOP = _preflop_classes()
N_BUCKETS = (N_PREFLOP,) + N_BUCKETS[1:]


def preflop_class(cards):
    a, b, c = sorted(cards)
    return int(_PRE_CUBE[a, b, c])


def preflop_class_batch(hole):
    """hole: (n, 3) int array -> (n,) class ids."""
    h = np.sort(hole, axis=1)
    return _PRE_CUBE[h[:, 0], h[:, 1], h[:, 2]].astype(np.int64)


# ================================================================== flop features
class FlopTable:
    """Keep scores for one flop: S[h] = mean percentile of holding h over runouts,
    V[h] = its spread, and RATIONAL[d, h] = holding h is a sensible keep for a
    player who threw card d.  Runouts come from an RNG seeded by the flop, so the
    trainer and the bot compute exactly the same table."""

    def __init__(self, flop):
        self.flop = tuple(sorted(int(c) for c in flop))
        a, b, c = self.flop
        rng = np.random.default_rng(1 + a * 2704 + b * 52 + c)
        rest = np.setdiff1d(np.arange(52), self.flop)
        picks = np.argsort(rng.random((FLOP_RUNOUTS, rest.size)), axis=1)[:, :2]
        boards = np.hstack((np.tile(self.flop, (FLOP_RUNOUTS, 1)), rest[picks]))
        scores = rank_boards(boards)
        pct = percentiles(scores)
        ok = scores >= 0
        seen = np.maximum(ok.sum(axis=0), 1)
        self.S = (pct * ok).sum(axis=0) / seen
        self.V = np.sqrt(np.maximum((pct * pct * ok).sum(axis=0) / seen - self.S ** 2, 0.0))
        self.valid = ~HAS[list(self.flop)].any(axis=0)
        alt = np.maximum(self.S[PID[PA[None, :], np.arange(52)[:, None]]],
                         self.S[PID[PB[None, :], np.arange(52)[:, None]]])
        self.RATIONAL = self.S[None, :] + KEEP_MARGIN >= alt     # (52, 1326)

    def keep(self, hole):
        """(kept holding id, discarded card) maximising S."""
        options = [(PID[hole[(i + 1) % 3], hole[(i + 2) % 3]], hole[i]) for i in range(3)]
        return max(options, key=lambda o: self.S[o[0]])

    def keep_batch(self, hole):
        """hole (n, 3) -> kept holding ids (n,), discarded cards (n,)."""
        ids = np.stack([PID[hole[:, 1], hole[:, 2]], PID[hole[:, 0], hole[:, 2]],
                        PID[hole[:, 0], hole[:, 1]]], axis=1)
        best = np.argmax(self.S[ids], axis=1)
        rows = np.arange(len(hole))
        return ids[rows, best], hole[rows, best]

    def opponent_holdings(self, opp_discard, dead):
        """Holdings the opponent plausibly kept, given its discard and the cards we know."""
        w = self.valid & self.RATIONAL[opp_discard] & ~HAS[opp_discard]
        for c in dead:
            w &= ~HAS[c]
        return w


def strength_vs(scores, mine, w):
    """Fraction of holdings in w (bool, 1326) that holding `mine` beats on each board row.
    scores: (n, 1326).  Ties count half; holdings overlapping a board are skipped."""
    me = scores[:, mine][:, None]
    ok = w[None, :] & (scores >= 0)
    win = ((me > scores) & ok).sum(axis=1) + 0.5 * ((me == scores) & ok).sum(axis=1)
    return win / np.maximum(ok.sum(axis=1), 1)


def turn_features(board4, mine, w, known):
    """(mean, spread) over river cards of the hand strength against w.
    known: every card the player has seen (its 3 hole cards, both discards, board)."""
    rivers = np.setdiff1d(np.arange(52), list(known))
    scores = rank_boards(np.hstack((np.tile(board4, (rivers.size, 1)), rivers[:, None])))
    hs = strength_vs(scores, mine, w)
    return float(hs.mean()), float(hs.std())


def river_feature(board5, mine, w):
    return float(strength_vs(rank_boards(board5), mine, w)[0])


# ================================================================== buckets
def bucket_1d(x, edges):
    return int(np.searchsorted(edges, x, "right"))


def bucket_2d(x, y, edges_x, edges_y):
    """edges_y[i] are the inner edges inside outer bin i."""
    i = bucket_1d(x, edges_x)
    return i * (edges_y.shape[1] + 1) + bucket_1d(y, edges_y[i])



# ================================================================== betting DAG
class Node:
    """A public state.  kind: 'act' (player to move), 'fold' or 'show' (terminal)."""
    __slots__ = ("id", "kind", "street", "player", "commit", "bets", "raises", "last_raise",
                 "seq", "actions", "amounts", "children", "key")

    def __init__(self, kind, street, player, commit, bets, raises, last_raise, seq, key):
        self.kind, self.street, self.player = kind, street, player
        self.commit, self.bets = commit, bets
        self.raises, self.last_raise, self.seq, self.key = raises, last_raise, seq, key
        self.actions, self.amounts, self.children = [], [], []

    @property
    def pot(self):
        return self.commit[0] + self.commit[1]

    def to_call(self):
        return self.bets[1 - self.player] - self.bets[self.player]


def raise_options(street, raises, pot, to_call, opp_bet, my_bet, my_stack, last_raise):
    """[(code, raise_to)] for the abstract raises legal here, all-in last."""
    if my_stack <= to_call or raises >= MAX_RAISES:
        return []
    all_in = my_bet + my_stack
    min_to = min(opp_bet + max(last_raise, BB), all_in)
    out, used = [], set()
    sizes = (PRE_SIZES if street == PREFLOP else POST_SIZES).get(raises, ())
    for f in sizes:
        to = max(opp_bet + int(round(f * (pot + to_call))), min_to)
        if to > ALLIN_SNAP * all_in or to in used:
            continue
        used.add(to)
        out.append(("r%g" % f, to))
    out.append(("a", all_in))
    return out


def build_tree():
    """All public states of the abstract game.  Returns (nodes, root id)."""
    nodes, index = [], {}

    def make(kind, street, player, commit, bets, raises, last_raise, seq, key):
        if key in index:
            return index[key]
        node = Node(kind, street, player, commit, bets, raises, last_raise, seq, key)
        node.id = len(nodes)
        nodes.append(node)
        index[key] = node.id
        if kind == "act":
            expand(node)
        return node.id

    def street_start(street, c, aggressor):
        if c >= STACK or street > RIVER:
            return make("show", RIVER, -1, (c, c), (0, 0), 0, 0, (), ("show", c))
        return make("act", street, 1, (c, c), (0, 0), 0, 0, (), (street, c, aggressor, ()))

    def expand(node):
        p, s = node.player, node.street
        my_bet, opp_bet = node.bets[p], node.bets[1 - p]
        to_call = opp_bet - my_bet
        my_stack = STACK - node.commit[p]
        base = node.key[:3] if s > PREFLOP else (PREFLOP,)
        if to_call > 0:
            node.actions.append("f")
            node.amounts.append(None)
            node.children.append(make("fold", s, p, tuple(node.commit), node.bets, 0, 0,
                                      node.seq + ("f",), ("fold", node.key, p)))
        # check or call
        commit = list(node.commit)
        commit[p] += to_call
        bets = list(node.bets)
        bets[p] = opp_bet
        node.actions.append("c")
        node.amounts.append(opp_bet)
        if node.seq:                                      # a call, or a second check, ends the street
            node.children.append(street_start(s + 1, commit[0], _last_aggressor(node.seq, s)))
        else:
            node.children.append(make("act", s, 1 - p, tuple(commit), tuple(bets), node.raises,
                                      node.last_raise, ("c",), base + (("c",),)))
        for code, to in raise_options(s, node.raises, node.pot, to_call, opp_bet, my_bet,
                                      my_stack, node.last_raise):
            commit = list(node.commit)
            commit[p] += to - my_bet
            bets = list(node.bets)
            bets[p] = to
            seq = node.seq + (code,)
            node.actions.append(code)
            node.amounts.append(to)
            node.children.append(make("act", s, 1 - p, tuple(commit), tuple(bets), node.raises + 1,
                                      max(to - opp_bet, node.last_raise), seq, base + (seq,)))

    root = make("act", PREFLOP, 0, (SB, BB), (SB, BB), 1, BB, (), (PREFLOP, ()))
    return nodes, root


def _last_aggressor(seq, street):
    """1 + seat of whoever made the last raise in this street's seq, else 0."""
    first = 0 if street == PREFLOP else 1
    for i in range(len(seq) - 1, -1, -1):
        if seq[i] not in ("c", "f"):
            return 1 + (first + i) % 2
    return 0


def fold_payoff(node):
    """Chips won by seat 0 at a fold terminal (node.player is the folder)."""
    folder = node.player
    won = node.commit[folder]
    return -won if folder == 0 else won


def decision_layout(nodes, n_buckets):
    """Offsets of each decision node's (buckets x actions) block in a flat table."""
    offsets = np.full(len(nodes), -1, dtype=np.int64)
    total = 0
    for n in nodes:
        if n.kind == "act":
            offsets[n.id] = total
            total += n_buckets[n.street] * len(n.actions)
    return offsets, total
