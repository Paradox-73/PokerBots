"""Train the solver bot's strategy with chance-sampled discounted CFR.

Three steps, one sub-command each:

  deals   sample deals and compute every player's street features
          (writes an .npz "deal pool"; parallel over --workers processes)
  solve   bucket the pool, then run discounted CFR (DCFR, alpha 1.5, beta 0,
          gamma 2) over the abstract betting DAG.  Each iteration every worker
          draws --batch deals from the pool and does one full vectorised pass of
          the DAG for all of them: a forward pass for reach probabilities and a
          backward pass for values and regrets.  Checkpoints every --every seconds
          and resumes from --checkpoint if it exists.
  export  average strategy -> bot/strategy.py (zlib-compressed npz, base85 text)

Example:
  python train.py deals --flops 150000 --workers 14 --out pool.npz
  python train.py solve --pool pool.npz --checkpoint ckpt.npz --workers 14 --hours 8
  python train.py export --checkpoint ckpt.npz --out bot/strategy.py
"""

import argparse
import base64
import io
import multiprocessing as mp
import os
import sys
import time
import zlib
from multiprocessing import shared_memory

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot"))
import abstraction as A  # noqa: E402

SCALE = 65535.0                     # features are stored as uint16 fractions
ALPHA, BETA, GAMMA = 1.5, 0.0, 2.0  # DCFR discounting


# ====================================================================== deals
def generate(seed, n_flops, turns, per_turn):
    """Features for n_flops * turns * per_turn deals.

    Returns pre (n,2) class ids, flop/turn (n,2,2) and river (n,2) uint16
    features, and result (n,) = sign of seat 0's showdown margin."""
    rng = np.random.default_rng(seed)
    pre, flop_f, turn_f, river_f, result = [], [], [], [], []
    rows = np.arange(per_turn)
    for _ in range(n_flops):
        flop = rng.choice(52, 3, replace=False)
        table = A.FlopTable(flop)
        rest = np.setdiff1d(np.arange(52), flop)
        for turn in rng.choice(rest, turns, replace=False):
            cards = np.setdiff1d(rest, [turn])                       # 48 unseen cards
            board4 = np.append(np.sort(flop), turn)
            scores = A.rank_boards(np.hstack((np.tile(board4, (cards.size, 1)), cards[:, None])))
            picks = np.argsort(rng.random((per_turn, cards.size)), axis=1)[:, :7]
            hole = (cards[picks[:, 0:3]], cards[picks[:, 3:6]])
            river = picks[:, 6]                                      # row of `scores`
            keep, disc = zip(*(table.keep_batch(h) for h in hole))
            for i in (0, 1):
                j = 1 - i
                w = (table.valid & table.RATIONAL[disc[j]] & ~A.HAS[disc[j]] & ~A.HAS[disc[i]]
                     & ~A.HAS[A.PA[keep[i]]] & ~A.HAS[A.PB[keep[i]]] & ~A.HAS[turn])
                me = scores[:, keep[i]].T                            # (n, 48)
                ok = w[:, None, :] & (scores >= 0)[None]
                win = ((me[:, :, None] > scores[None]) & ok).sum(-1) \
                    + 0.5 * ((me[:, :, None] == scores[None]) & ok).sum(-1)
                hs = win / np.maximum(ok.sum(-1), 1)                 # (n, 48)
                known = np.column_stack((hole[i], disc[j]))             # cards this player has seen
                live = ~(cards[None, :, None] == known[:, None, :]).any(-1)
                cnt = live.sum(1)
                mean = (hs * live).sum(1) / cnt
                std = np.sqrt(np.maximum((hs * hs * live).sum(1) / cnt - mean ** 2, 0.0))
                if i == 0:
                    feats = [[], [], [], []]
                feats[0].append(A.preflop_class_batch(hole[i]))
                feats[1].append(np.stack((table.S[keep[i]], table.V[keep[i]]), 1))
                feats[2].append(np.stack((mean, std), 1))
                feats[3].append(hs[rows, river])
            pre.append(np.stack(feats[0], 1))
            flop_f.append(np.stack(feats[1], 1))
            turn_f.append(np.stack(feats[2], 1))
            river_f.append(np.stack(feats[3], 1))
            v0, v1 = scores[river, keep[0]], scores[river, keep[1]]
            result.append(np.sign(v0 - v1))
    q = lambda xs: np.round(np.clip(np.concatenate(xs), 0, 1) * SCALE).astype(np.uint16)  # noqa: E731
    return (np.concatenate(pre).astype(np.uint16), q(flop_f), q(turn_f), q(river_f),
            np.concatenate(result).astype(np.int8))


