"""Range-aware strategy built on the equity bot's clock, lock-in and station read.

Two things replace the equity bot's:
  * equity: the opponent holds three unknown cards and keeps its best two; a raise
    narrows it in proportion to the raise's size, and its shown discard reweights
    hands (core.equity.range_equity).
  * betting: thin value bets, bluffs scaled to how often this opponent folds, mixed
    actions, and bet sizes that grow with strength.
"""

import time

import numpy as np

from pokerbots.bots.equity_bot import EquityBot
from pokerbots.bots.simple import bet_to
from pokerbots.core import rules
from pokerbots.core.equity import range_equity
from pokerbots.core.evaluator import category_of, hand_value
from pokerbots.core.types import Action, CALL, CHECK, FOLD, RAISE


class RangeBot(EquityBot):
    name = "range"

    SAMPLES_PREFLOP, SAMPLES_POSTFLOP, MIN_SAMPLES = 1200, 1600, 150
    PRESSURE_CAP = 3.5
    OPEN_AT, BIG_OPEN_AT = 0.505, 0.60
    REFOLD_PRIOR = 0.4
    ALL_IN_MARGIN = 0.01          # equity above the price needed to call an all-in
    MIN_RARITY = 0.15             # the least a preflop raise can ever mean
    TYPICAL_RARITY = 2.0 / 0.3 - 2.0   # the value for a bot raising 30% of hands

    def __init__(self, seed=None):
        super().__init__(seed)
        self.sample_cost = 40e-6       # seconds per sample, measured as we go
        self.bluff_shows = 0.0         # postflop raises of theirs that reached showdown
        self.bluffs_shown = 0.0        # of those, how many were weak hands

    # ---------------------------------------------------------------- reading
    def on_hand_end(self, view, my_delta):
        if view.opp_cards and len(view.board) == rules.BOARD_CARDS \
                and any(self.model.raises_this_hand.get(s) for s in (1, 2, 3)):
            kind = category_of(hand_value(view.opp_cards, view.board))
            self.bluff_shows += 1.0
            self.bluffs_shown += {"high_card": 1.0, "pair": 0.5}.get(kind, 0.0)
        super().on_hand_end(view, my_delta)

    def trust(self):
        """How much to believe the opponent's raises: less once it has shown bluffs."""
        rate = (self.bluffs_shown + 0.8) / (self.bluff_shows + 4.0)
        return float(np.clip(1.35 - 1.5 * rate, 0.45, 1.25))

    def preflop_raise_signal(self, size):
        """What one preflop raise says, discounted by how often this opponent raises:
        a bot that raises most hands tells us little by raising this one."""
        often = max(self.model.pfr(), 0.05)
        rarity = min(1.0, max(self.MIN_RARITY, (2.0 / often - 2.0) / self.TYPICAL_RARITY))
        return min(1.2, 0.1 + 0.3 * size) * rarity

    def opponent_pressure(self, view):
        """Evidence of strength in this hand so far, from the sizes of the opponent's
        raises and from its checks."""
        bets = {view.button: rules.SMALL_BLIND, 1 - view.button: rules.BIG_BLIND}
        carried, street, total = 0, 0, 0.0
        for ev in view.history:
            if ev.kind != "act":
                continue
            if ev.street != street:
                carried += 2 * max(bets.values())
                bets, street = {0: 0, 1: 0}, ev.street
            mine, other = bets[ev.seat], bets[1 - ev.seat]
            if ev.seat == view.opp_seat:
                if ev.action == RAISE:
                    size = (ev.amount - mine) / max(1, carried + mine + other + other - mine)
                    total += self.preflop_raise_signal(size) if ev.street == 0 \
                        else min(2.0, 0.35 + 0.9 * size)
                elif ev.action == CHECK and ev.street > 0:
                    total -= 0.25
            if ev.action in (CALL, RAISE):
                bets[ev.seat] = ev.amount
        total = max(-0.6, min(total, self.PRESSURE_CAP))
        return total * self.trust() if total > 0 else total

    # ---------------------------------------------------------------- equity
    def samples(self, view, cap):
        per_second = 1.0 / max(1e-7, self.sample_cost)
        return int(max(self.MIN_SAMPLES, min(cap, self.time_budget(view) * per_second)))

    def _timed_equity(self, view, cap, pressure):
        n = self.samples(view, cap)
        start = time.perf_counter()
        mine = view.dead[0] if view.dead else None
        theirs = view.dead[1] if len(view.dead) == 2 else None
        result = range_equity(view.hole, view.board, n, self.rng,
                              dead=() if mine is None else (mine,), opp_discard=theirs,
                              pressure=pressure)
        cost = (time.perf_counter() - start) / n
        self.sample_cost += 0.3 * (cost - self.sample_cost)
        return result, n

    def estimate_equity(self, view):
        if self.time_budget(view) <= 0.0:
            return self._cheap_strength(view), 0
        cap = self.SAMPLES_PREFLOP if view.street == 0 else self.SAMPLES_POSTFLOP
        result, n = self._timed_equity(view, cap, self.opponent_pressure(view))
        return max(result), n

    def _discard(self, view):
        if self.bank_critical(view) or self.time_budget(view) <= 0.0:
            return super()._discard(view)
        result, _ = self._timed_equity(view, self.SAMPLES_POSTFLOP, self.opponent_pressure(view))
        return view.hole[int(np.argmax(result))]

    # ---------------------------------------------------------------- betting
    def sized(self, view, fraction):
        """A bet of `fraction` pots, moved all-in when it would commit most of the stack."""
        to = bet_to(view, fraction)
        return view.max_raise if to > 0.55 * view.max_raise else to

    def bluff_rate(self):
        return float(np.clip(self.model.fold_to_bet() / self.REFOLD_PRIOR, 0.3, 2.0))

    def choose(self, view, eq):
        action = self.preflop(view, eq) if view.street == 0 else self.postflop(view, eq)
        if view.to_call > 0 and action.kind in (CALL, FOLD) and self.line_in_reach(view):
            return self.match_decision(view, eq, action)
        return action

    def lock_line(self, hands_left):
        """The most that check-folding every remaining hand can lose."""
        return (hands_left + 1) // 2 * rules.BIG_BLIND + hands_left // 2 * rules.SMALL_BLIND

    def win_chance(self, lead, hands_left):
        """Chance of winning the match from this lead, between evenly matched bots: a
        race to the lines where one side can fold out, so it is linear in the lead."""
        line = max(1, self.lock_line(hands_left))
        return min(1.0, max(0.0, (lead + line) / (2.0 * line)))

    def line_in_reach(self, view):
        """True when this pot, won or lost, would carry us past a lock line."""
        at_risk = rules.STARTING_STACK - view.my_stack + view.to_call
        return abs(self.net) + at_risk >= self.lock_line(view.hands_remaining - 1)

    def match_decision(self, view, eq, action):
        """Call or fold by the chance of winning the match.  Past the opponent's lock line
        the chance reads zero, but not every bot locks, so the chip decision stands; it
        stands too if both choices score the same."""
        left = view.hands_remaining - 1
        spent = rules.STARTING_STACK - view.my_stack
        at_risk = spent + view.to_call
        folded = self.win_chance(self.net - spent, left)
        called = eq * self.win_chance(self.net + at_risk, left) \
            + (1.0 - eq) * self.win_chance(self.net - at_risk, left)
        if folded <= 0.0 or called == folded:
            return action
        return Action.call() if called > folded else Action.fold()

    def postflop(self, view, eq):
        roll = self.pyrng.random()
        can_raise = RAISE in view.legal
        bluff = self.bluff_rate()
        river = view.street == rules.STREET_NAMES.index("river")
        if view.to_call > 0:
            price = view.to_call / (view.pot + view.to_call)
            strong = 0.82 if river else 0.78
            if can_raise and eq > strong and roll < 0.75:
                return Action.raise_to(self.sized(view, 0.7 + 2.0 * (eq - strong)))
            if can_raise and not river and 0.18 < eq < 0.34 and roll < 0.06 * bluff \
                    and view.to_call < 0.35 * view.pot:
                return Action.raise_to(self.sized(view, 0.8))
            margin = 0.045 if view.to_call >= view.my_stack else 0.025
            return Action.call() if eq > price + margin else Action.fold()
        if can_raise:
            if eq > 0.68:
                if eq > 0.9 and not river and roll < 0.2:
                    return Action.check()
                return Action.raise_to(self.sized(view, min(1.1, 0.5 + 2.0 * (eq - 0.68))))
            if eq > 0.55 and roll < 0.55:
                return Action.raise_to(self.sized(view, 0.33 + 1.5 * (eq - 0.55)))
            if eq < 0.30 and roll < 0.22 * bluff:
                return Action.raise_to(self.sized(view, 0.6))
            if 0.30 <= eq < 0.47 and not river and roll < 0.2 * bluff:
                return Action.raise_to(self.sized(view, 0.55))
        return Action.check()

    def preflop(self, view, eq):
        roll = self.pyrng.random()
        can_raise = RAISE in view.legal
        price = view.to_call / (view.pot + view.to_call) if view.to_call else 0.0
        if view.opp_bet <= rules.BIG_BLIND:
            if view.to_call > 0:
                if can_raise and eq > self.OPEN_AT:
                    return Action.raise_to(6 if eq < self.BIG_OPEN_AT else 8)
                return Action.call() if eq > price + 0.06 else Action.fold()
            if can_raise and eq > self.OPEN_AT + 0.02:
                return Action.raise_to(7)
            return Action.check()
        if can_raise and eq > self.BIG_OPEN_AT + 0.05 and roll < 0.85:
            return Action.raise_to(view.max_raise if view.opp_bet >= 40 else 3 * view.opp_bet)
        if can_raise and self.OPEN_AT < eq <= self.BIG_OPEN_AT and view.opp_bet <= 8 \
                and roll < 0.12 * self.bluff_rate():
            return Action.raise_to(3 * view.opp_bet)
        if view.to_call >= view.my_stack:   # no later streets, so all our equity is realised
            need = price + self.ALL_IN_MARGIN
        else:
            need = price + 0.04 + 0.01 * min(view.opp_bet / rules.BIG_BLIND, 10.0)
        return Action.call() if eq > need else Action.fold()
