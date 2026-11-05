"""Problem Statement Section 8: every worked example, replayed on our engine."""

import json
import unittest
from unittest import mock

from pokerbots.core import rules
from pokerbots.core.cards import str_to_card as C, str_to_cards as S
from pokerbots.core.types import Action, CALL, FOLD
from pokerbots.engine import match, protocol
from pokerbots.engine.game import Deal, HandState

A, B = 0, 1
CHECK, CALL_, FOLD_ = Action.check(), Action.call(), Action.fold()
R = Action.raise_to


def hand(a_hole, b_hole, board):
    return HandState(Deal([S(a_hole), S(b_hole)], S(board)), button=A)


def play(st, *actions):
    for a in actions:
        st.apply(a)


class Examples(unittest.TestCase):
    def test_1_complete_hand_to_showdown(self):
        st = hand("Qh,Jh,4c", "9s,9d,Kc", "Th,9h,2c,3s,5h")
        self.assertEqual((st.legal().min_raise, st.legal().max_raise), (4, 200))
        play(st, R(6))
        self.assertEqual(st.pot, 8)
        play(st, CALL_)
        self.assertEqual((st.pot, st.to_act), (12, B))
        play(st, CHECK)
        self.assertEqual(st.legal().min_raise, 2)
        play(st, R(8))
        self.assertEqual((st.pot, st.legal().min_raise), (20, 16))
        play(st, R(24), CALL_)
        self.assertEqual((st.pot, st.stacks), (60, [170, 170]))
        self.assertTrue(st.need_discard)
        st.discard([C("4c"), C("Kc")])
        line = json.loads(protocol.encode_discard_result(st, A, 7))
        self.assertEqual(line, {"type": "discard_result", "hand_id": 7, "my_discard": "4c",
                                "opp_discard": "Kc", "hole_cards": ["Qh", "Jh"]})
        play(st, R(40), CALL_)
        self.assertEqual((st.pot, st.stacks), (140, [130, 130]))
        play(st, CHECK, R(70), CALL_)
        self.assertEqual(st.deltas, [140, -140])

    def test_2_minimum_raises_and_cap(self):
        st = hand("2c,3d,4h", "5c,6d,7h", "8c,9d,Th,Js,Qc")
        for action, next_min, left in ((None, 4, 3), (R(6), 10, 2), (R(18), 30, 1)):
            if action:
                st.apply(action)
            self.assertEqual(st.legal().min_raise, next_min)
            self.assertEqual(rules.MAX_RAISES_PER_STREET - st.raises, left)
        st.apply(R(50))
        self.assertEqual(st.legal().kinds, frozenset((FOLD, CALL)))
        self.assertEqual(rules.MAX_RAISES_PER_STREET - st.raises, 0)
        st.apply(CALL_)
        self.assertEqual((st.pot, st.stacks), (100, [150, 150]))

    def test_3_all_in_preflop_still_discards(self):
        st = hand("As,Ad,5c", "Kh,Ks,Qd", "7c,Kd,2h,9s,Ac")
        play(st, R(200))
        self.assertEqual(st.legal().kinds, frozenset((FOLD, CALL)))
        play(st, CALL_)
        self.assertEqual((st.pot, st.board, st.need_discard), (400, S("7c,Kd,2h"), True))
        st.discard([C("5c"), C("Qd")])
        self.assertTrue(st.terminal)
        self.assertEqual(st.board, S("7c,Kd,2h,9s,Ac"))
        self.assertEqual(st.deltas, [200, -200])

    def test_4_fold_before_the_discard(self):
        st = hand("As,Ad,5c", "Kh,Ks,Qd", "7c,Kd,2h,9s,Ac")
        play(st, CALL_, CHECK)
        self.assertEqual(st.pot, 4)
        play(st, R(4))
        self.assertEqual(st.pot, 8)
        play(st, FOLD_)
        self.assertEqual(st.deltas, [-2, 2])
        msg = json.loads(protocol.encode_hand_result(st, A, 1))
        self.assertEqual(msg["my_hole_cards"], ["As", "Ad", "5c"])
        self.assertIsNone(msg["opp_hole_cards"])
        self.assertIsNone(msg["opp_discard"])

    def _showdown(self, a_keep, b_keep, board):
        st = hand(a_keep + ",2c", b_keep + ",2d", board)
        play(st, CALL_, CHECK, CHECK, CHECK)
        st.discard([C("2c"), C("2d")])
        for _ in range(4):
            st.apply(CHECK)
        return st.deltas

    def test_5_kicker_and_split_pot(self):
        self.assertEqual(self._showdown("Ac,Qs", "Ad,Js", "Ah,Kd,8c,5s,2h"), [2, -2])
        self.assertEqual(self._showdown("9c,9d", "4c,4h", "Ts,Js,Qd,Kh,Ac"), [0, 0])

    def test_6_engine_corrections(self):
        self.assertEqual(rules.default_discard(S("7d,7s,Ac")), C("7s"))
        st = hand("7d,7s,Ac", "Kh,Ks,Qd", "2c,3d,5h,9s,Jc")
        play(st, CALL_, CHECK, CHECK, CHECK)
        self.assertEqual(st.discard([C("Kh"), C("Qd")])[0], C("7s"))
        self.assertEqual(json.loads(protocol.encode_notice("illegal_discard", "7s")),
                         {"type": "notice", "code": "illegal_discard", "applied": "7s"})
        st = hand("7d,7s,Ac", "Kh,Ks,Qd", "2c,3d,5h,9s,Jc")
        play(st, CALL_, CHECK)
        self.assertEqual(st.apply(R(1)), CHECK)       # raise below the minimum
        self.assertEqual(st.illegal[B], 1)
        st.apply(R(4))
        self.assertEqual(st.apply(CHECK), FOLD_)      # check while facing a bet

    def test_stray_stdout_is_corrected_like_an_illegal_action(self):
        self.assertIsNone(protocol.parse_action("debug print"))
        self.assertIsNone(protocol.parse_discard("debug print"))


class ScriptedPeer:
    """A connected bot that checks or calls; discard_reply(request) makes its discard."""

    def __init__(self, discard_reply):
        self.discard_reply = discard_reply
        self.received = []

    def send(self, line):
        self.received.append(json.loads(line))

    def request(self, line, timeout):
        msg = json.loads(line)
        if msg["type"] == "discard_request":
            return self.discard_reply(msg), 0.0
        kind = "check" if "check" in msg["legal_actions"] else "call"
        return json.dumps({"type": "action", "action": kind}), 0.0

    def close(self):
        pass


class DiscardNotices(unittest.TestCase):
    def notice_codes(self, reply):
        peers = iter([ScriptedPeer(reply), ScriptedPeer(reply)])
        made = []

        def connect(spec, log=None):
            made.append(next(peers))
            return made[-1]

        with mock.patch.object(match, "connect", connect):
            match.play_match("a", "b", deals=1, seed=1)
        return {m["code"] for m in made[0].received if m["type"] == "notice"}

    def test_garbled_reply_is_malformed(self):
        self.assertEqual(self.notice_codes(lambda msg: "debug print"), {"malformed"})

    def test_unknown_card_text_is_malformed(self):
        self.assertEqual(self.notice_codes(lambda msg: '{"type":"discard","card":"Zz"}'),
                         {"malformed"})

    def test_card_not_held_is_illegal_discard(self):
        reply = lambda msg: json.dumps({"type": "discard", "card": msg["board"][0]})
        self.assertEqual(self.notice_codes(reply), {"illegal_discard"})


if __name__ == "__main__":
    unittest.main()
