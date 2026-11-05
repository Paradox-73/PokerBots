"""THE protocol adapter.  The only module that knows the wire format.

Official Discard Hold'em protocol v1.0 (docs/protocol.pdf): one JSON object
per line, UTF-8, with a "type" field.

  engine -> bot   init, new_hand, action_request, discard_request,
                  discard_result, hand_result, notice, match_end
  bot -> engine   {"type":"action","action":"fold|check|call|raise"[,"amount":N]}
                  {"type":"discard","card":"Kd"}

Amounts for call/raise are "to" amounts (the actor's street total).  Bots
reply only to action_request and discard_request, and must ignore unknown
message types and fields.

  * BotAdapter           (bot side)    JSON -> GameInfo/HandView/Event,
                                       Action / discard card -> JSON
  * encode_* / parse_*   (engine side, used only by our local runner)
"""

import json
import sys

from pokerbots.core import rules
from pokerbots.core.cards import card_to_str, str_to_card
from pokerbots.core.types import (Action, Event, GameInfo, HandView,
                                  FOLD, CHECK, CALL, RAISE)

STREET_INDEX = {name: i for i, name in enumerate(rules.STREET_NAMES)}


def _dump(msg):
    return json.dumps(msg, separators=(",", ":"))


def _cards(cards):
    return [card_to_str(c) for c in cards]


def _uncards(texts):
    return [str_to_card(t) for t in texts]


# ============================================================ engine side
def encode_init(total_hands, time_bank_s):
    return _dump({"type": "init", "protocol_version": "1.0", "total_hands": total_hands,
                  "starting_stack": rules.STARTING_STACK, "small_blind": rules.SMALL_BLIND,
                  "big_blind": rules.BIG_BLIND, "time_bank_ms": int(time_bank_s * 1000),
                  "per_response_ms": int(rules.PER_RESPONSE_SECONDS * 1000)})


def encode_new_hand(state, seat, hand_id):
    return _dump({"type": "new_hand", "hand_id": hand_id,
                  "seat": "button" if seat == state.button else "big_blind",
                  "hole_cards": _cards(state.hole[seat]),
                  "stack": state.start_stacks[seat], "opp_stack": state.start_stacks[1 - seat]})


def _history(state, seat):
    out = []
    for ev in state.events:
        if ev[0] != "act":
            continue
        _, street, actor, kind, amount = ev
        e = {"street": rules.STREET_NAMES[street], "actor": "me" if actor == seat else "opp",
             "action": kind}
        if kind in (CALL, RAISE):
            e["amount"] = amount
        out.append(e)
    return out


def encode_action_request(state, seat, hand_id, time_left_s):
    legal = state.legal(seat)
    msg = {"type": "action_request", "hand_id": hand_id,
           "street": rules.STREET_NAMES[state.street], "board": _cards(state.board),
           "pot": state.pot, "my_bet": state.bets[seat], "opp_bet": state.bets[1 - seat],
           "to_call": legal.to_call, "my_stack": state.stacks[seat],
           "opp_stack": state.stacks[1 - seat],
           "legal_actions": [k for k in (FOLD, CHECK, CALL, RAISE) if k in legal.kinds]}
    if RAISE in legal.kinds:
        msg["min_raise"], msg["max_raise"] = legal.min_raise, legal.max_raise
    msg["raises_left"] = max(0, rules.MAX_RAISES_PER_STREET - state.raises)
    msg["history"] = _history(state, seat)
    msg["time_left_ms"] = int(time_left_s * 1000)
    return _dump(msg)


def encode_discard_request(state, seat, hand_id, time_left_s):
    return _dump({"type": "discard_request", "hand_id": hand_id,
                  "hole_cards": _cards(state.hole[seat]), "board": _cards(state.board),
                  "pot": state.pot, "my_stack": state.stacks[seat],
                  "opp_stack": state.stacks[1 - seat], "time_left_ms": int(time_left_s * 1000)})


def encode_discard_result(state, seat, hand_id):
    return _dump({"type": "discard_result", "hand_id": hand_id,
                  "my_discard": card_to_str(state.discards[seat]),
                  "opp_discard": card_to_str(state.discards[1 - seat]),
                  "hole_cards": _cards(state.hole[seat])})


