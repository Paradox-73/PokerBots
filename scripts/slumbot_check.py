"""Play the equity bot's postflop logic against Slumbot, as a check on postflop play only.

    python scripts/slumbot_check.py results.jsonl --hands 5000

Never shipped: the submission holds no network code.  Only game actions are sent, one
request at a time with a pause between hands, and any error or block stops the run.
Slumbot's game differs from ours: 2 hole cards, no discard, 200 big blind stacks, so
preflop here is a simple rule and only the postflop figures mean anything.  Chips are
scaled by CHIP so the bot's own sizing logic sees blinds of 1 and 2.
"""

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pokerbots.bots.range_bot import RangeBot  # noqa: E402
from pokerbots.core.cards import str_to_card  # noqa: E402
from pokerbots.core.equity import equity_vs_random  # noqa: E402
from pokerbots.core.types import (Action, CALL, CHECK, Event, FOLD, HandView,  # noqa: E402
                                  RAISE)

HOST = "https://slumbot.com/slumbot/api/"
CHIP = 50                # Slumbot's blinds are 50/100; ours are 1/2
STACK = 20000
BIG_BLIND = 100
PAUSE = 0.05             # seconds between requests: one client, no bursts
HAND_PAUSE = 0.5         # seconds between hands
TOKEN = re.compile(r"k|c|f|b\d+")
OPEN_PCT = 0.25          # preflop: wide, so that most hands reach the postflop test
ALL_PAIRS = np.array([(a, b) for a in range(52) for b in range(a + 1, 52)], dtype=np.int64)


def pair_strengths():
    """Percentile of each two-card hand by equity against a random hand."""
    rng = np.random.default_rng(1)
    eq = np.array([equity_vs_random(list(p), (), 150, rng)[0] for p in ALL_PAIRS])
    return np.searchsorted(np.sort(eq), eq) / len(eq)


PAIR_PCT = pair_strengths()
PAIR_INDEX = {tuple(p): i for i, p in enumerate(ALL_PAIRS.tolist())}


