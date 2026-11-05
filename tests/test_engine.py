import random
import unittest

from pokerbots.core import rules
from pokerbots.core.cards import str_to_card as C, str_to_cards as S
from pokerbots.core.types import Action, RAISE
from pokerbots.engine.game import Deal, HandState, make_deal


def deal(btn_hole, bb_hole, board):
    return Deal([S(btn_hole), S(bb_hole)], S(board))


def check_down(st):
    while not st.terminal:
        if st.need_discard:
            st.discard([st.hole[0][0], st.hole[1][0]])
        else:
            st.apply(Action.check())


class Engine(unittest.TestCase):
    def test_blinds_and_fold(self):
        st = HandState(make_deal(0, 0), button=1)
        self.assertEqual(st.to_act, 1)
        self.assertEqual(st.bets, [2, 1])
        self.assertEqual([len(h) for h in st.hole], [3, 3])
        st.apply(Action.fold())
        self.assertTrue(st.terminal)
        self.assertEqual(st.deltas, [1, -1])
        self.assertIsNone(st.discards)

    def test_discard_after_flop_then_showdown_with_two_cards(self):
        st = HandState(deal("Ah,Ad,2d", "Kc,Kd,3s", "2c,7d,9h,Js,3c"), button=0)
        st.apply(Action.call())       # button completes
        st.apply(Action.check())      # BB option
        st.apply(Action.check())
        st.apply(Action.check())      # flop betting over
        self.assertTrue(st.need_discard)
        self.assertEqual(len(st.board), 3)
        st.discard([C("2d"), C("3s")])
        self.assertEqual(st.hole, [S("Ah,Ad"), S("Kc,Kd")])
        self.assertEqual(st.to_act, 1)   # BB acts first postflop
        check_down(st)
        self.assertTrue(st.showdown)
        self.assertEqual(st.deltas, [2, -2])

    def test_discarded_card_no_longer_plays(self):
        # the button would make trips with its 2d; discarding it loses to KK
        st = HandState(deal("Ah,2h,2d", "Kc,Kd,3s", "2c,7d,9h,Js,3c"), button=0)
        st.apply(Action.call())
        st.apply(Action.check())
        st.apply(Action.check())
        st.apply(Action.check())
        st.discard([C("2d"), C("3s")])
        check_down(st)
        self.assertEqual(st.deltas, [-2, 2])

    def test_illegal_discard_uses_lowest_rank_spade_first(self):
        st = HandState(deal("5h,5s,Ad", "Kc,Kd,Ks", "2c,7d,9h,Js,3c"), button=0)
        st.apply(Action.call())
        st.apply(Action.check())
        st.apply(Action.check())
        st.apply(Action.check())
        used = st.discard([C("Qc"), None])
        self.assertEqual(used, [C("5s"), C("Ks")])
        self.assertEqual(st.illegal, [1, 1])

    def test_default_discard_order(self):
        self.assertEqual(rules.default_discard(S("Ac,2h,2c")), C("2h"))
        self.assertEqual(rules.default_discard(S("9d,9c,9s")), C("9s"))

    def test_min_raise_and_illegal(self):
        st = HandState(make_deal(0, 1), button=0)
        lg = st.legal()
        self.assertEqual((lg.min_raise, lg.max_raise), (4, 200))
        st.apply(Action.raise_to(3))  # below min -> fold (check not legal)
        self.assertTrue(st.terminal)
        self.assertEqual(st.illegal, [1, 0])

    def test_reraise_min(self):
        st = HandState(make_deal(0, 1), button=0)
        st.apply(Action.raise_to(10))   # raise by 8
        self.assertEqual(st.legal().min_raise, 18)

    def test_four_raise_cap_counts_big_blind_preflop(self):
        st = HandState(make_deal(0, 1), button=0)
        st.apply(Action.raise_to(4))     # raise 2 (BB was 1)
        st.apply(Action.raise_to(8))     # 3
        st.apply(Action.raise_to(16))    # 4
        self.assertNotIn(RAISE, st.legal().kinds)
        st.apply(Action.call())
        self.assertIn(RAISE, st.legal().kinds)   # flop: a fresh 4

    def test_all_in_preflop_still_discards(self):
        st = HandState(deal("Ah,Ad,2d", "Kc,Kd,3s", "2c,7d,9h,Js,Kh"), button=0)
        st.apply(Action.raise_to(200))
        st.apply(Action.call())
        self.assertTrue(st.need_discard and not st.terminal)
        self.assertEqual(len(st.board), 3)
        st.discard([C("2d"), C("3s")])
        self.assertTrue(st.terminal)
        self.assertEqual(len(st.board), 5)
        self.assertEqual(st.deltas, [-200, 200])

    def test_uncalled_bet_returned(self):
        st = HandState(deal("Ah,Ad,2d", "Kc,Kd,3s", "2c,7d,9h,Js,3h"), button=0,
                       stacks=[200, 100])
        st.apply(Action.raise_to(200))
        st.apply(Action.call())       # BB calls all-in for 100 total
        st.discard([C("2d"), C("3s")])
        self.assertEqual(st.deltas, [100, -100])

    def test_split_pot(self):
        st = HandState(deal("2h,3d,4c", "2c,3s,4d", "Ac,Kd,Qh,Jc,Ts"), button=0)
        st.apply(Action.call())
        st.apply(Action.check())
        check_down(st)
        self.assertEqual(st.deltas, [0, 0])

    def test_random_play_conserves_chips(self):
        rng = random.Random(5)
        for i in range(2000):
            st = HandState(make_deal(7, i), button=i % 2)
            while not st.terminal:
                if st.need_discard:
                    st.discard([rng.choice(st.hole[0]), rng.choice(st.hole[1])])
                    continue
                lg = st.legal()
                k = rng.choice(sorted(lg.kinds))
                amt = rng.randint(lg.min_raise, lg.max_raise) if k == RAISE else 0
                st.apply(Action(k, amt))
                self.assertGreaterEqual(min(st.stacks), 0)
            self.assertEqual(sum(st.deltas), 0)
            self.assertEqual(st.illegal, [0, 0])
            self.assertLessEqual(max(abs(d) for d in st.deltas), rules.STARTING_STACK)
            if st.showdown:
                self.assertEqual([len(h) for h in st.hole], [2, 2])

    def test_duplicate_deal_same_cards_by_position(self):
        d = make_deal(3, 4)
        a, b = HandState(d, 0), HandState(d, 1)
        self.assertEqual(a.hole[0], b.hole[1])
        self.assertEqual(a.hole[1], b.hole[0])
        self.assertEqual(make_deal(3, 4), d)


if __name__ == "__main__":
    unittest.main()
