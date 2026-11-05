import time
import unittest

import numpy as np

from pokerbots.core.cards import str_to_cards as S
from pokerbots.bots.opponent import OpponentModel
from pokerbots.core.cards import str_to_card as C
from pokerbots.core.equity import (Range, discard_consistency, equity_timed, equity_vs_discarder,
                                   equity_vs_random, equity_vs_range)
from pokerbots.core.types import HandView


class Equity(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(42)

    def test_aces_vs_random(self):
        eq, n = equity_vs_random(S("As,Ah"), [], 20000, self.rng)
        self.assertEqual(n, 20000)
        self.assertAlmostEqual(eq, 0.852, delta=0.01)

    def test_aks_vs_queens(self):
        qq = Range([S("Qc,Qd")])
        eq, _ = equity_vs_range(S("As,Ks"), [], qq, 20000, self.rng)
        self.assertAlmostEqual(eq, 0.46, delta=0.015)

    def test_river_exact(self):
        board = S("2c,7d,9h,Js,Kc")
        self.assertEqual(equity_vs_range(S("Ah,Kd"), board, Range([S("Qh,Qd")]), 50, self.rng)[0], 1.0)
        self.assertEqual(equity_vs_range(S("3h,4d"), board, Range([S("Qh,Qd")]), 50, self.rng)[0], 0.0)
        self.assertEqual(equity_vs_range(S("Ah,Qd"), board, Range([S("Ad,Qc")]), 50, self.rng)[0], 0.5)

    def test_blocked_combos_ignored(self):
        # AsKd is blocked by hero's As, so the range is effectively KK only
        r = Range([S("As,Kd"), S("Kc,Kh")])
        eq, _ = equity_vs_range(S("As,Ad"), [], r, 20000, self.rng)
        self.assertAlmostEqual(eq, 0.82, delta=0.015)

    def test_speed_1000_rollouts(self):
        equity_vs_random(S("Ah,Kd"), S("Qs,7h,2c"), 1000, self.rng)
        t = time.perf_counter()
        for _ in range(10):
            equity_vs_random(S("Ah,Kd"), S("Qs,7h,2c"), 1000, self.rng)
        self.assertLess((time.perf_counter() - t) / 10, 0.050)

    def test_timed_respects_budget(self):
        t = time.perf_counter()
        eq, n = equity_timed(S("Ah,Kd"), [], 0.02, rng=self.rng)
        self.assertLess(time.perf_counter() - t, 0.1)
        self.assertGreaterEqual(n, 100)
        self.assertTrue(0.5 < eq < 0.8)


class Discard(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(7)

    def test_consistency(self):
        flop = S("Kd,7c,2s")
        fits = discard_consistency(np.array([S("Ac,As"), S("3h,4h"), S("Kh,9c")]), C("2c"), flop)
        # AA throwing the 2: best hand and lowest card; 34 and K9 throwing the 2
        # are not best keeps (2-3/2-4 pair the board, K-2 makes two pair)
        self.assertEqual(fits["best_made"].tolist(), [True, False, False])
        self.assertEqual(fits["lowest_rank"].tolist(), [True, True, True])
        fits = discard_consistency(np.array([S("3h,4h")]), C("Ah"), flop)
        self.assertEqual(fits["lowest_rank"].tolist(), [False])

    def test_discard_of_a_king_means_strength(self):
        hole, board, dead = S("9s,9h"), S("Kd,7c,2s,4h"), [C("3c"), C("Kh")]
        rand, _ = equity_vs_random(hole, board, 20000, self.rng, dead=dead)
        mixed, _ = equity_vs_discarder(hole, board, C("Kh"), dead, 20000, self.rng)
        lowest, _ = equity_vs_discarder(hole, board, C("Kh"), dead, 20000, self.rng,
                                        {"lowest_rank": 1.0})
        none, _ = equity_vs_discarder(hole, board, C("Kh"), dead, 20000, self.rng, {})
        self.assertAlmostEqual(none, rand, delta=0.015)    # random discarder: no information
        self.assertLess(mixed, rand - 0.03)
        self.assertLess(lowest, 0.1)                       # they hold two of A/K

    def test_model_learns_lowest_rank_habit(self):
        m = OpponentModel()
        rng = np.random.default_rng(3)
        for _ in range(40):
            cards = rng.permutation(52)[:8].tolist()
            three, board = cards[:3], cards[3:]
            disc = min(three, key=lambda c: c // 4)
            v = HandView(hand_no=1, my_seat=0, button=0, hole=[], num_hands=400, board=board)
            v.opp_cards = [c for c in three if c != disc]
            v.dead = [0 if disc else 1, disc]
            m.start_hand(v)
            m.end_hand(v)
        w = m.discard_policy()
        self.assertGreater(w["lowest_rank"], 0.6)
        self.assertLess(sum(w.values()), 1.0)
        self.assertLess(w["best_made"], w["lowest_rank"])


if __name__ == "__main__":
    unittest.main()
