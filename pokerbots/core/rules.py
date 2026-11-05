"""Every variant-specific assumption lives in this one module.

Values follow the official Discard Hold'em rulebook (docs/rulebook.pdf,
Section 4): heads-up no-limit Hold'em, 3 hole cards, and after the flop
betting each player discards one hole card face up, simultaneously.
200-chip stacks reset every hand, blinds 1/2, at most 4 bets/raises per street.

The evaluator, equity calculator, engine and bots all read their constants
from here:

  * deck              -> RANKS, SUITS, (build_deck)
  * dealing           -> HOLE_CARDS, STREETS
  * discard           -> DISCARD_STREET, KEEP_CARDS, default_discard()
  * money             -> STARTING_STACK, SMALL_BLIND, BIG_BLIND, ANTE,
                         RESET_STACKS_EACH_HAND
  * betting           -> BETTING, MAX_RAISES_PER_STREET, raise_bounds(),
                         first_to_act(), blinds()
  * hand ranking      -> HAND_SIZE, HAND_COMPOSITION, ACE_LOW_STRAIGHT,
                         CATEGORY_ORDER, hand_value()
  * match format      -> HANDS_PER_MATCH, TIME_BANK_SECONDS,
                         PER_RESPONSE_SECONDS, MATCH_CHIP_CAP

Python 3.11 compatible; stdlib only.
"""

# --------------------------------------------------------------------- deck
RANKS = "23456789TJQKA"          # weakest -> strongest
SUITS = "cdhs"
NUM_RANKS = len(RANKS)
NUM_SUITS = len(SUITS)
DECK_SIZE = NUM_RANKS * NUM_SUITS

# ------------------------------------------------------------------ dealing
NUM_PLAYERS = 2
HOLE_CARDS = 3
# (street name, number of NEW board cards dealt at the start of that street)
STREETS = (("preflop", 0), ("flop", 3), ("turn", 1), ("river", 1))
BOARD_CARDS = sum(n for _, n in STREETS)
STREET_NAMES = tuple(name for name, _ in STREETS)

# ------------------------------------------------------------------ discard
DISCARD_STREET = 1                # discard after this street's betting (flop)
KEEP_CARDS = 2                    # hole cards left after the discard
# order in which equal-rank cards are auto-discarded: spades, hearts, diamonds, clubs
DISCARD_SUIT_ORDER = "shdc"

# -------------------------------------------------------------------- money
STARTING_STACK = 200
SMALL_BLIND = 1
BIG_BLIND = 2
ANTE = 0
RESET_STACKS_EACH_HAND = True

# ------------------------------------------------------------------ betting
BETTING = "no-limit"              # "no-limit" | "pot-limit" | "fixed-limit"
MAX_RAISES_PER_STREET = 4         # bets+raises per street; the big blind is the first preflop

# ------------------------------------------------------------- hand ranking
HAND_SIZE = 5                     # a made hand is the best HAND_SIZE cards
# None -> best HAND_SIZE cards from hole+board in any mix (Hold'em).
# (h, b) -> must use exactly h hole cards and b board cards (Omaha = (2, 3)).
HAND_COMPOSITION = None
ACE_LOW_STRAIGHT = True           # A-2-3-4-5 counts as a straight
# Category names, weakest -> strongest.  Reorder for variants such as
# short-deck (where "flush" beats "full_house").  Names must stay the same.
CATEGORY_ORDER = (
    "high_card", "pair", "two_pair", "trips", "straight",
    "flush", "full_house", "quads", "straight_flush",
)

# ------------------------------------------------------------ match format
HANDS_PER_MATCH = 400             # Stage 1: 200 duplicate deals x 2 seatings
TIME_BANK_SECONDS = 60.0          # cumulative per bot per match (Stage 2: 150 s / ~1000 hands)
PER_RESPONSE_SECONDS = 5.0        # any single reply
STARTUP_SECONDS = 5.0             # from launch, not charged to any reply or the bank
MATCH_CHIP_CAP = 400              # tie-break clips each MATCH's net chips to +-C (Stage 2: 1000)


# ================================================================ functions
def build_deck():
    """Card ids 0..DECK_SIZE-1; id = rank_index * NUM_SUITS + suit_index."""
    return list(range(DECK_SIZE))


def first_to_act(street_index, button):
    """Heads-up: button (= small blind) acts first preflop, last afterwards."""
    return button if street_index == 0 else 1 - button


def blinds(button):
    """Forced bets posted at the start of a hand: {seat: amount}."""
    return {button: SMALL_BLIND, 1 - button: BIG_BLIND}


def street_bet_size(street_index):
    """Fixed-limit only: small bet on first two streets, big bet afterwards."""
    return BIG_BLIND if street_index <= 1 else 2 * BIG_BLIND


def raise_bounds(street_index, max_bet, my_bet, my_stack, last_raise, pot,
                 raises_this_street):
    """Return (min_raise_to, max_raise_to) for a raise, or None if no raise.

    All amounts are "raise TO", i.e. the player's total commitment on this
    street after the raise.  `pot` is every chip already committed by both
    players, including current-street bets.
    """
    to_call = max_bet - my_bet
    if my_stack <= to_call or raises_this_street >= MAX_RAISES_PER_STREET:
        return None
    all_in_to = my_bet + my_stack
    if BETTING == "fixed-limit":
        target = min(max_bet + street_bet_size(street_index), all_in_to)
        return target, target
    min_to = min(max_bet + max(last_raise, BIG_BLIND), all_in_to)
    if BETTING == "pot-limit":
        max_to = min(max_bet + pot + to_call, all_in_to)
        return min_to, max(min_to, max_to)
    return min_to, all_in_to


def hand_value(hole, board):
    """Showdown strength of a player's cards: higher int wins, equal = split."""
    from pokerbots.core import evaluator  # local import: evaluator imports rules
    return evaluator.hand_value(hole, board)


def default_discard(hole):
    """The card the engine discards for a bot whose discard is illegal or missing:
    lowest rank; among equal ranks, the first suit in DISCARD_SUIT_ORDER."""
    return min(hole, key=lambda c: (c // NUM_SUITS, DISCARD_SUIT_ORDER.index(SUITS[c % NUM_SUITS])))