def encode_hand_result(state, seat, hand_id):
    return _dump({"type": "hand_result", "hand_id": hand_id,
                  "result": "showdown" if state.showdown else "fold",
                  "net": state.deltas[seat], "board": _cards(state.board),
                  "my_hole_cards": _cards(state.hole[seat]),
                  "opp_hole_cards": _cards(state.hole[1 - seat]) if state.showdown else None,
                  "opp_discard": card_to_str(state.discards[1 - seat]) if state.discards else None,
                  "history": _history(state, seat)})


def encode_notice(code, applied):
    return _dump({"type": "notice", "code": code, "applied": applied})


def encode_match_end(reason="complete"):
    return _dump({"type": "match_end", "reason": reason})


def _parse(line, kind):
    if line is None:
        return None
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    return msg if isinstance(msg, dict) and msg.get("type") == kind else None


def parse_action(line):
    """Bot reply text -> Action, or None if unparseable."""
    msg = _parse(line, "action")
    if msg is None or msg.get("action") not in (FOLD, CHECK, CALL, RAISE):
        return None
    if msg["action"] == RAISE:
        amount = msg.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            return None
        return Action.raise_to(amount)
    return Action(msg["action"])


def parse_discard(line):
    """Bot reply text -> card id, or None if unparseable."""
    msg = _parse(line, "discard")
    try:
        return str_to_card(msg["card"]) if msg else None
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return None


def encode_action(action):
    msg = {"type": "action", "action": action.kind}
    if action.kind == RAISE:
        msg["amount"] = action.amount
    return _dump(msg)


def encode_discard(card):
    return _dump({"type": "discard", "card": card_to_str(card)})


