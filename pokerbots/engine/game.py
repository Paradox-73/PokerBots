"""Heads-up hand state machine.  Protocol-free; all variant facts from rules.

Seats are match-player indices 0 and 1.  `button` is the seat on the button.
Events are appended to `HandState.events` as tuples so the runner can
broadcast them:

  ("post",    street, seat, amount)
  ("act",     street, seat, kind, amount)   amount = street total after call/raise
  ("board",   street, cards_so_far)
  ("discard", street, seat, card)           both appended together, once revealed
  ("show",    street, seat, hole_cards)

After the betting on rules.DISCARD_STREET ends with nobody folded (all-in
included), `need_discard` is True and the hand waits for discard().
"""

import random
from dataclasses import dataclass
from typing import List

from pokerbots.core import rules
from pokerbots.core.types import Action, FOLD, CHECK, CALL, RAISE


@dataclass
class Deal:
    hole: List[List[int]]   # by POSITION: [0] = button's cards, [1] = other
    board: List[int]        # all board cards in dealing order


def make_deal(seed, deal_index):
    """Deterministic deal; the same (seed, index) gives the same cards."""
    rng = random.Random("%s:%s" % (seed, deal_index))
    deck = rules.build_deck()
    rng.shuffle(deck)
    h = rules.HOLE_CARDS
    hole = [deck[i * h:(i + 1) * h] for i in range(rules.NUM_PLAYERS)]
    start = rules.NUM_PLAYERS * h
    return Deal(hole, deck[start:start + rules.BOARD_CARDS])


@dataclass
class Legal:
    to_call: int
    kinds: frozenset
    min_raise: int
    max_raise: int


