"""Match-level and range decisions of the shipped strategy."""

import unittest

import numpy as np

from pokerbots.bots.equity_bot import EquityBot
from pokerbots.bots.range_bot import RangeBot
from pokerbots.core.cards import str_to_cards as S
from pokerbots.core.equity import best_kept, keep_score, range_equity, strength_weights
from pokerbots.core.types import Action, CALL, CHECK, Event, FOLD, HandView, RAISE


def view(hand_no=1, legal=(CHECK, RAISE), to_call=0, pot=20, hole="As,Ad,Ac", street=2):
    return HandView(hand_no=hand_no, my_seat=0, button=0, hole=S(hole), num_hands=400, pot=pot,
                    legal=frozenset(legal), to_call=to_call, time_bank=60.0, street=street,
                    min_raise=2, max_raise=180, board=S("2c,7d,9h,Js"))


class LockIn(unittest.TestCase):
    def bot(self, net, hands_done=300, squares=None):
        bot = EquityBot(seed=1)
        bot.net, bot.hands_done = net, hands_done
        bot.net_squares = hands_done * 400 if squares is None else squares
        return bot

    def test_locks_only_past_the_most_that_check_folding_can_lose(self):
        v = view(hand_no=301)                 # 100 hands left: 50 x 2 + 50 x 1 = 150 at risk
        self.assertFalse(self.bot(150).locked_in(v))
        self.assertTrue(self.bot(151).locked_in(v))

    def test_a_lead_safe_either_way_keeps_playing_for_tie_break_chips(self):
        self.assertFalse(self.bot(5000, squares=300).locked_in(view(hand_no=301)))

    def test_locked_bot_never_puts_in_more_chips(self):
        bot = self.bot(151)
        self.assertEqual(bot.act(view(301)), Action.check())
        self.assertEqual(bot.act(view(301, (FOLD, CALL, RAISE), to_call=8)), Action.fold())


class Station(unittest.TestCase):
    def bot(self, faced, folded):
        bot = EquityBot(seed=1)
        bot.model.post_faced, bot.model.post_folded = faced, folded
        return bot

    def test_reads_a_station_only_on_clear_evidence(self):
        self.assertAlmostEqual(self.bot(30, 1).model.station_rate(), 1 / 30)
        self.assertIsNone(self.bot(200, 80).model.station_rate())
        self.assertIsNone(self.bot(24, 0).model.station_rate())

    def test_raise_ev_with_known_numbers(self):
        # fold 50%, equity 60%: called, 10 of the remaining 50 points is 20% equity.
        # 0.5 x 20 + 0.5 x (0.2 x 40 - 10) = 9
        self.assertAlmostEqual(self.bot(1, 1).raise_ev(view(), 0.6, 0.5, 10), 9.0)

    def test_bets_big_for_value_into_a_station_and_never_bluffs_one(self):
        self.assertEqual(self.bot(30, 1).station_raise(view(), 0.8), 30)
        self.assertIsNone(self.bot(30, 1).station_raise(view(), 0.3))

    def test_no_read_means_no_raise(self):
        self.assertIsNone(self.bot(200, 80).station_raise(view(), 0.8))


class RangeEquity(unittest.TestCase):
    rng = np.random.default_rng(1)

    def test_keeps_the_set_over_the_kicker(self):
        eq = range_equity(S("9s,9d,Kc"), S("Th,9h,2c"), 3000, self.rng)
        self.assertEqual(int(np.argmax(eq)), 2)
        self.assertGreater(eq[2], 0.8)

    def test_pressure_lowers_a_one_pair_hand(self):
        hole, board = S("Ah,Kd"), S("Ac,7d,2s,9h")
        calm = range_equity(hole, board, 4000, self.rng)[0]
        pushed = range_equity(hole, board, 4000, self.rng, pressure=2.0)[0]
        self.assertLess(pushed, calm - 0.1)

    def test_strength_weights_lean_the_right_way(self):
        values = np.arange(100)
        self.assertIsNone(strength_weights(values, 0.0))
        self.assertGreater(strength_weights(values, 2.0)[-1], strength_weights(values, 2.0)[0])
        self.assertLess(strength_weights(values, -0.5)[-1], strength_weights(values, -0.5)[0])

    def test_draws_score_above_the_same_cards_without_them(self):
        flop = np.array([S("Th,9h,2c")])
        draw, offsuit = (keep_score(np.array([S(c)]), flop)[0] for c in ("Qh,Jh", "Qc,Jd"))
        self.assertGreater(draw, offsuit)

    def test_best_kept_takes_the_set(self):
        kept = best_kept(np.array([S("9s,9d,Kc")]), np.array([S("Th,9h,2c")]))
        self.assertEqual(sorted(kept[0].tolist()), sorted(S("9s,9d")))


class RaiseReading(unittest.TestCase):
    def bot(self, hands, raised):
        bot = RangeBot(seed=1)
        bot.model.hands, bot.model.pfr_n = hands, raised
        return bot

    def test_a_frequent_raiser_means_less(self):
        self.assertLess(self.bot(100, 75).preflop_raise_signal(1.0),
                        self.bot(100, 30).preflop_raise_signal(1.0) / 3)

    def test_a_big_raise_says_more_than_a_small_one(self):
        v = view(street=2)
        small = RangeBot(seed=1)
        v.history = [Event("act", 2, 1, RAISE, 4)]
        v.pot = 44
        low = small.opponent_pressure(v)
        v.history = [Event("act", 2, 1, RAISE, 40)]
        self.assertGreater(small.opponent_pressure(v), low)

    def test_trust_falls_once_bluffs_are_shown(self):
        bot = RangeBot(seed=1)
        fresh = bot.trust()
        bot.bluff_shows, bot.bluffs_shown = 20.0, 15.0
        self.assertLess(bot.trust(), fresh)


if __name__ == "__main__":
    unittest.main()
