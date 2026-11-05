"""Plays the river from the solved table.

A live hand maps onto the table in three steps: stack depth to the nearest solved
depth, each bet made on the river to the nearest solved size, and our equity to a
strength bucket.  Anything the table does not cover returns None and the caller
uses its normal rules.
"""

import base64
import math

import numpy as np

from pokerbots.field.river_table import BUCKETS, SPRS, TABLES
from pokerbots.bots.simple import bet_to
from pokerbots.core.types import Action, CALL, CHECK, RAISE

RIVER = 3
TABLE_CHECK = "x"
_rows = {}


def _depth(spr):
    return min(range(len(SPRS)), key=lambda i: abs(math.log(SPRS[i] / max(spr, 0.01))))


def _bet_label(actions, fraction, all_in):
    if all_in and "a" in actions:
        return "a"
    sizes = [a for a in actions if a.startswith("b")]
    if not sizes:
        return "a" if "a" in actions else None
    return min(sizes, key=lambda a: abs(float(a[1:]) - fraction))


def _row(depth, path, bucket):
    key = (depth, path)
    if key not in _rows:
        actions, data = TABLES[depth][path]
        _rows[key] = np.frombuffer(base64.b85decode(data), dtype=np.uint8).reshape(
            BUCKETS, len(actions)).astype(float)
    return _rows[key][bucket]


def locate(view):
    """(depth index, table key) for the current decision, or None if off the table."""
    acts = [e for e in view.history if e.kind == "act" and e.street == RIVER]
    start_pot = view.pot - view.my_bet - view.opp_bet
    behind = view.my_stack + view.my_bet
    if start_pot <= 0 or behind <= 0:
        return None
    depth = _depth(behind / start_pot)
    table = TABLES[depth]
    path = ""
    bets = {view.my_seat: 0, 1 - view.my_seat: 0}
    for e in acts:
        if path not in table:
            return None
        actions = table[path][0]
        other = bets[1 - e.seat]
        if e.action == CHECK:
            if TABLE_CHECK not in actions:
                return None
            path += TABLE_CHECK
        elif e.action == RAISE:
            pot_after_call = start_pot + bets[0] + bets[1] + other - bets[e.seat]
            label = _bet_label(actions, (e.amount - other) / max(1, pot_after_call),
                               e.amount >= behind)
            if label is None:
                return None
            path += label + "/"
            bets[e.seat] = e.amount
        else:
            return None
    return (depth, path) if path in table else None


def river_action(view, eq, rng):
    """An Action drawn from the solved strategy, or None when off the table."""
    where = locate(view)
    if where is None:
        return None
    depth, path = where
    actions = TABLES[depth][path][0]
    bucket = min(BUCKETS - 1, int(eq * BUCKETS))
    weights = _row(depth, path, bucket)
    total = weights.sum()
    if total <= 0:
        return None
    label = actions[int(rng.choice(len(actions), p=weights / total))]
    if label == "f":
        return Action.fold()
    if label == "c":
        return Action.call()
    if label == TABLE_CHECK:
        return Action.check()
    if RAISE not in view.legal:
        return Action.call() if CALL in view.legal else Action.check()
    if label == "a":
        return Action.raise_to(view.max_raise)
    return Action.raise_to(bet_to(view, float(label[1:])))
