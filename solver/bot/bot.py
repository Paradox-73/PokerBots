"""Discard Hold'em bot that plays a precomputed equilibrium strategy.

The strategy was solved offline with discounted CFR on an abstract game
(abstraction.py) and is embedded in strategy.py.  At each decision the bot

  1. replays the hand's action history through the abstract betting DAG,
     mapping each real raise onto the nearest abstract sizes (randomised
     pseudo-harmonic mapping for the opponent's raises),
  2. computes its card bucket for the current street,
  3. samples an action from the stored strategy and converts its pot fraction
     back to chips for the real pot.

On top of that: a match-level overlay that folds out a won match and judges
big call/fold decisions by the chance of winning the match, a simple
strength-based fallback for states the abstraction does not cover, and a time
guard that check-folds when the time bank runs low.
"""

import base64
import io
import json
import os
import random
import sys
import zlib

sys.dont_write_bytecode = True                 # the contest filesystem is read-only
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

import abstraction as A  # noqa: E402
from strategy import BLOB  # noqa: E402

MIN_PROB = 0.04            # actions below this probability are dropped before sampling
MIN_BANK_MS = 3000         # below this time bank, check or fold without computing
LOCK_SAFE_SDS = 3.0        # keep playing a won match only when this many sd safe
STREET = {name: i for i, name in enumerate(A.STREET_NAMES)}


# ====================================================================== strategy
class Strategy:
    def __init__(self):
        data = np.load(io.BytesIO(zlib.decompress(base64.b85decode("".join(BLOB)))))
        self.nodes, self.root = A.build_tree()
        self.offsets, size = A.decision_layout(self.nodes, A.N_BUCKETS)
        if int(data["size"]) != size:
            raise RuntimeError("strategy.py was trained for a different abstraction")
        self.table = data["table"]
        self.flop_x, self.flop_y = data["flop_x"], data["flop_y"]
        self.turn_x, self.turn_y = data["turn_x"], data["turn_y"]
        self.river = data["river"]
        self.pre_eq = data["pre_eq"]

    def probs(self, node, bucket):
        na = len(node.actions)
        o = self.offsets[node.id] + bucket * na
        p = self.table[o:o + na].astype(np.float64)
        if p.sum() <= 0:
            p[:] = 1.0
        p /= p.sum()
        p[p < MIN_PROB] = 0.0
        return p / p.sum() if p.sum() > 0 else np.full(na, 1.0 / na)


def pseudo_harmonic(x, lo, hi):
    """Probability of mapping a bet of x pots to the smaller abstract size lo (< x < hi)."""
    return (hi - x) * (1 + lo) / ((hi - lo) * (1 + x))


# ====================================================================== hand state
class Hand:
    def __init__(self, hand_id, seat, hole):
        self.id, self.seat, self.hole = hand_id, seat, hole
        self.flop = None              # FlopTable
        self.kept = self.discarded = self.opp_discard = None
        self.features = {}            # street -> (bucket, strength)
        self.opp_map = {}             # history index -> abstract code chosen for an opponent raise
        self.my_codes = {}            # history index -> abstract code of our own raise


