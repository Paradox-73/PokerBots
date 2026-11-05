"""Local match runner: duplicate deals, time bank, crash handling, results.

A bot is given as a spec string:
  "equity"                -> registered bot, run as  python -m pokerbots.bots equity
  "path/to/player.py"     -> run as  python -I path/to/player.py (from its folder)
  "cmd:<command line>"    -> run that command, e.g. a docker run
Prefix "inproc:" (e.g. "inproc:tag") to run a registered bot inside this
process (fast, for tests; time is measured but a hung bot cannot be killed).
"""

import os
import queue
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

from pokerbots.core import rules
from pokerbots.engine import protocol
from pokerbots.engine.game import HandState, make_deal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BotFailure(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ------------------------------------------------------------ connections
class SubprocessBot:
    def __init__(self, spec, log_path=None):
        cwd = PROJECT_ROOT
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if spec.startswith("cmd:"):
            cmd = shlex.split(spec[len("cmd:"):], posix=True)
        elif spec.endswith(".py"):
            # isolated (-I): the script sees no PYTHONPATH and must find its own modules
            cmd = [sys.executable, "-I", "-u", os.path.abspath(spec)]
            cwd = os.path.dirname(os.path.abspath(spec))
        else:
            cmd = [sys.executable, "-u", "-m", "pokerbots.bots", spec]
            env["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
        self._log = open(log_path, "w") if log_path else subprocess.DEVNULL
        self.free_until = time.perf_counter() + rules.STARTUP_SECONDS
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._log, text=True, encoding="utf-8", bufsize=1, env=env)
        self.lines = queue.Queue()
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def _reader(self):
        try:
            for line in iter(self.proc.stdout.readline, ""):
                self.lines.put(line)
        except (OSError, ValueError):
            pass
        self.lines.put(None)   # EOF -> crashed / exited

    def send(self, line):
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            raise BotFailure("crash (stdin closed)")

    def request(self, line, timeout):
        """Send and wait for a reply line.  Returns (reply, seconds)."""
        start = max(time.perf_counter(), self.free_until)
        self.send(line)
        try:
            reply = self.lines.get(timeout=max(0.0, start + timeout - time.perf_counter()))
        except queue.Empty:
            raise BotFailure("timeout (no reply within %.2f s)" % timeout)
        elapsed = max(0.0, time.perf_counter() - start)
        if reply is None:
            raise BotFailure("crash (exit code %s)" % self.proc.poll())
        return reply.strip(), elapsed

    def close(self):
        try:
            self.send(protocol.encode_match_end())
        except BotFailure:
            pass
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        if self._log is not subprocess.DEVNULL:
            self._log.close()


class InProcessBot:
    def __init__(self, name):
        from pokerbots.bots import make_bot
        self.adapter = protocol.BotAdapter(make_bot(name))

    def send(self, line):
        try:
            self.adapter.handle_line(line)
        except Exception as exc:  # noqa: BLE001
            raise BotFailure("crash (%r)" % (exc,))

    def request(self, line, timeout):
        start = time.perf_counter()
        try:
            reply = self.adapter.handle_line(line)
        except Exception as exc:  # noqa: BLE001
            raise BotFailure("crash (%r)" % (exc,))
        elapsed = time.perf_counter() - start
        if elapsed > timeout:
            raise BotFailure("timeout (time bank exhausted)")
        return (reply or "").strip(), elapsed

    def close(self):
        try:
            self.adapter.handle_line(protocol.encode_match_end())
        except Exception:  # noqa: BLE001
            pass


def connect(spec, log_path=None):
    if spec.startswith("inproc:"):
        return InProcessBot(spec[len("inproc:"):])
    return SubprocessBot(spec, log_path)


# ---------------------------------------------------------------- results
@dataclass
class MatchResult:
    names: List[str]
    hands_played: int = 0
    chips: List[int] = field(default_factory=lambda: [0, 0])
    time_used: List[float] = field(default_factory=lambda: [0.0, 0.0])
    max_decision: List[float] = field(default_factory=lambda: [0.0, 0.0])
    illegal: List[int] = field(default_factory=lambda: [0, 0])
    forfeit: Optional[int] = None
    forfeit_reason: str = ""
    path: List[int] = field(default_factory=list)   # first bot's chip total after each hand

    @property
    def match_points(self):
        if self.forfeit is not None:
            pts = [1.0, 1.0]
            pts[self.forfeit] = 0.0
            return pts
        if self.chips[0] > self.chips[1]:
            return [1.0, 0.0]
        if self.chips[1] > self.chips[0]:
            return [0.0, 1.0]
        return [0.5, 0.5]

    def capped(self, i):
        """This match's tie-break score: net chips clipped to +-C (Rulebook 8.3).
        A forfeit sets the opponent's result to +C (9.2)."""
        cap = rules.MATCH_CHIP_CAP
        if self.forfeit is not None:
            # shortcut: the rulebook does not say what the forfeiter gets; -C is assumed
            return -cap if i == self.forfeit else cap
        return max(-cap, min(cap, self.chips[i]))

    def per_hand(self, i, capped=True):
        return (self.capped(i) if capped else self.chips[i]) / max(1, self.hands_played)

    def summary(self):
        lines = []
        mp = self.match_points
        for i in (0, 1):
            lines.append(
                "%-14s MP %.1f | chips %+7d | chips/hand %+7.2f | capped/hand %+7.2f"
                " | time %6.2fs (max %4.0f ms) | illegal %d"
                % (self.names[i], mp[i], self.chips[i], self.per_hand(i, False),
                   self.per_hand(i), self.time_used[i], self.max_decision[i] * 1000,
                   self.illegal[i]))
        if self.forfeit is not None:
            lines.append("FORFEIT by %s: %s" % (self.names[self.forfeit], self.forfeit_reason))
        lines.append("hands played: %d" % self.hands_played)
        return "\n".join(lines)


# ------------------------------------------------------------------ match
def play_match(spec_a, spec_b, deals=None, seed=0, time_bank=None,
               names=None, log_dir=None, opp_time_bank=None):
    """Play `deals` duplicate deals (2 hands each, seats swapped).  `opp_time_bank`
    gives the second bot its own bank, so a slow opponent can finish a measurement."""
    deals = rules.HANDS_PER_MATCH // 2 if deals is None else deals
    time_bank = rules.TIME_BANK_SECONDS if time_bank is None else time_bank
    banks = [time_bank, time_bank if opp_time_bank is None else opp_time_bank]
    specs = [spec_a, spec_b]
    names = names or specs
    result = MatchResult(list(names))
    num_hands = deals * 2
    bots = [None, None]
    try:
        for i in (0, 1):
            log = None
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
                log = os.path.join(log_dir, "%s_seat%d.log" % (os.path.basename(specs[i]).replace(":", "_"), i))
            try:
                bots[i] = connect(specs[i], log)
            except Exception as exc:  # noqa: BLE001
                result.forfeit, result.forfeit_reason = i, "failed to start (%r)" % (exc,)
                return result

        def ask(i, line):
            remaining = banks[i] - result.time_used[i]
            limit = min(remaining, rules.PER_RESPONSE_SECONDS)
            reply, dt = bots[i].request(line, limit)
            result.time_used[i] += dt
            result.max_decision[i] = max(result.max_decision[i], dt)
            if result.time_used[i] > banks[i]:
                raise BotFailure("timeout (time bank exhausted)")
            if dt > rules.PER_RESPONSE_SECONDS:
                raise BotFailure("timeout (reply over %.0f s)" % rules.PER_RESPONSE_SECONDS)
            return reply

        current = [0]

        def fail(i, reason):
            result.forfeit, result.forfeit_reason = i, reason

        for i in (0, 1):
            current[0] = i
            try:
                bots[i].send(protocol.encode_init(num_hands, banks[i]))
            except BotFailure as f:
                fail(i, f.reason)
                return result

        hand_no = 0
        for d in range(deals):
            deal = make_deal(seed, d)
            for button in (0, 1):          # duplicate: same cards, seats swapped
                hand_no += 1
                try:
                    _play_hand(bots, deal, button, hand_no, banks, result, ask, current)
                except BotFailure as f:
                    fail(current[0], f.reason)
                    return result
        return result
    finally:
        for b in bots:
            if b is not None:
                b.close()


def _play_hand(bots, deal, button, hand_no, banks, result, ask, current):
    state = HandState(deal, button)

    def send(i, line):
        current[0] = i
        bots[i].send(line)

    def left(i):
        return banks[i] - result.time_used[i]

    for i in (0, 1):
        send(i, protocol.encode_new_hand(state, i, hand_no))
    while not state.terminal:
        if state.need_discard:
            # shortcut: asked one after the other, not at the same time; each bot is
            # still charged only its own reply time and sees nothing of the other's
            cards = []
            for i in (0, 1):
                current[0] = i
                cards.append(protocol.parse_discard(
                    ask(i, protocol.encode_discard_request(state, i, hand_no, left(i)))))
            before = list(state.illegal)
            used = state.discard(cards)
            for i in (0, 1):
                if state.illegal[i] > before[i]:
                    code = "malformed" if cards[i] is None else "illegal_discard"
                    send(i, protocol.encode_notice(code, protocol.card_to_str(used[i])))
                send(i, protocol.encode_discard_result(state, i, hand_no))
            continue
        seat = state.to_act
        current[0] = seat
        reply = ask(seat, protocol.encode_action_request(state, seat, hand_no, left(seat)))
        action = protocol.parse_action(reply)
        before = state.illegal[seat]
        used = state.apply(action)
        if state.illegal[seat] > before:
            send(seat, protocol.encode_notice("malformed" if action is None else "illegal_action",
                                              used.kind))
    for i in (0, 1):
        send(i, protocol.encode_hand_result(state, i, hand_no))
        result.chips[i] += state.deltas[i]
        result.illegal[i] += state.illegal[i]
    result.hands_played += 1
    result.path.append(result.chips[0])
