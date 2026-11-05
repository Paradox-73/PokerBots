"""Baseline bots: random, always-call, starter, maniac, tight-aggressive rule bot."""

import random

from pokerbots.bots.base import Bot
from pokerbots.bots.common import flush_draw, made_hand, preflop_percentile, CATEGORY_RANK
from pokerbots.core import rules
from pokerbots.core.types import Action, CALL, CHECK, FOLD, RAISE


class RandomBot(Bot):
    """Uniform over legal action kinds; raise sizes skewed toward the minimum."""
    name = "random"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def act(self, view):
        kind = self.rng.choice(sorted(view.legal))
        if kind == RAISE:
            u = self.rng.random() ** 3
            return Action.raise_to(view.min_raise + u * (view.max_raise - view.min_raise))
        return Action(kind)


class CallBot(Bot):
    """Always check or call."""
    name = "call"

    def act(self, view):
        return Action.call() if CALL in view.legal else Action.check()


class StarterBot(CallBot):
    """The organisers' starter bot: check/call, discard the lowest rank."""
    name = "starter"

    def discard(self, view):
        return min(view.hole, key=lambda c: c // rules.NUM_SUITS)


class ManiacBot(Bot):
    """Raises a pot-sized bet most of the time, calls the rest; never folds."""
    name = "maniac"

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def act(self, view):
        if RAISE in view.legal and self.rng.random() < 0.7:
            return Action.raise_to(bet_to(view, 1.0))
        return Action.call() if CALL in view.legal else Action.check()


def bet_to(view, fraction):
    """Raise-to amount for a bet/raise of `fraction` x pot (after calling)."""
    target = view.opp_bet + int(fraction * (view.pot + view.to_call))
    return max(view.min_raise, min(view.max_raise, target))


class TagBot(Bot):
    """Tight-aggressive rules.

    Preflop: raise top ~20%, call top ~45% for a small price, re-raise top 6%.
    Postflop: bet/raise two pair+ and strong pairs, call medium pairs and
    flush draws at decent pot odds, otherwise check/fold.
    """
    name = "tag"

    def act(self, view):
        if view.street == 0:
            return self._preflop(view)
        return self._postflop(view)

    def _preflop(self, view):
        pct = preflop_percentile(view.hole)
        legal = view.legal
        facing_raise = view.opp_bet > 2 * view.my_bet and view.opp_bet > 2
        if pct >= 0.94 and RAISE in legal:
            return Action.raise_to(bet_to(view, 1.0 if facing_raise else 0.75))
        if pct >= 0.80 and RAISE in legal and not facing_raise:
            return Action.raise_to(bet_to(view, 0.75))
        if CHECK in legal:
            return Action.check()
        price = view.to_call / max(1, view.pot + view.to_call)
        if pct >= 0.80 or (pct >= 0.55 and price <= 0.34 and view.to_call <= 6):
            return Action.call()
        return Action.fold()

    def _postflop(self, view):
        cat, bcat, _ = made_hand(view.hole, view.board)
        legal = view.legal
        improves = cat > bcat
        strong = improves and cat >= CATEGORY_RANK["two_pair"]
        pair_rank = CATEGORY_RANK["pair"]
        top_pair = False
        if improves and cat == pair_rank:
            ns = rules.NUM_SUITS
            board_hi = max(c // ns for c in view.board)
            top_pair = any(c // ns >= board_hi for c in view.hole)
        price = view.to_call / max(1, view.pot + view.to_call)
        if strong or (top_pair and view.to_call <= view.pot // 2):
            if RAISE in legal and (strong or view.to_call == 0):
                return Action.raise_to(bet_to(view, 0.7))
            return Action.call() if CALL in legal else Action.check()
        if view.to_call == 0:
            return Action.check()
        if (improves and cat == pair_rank and price <= 0.3) or \
                (flush_draw(view.hole, view.board) and view.street < 3 and price <= 0.25):
            return Action.call()
        return Action.fold() if FOLD in legal else Action.check()
