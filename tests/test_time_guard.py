"""The bot must finish a match on a machine far slower than planned."""

import unittest
from unittest import mock

from pokerbots.bots.equity_bot import EquityBot
from pokerbots.core.cards import str_to_cards as S
from pokerbots.core.types import Action, CALL, CHECK, FOLD, HandView, RAISE
from pokerbots.engine import match


def view(hand_no, bank, legal=(CHECK, RAISE)):
    return HandView(hand_no=hand_no, my_seat=0, button=0, hole=S("As,Ad,Ac"), num_hands=400,
                    legal=frozenset(legal), time_bank=bank, pot=4, to_call=8 if CALL in legal else 0,
                    min_raise=4, max_raise=200, board=S("2c,7d,9h"), street=1)


class BankGuard(unittest.TestCase):
    def test_short_bank_check_folds_without_simulating(self):
        bot = EquityBot(seed=1)
        bot.overhead = 0.10                   # 400 x 3 x 0.102 x 1.1 = 135 s needed
        self.assertTrue(bot.bank_critical(view(1, 60.0)))
        self.assertEqual(bot.act(view(1, 60.0)), Action.check())
        self.assertEqual(bot.act(view(1, 60.0, (FOLD, CALL, RAISE))), Action.fold())
        self.assertEqual(bot.last_rollouts, 0)

    def test_normal_machine_is_not_critical(self):
        self.assertFalse(EquityBot(seed=1).bank_critical(view(1, 60.0)))

    def test_short_bank_discards_instantly_and_legally(self):
        bot = EquityBot(seed=1)
        bot.overhead = 0.10
        self.assertIn(bot.discard(view(1, 1.0)), S("As,Ad,Ac"))

    def test_stalled_reply_makes_the_next_decision_cheap(self):
        bot = EquityBot(seed=1)
        v = view(1, 60.0)
        self.assertGreater(bot.time_budget(v), 0.0)
        bot._last_compute = 1.5
        self.assertEqual(bot.time_budget(v), 0.0)

    def test_one_stall_does_not_trigger_the_guard(self):
        bot = EquityBot(seed=1)
        bot._last_bank, bot._last_compute = 60.0, 0.0
        bot._clocked(view(1, 59.1), lambda v: None)    # 0.9 s lost outside the bot
        self.assertFalse(bot.bank_critical(view(1, 59.1)))


class SlowMachine(unittest.TestCase):
    """Every reply is charged 40 ms it did not use, as measured on a machine under
    heavy load. No real delay: the match runs at full speed."""

    def play(self, opponent="starter"):
        real = match.InProcessBot.request
        hero = []

        def charged(self_, line, timeout):
            reply, dt = real(self_, line, timeout)
            if not hero:
                hero.append(self_)
            return reply, dt + (0.04 if self_ is hero[0] else 0.0)

        with mock.patch.object(match.InProcessBot, "request", charged):
            return match.play_match("inproc:equity", "inproc:" + opponent, deals=200, seed=4)

    def test_guard_finishes_the_match(self):
        res = self.play()
        self.assertIsNone(res.forfeit, res.forfeit_reason)
        self.assertEqual(res.hands_played, 400)

    def test_without_the_guard_the_same_machine_forfeits(self):
        with mock.patch.object(EquityBot, "bank_critical", lambda self, v: False):
            self.assertEqual(self.play().forfeit, 0)


if __name__ == "__main__":
    unittest.main()