class Bot:
    def __init__(self):
        self.strategy = Strategy()
        self.rng = random.Random()
        self.total_hands = 1000
        self.net = self.net_squares = self.hands_done = 0
        self.hand = None

    # ------------------------------------------------------------------ messages
    def on_init(self, msg):
        self.total_hands = int(msg.get("total_hands", self.total_hands))

    def on_new_hand(self, msg):
        seat = 0 if msg["seat"] == "button" else 1
        self.hand = Hand(msg["hand_id"], seat, [A.card_id(c) for c in msg["hole_cards"]])

    def on_discard_result(self, msg):
        h = self.hand
        h.opp_discard = A.card_id(msg["opp_discard"])
        h.discarded = A.card_id(msg["my_discard"])
        kept = [A.card_id(c) for c in msg["hole_cards"]]
        h.kept = A.PID[kept[0], kept[1]]

    def on_hand_result(self, msg):
        delta = int(msg.get("net", 0))
        self.net += delta
        self.net_squares += delta * delta
        self.hands_done += 1

    # ------------------------------------------------------------------ features
    def features(self, street, board):
        """(bucket, strength) for this street; strength is an equity-like number in [0, 1]."""
        h, s = self.hand, self.strategy
        if street in h.features:
            return h.features[street]
        if street == A.PREFLOP:
            cls = A.preflop_class(h.hole)
            out = (cls, float(s.pre_eq[cls]))
        elif street == A.FLOP:
            table = self.flop_table(board)
            kept, _ = table.keep(h.hole)
            out = (A.bucket_2d(table.S[kept], table.V[kept], s.flop_x, s.flop_y), float(table.S[kept]))
        else:
            table = self.flop_table(board)
            if h.kept is None:        # no discard_result seen; assume our own keep rule
                h.kept, h.discarded = table.keep(h.hole)
            dead = [A.PA[h.kept], A.PB[h.kept], h.discarded]
            w = table.opponent_holdings(h.opp_discard, dead) if h.opp_discard is not None \
                else table.valid & ~A.HAS[dead].any(axis=0)
            if street == A.TURN:
                known = list(h.hole) + list(board) + ([h.opp_discard] if h.opp_discard is not None else [])
                mean, spread = A.turn_features(np.array(board), h.kept, w, known)
                out = (A.bucket_2d(mean, spread, s.turn_x, s.turn_y), mean)
            else:
                hs = A.river_feature(np.array(board), h.kept, w)
                out = (A.bucket_1d(hs, s.river), hs)
        h.features[street] = out
        return out

    def flop_table(self, board):
        if self.hand.flop is None:
            self.hand.flop = A.FlopTable(board[:3])
        return self.hand.flop

    # ------------------------------------------------------------------ abstraction
    def abstract_node(self, req):
        """The abstract node matching the real history, or None when off the tree."""
        nodes, h = self.strategy.nodes, self.hand
        node = nodes[self.strategy.root]
        commit, bets = [A.SB, A.BB], [A.SB, A.BB]
        street = 0
        for i, ev in enumerate(req.get("history", [])):
            st = STREET[ev["street"]]
            if st != street:
                street, bets = st, [0, 0]
            actor = h.seat if ev["actor"] == "me" else 1 - h.seat
            if node.kind != "act" or node.player != actor or node.street != st:
                return None
            kind = ev["action"]
            if kind in ("check", "call"):
                code, to = "c", bets[1 - actor]
            elif kind == "raise":
                to = int(ev["amount"])
                if ev["actor"] == "me":
                    code = h.my_codes.get(i) or self.map_raise(node, to, commit, bets, actor, None)
                else:
                    code = h.opp_map.get(i) or self.map_raise(node, to, commit, bets, actor, self.rng)
                    h.opp_map[i] = code
                if code is None:
                    return None
            else:
                return None
            commit[actor] += to - bets[actor]
            bets[actor] = to
            node = nodes[node.children[node.actions.index(code)]]
        st = STREET[req["street"]]
        if node.kind != "act" or node.player != h.seat or node.street != st:
            return None
        return node

    @staticmethod
    def map_raise(node, to, commit, bets, actor, rng):
        """Abstract code for a real raise to `to`: nearest by pot fraction, or randomised
        pseudo-harmonic between the two neighbouring abstract sizes when rng is given."""
        options = [(c, a) for c, a in zip(node.actions, node.amounts) if c not in ("f", "c")]
        if not options:
            return None
        all_in = bets[actor] + A.STACK - commit[actor]
        if to >= all_in and options[-1][0] == "a":
            return "a"
        real_call = bets[1 - actor] - bets[actor]
        x = (to - bets[1 - actor]) / max(1, commit[0] + commit[1] + real_call)
        ab_call = node.bets[1 - actor] - node.bets[actor]
        fracs = [((a - node.bets[1 - actor]) / max(1, node.pot + ab_call), c) for c, a in options]
        fracs.sort()
        if x <= fracs[0][0]:
            return fracs[0][1]
        if x >= fracs[-1][0]:
            return fracs[-1][1]
        for (lo, c_lo), (hi, c_hi) in zip(fracs, fracs[1:]):
            if lo <= x <= hi:
                if rng is None:
                    return c_lo if x - lo <= hi - x else c_hi
                return c_lo if rng.random() < pseudo_harmonic(x, lo, hi) else c_hi
        return fracs[-1][1]

    # ------------------------------------------------------------------ decisions
    def act(self, req):
        legal = req["legal_actions"]
        if req.get("time_left_ms", 10 ** 9) < MIN_BANK_MS or self.locked_in(req):
            return check_or_fold(legal)
        street = STREET[req["street"]]
        bucket, strength = self.features(street, [A.card_id(c) for c in req["board"]])
        node = self.abstract_node(req)
        if node is None:
            action = fallback(req, strength)
        else:
            p = self.strategy.probs(node, bucket)
            pick = int(np.searchsorted(np.cumsum(p), self.rng.random()))
            code = node.actions[min(pick, len(p) - 1)]
            action = self.to_real(req, code)
            if action["action"] == "raise":
                self.hand.my_codes[len(req.get("history", []))] = code
        if req["to_call"] > 0 and action["action"] in ("call", "fold") and self.line_in_reach(req):
            action = self.match_decision(req, strength, action)
        return action

    @staticmethod
    def to_real(req, code):
        legal, to_call = req["legal_actions"], req["to_call"]
        if code == "f":
            return check_or_fold(legal) if to_call > 0 else {"type": "action", "action": "check"}
        if code == "c" or "raise" not in legal:
            return {"type": "action", "action": "call" if to_call > 0 else "check"}
        if code == "a":
            amount = req["max_raise"]
        else:
            amount = req["opp_bet"] + int(round(float(code[1:]) * (req["pot"] + to_call)))
        amount = max(req["min_raise"], min(req["max_raise"], amount))
        return {"type": "action", "action": "raise", "amount": int(amount)}

    def discard(self, req):
        hole = [A.card_id(c) for c in req["hole_cards"]]
        table = self.flop_table([A.card_id(c) for c in req["board"]])
        kept, thrown = table.keep(hole)
        self.hand.kept, self.hand.discarded = kept, thrown
        return {"type": "discard", "card": A.card_name(int(thrown))}

    # ------------------------------------------------------------------ match overlay
    def hands_left(self, req):
        """Hands still to play, this one included."""
        return max(1, self.total_hands - int(req.get("hand_id", self.hand.id)) + 1)

    @staticmethod
    def lock_line(hands):
        """The most that check-folding `hands` hands can lose."""
        return (hands + 1) // 2 * A.BB + hands // 2 * A.SB

    def locked_in(self, req):
        """True when check-folding the rest surely wins and playing on could lose."""
        left = self.hands_left(req)
        if self.net <= self.lock_line(left):
            return False
        rate = self.net / max(1, self.hands_done)
        spread = max(1.0, (self.net_squares / max(1, self.hands_done) * left) ** 0.5)
        return (self.net + max(0.0, rate) * left) / spread < LOCK_SAFE_SDS

    def win_chance(self, lead, hands):
        """Match-win chance from a lead between even bots: linear between the lock lines."""
        line = max(1, self.lock_line(hands))
        return min(1.0, max(0.0, (lead + line) / (2.0 * line)))

    def line_in_reach(self, req):
        at_risk = A.STACK - req["my_stack"] + req["to_call"]
        return abs(self.net) + at_risk >= self.lock_line(self.hands_left(req) - 1)

    def match_decision(self, req, eq, action):
        """Call or fold by the chance of winning the match; keeps the chip decision when
        the opponent's lock line is already passed or both choices score the same."""
        left = self.hands_left(req) - 1
        spent = A.STACK - req["my_stack"]
        at_risk = spent + req["to_call"]
        folded = self.win_chance(self.net - spent, left)
        called = eq * self.win_chance(self.net + at_risk, left) \
            + (1.0 - eq) * self.win_chance(self.net - at_risk, left)
        if folded <= 0.0 or called == folded:
            return action
        return {"type": "action", "action": "call" if called > folded else "fold"}


