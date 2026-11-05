"""Opponent statistics tracked from the event stream (opponent-modelling hooks).

Every rate uses a Bayesian prior so it is sensible after a handful of hands:
    rate = (count + prior * weight) / (opportunities + weight)
"""

import math

import numpy as np

from pokerbots.core.equity import DEFAULT_POLICY_WEIGHTS, discard_consistency
from pokerbots.core.types import CALL, CHECK, FOLD, RAISE


class OpponentModel:
    PRIOR_WEIGHT = 10.0
    MIN_FOLD_SAMPLES = 25    # postflop bets seen answered before reading a station
    MAX_STATION_FOLD = 0.25  # fold rate the upper bound must clear to be read as a station

    def __init__(self):
        self.hands = 0
        self.vpip_n = 0          # hands with a voluntary preflop call/raise
        self.pfr_n = 0           # hands with a preflop raise
        self.post_raises = 0     # postflop bets + raises
        self.post_calls = 0
        self.faced_bet = 0       # times the opponent faced our bet/raise
        self.folded_to_bet = 0
        self.post_faced = 0      # postflop bets the opponent answered
        self.post_folded = 0     # of those, folds
        self.discard_obs = []    # per showdown: {policy: would it make that discard}
        self._policy = None      # cached discard_policy()
        self._reset_hand(None)

    # ------------------------------------------------------------ updates
    def _reset_hand(self, view):
        self.my_seat = view.my_seat if view else 0
        self.vpip_hand = False
        self.pfr_hand = False
        self.raises_this_hand = {}   # street -> opponent raises on that street
        self.last_aggressor = None

    def start_hand(self, view):
        self._reset_hand(view)

    def observe(self, view, ev):
        if ev.kind != "act":
            return
        opp = 1 - view.my_seat
        if ev.seat != opp:
            self.last_aggressor = view.my_seat if ev.action == RAISE else self.last_aggressor
            return
        if self.last_aggressor == view.my_seat and ev.action in (FOLD, CALL, RAISE):
            self.faced_bet += 1
            self.post_faced += ev.street > 0
            if ev.action == FOLD:
                self.folded_to_bet += 1
                self.post_folded += ev.street > 0
            self.last_aggressor = None
        if ev.street == 0:
            if ev.action in (CALL, RAISE):
                self.vpip_hand = True
            if ev.action == RAISE:
                self.pfr_hand = True
        else:
            if ev.action == RAISE:
                self.post_raises += 1
            elif ev.action == CALL:
                self.post_calls += 1
        if ev.action == RAISE:
            self.raises_this_hand[ev.street] = self.raises_this_hand.get(ev.street, 0) + 1
            self.last_aggressor = opp

    def end_hand(self, view):
        self.hands += 1
        self.vpip_n += self.vpip_hand
        self.pfr_n += self.pfr_hand
        if view is not None and view.opp_cards:
            if len(view.dead) == 2 and len(view.opp_cards) == 2 and len(view.board) >= 3:
                fits = discard_consistency(np.array([view.opp_cards]), view.dead[1],
                                           view.board[:3])
                self.discard_obs.append({p: bool(fits[p][0]) for p in DEFAULT_POLICY_WEIGHTS})
                del self.discard_obs[:-200]
                self._policy = None

    # -------------------------------------------------------------- stats
    def _rate(self, k, n, prior):
        return (k + prior * self.PRIOR_WEIGHT) / (n + self.PRIOR_WEIGHT)

    def vpip(self):
        return self._rate(self.vpip_n, self.hands, 0.6)

    def pfr(self):
        return self._rate(self.pfr_n, self.hands, 0.3)

    def station_rate(self):
        """The fold rate to postflop bets if it is clearly too low, else None.  Clear
        means enough samples and a 95% Wilson upper bound below MAX_STATION_FOLD."""
        n, k = self.post_faced, self.post_folded
        if n < self.MIN_FOLD_SAMPLES:
            return None
        z = 1.96
        p = k / n
        mid = (p + z * z / (2 * n)) / (1 + z * z / n)
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return p if mid + half < self.MAX_STATION_FOLD else None

    def aggression(self):
        """(bets + raises) / calls postflop; ~1 is neutral, >2 aggressive."""
        return (self.post_raises + 1.0 * 3) / (self.post_calls + 1.0 * 3)

    def discard_policy(self):
        """Mixture weights for equity_vs_discarder, fitted to showdowns by EM.

        Components: each policy in DEFAULT_POLICY_WEIGHTS (makes the seen discard
        with probability 1 if it fits, else 0) and "random" (1/3).  The prior is
        DEFAULT_POLICY_WEIGHTS, worth PRIOR_WEIGHT showdowns."""
        if self._policy is not None:
            return self._policy
        prior = dict(DEFAULT_POLICY_WEIGHTS)
        prior["random"] = 1.0 - sum(prior.values())
        pi = dict(prior)
        for _ in range(30):
            counts = {k: self.PRIOR_WEIGHT * v for k, v in prior.items()}
            for obs in self.discard_obs:
                like = {k: (1.0 / 3.0 if k == "random" else float(obs[k])) * pi[k] for k in pi}
                total = sum(like.values())
                for k in pi:
                    counts[k] += like[k] / total
            n = sum(counts.values())
            pi = {k: c / n for k, c in counts.items()}
        pi.pop("random")
        self._policy = pi
        return pi

    def fold_to_bet(self):
        return self._rate(self.folded_to_bet, self.faced_bet, 0.4)
