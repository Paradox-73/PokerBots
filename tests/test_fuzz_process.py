"""Fuzz the real bot.py process with raw bytes: a crash forfeits the match."""

import json
import os
import random
import subprocess
import sys
import unittest

from tests.test_robust import SPEC_HAND, SPEC_INIT, mutate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_NOISE = [b"\xff\xfe\xfa bad utf8", b"\x00\x00", b"{", b"null", b"[1,2", b"\xed\xa0\x80",
             b"x" * 200000, b'{"type":"action_request"}', b'{"type":"discard_request"}',
             b'{"type":"new_hand"}', b'{"type":"hand_result"}', b'{"type":"init"}']


# strict is how a UTF-8 locale reads stdin; it is the worst case for a bad byte
LAUNCH = ("import os, runpy, sys; sys.stdin.reconfigure(encoding='utf-8', errors='strict'); "
          "sys.argv = [sys.argv[1]]; runpy.run_path(sys.argv[0], run_name='__main__')")


def run_bot(payload):
    return subprocess.run([sys.executable, "-I", "-c", LAUNCH, os.path.join(ROOT, "bot.py")],
                          input=payload, capture_output=True, timeout=60, cwd=ROOT)


class ProcessFuzz(unittest.TestCase):
    def test_survives_raw_noise_between_real_messages(self):
        rng = random.Random(7)
        lines = [json.dumps(SPEC_INIT).encode()]
        for _ in range(60):
            for msg in SPEC_HAND:
                lines.append(json.dumps(mutate(msg, rng) if rng.random() < 0.3 else msg).encode())
                if rng.random() < 0.3:
                    lines.append(rng.choice(RAW_NOISE))
        lines.append(b'{"type":"match_end","reason":"complete"}')
        done = run_bot(b"\n".join(lines) + b"\n")
        self.assertEqual(done.returncode, 0, done.stderr[-500:])
        self.assertNotIn(b"Traceback", done.stderr)
        for line in done.stdout.splitlines():
            self.assertIn(json.loads(line)["type"], ("action", "discard"))

    def test_invalid_utf8_inside_a_request_still_gets_a_reply_to_the_next_one(self):
        good = json.dumps(SPEC_HAND[1]).encode()
        payload = b"\n".join([json.dumps(SPEC_INIT).encode(), json.dumps(SPEC_HAND[0]).encode(),
                              b"\xff" + good, good, b'{"type":"match_end"}']) + b"\n"
        done = run_bot(payload)
        self.assertEqual(done.returncode, 0, done.stderr[-500:])
        self.assertEqual(len(done.stdout.splitlines()), 1)

    def test_engine_closing_the_pipe_mid_match_is_a_clean_exit(self):
        payload = b"\n".join(json.dumps(m).encode() for m in [SPEC_INIT] + SPEC_HAND[:2]) + b"\n"
        done = run_bot(payload)
        self.assertEqual(done.returncode, 0, done.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