def check_or_fold(legal):
    return {"type": "action", "action": "check" if "check" in legal else "fold"}


def fallback(req, strength):
    """Strength-versus-price play for states outside the abstraction."""
    legal, to_call, pot = req["legal_actions"], req["to_call"], req["pot"]
    can_raise = "raise" in legal

    def raise_to(fraction):
        amount = req["opp_bet"] + int(fraction * (pot + to_call))
        return {"type": "action", "action": "raise",
                "amount": int(max(req["min_raise"], min(req["max_raise"], amount)))}

    if to_call > 0:
        if can_raise and strength > 0.88:
            return raise_to(1.0)
        price = to_call / (pot + to_call)
        return {"type": "action", "action": "call" if strength > price + 0.05 else "fold"}
    if can_raise and strength > 0.72:
        return raise_to(0.6)
    return {"type": "action", "action": "check"}


def main():
    bot = Bot()
    handlers = {"init": bot.on_init, "new_hand": bot.on_new_hand,
                "discard_result": bot.on_discard_result, "hand_result": bot.on_hand_result}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        kind = msg.get("type")
        try:
            if kind == "action_request":
                reply = bot.act(msg)
            elif kind == "discard_request":
                reply = bot.discard(msg)
            elif kind == "match_end":
                break
            else:
                if kind in handlers:
                    handlers[kind](msg)
                continue
        except Exception as exc:          # a poor move costs one hand; a crash forfeits the match
            print(f"error on {kind}: {exc!r}", file=sys.stderr)
            if kind == "action_request":
                reply = check_or_fold(msg.get("legal_actions", []))
            else:
                reply = {"type": "discard", "card": msg["hole_cards"][0]}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
