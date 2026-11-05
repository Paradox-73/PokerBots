"""The bot must answer every request, whatever the engine sends: a crash forfeits the match."""
import io
import json
import random
import unittest

from pokerbots.bots import make_bot
from pokerbots.engine import protocol
from tests.test_protocol import (SPEC_DISCARD_REQ, SPEC_DISCARD_RES, SPEC_FLOP, SPEC_INIT,
                                 SPEC_NEW_HAND, SPEC_PREFLOP, SPEC_RESULT, SPEC_RIVER, SPEC_TURN)

SPEC_HAND = [SPEC_NEW_HAND, SPEC_PREFLOP, SPEC_FLOP, SPEC_DISCARD_REQ, SPEC_DISCARD_RES,
             SPEC_TURN, SPEC_RIVER, SPEC_RESULT]
JUNK = [None, -1, 10 ** 9, "x", [], {}, ["Zz"], 3.5, True]


def mutate(msg, rng):
    msg = dict(msg)
    keys = [k for k in msg if k != "type"]
    for _ in range(rng.randint(1, 3)):
        k = rng.choice(keys)
        if rng.random() < 0.4:
            msg.pop(k, None)
        else:
            msg[k] = rng.choice(JUNK)
    return msg


class Robust(unittest.TestCase):
    def run_lines(self, bot_name, lines):
        out = io.StringIO()
        protocol.BotAdapter(make_bot(bot_name)).run(io.StringIO("".join(l + "\n" for l in lines)), out)
        return [json.loads(r) for r in out.getvalue().splitlines()]

    def test_every_request_answered_under_garbage(self):
        rng = random.Random(1)
        for bot in ("equity", "tag", "random", "call"):
            lines, requests = [json.dumps(SPEC_INIT)], []
            for _ in range(150):
                for msg in SPEC_HAND:
                    m = mutate(msg, rng) if rng.random() < 0.3 else msg
                    lines.append(json.dumps(m))
                    if m["type"] in ("action_request", "discard_request"):
                        requests.append(m)
                if rng.random() < 0.2:
                    lines.append(rng.choice(["not json", "[]", '{"type":"surprise"}', "", "{"]))
            replies = self.run_lines(bot, lines + ['{"type":"match_end","reason":"complete"}'])
            self.assertEqual(len(replies), len(requests), bot)
            for req, rep in zip(requests, replies):
                if req["type"] == "action_request":
                    self.assertEqual(rep["type"], "action")
                    legal = req.get("legal_actions")
                    if isinstance(legal, list) and "check" in legal:
                        self.assertNotEqual(rep["action"], "fold")
                else:
                    self.assertEqual(rep["type"], "discard")

    def test_clean_hand_replies_are_legal(self):
        replies = self.run_lines("equity", [json.dumps(m) for m in [SPEC_INIT] + SPEC_HAND])
        acts = [r for r in replies if r["type"] == "action"]
        for req, rep in zip([SPEC_PREFLOP, SPEC_FLOP, SPEC_TURN, SPEC_RIVER], acts):
            self.assertIn(rep["action"], req["legal_actions"])
            if rep["action"] == "raise":
                self.assertTrue(req["min_raise"] <= rep["amount"] <= req["max_raise"])
        self.assertIn(replies[2]["card"], SPEC_DISCARD_REQ["hole_cards"])


if __name__ == "__main__":
    unittest.main()
