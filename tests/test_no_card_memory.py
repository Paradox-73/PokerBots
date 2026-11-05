"""Rulebook 10.3: duplicate deals must never be exploited.

Hands 2k+1 and 2k+2 share a deal with the cards swapped, so a bot that remembered cards
could read its opponent's hole cards.  Nothing a bot keeps between hands may depend on
which cards were dealt.  Each test plays one hand in two worlds that differ only in the
cards, then requires the bot's state afterwards to be identical.
"""

import json
import random
import unittest

import numpy as np

from pokerbots.bots import make_bot
from pokerbots.engine.protocol import BotAdapter

# clocks and random generators differ between any two runs, whatever the cards
IGNORED = {"rng", "pyrng", "overhead", "sample_cost", "_last_bank", "_last_compute"}
HISTORY = [{"street": "preflop", "actor": "me", "action": "call", "amount": 2},
           {"street": "preflop", "actor": "opp", "action": "check"},
           {"street": "flop", "actor": "opp", "action": "check"},
           {"street": "flop", "actor": "me", "action": "check"},
           {"street": "turn", "actor": "opp", "action": "check"},
           {"street": "turn", "actor": "me", "action": "check"},
           {"street": "river", "actor": "opp", "action": "check"},
           {"street": "river", "actor": "me", "action": "check"}]


def snapshot(value, seen=None):
    """Plain data form of an object's whole state, recursively."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return "<seen>"
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(id(value))
        items = [snapshot(v, seen) for v in value]
        return sorted(items, key=repr) if isinstance(value, (set, frozenset)) else items
    if isinstance(value, dict):
        seen.add(id(value))
        return {repr(k): snapshot(v, seen) for k, v in value.items() if k not in IGNORED}
    if hasattr(value, "__dict__"):
        seen.add(id(value))
        return snapshot(vars(value), seen)
    return value


def play(bot_name, hole, board, opp_hole, my_discard, opp_discard, showdown):
    bot = make_bot(bot_name)
    adapter = BotAdapter(bot)
    send = lambda **msg: adapter.handle_line(json.dumps(msg))
    send(type="init", protocol_version="1.0", total_hands=4, starting_stack=200, small_blind=1,
         big_blind=2, time_bank_ms=60000, per_response_ms=5000)
    send(type="new_hand", hand_id=1, seat="button", hole_cards=hole, stack=200, opp_stack=200)
    send(type="discard_result", hand_id=1, my_discard=my_discard, opp_discard=opp_discard,
         hole_cards=[c for c in hole if c != my_discard])
    send(type="hand_result", hand_id=1, result="showdown" if showdown else "fold", net=0,
         board=board, my_hole_cards=[c for c in hole if c != my_discard],
         opp_hole_cards=opp_hole if showdown else None, opp_discard=opp_discard,
         history=HISTORY)
    adapter.view = None        # the per-hand view is replaced at the next new_hand
    return snapshot(bot)


WORLD_A = (["As", "Kd", "7c"], ["2h", "3d", "9s", "Jc", "4h"], ["Qs", "Qd"], "7c", "6c")
WORLD_B = (["Ah", "Kc", "8d"], ["2s", "3c", "9h", "Jd", "5c"], ["Td", "Tc"], "8d", "6d")


class NoCardMemory(unittest.TestCase):
    def check(self, bot_name, showdown):
        a = play(bot_name, *WORLD_A, showdown)
        b = play(bot_name, *WORLD_B, showdown)
        self.assertEqual(a, b, "%s kept card information between hands" % bot_name)

    def test_equity_bot_keeps_no_cards_after_a_folded_hand(self):
        self.check("equity", False)

    def test_equity_bot_keeps_no_cards_after_a_showdown(self):
        self.check("equity", True)

    def test_shipped_bot_keeps_no_cards_after_a_folded_hand(self):
        self.check("range", False)

    def test_shipped_bot_keeps_no_cards_after_a_showdown(self):
        self.check("range", True)

    def test_no_state_field_holds_a_card_list(self):
        # a direct look: nothing kept may be a list of ints shaped like a hand
        bot = make_bot("range")
        random.seed(1)
        state = snapshot(bot)
        self.assertNotIn("showdowns", json.dumps(state, default=str))


if __name__ == "__main__":
    unittest.main()
