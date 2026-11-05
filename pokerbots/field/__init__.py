"""Practice opponents for local measurement.  Never shipped: build_submission.py
copies only the core and bots folders.  Importing this module registers them."""

import random

import numpy as np

from pokerbots.bots import EXTRA
from pokerbots.bots.base import Bot
from pokerbots.bots.common import CATEGORY_RANK, made_hand, preflop_percentile
from pokerbots.bots.range_bot import RangeBot
from pokerbots.bots.simple import CallBot, TagBot, bet_to
from pokerbots.core import rules
from pokerbots.core.equity import equity_vs_discarder, equity_vs_random
from pokerbots.core.types import Action, CALL, CHECK, RAISE
from pokerbots.field.river import river_action


class FoldBot(Bot):
    """Folds whenever it faces a bet."""
    name = "fold"

    def act(self, view):
        return Action.check() if CHECK in view.legal else Action.fold()


class ShoveBot(Bot):
    """All-in with every hand."""
    name = "shove"

    def act(self, view):
        if RAISE in view.legal:
            return Action.raise_to(view.max_raise)
        return Action.call() if CALL in view.legal else Action.check()


class NitBot(ShoveBot):
    """Plays only the top 12% of starting hands, and plays them all-in."""
    name = "nit"

    def act(self, view):
        if view.dead or preflop_percentile(view.hole) >= 0.88:
            return super().act(view)
        return Action.check() if CHECK in view.legal else Action.fold()


class MinRaiseBot(Bot):
    """Always makes the smallest legal raise, else calls."""
    name = "minraise"

    def act(self, view):
        if RAISE in view.legal:
            return Action.raise_to(view.min_raise)
        return Action.call() if CALL in view.legal else Action.check()


class LooseBot(Bot):
    """Raises 20% of the time, calls 60% of bets, discards at random."""
    name = "loose"
    SIZES = (0.5, 0.75, 1.0, 2.0)

    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def act(self, view):
        roll = self.rng.random()
        if RAISE in view.legal and roll < 0.2:
            return Action.raise_to(bet_to(view, self.rng.choice(self.SIZES)))
        if CHECK in view.legal:
            return Action.check()
        return Action.call() if roll < 0.8 else Action.fold()

    def discard(self, view):
        return self.rng.choice(view.hole)


class ScaredBot(CallBot):
    """Overfolds: never raises, and folds to any postflop bet unless its hole cards
    improve the board."""
    name = "scared"

    def act(self, view):
        if view.to_call == 0 or view.street == 0:
            return super().act(view)
        cat, bcat, _ = made_hand(view.hole, view.board)
        return Action.call() if cat > bcat else Action.fold()


class JammerBot(ShoveBot):
    """Moves all-in preflop with the top 40% of hands and folds the rest to a raise."""
    name = "jammer"

    def act(self, view):
        if view.dead or preflop_percentile(view.hole) >= 0.60:
            return super().act(view)
        return Action.check() if CHECK in view.legal else Action.fold()


class BarrelBot(Bot):
    """Bets 3/4 pot whenever checked to, with any hand, and folds to a raise on the river."""
    name = "barrel"

    def act(self, view):
        if view.to_call == 0 and RAISE in view.legal:
            return Action.raise_to(bet_to(view, 0.75))
        if view.street == 3 and view.to_call > 0:
            return Action.fold()
        return Action.call() if CALL in view.legal else Action.check()


class PassiveBot(CallBot):
    """Calls with almost everything, and raises only with two pair or better."""
    name = "passive"

    def act(self, view):
        if view.street > 0 and RAISE in view.legal:
            cat, bcat, _ = made_hand(view.hole, view.board)
            if cat > bcat and cat >= CATEGORY_RANK["two_pair"]:
                return Action.raise_to(bet_to(view, 1.0))
        return super().act(view)


