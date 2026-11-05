"""Equity / pot-odds bot with opponent modelling and a time-bank-aware budget.

Decision per action:
  1. Build the opponent's likely range from their preflop action and
     tracked VPIP/PFR, narrowed for each postflop bet they made.
  2. Monte Carlo equity vs that range within a per-decision time budget
     derived from the remaining time bank.
  3. Raise for value when equity is high, call when equity beats the pot
     odds plus a margin, bluff occasionally against players who fold a lot,
     otherwise check/fold.  Thresholds shift with opponent aggression.
  4. Discard: keep the pair of hole cards with the best equity vs a random
     hand on the flop, within the same time budget.
"""

import random
import time

import numpy as np

from pokerbots.bots.base import Bot
from pokerbots.bots.common import made_hand, preflop_percentile, range_weight, top_range
from pokerbots.bots.opponent import OpponentModel
from pokerbots.bots.simple import bet_to
from pokerbots.core import rules
from pokerbots.core.equity import equity_timed, equity_vs_random
from pokerbots.core.types import Action, CHECK, FOLD, RAISE


class EquityBot(Bot):
    name = "equity"

    DECISIONS_PER_HAND = 3.5   # actions + the discard, a high-side average
    BANK_SAFETY = 0.3          # spend at most this share of the spare bank
    MAX_BUDGET = 0.040         # seconds of Monte Carlo per decision
    MIN_BUDGET = 0.002         # below this: no Monte Carlo, cheap heuristic
    CHEAP_COST = 0.002         # what a reply costs us without Monte Carlo
    REPLY_CEILING = 1.0        # a reply this slow means a stall: next decision is cheap
    # check-folding costs 1 reply on the button; the big blind cannot fold unbet
    # streets, so against a passive opponent it costs 5: 3 on average
    FOLD_REPLIES_PER_HAND = 3.0
    PANIC_MARGIN = 1.3         # check-fold before the bank is strictly too short
    PANIC_RESERVE = 0.05       # share of the starting bank always kept
    LOCK_SAFE_SDS = 3.0        # keep playing a locked match only if this many sd safe
    STATION_SIZES = (0.5, 1.0, 1.5)   # raise sizes, in pots, tried against a station
    OVERHEAD_SAMPLE_CAP = 0.2  # seconds; largest single overhead measurement used

    def __init__(self, seed=None):
        self.model = OpponentModel()
        self.rng = np.random.default_rng(seed)
        self.pyrng = random.Random(seed)
        self.my_raises_street = {}
        self.last_equity = None
        self.last_rollouts = 0
        # the bank also pays for pipes, parsing and scheduling outside our code;
        # measured as (bank drop since the last request) - (our own compute time)
        self.overhead = 0.010      # seconds per reply; starts pessimistic
        self._last_bank = None
        self._last_compute = 0.0
        self.reserve = self.PANIC_RESERVE * rules.TIME_BANK_SECONDS
        self.net = 0               # chips won so far this match
        self.net_squares = 0       # sum of squared hand results
        self.hands_done = 0

    # ----------------------------------------------------------- hooks
    def on_game_start(self, info):
        self.reserve = self.PANIC_RESERVE * info.time_bank

    def on_hand_start(self, view):
        self.model.start_hand(view)
        self.my_raises_street = {}

    def on_event(self, view, ev):
        self.model.observe(view, ev)
        if ev.kind == "act" and ev.seat == view.my_seat and ev.action == RAISE:
            self.my_raises_street[ev.street] = self.my_raises_street.get(ev.street, 0) + 1

    def on_hand_end(self, view, my_delta):
        self.model.end_hand(view)
        self.net += my_delta
        self.net_squares += my_delta * my_delta
        self.hands_done += 1

    def locked_in(self, view):
        """True when check-folding the rest wins the match for certain and playing on
        could lose it.  A lead safe either way keeps playing for tie-break chips."""
        left = view.hands_remaining
        worst = (left + 1) // 2 * rules.BIG_BLIND + left // 2 * rules.SMALL_BLIND
        if self.net <= worst:
            return False
        rate = self.net / max(1, self.hands_done)
        spread = max(1.0, (self.net_squares / max(1, self.hands_done) * left) ** 0.5)
        return (self.net + max(0.0, rate) * left) / spread < self.LOCK_SAFE_SDS

    # ----------------------------------------------------------- budget
    def time_budget(self, view):
        """Monte Carlo seconds for this decision: first reserve the fixed cost of
        every reply left in the match, then spend a share of what is spare."""
        if self._last_compute > self.REPLY_CEILING:
            return 0.0
        left = view.hands_remaining * self.DECISIONS_PER_HAND
        spare = view.time_bank - left * (self.overhead + self.CHEAP_COST)
        budget = min(self.MAX_BUDGET, max(0.0, spare) / left * self.BANK_SAFETY)
        return budget if budget >= self.MIN_BUDGET else 0.0

    def bank_critical(self, view):
        """True when the bank cannot pay for even cheap replies: check-folding uses the
        fewest replies, and losing blinds beats forfeiting the match."""
        per_reply = self.overhead + self.CHEAP_COST
        need = view.hands_remaining * self.FOLD_REPLIES_PER_HAND * per_reply
        return view.time_bank < need * self.PANIC_MARGIN + self.reserve

    def _clocked(self, view, decide):
        """Run decide(view), measuring our time and learning the overhead."""
        start = time.perf_counter()
        if self._last_bank is not None:
            sample = self._last_bank - view.time_bank - self._last_compute
            if 0.0 <= sample < 1.0:   # ignore a new match or a clock glitch
                # capped so one stall cannot trigger bank_critical on its own
                self.overhead += 0.1 * (min(sample, self.OVERHEAD_SAMPLE_CAP) - self.overhead)
        try:
            return decide(view)
        finally:
            self._last_compute = time.perf_counter() - start
            self._last_bank = view.time_bank

    # ------------------------------------------------------------ range
    def opponent_range(self, view):
        return top_range(self.range_fraction(view))

    def range_fraction(self, view):
        """Share of starting hands the opponent is likely to hold, from their actions."""
        m = self.model
        if view.street == 0:
            raised = m.raises_this_hand.get(0, 0)
            if raised:
                frac = m.pfr() * (0.6 ** (raised - 1))
            elif m.vpip_hand:
                frac = m.vpip()
            else:
                frac = 1.0
        else:
            frac = m.pfr() if m.pfr_hand else (m.vpip() if m.vpip_hand else 1.0)
            narrow = min(0.9, max(0.45, 0.4 + 0.15 * m.aggression()))
            for street in range(1, view.street + 1):
                frac *= narrow ** m.raises_this_hand.get(street, 0)
        return frac

    # ------------------------------------------------------------ equity
    def estimate_equity(self, view):
        budget = self.time_budget(view)
        if budget <= 0.0:
            return self._cheap_strength(view), 0
        kw = dict(batch=250, max_rollouts=3000, min_rollouts=250, rng=self.rng, dead=view.dead)
        if len(view.dead) == 2:   # after the discard: use what the opponent threw away
            return equity_timed(view.hole, view.board, budget, opp_discard=view.dead[1],
                                policy_weights=self.model.discard_policy(),
                                hand_weight=range_weight(self.range_fraction(view)), **kw)
        return equity_timed(view.hole, view.board, budget, opp_range=self.opponent_range(view),
                            **kw)

    def _cheap_strength(self, view):
        if view.street == 0:
            return 0.3 + 0.5 * preflop_percentile(view.hole)
        cat, bcat, _ = made_hand(view.hole, view.board)
        if cat <= bcat:
            return 0.3
        return min(0.95, 0.45 + 0.1 * cat)

    # --------------------------------------------------------- exploits
    def raise_ev(self, view, eq, fold, target):
        """Expected chips from raising to `target` against a fold rate.  The hands that
        fold are taken to be ones we beat, so we hold less equity against the rest."""
        added = target - view.my_bet
        called_pot = view.pot + added + (target - view.opp_bet)
        eq_called = max(0.0, (eq - fold) / (1.0 - fold))
        return fold * view.pot + (1.0 - fold) * (eq_called * called_pot - added)

    def station_raise(self, view, eq):
        """A raise-to amount against a clear station, when it beats check or call."""
        fold = self.model.station_rate()
        if view.street == 0 or fold is None or RAISE not in view.legal:
            return None
        if view.to_call == 0:
            passive = eq * view.pot
        else:
            passive = max(0.0, eq * (view.pot + view.to_call) - view.to_call)
        targets = {bet_to(view, f) for f in self.STATION_SIZES}
        best = max(targets, key=lambda t: self.raise_ev(view, eq, fold, t))
        return best if self.raise_ev(view, eq, fold, best) > passive else None

    # --------------------------------------------------------- discard
    def discard(self, view):
        return self._clocked(view, self._discard)

    def _discard(self, view):
        if self.bank_critical(view):
            return rules.default_discard(view.hole)
        if self.time_budget(view) <= 0.0:
            return super().discard(view)
        n = 500

        def keep_equity(c):
            keep = [x for x in view.hole if x != c]
            return equity_vs_random(keep, view.board, n, self.rng, dead=[c])[0]
        return max(view.hole, key=keep_equity)

    # ------------------------------------------------------------- act
    def act(self, view):
        return self._clocked(view, self._act)

    def _act(self, view):
        if self.bank_critical(view) or self.locked_in(view):
            return Action.check() if CHECK in view.legal else Action.fold()
        eq, n = self.estimate_equity(view)
        self.last_equity, self.last_rollouts = eq, n
        target = self.station_raise(view, eq)
        if target is not None:
            return Action.raise_to(target)
        return self.choose(view, eq)

    def choose(self, view, eq):
        """The action for this equity."""
        m = self.model
        legal = view.legal
        pot_after = view.pot + view.to_call
        price = view.to_call / max(1, pot_after)

        aggr = m.aggression()
        margin = 0.08
        if view.to_call > 0:
            if aggr > 2.0:
                margin -= 0.04        # maniac: their bets mean less
            elif aggr < 0.8:
                margin += 0.05        # passive player betting = strength
        raise_thresh = 0.70
        if m.fold_to_bet() < 0.25:
            raise_thresh -= 0.04      # calling station: value-bet thinner
        my_raises = self.my_raises_street.get(view.street, 0)

        if RAISE in legal and eq >= raise_thresh + 0.08 * my_raises:
            frac = 0.6 + 1.2 * (eq - raise_thresh)
            return Action.raise_to(bet_to(view, frac))
        if view.to_call > 0:
            if eq >= price + margin:
                return Action.call()
            return Action.fold() if FOLD in legal else Action.check()
        # nobody has bet: consider a bluff / semi-bluff
        ftb = m.fold_to_bet()
        if (RAISE in legal and view.street > 0 and my_raises == 0
                and ftb > 0.5 and self.pyrng.random() < (ftb - 0.4)):
            return Action.raise_to(bet_to(view, 0.5))
        return Action.check() if CHECK in legal else Action.call()