def _generate_job(args):
    return generate(*args)


def cmd_deals(a):
    jobs = [(a.seed * 100003 + k, a.flops_per_job, a.turns, a.per_turn)
            for k in range(max(1, a.flops // a.flops_per_job))]
    start, parts = time.time(), []
    total = len(jobs) * a.flops_per_job * a.turns * a.per_turn
    print(f"{len(jobs)} jobs, {total} deals, {a.workers} workers", flush=True)
    if a.workers > 1:
        with mp.get_context(_start_method()).Pool(a.workers) as pool:
            for k, part in enumerate(pool.imap_unordered(_generate_job, jobs)):
                parts.append(part)
                _deal_progress(k + 1, len(jobs), start)
    else:
        for k, job in enumerate(jobs):
            parts.append(_generate_job(job))
            _deal_progress(k + 1, len(jobs), start)
    pre, flop_f, turn_f, river_f, result = (np.concatenate(x) for x in zip(*parts))
    np.savez(a.out, pre=pre, flop=flop_f, turn=turn_f, river=river_f, result=result)
    print(f"wrote {a.out}: {len(result)} deals in {time.time() - start:.0f} s", flush=True)


def _deal_progress(done, total, start):
    if done == total or done % max(1, total // 50) == 0:
        el = time.time() - start
        print(f"  deals: {done}/{total} jobs, {el:.0f} s, eta {el / done * (total - done):.0f} s",
              flush=True)


# ====================================================================== buckets
def quantile_edges(x, bins):
    return np.quantile(x, np.arange(1, bins) / bins) if len(x) else np.zeros(bins - 1)


def grid_edges(x, y, grid):
    """Outer quantile edges on x, and per outer bin quantile edges on y."""
    ex = quantile_edges(x, grid[0])
    outer = np.searchsorted(ex, x, "right")
    ey = np.stack([quantile_edges(y[outer == i], grid[1]) for i in range(grid[0])])
    return ex, ey


def grid_bucket(x, y, ex, ey):
    i = np.searchsorted(ex, x, "right")
    j = np.zeros_like(i)
    for k in range(len(ey)):
        sel = i == k
        j[sel] = np.searchsorted(ey[k], y[sel], "right")
    return i * (ey.shape[1] + 1) + j


def make_buckets(pool):
    """Bucket edges from the pool and the (n, 8) bucket ids: column 2*street + seat."""
    f = pool["flop"] / SCALE
    t = pool["turn"] / SCALE
    r = pool["river"] / SCALE
    edges = {}
    edges["flop_x"], edges["flop_y"] = grid_edges(f[..., 0].ravel(), f[..., 1].ravel(), A.FLOP_GRID)
    edges["turn_x"], edges["turn_y"] = grid_edges(t[..., 0].ravel(), t[..., 1].ravel(), A.TURN_GRID)
    edges["river"] = quantile_edges(r.ravel(), A.RIVER_BINS)
    n = len(pool["result"])
    ids = np.zeros((n, 8), dtype=np.int16)
    for seat in (0, 1):
        ids[:, seat] = pool["pre"][:, seat]
        ids[:, 2 + seat] = grid_bucket(f[:, seat, 0], f[:, seat, 1], edges["flop_x"], edges["flop_y"])
        ids[:, 4 + seat] = grid_bucket(t[:, seat, 0], t[:, seat, 1], edges["turn_x"], edges["turn_y"])
        ids[:, 6 + seat] = np.searchsorted(edges["river"], r[:, seat], "right")
    win = (pool["result"].astype(np.float64) + 1) / 2             # seat 0's share of the pot
    tot = (np.bincount(pool["pre"][:, 0], weights=win, minlength=A.N_PREFLOP)
           + np.bincount(pool["pre"][:, 1], weights=1 - win, minlength=A.N_PREFLOP))
    cnt = np.bincount(pool["pre"].ravel(), minlength=A.N_PREFLOP)
    pre_eq = np.where(cnt > 0, tot / np.maximum(cnt, 1), 0.5)   # showdown equity per class
    edges["pre_eq"] = pre_eq
    return edges, ids


# ====================================================================== CFR
class Game:
    """The abstract betting DAG with each decision node's slice of the flat tables."""

    def __init__(self):
        self.nodes, self.root = A.build_tree()
        self.offsets, self.size = A.decision_layout(self.nodes, A.N_BUCKETS)
        # topological order: streets in order, shorter street sequences first
        acts = [n for n in self.nodes if n.kind == "act"]
        self.order = [n.id for n in sorted(acts, key=lambda n: (n.street, len(n.seq)))]
        self.n_infosets = sum(A.N_BUCKETS[n.street] for n in acts)

    def block(self, table, node):
        nb, na = A.N_BUCKETS[node.street], len(node.actions)
        o = self.offsets[node.id]
        return table[o:o + nb * na].reshape(nb, na)


def regret_match(block):
    pos = np.maximum(block, 0.0)
    total = pos.sum(axis=1, keepdims=True)
    return np.where(total > 0, pos / np.where(total > 0, total, 1.0), 1.0 / block.shape[1])


def cfr_pass(game, R, ids, result, dR, dS):
    """One chance-sampled CFR pass over all deals in the batch; adds into dR, dS."""
    nodes, n = game.nodes, len(result)
    reach = {game.root: [np.ones(n), np.ones(n)]}
    sigma = {}
    for nid in game.order:                                   # forward: reach probabilities
        node = nodes[nid]
        if nid not in reach:
            continue
        p, r = node.player, reach[nid]
        strat = regret_match(game.block(R, node))[ids[:, 2 * node.street + p]]
        sigma[nid] = strat
        for a, child in enumerate(node.children):
            if nodes[child].kind != "act":
                continue
            add = [r[0], r[1]]
            add[p] = r[p] * strat[:, a]
            if child in reach:
                reach[child][0] = reach[child][0] + add[0]
                reach[child][1] = reach[child][1] + add[1]
            else:
                reach[child] = add
    value = {}
    for nid in reversed(game.order):                         # backward: values and regrets
        if nid not in sigma:
            continue
        node = nodes[nid]
        p, strat = node.player, sigma.pop(nid)
        vals = np.empty_like(strat)
        for a, child in enumerate(node.children):
            ch = nodes[child]
            vals[:, a] = (A.fold_payoff(ch) if ch.kind == "fold"
                          else result * ch.commit[0] if ch.kind == "show" else value[child])
        v = (strat * vals).sum(axis=1)
        value[nid] = v
        regret = vals - v[:, None]
        if p == 1:
            regret = -regret
        r = reach.pop(nid)
        bk = ids[:, 2 * node.street + p]
        nb, na = A.N_BUCKETS[node.street], strat.shape[1]
        flat = (bk[:, None] * na + np.arange(na)).ravel()
        o = game.offsets[nid]
        dR[o:o + nb * na] += np.bincount(flat, (regret * r[1 - p][:, None]).ravel(), nb * na)
        dS[o:o + nb * na] += np.bincount(flat, (strat * r[p][:, None]).ravel(), nb * na)
    return value[game.root]


def discount(R, S, t):
    """DCFR weights applied after iteration t."""
    pos = t ** ALPHA / (t ** ALPHA + 1)
    neg = t ** BETA / (t ** BETA + 1)
    R *= np.where(R > 0, pos, neg)
    S *= (t / (t + 1)) ** GAMMA
    if t % 100 == 0:          # regrets of unvisited rows halve forever; keep them out of slow subnormals
        R[np.abs(R) < 1e-150] = 0.0


# ---------------------------------------------------------------------- workers
def _start_method():
    return "fork" if "fork" in mp.get_all_start_methods() else "spawn"


def _worker(rank, ids_path, res_path, shm_names, size, batch, seed, conn):
    ids = np.load(ids_path, mmap_mode="r")
    res = np.load(res_path, mmap_mode="r")
    shms = [shared_memory.SharedMemory(name=nm) for nm in shm_names]
    if _start_method() != "spawn":   # the parent owns these blocks; keep the tracker from unlinking them
        from multiprocessing import resource_tracker
        for shm in shms:
            try:
                resource_tracker.unregister(shm._name, "shared_memory")
            except Exception:
                pass
    R, dR, dS = (np.ndarray((size,), dtype=np.float64, buffer=s.buf) for s in shms)
    game = Game()
    rng = np.random.default_rng(seed + 7919 * rank)
    while True:
        msg = conn.recv()
        if msg is None:
            break
        dR[:] = 0.0
        dS[:] = 0.0
        pick = np.sort(rng.integers(0, len(res), batch))
        cfr_pass(game, R, np.asarray(ids[pick], dtype=np.int64), np.asarray(res[pick], dtype=np.float64),
                 dR, dS)
        conn.send(1)
    del R, dR, dS
    for s in shms:
        s.close()


class Workers:
    """N processes sharing R through shared memory, each writing its own dR, dS."""

    def __init__(self, n, ids_path, res_path, size, batch, seed):
        self.shms = []
        self.R = self._shared(size)
        self.dR = [self._shared(size) for _ in range(n)]
        self.dS = [self._shared(size) for _ in range(n)]
        ctx = mp.get_context(_start_method())
        self.conns, self.procs = [], []
        for k in range(n):
            names = [self.shms[0].name, self.shms[1 + k].name, self.shms[1 + n + k].name]
            parent, child = ctx.Pipe()
            proc = ctx.Process(target=_worker, args=(k, ids_path, res_path, names, size, batch, seed, child),
                               daemon=True)
            proc.start()
            self.conns.append(parent)
            self.procs.append(proc)

    def _shared(self, size):
        shm = shared_memory.SharedMemory(create=True, size=size * 8)
        self.shms.append(shm)
        arr = np.ndarray((size,), dtype=np.float64, buffer=shm.buf)
        arr[:] = 0.0
        return arr

    def step(self):
        for c in self.conns:
            c.send(1)
        for c in self.conns:
            c.recv()
        return sum(self.dR[1:], self.dR[0].copy()), sum(self.dS[1:], self.dS[0].copy())

    def close(self):
        for c in self.conns:
            c.send(None)
        for p in self.procs:
            p.join(timeout=10)
        del self.R, self.dR, self.dS
        for s in self.shms:
            s.close()
            s.unlink()


def save_checkpoint(path, R, S, t, edges, deals):
    tmp = path + ".tmp.npz"
    np.savez(tmp, R=R, S=S, t=t, deals=deals, size=R.size, **edges)
    os.replace(tmp, path)


def cmd_solve(a):
    game = Game()
    print(f"tree: {len(game.nodes)} public states, {len(game.order)} decision nodes, "
          f"{game.n_infosets} infosets, {game.size} table entries", flush=True)
    work = os.path.splitext(a.checkpoint)[0]
    ids_path, res_path = work + "_ids.npy", work + "_res.npy"
    if os.path.exists(a.checkpoint) and not a.restart:
        ck = np.load(a.checkpoint)
        assert int(ck["size"]) == game.size, "checkpoint was made with a different abstraction"
        R, S, t, deals = ck["R"].copy(), ck["S"].copy(), int(ck["t"]), int(ck["deals"])
        edges = {k: ck[k] for k in ("flop_x", "flop_y", "turn_x", "turn_y", "river", "pre_eq")}
        print(f"resumed at iteration {t}", flush=True)
        if not (os.path.exists(ids_path) and os.path.exists(res_path)):
            _, ids = make_buckets(np.load(a.pool))
            np.save(ids_path, ids)
            np.save(res_path, np.load(a.pool)["result"])
    else:
        pool = np.load(a.pool)
        edges, ids = make_buckets(pool)
        np.save(ids_path, ids)
        np.save(res_path, pool["result"])
        R, S, t, deals = np.zeros(game.size), np.zeros(game.size), 0, 0
        print(f"bucketed {len(ids)} deals", flush=True)

    workers = Workers(a.workers, ids_path, res_path, game.size, a.batch, a.seed + t) if a.workers > 1 else None
    if workers is None:
        ids_all, res_all = np.load(ids_path).astype(np.int64), np.load(res_path).astype(np.float64)
        rng = np.random.default_rng(a.seed + t)
        dR, dS = np.zeros(game.size), np.zeros(game.size)
    start = last_print = last_save = time.time()
    t0, deals0, prev_avg = t, deals, None
    per_iter = a.batch * max(1, a.workers)
    stop_at = start + a.hours * 3600 if a.hours else None
    try:
        while (a.iters is None or t - t0 < a.iters) and (stop_at is None or time.time() < stop_at):
            if workers is not None:
                workers.R[:] = R
                d_r, d_s = workers.step()
            else:
                dR[:] = 0.0
                dS[:] = 0.0
                pick = rng.integers(0, len(res_all), a.batch)
                cfr_pass(game, R, ids_all[pick], res_all[pick], dR, dS)
                d_r, d_s = dR, dS
            t += 1
            deals += per_iter
            R += d_r / per_iter
            S += d_s / per_iter
            discount(R, S, t)
            now = time.time()
            if now - last_print >= a.print_every:
                el = now - start
                print(f"iter {t}  {(t - t0) / el:.2f} it/s  {(deals - deals0) / el:.0f} deals/s  "
                      f"mean max-regret {mean_max_regret(game, R):.4f}", flush=True)
                last_print = now
            if now - last_save >= a.every:
                save_checkpoint(a.checkpoint, R, S, t, edges, deals)
                avg = average_strategy(game, S, R)
                if prev_avg is not None:
                    print(f"checkpoint {t}: mean |change| of average strategy "
                          f"{np.abs(avg - prev_avg).mean():.5f}", flush=True)
                prev_avg = avg
                last_save = now
    finally:
        if workers is not None:
            workers.close()
    save_checkpoint(a.checkpoint, R, S, t, edges, deals)
    print(f"done: {t} iterations, {deals} deals, {time.time() - start:.0f} s", flush=True)


def mean_max_regret(game, R):
    """Mean over decision nodes of the largest positive regret, an inexpensive progress signal."""
    out = [np.maximum(game.block(R, game.nodes[n]), 0).max(axis=1).mean() for n in game.order]
    return float(np.mean(out))


def average_strategy(game, S, R):
    """Normalised average strategy; rows never reached fall back to regret matching."""
    out = np.zeros(game.size)
    for nid in game.order:
        node = game.nodes[nid]
        s = game.block(S, node)
        cur = regret_match(game.block(R, node))
        tot = s.sum(axis=1, keepdims=True)
        game.block(out, node)[:] = np.where(tot > 0, s / np.where(tot > 0, tot, 1), cur)
    return out


# ====================================================================== export
def cmd_export(a):
    game = Game()
    ck = np.load(a.checkpoint)
    assert int(ck["size"]) == game.size, "checkpoint was made with a different abstraction"
    avg = average_strategy(game, ck["S"], ck["R"])
    table = np.round(avg * 255).astype(np.uint8)
    buf = io.BytesIO()
    np.savez(buf, table=table, size=np.int64(game.size),
             **{k: ck[k].astype(np.float32) for k in ("flop_x", "flop_y", "turn_x", "turn_y", "river", "pre_eq")})
    blob = base64.b85encode(zlib.compress(buf.getvalue(), 9)).decode("ascii")
    with open(a.out, "w", encoding="ascii", newline="\n") as fh:
        fh.write('"""Trained strategy for bot.py, written by solver/train.py export. Do not edit."""\n')
        fh.write(f"ITERATIONS = {int(ck['t'])}\n")
        fh.write(f"DEALS = {int(ck['deals'])}\n")
        fh.write("BLOB = (\n")
        for i in range(0, len(blob), 100):
            fh.write(f"    '{blob[i:i + 100]}'\n")
        fh.write(")\n")
    print(f"wrote {a.out}: {os.path.getsize(a.out) / 1e6:.2f} MB, {game.size} entries, "
          f"{int(ck['t'])} iterations", flush=True)


# ====================================================================== cli
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deals", help="build the deal pool")
    d.add_argument("--flops", type=int, default=150000, help="flops to sample (deals = flops*turns*per-turn)")
    d.add_argument("--turns", type=int, default=4, help="turn cards per flop")
    d.add_argument("--per-turn", type=int, default=32, help="deals per flop+turn")
    d.add_argument("--flops-per-job", type=int, default=200)
    d.add_argument("--workers", type=int, default=1)
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--out", default="pool.npz")
    s = sub.add_parser("solve", help="run CFR")
    s.add_argument("--pool", default="pool.npz")
    s.add_argument("--checkpoint", default="ckpt.npz", help="checkpoint path; resumed if present")
    s.add_argument("--restart", action="store_true", help="ignore an existing checkpoint")
    s.add_argument("--workers", type=int, default=1)
    s.add_argument("--batch", type=int, default=1024, help="deals per worker per iteration")
    s.add_argument("--iters", type=int, default=None, help="stop after this many iterations")
    s.add_argument("--hours", type=float, default=None, help="stop after this many hours")
    s.add_argument("--every", type=float, default=600, help="seconds between checkpoints")
    s.add_argument("--print-every", type=float, default=30)
    s.add_argument("--seed", type=int, default=1)
    e = sub.add_parser("export", help="write bot/strategy.py")
    e.add_argument("--checkpoint", default="ckpt.npz")
    e.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot", "strategy.py"))
    a = p.parse_args()
    {"deals": cmd_deals, "solve": cmd_solve, "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    main()