# ------------------------------------------------- the kinds of bot entrants write
class SimpleEquity(Bot):
    """The usual first entry: Monte Carlo against a random hand and pot odds.
    Thresholds are class constants, so each subclass is another entrant's tuning."""
    name = "mc"
    ROLLOUTS = 200
    RAISE_AT = 0.70
    SIZE = 0.75
    CALL_EDGE = 0.0
    BLUFF = 0.0

    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)

    def strength(self, view):
        return equity_vs_random(view.hole, view.board, self.ROLLOUTS, self.rng, view.dead)[0]

    def act(self, view):
        eq = self.strength(view)
        price = view.to_call / max(1, view.pot + view.to_call)
        if RAISE in view.legal and (eq >= self.RAISE_AT or self.rng.random() < self.BLUFF):
            return Action.raise_to(bet_to(view, self.SIZE))
        if view.to_call == 0:
            return Action.check()
        return Action.call() if eq >= price + self.CALL_EDGE else Action.fold()

    def discard(self, view):
        def keep(c):
            cards = [x for x in view.hole if x != c]
            return equity_vs_random(cards, view.board, 150, self.rng, [c])[0]
        return max(view.hole, key=keep)


class TossLowest(SimpleEquity):
    """Same bot with the discard everyone starts with."""
    name = "tosslow"

    def discard(self, view):
        return min(view.hole, key=lambda c: c // rules.NUM_SUITS)


class TightEquity(SimpleEquity):
    name = "tight"
    RAISE_AT = 0.80
    SIZE = 1.0
    CALL_EDGE = 0.10


class LooseEquity(SimpleEquity):
    name = "lag"
    RAISE_AT = 0.58
    SIZE = 1.0
    BLUFF = 0.15


class SmallBall(SimpleEquity):
    """Bets small with anything decent and calls light."""
    name = "smallball"
    RAISE_AT = 0.62
    SIZE = 0.33
    CALL_EDGE = -0.03


class PotOdds(SimpleEquity):
    """Never bluffs and raises only near-certain hands."""
    name = "potodds"
    RAISE_AT = 0.88
    SIZE = 1.0
    ROLLOUTS = 400


class TagBig(TagBot):
    """Tight-aggressive rules with big bets and a wider opening range."""
    name = "tagbig"

    def act(self, view):
        action = super().act(view)
        if action.kind == RAISE:
            return Action.raise_to(bet_to(view, 1.2))
        return action


class Exploiter(SimpleEquity):
    """Built against us.  Reshoves over our opens with a wide range, folds to our big
    bets without a strong hand, and reads our discards as keeping the best made hand."""
    name = "exploiter"
    RAISE_AT = 0.72

    def __init__(self, seed=None):
        super().__init__(seed)
        self.rng = np.random.default_rng(seed)

    def strength(self, view):
        if len(view.dead) == 2:
            return equity_vs_discarder(view.hole, view.board, view.dead[0], view.dead,
                                       self.ROLLOUTS, self.rng,
                                       {"best_made": 0.9, "lowest_rank": 0.0})[0]
        return super().strength(view)

    def act(self, view):
        if view.street == 0 and view.to_call > 1 and RAISE in view.legal \
                and preflop_percentile(view.hole) >= 0.55:
            return Action.raise_to(view.max_raise)
        if view.street > 0 and view.to_call >= 0.6 * max(1, view.pot - view.to_call) \
                and self.strength(view) < 0.8:
            return Action.fold()
        return super().act(view)


class BalancedBot(SimpleEquity):
    """Stands in for a solver entry: mixes actions by strength from a smooth curve,
    and plays the river from a solved table."""
    name = "balanced"
    ROLLOUTS = 300

    def act(self, view):
        eq = self.strength(view)
        if view.street == 3:
            action = river_action(view, eq, self.rng)
            if action is not None and action.kind in view.legal:
                return action
        price = view.to_call / max(1, view.pot + view.to_call)
        bet = 1.0 / (1.0 + np.exp(-(eq - 0.68) / 0.05))
        if RAISE in view.legal and self.rng.random() < bet + 0.06 * (eq < 0.3):
            return Action.raise_to(bet_to(view, float(self.rng.choice((0.5, 0.75, 1.0)))))
        if view.to_call == 0:
            return Action.check()
        return Action.call() if eq >= price + 0.02 else Action.fold()


class Mirror(RangeBot):
    """A second copy of our bot under its own name."""
    name = "mirror"


for _bot in (FoldBot, ShoveBot, NitBot, MinRaiseBot, LooseBot, ScaredBot, JammerBot, BarrelBot,
             PassiveBot, SimpleEquity, TossLowest, TightEquity, LooseEquity, SmallBall, PotOdds,
             TagBig, Exploiter, BalancedBot, Mirror):
    EXTRA[_bot.name] = _bot
