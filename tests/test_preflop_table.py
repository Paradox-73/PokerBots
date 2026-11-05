import unittest
from itertools import combinations

import numpy as np

from pokerbots.bots import common
from pokerbots.core import rules
from pokerbots.core.cards import str_to_cards as S


class PreflopTable(unittest.TestCase):
    def test_covers_every_class(self):
        classes = {common.hand_class(c) for c in combinations(range(rules.DECK_SIZE), 3)}
        self.assertEqual(set(common.PREFLOP_EQUITY), classes)
        self.assertEqual(len(classes), 1755)
        self.assertEqual(common.ALL_COMBOS.shape, (22100, 3))

    def test_class_is_suit_invariant(self):
        self.assertEqual(common.hand_class(S("Ah,Ac,Kh")), common.hand_class(S("Ad,As,Ks")))
        self.assertEqual(common.hand_class(S("Ah,Ac,Kh")), common.hand_class(S("Ac,Ah,Kh")))
        self.assertNotEqual(common.hand_class(S("Ah,Kh,Qh")), common.hand_class(S("Ah,Kh,Qd")))

    def test_equities_in_open_interval(self):
        self.assertTrue(all(0 < v < 1 for v in common.PREFLOP_EQUITY.values()))

    def test_top_and_bottom(self):
        ranked = sorted(common.PREFLOP_EQUITY, key=common.PREFLOP_EQUITY.get, reverse=True)
        top = set(ranked[:len(ranked) // 10])
        bottom = set(ranked[-len(ranked) // 10:])
        self.assertIn(common.hand_class(S("As,Ah,Kd")), top)
        self.assertIn(common.hand_class(S("Ks,Kh,Qd")), top)
        self.assertIn(common.hand_class(S("2s,3h,4d")), bottom)
        self.assertGreater(common.preflop_percentile(S("As,Ah,Ad")), 0.8)
        self.assertGreater(common.preflop_percentile(S("As,Ks,Qs")), 0.5)
        self.assertLess(common.preflop_percentile(S("2s,3h,4d")), 0.05)

    def test_percentile_monotone_in_equity(self):
        items = sorted(common.PREFLOP_EQUITY.items(), key=lambda kv: kv[1])
        pcts = [common.COMBO_PCT[i] for i in
                [next(i for i, c in enumerate(common.ALL_COMBOS.tolist())
                      if common.hand_class(c) == k) for k, _ in items[::50]]]
        self.assertEqual(pcts, sorted(pcts))
        self.assertTrue(0 <= min(pcts) and max(pcts) <= 1)

    def test_top_range_concentrates_on_strong_combos(self):
        r = common.top_range(0.1)
        self.assertEqual(r.combos.shape, (22100, 3))
        w = r.weights
        top = common.COMBO_PCT >= 0.9
        self.assertGreater(w[top].sum() / w.sum(), 0.7)
        self.assertLess(w[common.COMBO_PCT < 0.7].sum() / w.sum(), 0.01)
        self.assertTrue(np.all(w >= 0))


if __name__ == "__main__":
    unittest.main()
