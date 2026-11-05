import random
import unittest
from itertools import combinations

import numpy as np

from pokerbots.core import evaluator
from pokerbots.core.cards import str_to_cards
from tests.reference import best_rank


def S(text):
    return str_to_cards(text)


class KnownHands(unittest.TestCase):
    def cat(self, text):
        return evaluator.category_of(evaluator.evaluate(S(text)))

    def test_categories(self):
        self.assertEqual(self.cat("As,Ks,Qs,Js,Ts,2c,3d"), "straight_flush")
        self.assertEqual(self.cat("Ah,2d,3c,4s,5h,9c,Kd"), "straight")
        self.assertEqual(self.cat("Ah,Ad,Ac,As,5h,9c,Kd"), "quads")
        self.assertEqual(self.cat("Ah,Ad,Ac,Ks,Kh,Kc,2d"), "full_house")
        self.assertEqual(self.cat("2h,7h,9h,Jh,Kh,Ac,Ad"), "flush")
        self.assertEqual(self.cat("2h,2d,9c,9h,Kh,Kc,3d"), "two_pair")

    def test_orderings(self):
        e = lambda t: evaluator.evaluate(S(t))  # noqa: E731
        self.assertLess(e("Ah,2d,3c,4s,5h"), e("2h,3d,4c,5s,6h"))           # wheel lowest
        self.assertGreater(e("Ah,Ad,Kc,Ks,Qh,Qc,2d"), e("Ah,Ad,Kc,Ks,Jh,Jc,Td"))  # 3rd pair kicker
        self.assertEqual(e("Ah,Kd,Qc,Js,9h,3c,2d"), e("Ad,Kh,Qs,Jc,9d,4c,2h"))   # 6th card irrelevant
        self.assertGreater(e("Ah,Ad,Ac,Ks,Kh,2c,2d"), e("Ah,Ad,Ac,Qs,Qh,Qc,2d"))  # AAAKK > AAAQQ

    def test_all_five_card_hands(self):
        hands = np.array(list(combinations(range(52), 5)), dtype=np.int64)
        vals = evaluator.evaluate_batch(hands)
        self.assertEqual(len(np.unique(vals)), 7462)
        cats = vals >> evaluator.SHIFT
        counts = np.bincount(cats, minlength=9).tolist()
        self.assertEqual(counts, [1302540, 1098240, 123552, 54912, 10200, 5108, 3744, 624, 40])


class AgainstReference(unittest.TestCase):
    def check(self, n_cards, n_hands, seed):
        rng = random.Random(seed)
        hands = [rng.sample(range(52), n_cards) for _ in range(n_hands)]
        fast = [evaluator.evaluate(h) for h in hands]
        batch = evaluator.evaluate_batch(np.array(hands)).tolist()
        self.assertEqual(fast, batch)
        ref = [best_rank(h) for h in hands]
        order = sorted(range(n_hands), key=lambda i: ref[i])
        for a, b in zip(order, order[1:]):
            if ref[a] == ref[b]:
                self.assertEqual(fast[a], fast[b], (hands[a], hands[b]))
            else:
                self.assertLess(fast[a], fast[b], (hands[a], hands[b]))

    def test_5(self):
        self.check(5, 3000, 1)

    def test_6(self):
        self.check(6, 2000, 2)

    def test_7(self):
        self.check(7, 2000, 3)

    def test_8_and_9(self):
        self.check(8, 600, 4)
        self.check(9, 300, 5)

    def test_rich_hands(self):
        """Bias toward paired / suited boards where bugs hide."""
        rng = random.Random(9)
        hands = []
        for _ in range(1500):
            ranks = [rng.randrange(13) for _ in range(4)]
            cards = set()
            while len(cards) < 7:
                r = rng.choice(ranks) if rng.random() < 0.7 else rng.randrange(13)
                s = 0 if rng.random() < 0.4 else rng.randrange(4)
                cards.add(r * 4 + s)
            hands.append(list(cards))
        fast = [evaluator.evaluate(h) for h in hands]
        ref = [best_rank(h) for h in hands]
        for i in range(len(hands)):
            for j in range(i + 1, min(len(hands), i + 20)):
                self.assertEqual(ref[i] < ref[j], fast[i] < fast[j], (hands[i], hands[j]))
                self.assertEqual(ref[i] == ref[j], fast[i] == fast[j], (hands[i], hands[j]))


if __name__ == "__main__":
    unittest.main()
