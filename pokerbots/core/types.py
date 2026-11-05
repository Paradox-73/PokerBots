"""Protocol-independent data types shared by the engine, adapter and bots.

Bots only ever see these objects.  The protocol adapter
(pokerbots/engine/protocol.py) is the only code that turns wire text into
them, so the official protocol can be swapped in without touching bots.
"""

from dataclasses import dataclass, field
from typing import List, Optional

FOLD, CHECK, CALL, RAISE = "fold", "check", "call", "raise"
ACTION_KINDS = (FOLD, CHECK, CALL, RAISE)


@dataclass(frozen=True)
class Action:
    kind: str                 # one of ACTION_KINDS
    amount: int = 0           # RAISE: total street commitment ("raise to")

    @staticmethod
    def fold():
        return Action(FOLD)

    @staticmethod
    def check():
        return Action(CHECK)

    @staticmethod
    def call():
        return Action(CALL)

    @staticmethod
    def raise_to(amount):
        return Action(RAISE, int(amount))


@dataclass
class GameInfo:
    num_hands: int
    time_bank: float
    starting_stack: int
    small_blind: int
    big_blind: int


@dataclass
class Event:
    """Something that happened in the current hand, as seen by one bot.

    kind: "post" | "act" | "board" | "discard" | "show"
    act: amount = the actor's street total after a call/raise.
    discard: cards = [the discarded card].
    """
    kind: str
    street: int
    seat: int = -1
    action: str = ""          # for kind == "act": an ACTION_KINDS value
    amount: int = 0
    cards: List[int] = field(default_factory=list)


@dataclass
class HandView:
    """Everything a bot knows about the current hand."""
    hand_no: int
    my_seat: int
    button: int
    hole: List[int]
    num_hands: int
    board: List[int] = field(default_factory=list)
    street: int = 0                       # index into rules.STREETS
    history: List[Event] = field(default_factory=list)
    # filled in on every decision request
    pot: int = 0                          # all chips committed, incl. current bets
    my_stack: int = 0                     # chips behind
    opp_stack: int = 0
    my_bet: int = 0                       # committed on this street
    opp_bet: int = 0
    to_call: int = 0
    legal: frozenset = frozenset()        # subset of ACTION_KINDS
    min_raise: int = 0                    # raise-to bounds (0 if no raise)
    max_raise: int = 0
    time_bank: float = 0.0                # seconds left in my bank
    opp_cards: Optional[List[int]] = None  # set at showdown
    dead: List[int] = field(default_factory=list)  # both discards, once revealed

    @property
    def opp_seat(self):
        return 1 - self.my_seat

    @property
    def is_button(self):
        return self.my_seat == self.button

    @property
    def hands_remaining(self):
        """Hands left including this one (hand_no is 1-based)."""
        return max(1, self.num_hands - self.hand_no + 1)
