"""Solve preflop ranges offline on the GPU.  Never shipped; needs PyTorch.

    python scripts/gpu_preflop.py work_dir --samples 400000000

Step 1 deals random hands to fill an equity table between starting-hand buckets, each
player keeping its best two cards on the flop.  It saves a checkpoint as it goes and
resumes from one.  Step 2 solves preflop betting over those buckets with CFR, a called
hand paying its equity.  The result is written as a small numpy file for export.
"""

import argparse
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pokerbots.bots import common  # noqa: E402
from pokerbots.core import evaluator as ev  # noqa: E402
from pokerbots.core import rules  # noqa: E402

BUCKETS = 48
BATCH = 400000
CHECKPOINT_EVERY = 20000000
MAX_GPU_GB = 3.0
DEVICE = "cuda"
KEEPS = ((1, 2), (0, 2), (0, 1))


def tensor(a):
    return torch.as_tensor(np.asarray(a), dtype=torch.int64, device=DEVICE)


class Tables:
    def __init__(self):
        self.pack = tensor(ev._PACK_NP)
        self.pop, self.hb, self.hr = tensor(ev._POP_NP), tensor(ev._HB_NP), tensor(ev._HR_NP)
        self.top1, self.top2 = tensor(ev._TOP1_NP), tensor(ev._TOP2_NP)
        self.top3, self.top5 = tensor(ev._TOP3_NP), tensor(ev._TOP5_NP)
        self.straight = tensor(ev._STR_NP)
        self.percent = torch.as_tensor(common._PCT_CUBE, dtype=torch.float32, device=DEVICE)


def evaluate(t, cards):
    """Torch form of evaluator.evaluate_batch: (n, k) cards to (n,) values."""
    packed = t.pack[cards].sum(dim=1)
    suits = [(packed >> sh) & ev.RMASK for sh in ev._SUIT_SHIFTS]
    any_rank = suits[0] | suits[1] | suits[2] | suits[3]
    zero = torch.zeros_like(any_rank)
    m2, m3 = zero.clone(), zero.clone()
    for a, b in ev._PAIRS:
        m2 |= suits[a] & suits[b]
    for a, b, c in ev._TRIPLES:
        m3 |= suits[a] & suits[b] & suits[c]
    m4 = suits[0] & suits[1] & suits[2] & suits[3]
    cv = ev._CV

    best = cv[ev.HIGH] | t.top5[any_rank]
    st = t.straight[any_rank]
    best = torch.where(st > 0, torch.maximum(best, cv[ev.STRAIGHT] | st << 16), best)
    for mask in suits:
        has = t.pop[mask] >= 5
        if has.any():
            sf = t.straight[mask]
            flush = cv[ev.FLUSH] | t.top5[mask]
            cand = torch.where(sf > 0, torch.maximum(cv[ev.STRAIGHT_FLUSH] | sf << 16, flush), flush)
            best = torch.where(has, torch.maximum(best, cand), best)
    p1 = t.hb[m2]
    hr1 = t.hr[p1]
    cand = cv[ev.PAIR] | hr1 << 16 | t.top3[any_rank & ~p1] << 4
    best = torch.where(m2 != 0, torch.maximum(best, cand), best)
    rest = m2 & ~p1
    p2 = t.hb[rest]
    cand = cv[ev.TWO_PAIR] | hr1 << 16 | t.hr[p2] << 12 | t.top1[any_rank & ~(p1 | p2)] << 8
    best = torch.where(rest != 0, torch.maximum(best, cand), best)
    tr = t.hb[m3]
    hrt = t.hr[tr]
    cand = cv[ev.TRIPS] | hrt << 16 | t.top2[any_rank & ~tr] << 8
    best = torch.where(m3 != 0, torch.maximum(best, cand), best)
    rest = m2 & ~tr
    cand = cv[ev.FULL_HOUSE] | hrt << 16 | t.hr[t.hb[rest]] << 12
    best = torch.where((m3 != 0) & (rest != 0), torch.maximum(best, cand), best)
    q = t.hb[m4]
    cand = cv[ev.QUADS] | t.hr[q] << 16 | t.top1[any_rank & ~q] << 12
    return torch.where(m4 != 0, torch.maximum(best, cand), best)


