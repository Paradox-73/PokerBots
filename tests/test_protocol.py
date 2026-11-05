"""Replays the example hand from the official protocol spec (docs/protocol.pdf,
Section 10) through our engine encoder and our bot adapter."""
import json
import unittest

from pokerbots.bots.base import Bot
from pokerbots.bots.simple import CallBot
from pokerbots.core.cards import str_to_card as C, str_to_cards as S
from pokerbots.core.types import Action
from pokerbots.engine import protocol
from pokerbots.engine.game import Deal, HandState, make_deal

J = json.loads

# E>B lines from the spec ("..." history entries dropped: compared without history)
SPEC_INIT = {"type": "init", "protocol_version": "1.0", "total_hands": 400, "starting_stack": 200,
             "small_blind": 1, "big_blind": 2, "time_bank_ms": 60000, "per_response_ms": 5000}
SPEC_NEW_HAND = {"type": "new_hand", "hand_id": 1, "seat": "button",
                 "hole_cards": ["As", "Kd", "7c"], "stack": 200, "opp_stack": 200}
SPEC_PREFLOP = {"type": "action_request", "hand_id": 1, "street": "preflop", "board": [], "pot": 3,
                "my_bet": 1, "opp_bet": 2, "to_call": 1, "my_stack": 199, "opp_stack": 198,
                "legal_actions": ["fold", "call", "raise"], "min_raise": 4, "max_raise": 200,
                "raises_left": 3, "history": [], "time_left_ms": 60000}
SPEC_FLOP = {"type": "action_request", "hand_id": 1, "street": "flop", "board": ["Ah", "7d", "2s"],
             "pot": 12, "my_bet": 0, "opp_bet": 0, "to_call": 0, "my_stack": 194, "opp_stack": 194,
             "legal_actions": ["check", "raise"], "min_raise": 2, "max_raise": 194,
             "raises_left": 4,
             "history": [{"street": "preflop", "actor": "me", "action": "raise", "amount": 6},
                         {"street": "preflop", "actor": "opp", "action": "call", "amount": 6},
                         {"street": "flop", "actor": "opp", "action": "check"}],
             "time_left_ms": 59940}
SPEC_DISCARD_REQ = {"type": "discard_request", "hand_id": 1, "hole_cards": ["As", "Kd", "7c"],
                    "board": ["Ah", "7d", "2s"], "pot": 24, "my_stack": 188, "opp_stack": 188,
                    "time_left_ms": 59900}
SPEC_DISCARD_RES = {"type": "discard_result", "hand_id": 1, "my_discard": "Kd",
                    "opp_discard": "Qs", "hole_cards": ["As", "7c"]}
SPEC_TURN = {"type": "action_request", "hand_id": 1, "street": "turn",
             "board": ["Ah", "7d", "2s", "3c"], "pot": 24, "my_bet": 0, "opp_bet": 0, "to_call": 0,
             "my_stack": 188, "opp_stack": 188, "legal_actions": ["check", "raise"],
             "min_raise": 2, "max_raise": 188, "raises_left": 4, "time_left_ms": 59860}
SPEC_RIVER = dict(SPEC_TURN, street="river", board=["Ah", "7d", "2s", "3c", "4h"],
                  time_left_ms=59820)
SPEC_RESULT = {"type": "hand_result", "hand_id": 1, "result": "fold", "net": 12,
               "board": ["Ah", "7d", "2s", "3c", "4h"], "my_hole_cards": ["As", "7c"],
               "opp_hole_cards": None, "opp_discard": "Qs"}


def no_history(msg):
    return {k: v for k, v in J(msg).items() if k != "history"}


class SpecExampleEngine(unittest.TestCase):
    def test_engine_emits_spec_messages(self):
        st = HandState(Deal([S("As,Kd,7c"), S("Qs,Jc,5d")], S("Ah,7d,2s,3c,4h")), button=0)
        self.assertEqual(J(protocol.encode_init(400, 60.0)), SPEC_INIT)
        self.assertEqual(J(protocol.encode_new_hand(st, 0, 1)), SPEC_NEW_HAND)
        self.assertEqual(J(protocol.encode_action_request(st, 0, 1, 60.0)), SPEC_PREFLOP)
        st.apply(Action.raise_to(6))
        st.apply(Action.call())
        st.apply(Action.check())
        self.assertEqual(J(protocol.encode_action_request(st, 0, 1, 59.94)), SPEC_FLOP)
        st.apply(Action.raise_to(6))
        st.apply(Action.call())
        self.assertTrue(st.need_discard)
        self.assertEqual(J(protocol.encode_discard_request(st, 0, 1, 59.9)), SPEC_DISCARD_REQ)
        st.discard([C("Kd"), C("Qs")])
        self.assertEqual(J(protocol.encode_discard_result(st, 0, 1)), SPEC_DISCARD_RES)
        st.apply(Action.check())
        self.assertEqual(no_history(protocol.encode_action_request(st, 0, 1, 59.86)), SPEC_TURN)
        st.apply(Action.check())
        st.apply(Action.check())
        self.assertEqual(no_history(protocol.encode_action_request(st, 0, 1, 59.82)), SPEC_RIVER)
        st.apply(Action.raise_to(10))
        st.apply(Action.fold())
        self.assertEqual(no_history(protocol.encode_hand_result(st, 0, 1)), SPEC_RESULT)
        hist = J(protocol.encode_hand_result(st, 0, 1))["history"]
        self.assertEqual(hist[-1], {"street": "river", "actor": "opp", "action": "fold"})
        self.assertEqual(len(hist), 10)