class State:
    """The betting so far, parsed from Slumbot's action string."""

    def __init__(self, action):
        self.bets = [BIG_BLIND, BIG_BLIND // 2]     # by Slumbot position: 0 big blind, 1 small
        self.prior = 0                              # each player's chips from earlier streets
        self.street = 0
        self.last_raise = BIG_BLIND
        self.acts = []                              # (street, position, token)
        self.actor = 1
        self.raises = 1
        streets = action.split("/")
        for street, text in enumerate(streets):
            if street:
                self.prior += max(self.bets)
                self.bets, self.last_raise, self.raises = [0, 0], BIG_BLIND, 0
                self.street, self.actor = street, 0
            for token in TOKEN.findall(text):
                self.acts.append((street, self.actor, token))
                if token == "c":
                    self.bets[self.actor] = max(self.bets)
                elif token[0] == "b":
                    to = int(token[1:])
                    self.last_raise = to - max(self.bets)
                    self.bets[self.actor] = to
                    self.raises += 1
                self.actor = 1 - self.actor


def view_for(state, pos, hole, board, hand_no, total):
    me, opp = state.bets[pos], state.bets[1 - pos]
    behind = STACK - state.prior - me
    to_call = opp - me
    legal = {CALL, FOLD} if to_call else {CHECK}
    top = STACK - state.prior
    low = min(opp + max(state.last_raise, BIG_BLIND), top)
    if opp < top and behind > to_call:
        legal.add(RAISE)
    return HandView(hand_no=hand_no, my_seat=0, button=0 if pos == 1 else 1, hole=hole,
                    num_hands=total, board=board, street=state.street,
                    pot=(2 * state.prior + me + opp) // CHIP, my_stack=behind // CHIP,
                    opp_stack=(STACK - state.prior - opp) // CHIP, my_bet=me // CHIP,
                    opp_bet=opp // CHIP, to_call=to_call // CHIP, legal=frozenset(legal),
                    min_raise=math.ceil(low / CHIP), max_raise=top // CHIP, time_bank=600.0)


class Hero(RangeBot):
    """The shipped postflop code.  Lock-in and the bank guard are match rules, so they are
    off here, and preflop is a plain rule because this game deals two cards."""

    def locked_in(self, view):
        return False

    def bank_critical(self, view):
        return False

    def two_card_preflop(self, view, pct):
        if view.to_call == 0:
            return Action.check()
        if RAISE in view.legal and view.opp_bet == 2 and pct >= OPEN_PCT:
            return Action.raise_to(max(view.min_raise, 5))
        if pct >= 0.95 and RAISE in view.legal:
            return Action.raise_to(view.max_raise)
        if view.to_call <= 12 and pct >= OPEN_PCT:
            return Action.call()
        return Action.fold()


def post(path, body):
    req = urllib.request.Request(HOST + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as reply:
        data = json.load(reply)
    if data.get("error_msg"):
        raise RuntimeError(data["error_msg"])
    time.sleep(PAUSE)
    return data


def to_wire(action, state, pos):
    if action.kind == FOLD:
        return "f"
    if action.kind == CHECK:
        return "k"
    if action.kind == CALL:
        return "c"
    top = STACK - state.prior
    low = min(max(state.bets) + max(state.last_raise, BIG_BLIND), top)
    return "b%d" % max(low, min(top, action.amount * CHIP))


def play_hand(bot, token, hand_no, total):
    """Plays one hand; returns (token, winnings in chips, reached_flop)."""
    r = post("new_hand", {"token": token} if token else {})
    token = r.get("token", token)
    pos = r["client_pos"]
    hole = [str_to_card(c) for c in r["hole_cards"]]
    bot.on_hand_start(HandView(hand_no=hand_no, my_seat=0, button=0 if pos == 1 else 1,
                               hole=hole, num_hands=total))
    told = 0
    view = view_for(State(r.get("action", "")), pos, hole, [], hand_no, total)  # Slumbot can fold before we act
    while "winnings" not in r or r["winnings"] is None:
        state = State(r.get("action", ""))
        board = [str_to_card(c) for c in r.get("board", [])]
        view = view_for(state, pos, hole, board, hand_no, total)
        for street, who, tok in state.acts[told:]:
            kind = {"k": CHECK, "c": CALL, "f": FOLD}.get(tok[0], RAISE)
            amount = int(tok[1:]) // CHIP if tok[0] == "b" else 0
            bot.on_event(view, Event("act", street, 0 if who == pos else 1, kind, amount))
        told = len(state.acts)
        if state.street == 0:
            action = bot.two_card_preflop(view, float(PAIR_PCT[PAIR_INDEX[tuple(sorted(hole))]]))
        else:
            action = bot.act(view)
            if action.kind not in view.legal:
                action = Action.check() if CHECK in view.legal else Action.fold()
        r = post("act", {"token": token, "incr": to_wire(action, state, pos)})
        token = r.get("token", token)
    final = State(r.get("action", ""))
    bot.on_hand_end(view, r["winnings"] // CHIP)
    return token, r["winnings"], final.street > 0 or "/" in r.get("action", ""), pos


def summary(rows):
    def line(name, values):
        n = len(values)
        if not n:
            return "%s: none" % name
        mean = sum(values) / n
        sd = math.sqrt(sum((v - mean) ** 2 for v in values) / max(1, n - 1))
        per100 = 100 * mean / BIG_BLIND
        return "%-14s %6d hands  %+8.1f bb/100  +- %6.1f" % (name, n, per100,
                                                             196 * sd / math.sqrt(n) / BIG_BLIND)
    print(line("all hands", [r["won"] for r in rows]))
    print(line("reached flop", [r["won"] for r in rows if r["flop"]]))
    print(line("no flop", [r["won"] for r in rows if not r["flop"]]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--hands", type=int, default=5000)
    args = ap.parse_args()
    rows = []
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
    bot, token = Hero(), None
    with open(args.out, "a", encoding="utf-8") as out:
        for hand_no in range(len(rows) + 1, args.hands + 1):
            try:
                token, won, flop, pos = play_hand(bot, token, hand_no, args.hands)
            except (OSError, RuntimeError) as exc:
                print("stopping at hand %d on %r" % (hand_no, exc))
                break
            time.sleep(HAND_PAUSE)
            row = {"won": won, "flop": bool(flop), "pos": pos}
            rows.append(row)
            out.write(json.dumps(row) + "\n")
            out.flush()
    summary(rows)


if __name__ == "__main__":
    main()