def best_keep(t, three, flop):
    """The two of (n, 3) cards that make the best hand on the flop."""
    made = torch.stack([evaluate(t, torch.cat([three[:, list(k)], flop], dim=1)) for k in KEEPS], dim=1)
    index = torch.as_tensor(KEEPS, device=DEVICE)[made.argmax(dim=1)]
    return three.gather(1, index)


def bucket_of(t, three):
    ordered = three.sort(dim=1).values
    pct = t.percent[ordered[:, 0], ordered[:, 1], ordered[:, 2]]
    return (pct * BUCKETS).long().clamp(max=BUCKETS - 1)


def sample_equity(work, target):
    path = os.path.join(work, "equity_counts.npz")
    wins = torch.zeros((BUCKETS, BUCKETS), device=DEVICE, dtype=torch.float64)
    games = torch.zeros((BUCKETS, BUCKETS), device=DEVICE, dtype=torch.float64)
    done = 0
    if os.path.exists(path):
        saved = np.load(path)
        wins += torch.as_tensor(saved["wins"], device=DEVICE)
        games += torch.as_tensor(saved["games"], device=DEVICE)
        done = int(saved["done"])
    t = Tables()
    start, last_save = time.time(), done
    while done < target:
        cards = torch.rand(BATCH, rules.DECK_SIZE, device=DEVICE).argsort(dim=1)[:, :11]
        a, b, board = cards[:, :3], cards[:, 3:6], cards[:, 6:]
        flop = board[:, :3]
        value_a = evaluate(t, torch.cat([best_keep(t, a, flop), board], dim=1))
        value_b = evaluate(t, torch.cat([best_keep(t, b, flop), board], dim=1))
        score = (value_a > value_b).double() + 0.5 * (value_a == value_b).double()
        i, j = bucket_of(t, a), bucket_of(t, b)
        key = i * BUCKETS + j
        wins += torch.bincount(key, weights=score, minlength=BUCKETS ** 2).view(BUCKETS, BUCKETS)
        games += torch.bincount(key, minlength=BUCKETS ** 2).view(BUCKETS, BUCKETS).double()
        done += BATCH
        peak = torch.cuda.max_memory_allocated() / 2 ** 30
        if peak > MAX_GPU_GB:
            raise RuntimeError("GPU memory %.1f GB over the limit" % peak)
        if done - last_save >= CHECKPOINT_EVERY or done >= target:
            np.savez(path + ".tmp.npz", wins=wins.cpu().numpy(), games=games.cpu().numpy(), done=done)
            os.replace(path + ".tmp.npz", path)
            last_save = done
            print("%d hands, %.0f per second, gpu peak %.2f GB"
                  % (done, (done - 0) / max(1.0, time.time() - start), peak), flush=True)
    # a game of i against j also counts for j against i, with the score reversed
    won = wins + (games.T - wins.T)
    return ((won + 1.0) / (games + games.T + 2.0)).cpu().numpy()


# ------------------------------------------------------------------- preflop CFR
OPEN_SIZES = (5, 7)        # raise-to amounts for a first raise
THREE_BET = 3.0            # later raises multiply the last raise
STACK = rules.STARTING_STACK


class Node:
    def __init__(self, player, key, actions, children):
        self.player, self.key, self.actions, self.children = player, key, actions, children
        self.regret = torch.zeros((BUCKETS, len(actions)), device=DEVICE, dtype=torch.float64)
        self.total = torch.zeros((BUCKETS, len(actions)), device=DEVICE, dtype=torch.float64)


class Leaf:
    def __init__(self, fold_player, stake):
        self.fold_player, self.stake = fold_player, stake