class Scripted(Bot):
    """Plays the bot's side of the spec example."""
    def __init__(self):
        self.replies = [Action.raise_to(6), Action.raise_to(6), Action.check(), Action.raise_to(10)]
        self.events = []
        self.result = None

    def on_event(self, view, ev):
        self.events.append((ev.kind, ev.street, ev.seat, ev.action, ev.amount, ev.cards))

    def act(self, view):
        return self.replies.pop(0)

    def discard(self, view):
        return C("Kd")

    def on_hand_end(self, view, my_delta):
        self.result = my_delta


class SpecExampleBot(unittest.TestCase):
    def test_adapter_replies_like_spec(self):
        bot = Scripted()
        ad = protocol.BotAdapter(bot)
        D = json.dumps
        self.assertIsNone(ad.handle_line(D(SPEC_INIT)))
        self.assertEqual(ad.info.time_bank, 60.0)
        self.assertIsNone(ad.handle_line(D(SPEC_NEW_HAND)))
        self.assertTrue(ad.view.is_button)
        self.assertEqual(J(ad.handle_line(D(SPEC_PREFLOP))),
                         {"type": "action", "action": "raise", "amount": 6})
        self.assertEqual(J(ad.handle_line(D(SPEC_FLOP))),
                         {"type": "action", "action": "raise", "amount": 6})
        self.assertEqual(ad.view.street, 1)
        self.assertEqual(J(ad.handle_line(D(SPEC_DISCARD_REQ))), {"type": "discard", "card": "Kd"})
        self.assertIsNone(ad.handle_line(D(SPEC_DISCARD_RES)))
        self.assertEqual(ad.view.hole, S("As,7c"))
        self.assertEqual(ad.view.dead, S("Kd,Qs"))
        hist = SPEC_FLOP["history"] + [
            {"street": "flop", "actor": "me", "action": "raise", "amount": 6},
            {"street": "flop", "actor": "opp", "action": "call", "amount": 6},
            {"street": "turn", "actor": "opp", "action": "check"}]
        self.assertEqual(J(ad.handle_line(D(dict(SPEC_TURN, history=hist)))),
                         {"type": "action", "action": "check"})
        hist += [{"street": "turn", "actor": "me", "action": "check"},
                 {"street": "river", "actor": "opp", "action": "check"}]
        self.assertEqual(J(ad.handle_line(D(dict(SPEC_RIVER, history=hist)))),
                         {"type": "action", "action": "raise", "amount": 10})
        hist += [{"street": "river", "actor": "me", "action": "raise", "amount": 10},
                 {"street": "river", "actor": "opp", "action": "fold"}]
        self.assertIsNone(ad.handle_line(D(dict(SPEC_RESULT, history=hist))))
        self.assertEqual(bot.result, 12)
        kinds = [e[0] for e in bot.events]
        # discard_request carries no history, so the flop raise/call reach the bot
        # with the turn request, after the discard events
        self.assertEqual(kinds, ["act", "act", "board", "act", "discard", "discard",
                                 "act", "act", "board", "act", "act", "board", "act",
                                 "act", "act"])
        self.assertEqual(bot.events[-1][:4], ("act", 3, 1, "fold"))
        self.assertIsNone(ad.handle_line(D({"type": "match_end", "reason": "complete"})))
        self.assertTrue(ad.done)

    def test_ignores_unknown_and_garbage(self):
        ad = protocol.BotAdapter(CallBot())
        self.assertIsNone(ad.handle_line("not json"))
        self.assertIsNone(ad.handle_line('{"type":"future_thing","x":1}'))
        self.assertIsNone(ad.handle_line('{"type":"notice","code":"malformed","applied":"fold"}'))

    def test_adapter_clamps_bad_raise_and_survives_exception(self):
        class Wild(CallBot):
            def act(self, view):
                return Action.raise_to(10 ** 6)

        class Broken(CallBot):
            def act(self, view):
                raise RuntimeError("bug")

            def discard(self, view):
                raise RuntimeError("bug")
        st = HandState(make_deal(0, 0), button=0)
        for bot, want in ((Wild(), {"type": "action", "action": "raise", "amount": 200}),
                          (Broken(), {"type": "action", "action": "fold"})):
            ad = protocol.BotAdapter(bot)
            ad.handle_line(protocol.encode_init(4, 60))
            ad.handle_line(protocol.encode_new_hand(st, 0, 1))
            self.assertEqual(J(ad.handle_line(protocol.encode_action_request(st, 0, 1, 60))), want)
        st = HandState(Deal([S("5h,5s,Ad"), S("Kc,Kd,Ks")], S("2c,7d,9h,Js,3c")), button=0)
        st.apply(Action.call())
        st.apply(Action.check())
        st.apply(Action.check())
        st.apply(Action.check())
        self.assertEqual(J(ad.handle_line(protocol.encode_discard_request(st, 0, 1, 60))),
                         {"type": "discard", "card": "5s"})

    def test_parse_replies(self):
        self.assertEqual(protocol.parse_action('{"type":"action","action":"raise","amount":40}'),
                         Action.raise_to(40))
        self.assertEqual(protocol.parse_action('{"type":"action","action":"call"}\n'), Action.call())
        self.assertIsNone(protocol.parse_action('{"type":"action","action":"raise","amount":"x"}'))
        self.assertIsNone(protocol.parse_action("R 12"))
        self.assertIsNone(protocol.parse_action(None))
        self.assertEqual(protocol.parse_discard('{"type":"discard","card":"Kd"}'), C("Kd"))
        self.assertIsNone(protocol.parse_discard('{"type":"discard","card":"Zz"}'))
        self.assertIsNone(protocol.parse_discard('{"type":"discard"}'))


if __name__ == "__main__":
    unittest.main()