# =============================================================== bot side
class BotAdapter:
    """Feeds wire messages to a Bot (see pokerbots/bots/base.py).

    handle_line(line) returns the reply text, or None if no reply is due.
    The bot is always seat 0 in its HandView and the opponent seat 1.
    """

    ME, OPP = 0, 1

    def __init__(self, bot):
        self.bot = bot
        self.info = None
        self.view = None
        self.seen = 0          # history entries already turned into events
        self.done = False

    def handle_line(self, line):
        try:
            msg = json.loads(line)
        except ValueError:
            return None
        if not isinstance(msg, dict):
            return None
        t = msg.get("type")
        if t == "init":
            self.info = GameInfo(msg["total_hands"], msg["time_bank_ms"] / 1000.0,
                                 msg["starting_stack"], msg["small_blind"], msg["big_blind"])
            self.bot.on_game_start(self.info)
            return None
        if t == "new_hand":
            info = self.info
            self.view = HandView(
                hand_no=msg["hand_id"], my_seat=self.ME,
                button=self.ME if msg["seat"] == "button" else self.OPP,
                hole=_uncards(msg["hole_cards"]),
                num_hands=info.num_hands if info else 0,
                time_bank=self.view.time_bank if self.view else (info.time_bank if info else 0.0))
            self.seen = 0
            self.bot.on_hand_start(self.view)
            return None
        v = self.view
        if v is None:          # new_hand was lost or unreadable
            return fallback_reply(line)
        if t == "action_request":
            self._sync(msg, STREET_INDEX[msg["street"]])
            v.legal = frozenset(msg["legal_actions"])
            v.pot, v.my_bet, v.opp_bet = msg["pot"], msg["my_bet"], msg["opp_bet"]
            v.to_call, v.my_stack, v.opp_stack = msg["to_call"], msg["my_stack"], msg["opp_stack"]
            v.min_raise, v.max_raise = msg.get("min_raise", 0), msg.get("max_raise", 0)
            v.time_bank = msg["time_left_ms"] / 1000.0
            return encode_action(self._safe_action(v))
        if t == "discard_request":
            self._sync(msg, rules.DISCARD_STREET)
            v.hole = _uncards(msg["hole_cards"])
            v.pot, v.my_stack, v.opp_stack = msg["pot"], msg["my_stack"], msg["opp_stack"]
            v.time_bank = msg["time_left_ms"] / 1000.0
            return encode_discard(self._safe_discard(v))
        if t == "discard_result":
            mine, theirs = str_to_card(msg["my_discard"]), str_to_card(msg["opp_discard"])
            v.hole = _uncards(msg["hole_cards"])
            v.dead = [mine, theirs]
            self._event(Event("discard", rules.DISCARD_STREET, self.ME, cards=[mine]))
            self._event(Event("discard", rules.DISCARD_STREET, self.OPP, cards=[theirs]))
            return None
        if t == "hand_result":
            self._sync(msg, None)
            if msg.get("opp_hole_cards"):
                v.opp_cards = _uncards(msg["opp_hole_cards"])
                self._event(Event("show", v.street, self.OPP, cards=list(v.opp_cards)))
            self.bot.on_hand_end(v, msg["net"])
            return None
        if t == "match_end":
            self.done = True
            self.bot.on_game_end()
            return None
        if t == "notice":
            sys.stderr.write("notice: %s -> %s\n" % (msg.get("code"), msg.get("applied")))
        return None

    def _sync(self, msg, street):
        """Turn new history entries and board cards into events, in order."""
        board = _uncards(msg.get("board", []))
        hist = msg.get("history") or []
        for e in hist[self.seen:]:
            st = STREET_INDEX[e["street"]]
            if st > self.view.street:
                self._new_street(st, board)
            seat = self.ME if e["actor"] == "me" else self.OPP
            self._event(Event("act", st, seat, e["action"], e.get("amount", 0)))
        self.seen = max(self.seen, len(hist))
        if street is None:     # hand_result: board as dealt, street unknown
            street = max(self.view.street,
                         max((i for i, n in enumerate(_DEALT) if n <= len(board)), default=0))
        if street > self.view.street:
            self._new_street(street, board)

    def _new_street(self, street, board):
        v = self.view
        v.street = street
        v.board = board[:_DEALT[street]]
        self._event(Event("board", street, cards=list(v.board)))

    def _event(self, ev):
        self.view.history.append(ev)
        self.bot.on_event(self.view, ev)

    def _safe_action(self, v):
        """Never let a strategy bug produce an illegal or crashing reply."""
        try:
            a = self.bot.act(v)
        except Exception as exc:  # noqa: BLE001 - survival beats purity here
            sys.stderr.write("bot.act raised %r\n" % (exc,))
            a = None
        if not isinstance(a, Action) or a.kind not in v.legal:
            return Action.check() if CHECK in v.legal else Action.fold()
        if a.kind == RAISE:
            amt = max(v.min_raise, min(v.max_raise, int(a.amount)))
            return Action.raise_to(amt)
        return a

    def _safe_discard(self, v):
        try:
            c = self.bot.discard(v)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write("bot.discard raised %r\n" % (exc,))
            c = None
        return c if c in v.hole else rules.default_discard(v.hole)

    def run(self, inp=None, out=None):
        if inp is None:
            sys.stdin.reconfigure(errors="replace")   # a bad byte must not raise in readline
        inp = inp or sys.stdin
        out = out or sys.stdout
        while not self.done:
            line = inp.readline()
            if not line:
                break
            try:
                reply = self.handle_line(line)
            except Exception as exc:  # noqa: BLE001 - a crash forfeits the whole match
                sys.stderr.write("handle_line raised %r on %r\n" % (exc, line[:200]))
                reply = fallback_reply(line, self.view.hole if self.view else None)
            if reply is not None:
                try:
                    out.write(reply + "\n")
                    out.flush()
                except OSError:      # the engine has gone: nothing is left to answer
                    return


def fallback_reply(line, known_hole=None):
    """Reply to a request the adapter failed to process.  The engine turns an
    illegal check into a fold and an illegal discard into its default card, so
    answering is never worse than staying silent (which forfeits)."""
    try:
        msg = json.loads(line)
        kind = msg.get("type")
    except Exception:  # noqa: BLE001
        return None
    if kind == "action_request":
        return encode_action(Action.check())
    if kind == "discard_request":
        try:
            hole = _uncards(msg["hole_cards"])
        except Exception:  # noqa: BLE001
            hole = known_hole
        if not hole:
            return _dump({"type": "discard", "card": None})
        return encode_discard(rules.default_discard(hole))
    return None


# board cards dealt by the end of each street index
_DEALT = [sum(n for _, n in rules.STREETS[:i + 1]) for i in range(len(rules.STREETS))]