class HandState:
    def __init__(self, deal, button, stacks=None):
        if stacks is None:
            stacks = [rules.STARTING_STACK] * 2
        self.button = button
        self.hole = [None, None]
        self.hole[button] = list(deal.hole[0])
        self.hole[1 - button] = list(deal.hole[1])
        self.full_board = list(deal.board)
        self.board = []
        self.start_stacks = list(stacks)
        self.stacks = list(stacks)
        self.bets = [0, 0]
        self.contrib = [0, 0]
        self.street = 0
        self.events = []
        self.terminal = False
        self.deltas = None
        self.showdown = False
        self.illegal = [0, 0]
        self.discards = None              # [card of seat 0, card of seat 1] once made
        self.need_discard = False
        self._new_street_state()
        if rules.ANTE:
            for seat in (0, 1):
                amt = min(rules.ANTE, self.stacks[seat])
                self.stacks[seat] -= amt
                self.contrib[seat] += amt
                self.events.append(("post", 0, seat, amt))
        for seat, amt in sorted(rules.blinds(button).items(), key=lambda kv: kv[1]):
            amt = min(amt, self.stacks[seat])
            self._put(seat, amt)
            self.events.append(("post", 0, seat, amt))
        self.last_raise = rules.BIG_BLIND
        self.raises = 1                   # the big blind is the first raise preflop
        self.to_act = rules.first_to_act(0, button)
        if min(self.stacks) == 0 and self.bets[0] == self.bets[1]:
            self._finish_street()

    # ----------------------------------------------------------- helpers
    def _new_street_state(self):
        self.bets = [0, 0]
        self.acted = [False, False]
        self.last_raise = rules.BIG_BLIND
        self.raises = 0

    def _put(self, seat, amt):
        self.stacks[seat] -= amt
        self.bets[seat] += amt
        self.contrib[seat] += amt

    @property
    def pot(self):
        return self.contrib[0] + self.contrib[1]

    def legal(self, seat=None):
        seat = self.to_act if seat is None else seat
        to_call = max(self.bets) - self.bets[seat]
        kinds = set()
        if to_call > 0:
            kinds.update((FOLD, CALL))
        else:
            kinds.add(CHECK)
        lo = hi = 0
        if self.stacks[1 - seat] > 0:
            b = rules.raise_bounds(self.street, max(self.bets), self.bets[seat],
                                   self.stacks[seat], self.last_raise, self.pot,
                                   self.raises)
            if b is not None:
                kinds.add(RAISE)
                lo, hi = b
        return Legal(to_call, frozenset(kinds), lo, hi)

    def sanitize(self, action, seat=None):
        """Map an illegal/garbled action to check (if legal) else fold."""
        legal = self.legal(seat)
        if isinstance(action, Action) and action.kind in legal.kinds:
            if action.kind != RAISE:
                return action, True
            if legal.min_raise <= action.amount <= legal.max_raise:
                return action, True
        return (Action.check() if CHECK in legal.kinds else Action.fold()), False

    # ------------------------------------------------------------ actions
    def apply(self, action):
        """Apply `action` for the player to act.  Returns the action used."""
        assert not self.terminal and not self.need_discard
        seat = self.to_act
        action, ok = self.sanitize(action, seat)
        if not ok:
            self.illegal[seat] += 1
        other = 1 - seat
        if action.kind == FOLD:
            self.events.append(("act", self.street, seat, FOLD, 0))
            self._award([other])
            return action
        if action.kind == CHECK:
            self.events.append(("act", self.street, seat, CHECK, 0))
        elif action.kind == CALL:
            amt = min(max(self.bets) - self.bets[seat], self.stacks[seat])
            self._put(seat, amt)
            self.events.append(("act", self.street, seat, CALL, self.bets[seat]))
        else:
            prev_max = max(self.bets)
            self._put(seat, action.amount - self.bets[seat])
            self.last_raise = action.amount - prev_max
            self.raises += 1
            self.acted[other] = False
            self.events.append(("act", self.street, seat, RAISE, action.amount))
        self.acted[seat] = True

        if self._needs_action(other):
            self.to_act = other
        elif self._needs_action(seat):
            self.to_act = seat
        else:
            self._finish_street()
        return action

    def _needs_action(self, seat):
        if self.stacks[seat] == 0:
            return False
        if self.stacks[1 - seat] == 0 and self.bets[seat] >= self.bets[1 - seat]:
            return False
        return (not self.acted[seat]) or self.bets[seat] < max(self.bets)

    def _finish_street(self):
        # return an uncalled part of a bet
        hi = 0 if self.bets[0] > self.bets[1] else 1
        excess = self.bets[hi] - self.bets[1 - hi]
        if excess > 0:
            self.stacks[hi] += excess
            self.bets[hi] -= excess
            self.contrib[hi] -= excess
        self._advance()

    def _advance(self):
        run_out = min(self.stacks) == 0
        while True:
            if self.street == rules.DISCARD_STREET and self.discards is None:
                self.need_discard = True
                return
            if self.street + 1 >= len(rules.STREETS):
                self._showdown()
                return
            self.street += 1
            n_new = rules.STREETS[self.street][1]
            if n_new:
                self.board = self.full_board[:len(self.board) + n_new]
                self.events.append(("board", self.street, list(self.board)))
            self._new_street_state()
            if not run_out:
                self.to_act = rules.first_to_act(self.street, self.button)
                return

    def discard(self, cards):
        """cards[seat] = the hole card that seat discards; anything that is not
        one of its hole cards becomes rules.default_discard.  Returns the
        cards used."""
        assert self.need_discard
        used = []
        for seat in (0, 1):
            c = cards[seat]
            if c not in self.hole[seat]:
                self.illegal[seat] += 1
                c = rules.default_discard(self.hole[seat])
            used.append(c)
        for seat in (0, 1):
            self.hole[seat].remove(used[seat])
            self.events.append(("discard", self.street, seat, used[seat]))
        self.discards = used
        self.need_discard = False
        self._advance()
        return used

    def _showdown(self):
        self.showdown = True
        values = []
        for seat in (0, 1):
            self.events.append(("show", self.street, seat, list(self.hole[seat])))
            values.append(rules.hand_value(self.hole[seat], self.board))
        best = max(values)
        self._award([s for s in (0, 1) if values[s] == best])

    def _award(self, winners):
        pot = self.pot
        final = [self.stacks[0], self.stacks[1]]
        share, odd = divmod(pot, len(winners))
        for w in winners:
            final[w] += share
        if odd:  # odd chip to the out-of-position player
            final[1 - self.button if (1 - self.button) in winners else winners[0]] += odd
        self.deltas = [final[s] - self.start_stacks[s] for s in (0, 1)]
        self.terminal = True