def build(nodes):
    """Player 0 is the small blind.  Raises counted include the big blind's, as the rules do."""

    def node(player, bets, raises, key):
        me, opp = bets[player], bets[1 - player]
        acts, kids = [], []
        if opp > me:
            acts.append("f")
            kids.append(Leaf(player, me))
        acts.append("c")
        if opp > me and not (player == 0 and raises == 1):
            kids.append(Leaf(None, opp))
        elif player == 0:          # the small blind completes: the big blind has its option
            kids.append(node(1, [2, 2], raises, key + "c"))
        else:
            kids.append(Leaf(None, opp))
        if raises < rules.MAX_RAISES_PER_STREET and opp < STACK:
            sizes = OPEN_SIZES if raises == 1 else (int(THREE_BET * opp),)
            for to in sorted({min(s, STACK) for s in sizes} | {STACK}):
                if to <= opp:
                    continue
                label = "a" if to >= STACK else "r%d" % to
                acts.append(label)
                new = list(bets)
                new[player] = to
                kids.append(node(1 - player, new, raises + 1, key + label + "/"))
        n = Node(player, key, acts, kids)
        nodes.append(n)
        return n

    return node(0, [1, 2], 1, "")


def strategy(regret):
    pos = regret.clamp(min=0.0)
    total = pos.sum(dim=1, keepdim=True)
    return torch.where(total > 0, pos / total.clamp(min=1e-30), torch.full_like(pos, 1.0 / regret.shape[1]))


def walk(n, hero, reach, equity, weight):
    """Chip value for hero of each hero bucket; updates hero's regrets."""
    if isinstance(n, Leaf):
        mass = reach.sum()
        if n.fold_player is not None:
            net = -n.stake if n.fold_player == hero else n.stake
            return torch.full_like(reach, float(net)) * mass
        return (2.0 * equity[hero] - 1.0) @ reach * n.stake
    s = strategy(n.regret)
    if n.player == hero:
        values = torch.stack([walk(c, hero, reach, equity, weight) for c in n.children], dim=1)
        mean = (s * values).sum(dim=1)
        n.regret = (n.regret + values - mean[:, None]).clamp(min=0.0)
        return mean
    n.total += weight * s * reach[:, None]
    return sum(walk(c, hero, reach * s[:, a], equity, weight) for a, c in enumerate(n.children))


def average(n):
    t = n.total.sum(dim=1, keepdim=True)
    return torch.where(t > 0, n.total / t.clamp(min=1e-30), torch.full_like(n.total, 1.0 / n.total.shape[1]))


def best_value(n, hero, reach, equity):
    if isinstance(n, Leaf):
        mass = reach.sum()
        if n.fold_player is not None:
            net = -n.stake if n.fold_player == hero else n.stake
            return torch.full_like(reach, float(net)) * mass
        return (2.0 * equity[hero] - 1.0) @ reach * n.stake
    if n.player == hero:
        return torch.stack([best_value(c, hero, reach, equity) for c in n.children], dim=1).max(dim=1).values
    s = average(n)
    return sum(best_value(c, hero, reach * s[:, a], equity) for a, c in enumerate(n.children))


def solve(work, table, iterations):
    nodes = []
    root = build(nodes)
    e = torch.as_tensor(table, device=DEVICE, dtype=torch.float64)
    equity = (e, e)
    uniform = torch.full((BUCKETS,), 1.0 / BUCKETS, device=DEVICE, dtype=torch.float64)
    for t in range(1, iterations + 1):
        for hero in (0, 1):
            walk(root, hero, uniform, equity, float(t))
        if t % 2000 == 0 or t == iterations:
            gain = sum(float((best_value(root, h, uniform, equity) * uniform).sum()) for h in (0, 1))
            print("iteration %d, exploitability %.4f chips per hand" % (t, gain / 2), flush=True)
            np.savez(os.path.join(work, "preflop_strategy.npz"),
                     **{"n" + n.key: average(n).cpu().numpy() for n in nodes},
                     **{"a" + n.key: np.array(n.actions) for n in nodes})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--samples", type=int, default=400000000)
    ap.add_argument("--iterations", type=int, default=20000)
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    assert torch.cuda.is_available(), "this job runs on the GPU"
    table = sample_equity(args.work, args.samples)
    gap = float(np.abs(table + table.T - 1.0).max())
    print("equity table done, symmetry %.5f, best vs worst %.3f" % (gap, table[-1, 0]), flush=True)
    assert gap < 0.01 and table[-1, 0] > 0.6, "the equity table is wrong"
    solve(args.work, table, args.iterations)
    print("SOLVED", flush=True)


if __name__ == "__main__":
    main()
