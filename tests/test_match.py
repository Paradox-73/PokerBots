import os
import unittest

from pokerbots.engine.match import play_match

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Match(unittest.TestCase):
    def test_duplicate_cancels_luck(self):
        # two identical passive bots: every deal is played from both seats,
        # so card luck cancels exactly
        res = play_match("inproc:call", "inproc:call", deals=100, seed=1)
        self.assertEqual(res.hands_played, 200)
        self.assertEqual(res.chips, [0, 0])
        self.assertEqual(res.match_points, [0.5, 0.5])

    def test_inproc_all_bots(self):
        for a in ("random", "tag", "equity"):
            res = play_match("inproc:" + a, "inproc:call", deals=10, seed=2)
            self.assertIsNone(res.forfeit, res.forfeit_reason)
            self.assertEqual(sum(res.chips), 0)

    def test_subprocess_match(self):
        res = play_match("equity", "tag", deals=5, seed=3)
        self.assertIsNone(res.forfeit, res.forfeit_reason)
        self.assertEqual(res.hands_played, 10)
        self.assertEqual(sum(res.chips), 0)

    def test_official_starter_bot(self):
        res = play_match(os.path.join(FIX, "starter_bot.py"), "equity", deals=5, seed=4)
        self.assertIsNone(res.forfeit, res.forfeit_reason)
        self.assertEqual(res.illegal, [0, 0])
        self.assertEqual(sum(res.chips), 0)

    def test_equity_survives_tiny_bank(self):
        # 400 hands on a 3 s bank: like a machine 20x slower than budgeted
        res = play_match("inproc:equity", "inproc:tag", deals=200, seed=9, time_bank=3.0)
        self.assertIsNone(res.forfeit, res.forfeit_reason)
        self.assertLess(res.time_used[0], 3.0)

    def test_crash_forfeits(self):
        res = play_match(os.path.join(FIX, "crash_bot.py"), "call", deals=5)
        self.assertEqual(res.forfeit, 0)
        self.assertIn("crash", res.forfeit_reason)
        self.assertEqual(res.match_points, [0.0, 1.0])

    def test_timeout_forfeits(self):
        res = play_match("call", os.path.join(FIX, "slow_bot.py"), deals=20, time_bank=1.0)
        self.assertEqual(res.forfeit, 1)
        self.assertIn("timeout", res.forfeit_reason)
        self.assertLessEqual(res.time_used[1], 1.0 + 0.2)


if __name__ == "__main__":
    unittest.main()
