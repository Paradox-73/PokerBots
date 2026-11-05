"""Quick self-checks for the solver abstraction and trainer (about 20 s, one core).

    python solver/test_solver.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "bot"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402

import abstraction as A  # noqa: E402
import train  # noqa: E402


def test_evaluator_matches_project_evaluator():
    from pokerbots.core.evaluator import evaluate
    rng = np.random.default_rng(0)
    for _ in range(500):
        c = rng.choice(52, 9, replace=False)
        scores = A.rank_boards(c[None, :5])[0]
        mine, theirs = scores[A.PID[c[5], c[6]]], scores[A.PID[c[7], c[8]]]
        ref = evaluate(list(c[:5]) + [c[5], c[6]]) - evaluate(list(c[:5]) + [c[7], c[8]])
        assert np.sign(mine - theirs) == np.sign(ref)


def test_preflop_classes():
    assert A.N_PREFLOP == 1755
    assert A.preflop_class([A.card_id(x) for x in ("As", "Kh", "2d")]) == \
        A.preflop_class([A.card_id(x) for x in ("Ac", "Kd", "2s")])


def test_tree_actions_are_legal():
    nodes, root = A.build_tree()
    for n in nodes:
        if n.kind != "act":
            continue
        p = n.player
        to_call = n.bets[1 - p] - n.bets[p]
        assert ("f" in n.actions) == (to_call > 0)
        assert n.raises <= A.MAX_RAISES
        all_in = n.bets[p] + A.STACK - n.commit[p]
        min_to = min(n.bets[1 - p] + max(n.last_raise, A.BB), all_in)
        for code, to in zip(n.actions, n.amounts):
            if code not in ("f", "c"):
                assert min_to <= to <= all_in, (n.key, code, to)
                assert n.raises < A.MAX_RAISES


def test_pool_features_match_bot_features():
    seed, per_turn = 11, 6
    pre, ff, tf, rf, _ = train.generate(seed, 1, 1, per_turn)
    rng = np.random.default_rng(seed)                       # replay generate()'s draws
    flop = rng.choice(52, 3, replace=False)
    table = A.FlopTable(flop)
    rest = np.setdiff1d(np.arange(52), flop)
    turn = rng.choice(rest, 1, replace=False)[0]
    cards = np.setdiff1d(rest, [turn])
    picks = np.argsort(rng.random((per_turn, cards.size)), axis=1)[:, :7]
    board4 = np.append(np.sort(flop), turn)
    for k in range(per_turn):
        holes = [list(cards[picks[k, 0:3]]), list(cards[picks[k, 3:6]])]
        keeps = [table.keep(h) for h in holes]
        for i in (0, 1):
            kept, thrown = keeps[i]
            w = table.opponent_holdings(keeps[1 - i][1], [A.PA[kept], A.PB[kept], thrown])
            mean, spread = A.turn_features(board4, kept, w, holes[i] + [keeps[1 - i][1]] + list(board4))
            hs = A.river_feature(np.append(board4, cards[picks[k, 6]]), kept, w)
            got = np.array([ff[k, i, 0], ff[k, i, 1], tf[k, i, 0], tf[k, i, 1], rf[k, i]]) / train.SCALE
            want = np.array([table.S[kept], table.V[kept], mean, spread, hs])
            assert np.abs(got - want).max() < 1e-4, (got, want)
            assert pre[k, i] == A.preflop_class(holes[i])


def test_cfr_pass_is_zero_sum_and_fills_tables():
    game = train.Game()
    rng = np.random.default_rng(1)
    n = 64
    ids = np.column_stack([rng.integers(0, A.N_BUCKETS[s // 2], n) for s in range(8)])
    result = rng.choice([-1.0, 0.0, 1.0], n)
    dR, dS = np.zeros(game.size), np.zeros(game.size)
    value = train.cfr_pass(game, np.zeros(game.size), ids, result, dR, dS)
    assert np.isfinite(value).all() and np.abs(value).max() <= A.STACK
    root = game.nodes[game.root]
    assert np.isclose(game.block(dS, root).sum(), n)        # root strategy weights sum to one per deal


def test_raise_mapping():
    import random
    from bot import Bot
    nodes, root = A.build_tree()
    flop = next(n for n in nodes if n.kind == "act" and n.street == A.FLOP and n.key[1] == 6 and not n.seq)
    commit, bets = list(flop.commit), [0, 0]
    for code, to in zip(flop.actions, flop.amounts):
        if code not in ("f", "c"):
            assert Bot.map_raise(flop, to, commit, bets, flop.player, None) == code
    assert Bot.map_raise(flop, 1000, commit, bets, flop.player, None) == "a"
    rng = random.Random(0)
    picks = {Bot.map_raise(flop, 5, commit, bets, flop.player, rng) for _ in range(200)}
    assert picks == {"r0.33", "r0.66"}                          # 5 chips into 12 lies between them


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
