"""The bot's preflop table (PRE_DATA) rebuilt without the card-overlap shortcut of the original table builder:
each triple is scored only against opponent triples that share no card with it.

Same method otherwise: pass 1 ranks the 3-card classes by equity against a random triple, both
sides keeping their strongest pair on the flop; pass 2 measures each class against each of the
PRE_BUCKETS strength buckets. Overlapping triples are removed by inclusion-exclusion per runout:
all - (triples sharing card a, b or c) + (sharing two of them) - (the triple itself).

usage: gen_pre2.py BOT 1 FLOPS SEED OUT.npz                 pass-1 part
       gen_pre2.py BOT 2 FLOPS SEED OUT.npz PASS1.npz       pass-2 part (buckets from merged pass 1)
       gen_pre2.py BOT merge OUT.npz PART.npz...            sum parts
       gen_pre2.py BOT embed PASS1.npz PASS2.npz OUT_BOT    write the new table into a copy of BOT
       gen_pre2.py BOT test                                 self-check of the overlap removal"""
import base64
import importlib.util
import itertools
import sys
import zlib

import numpy as np


def load_bot(path):
    spec = importlib.util.spec_from_file_location("botmod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = load_bot(sys.argv[1])
mode = sys.argv[2]
N = B.PRE_BUCKETS
RUNS = 8
NT, TR = B.NT, B.TRIPS
CARD_T = [np.nonzero((TR == c).any(1))[0] for c in range(52)]
TID = np.full((52, 52, 52), -1)
for i, t in enumerate(TR):
    for a, b, c in itertools.permutations(t):
        TID[a, b, c] = i
PAIR_T = np.array([[TID[c, d, x] for x in range(52) if x not in (c, d)]
                   for c, d in itertools.combinations(range(52), 2)])  # (1326, 50)


def block(v, b, nb):
    """Per-bucket count of the set's members each member beats (ties half, itself included), and set sizes."""
    order = np.argsort(v, kind="stable")
    s = v[order]
    lo, hi = np.searchsorted(s, v, "left"), np.searchsorted(s, v, "right")
    hot = np.zeros((len(s) + 1, nb))
    hot[np.arange(1, len(s) + 1), b[order]] = 1
    cum = np.cumsum(hot, axis=0)
    return (cum[lo] + cum[hi]) * .5, np.broadcast_to(cum[-1], (len(v), nb))


def disjoint(ok, vals, bucket, nb):
    """win, cnt (NT x nb): for every triple allowed on this board, the bucket counts of card-disjoint
    allowed triples it beats (ties half) and of all card-disjoint allowed triples."""
    win, cnt = np.zeros((NT, nb)), np.zeros((NT, nb))
    idx = np.nonzero(ok)[0]
    w, c = block(vals[idx], bucket[idx], nb)
    win[idx] += w
    cnt[idx] += c
    for card in range(52):
        t = CARD_T[card][ok[CARD_T[card]]]
        if len(t):
            w, c = block(vals[t], bucket[t], nb)
            win[t] -= w
            cnt[t] -= c
    valid = ok[PAIR_T]
    V = np.where(valid, vals[PAIR_T], np.nan)
    score = (V[:, None, :] < V[:, :, None]) + .5 * (V[:, None, :] == V[:, :, None])  # [p, hero x, other y]
    hot = np.zeros(PAIR_T.shape + (nb,))
    hot[valid, bucket[PAIR_T][valid]] = 1
    W = np.einsum("pxy,pyb->pxb", score, hot)
    C = np.broadcast_to(hot.sum(1)[:, None, :], W.shape)
    np.add.at(win, PAIR_T[valid], W[valid])
    np.add.at(cnt, PAIR_T[valid], C[valid])
    win[idx, bucket[idx]] -= .5
    cnt[idx, bucket[idx]] -= 1
    return win, cnt, idx


def deal(rng):
    """One flop: for each runout, the board's allowed-triple mask and each triple's kept-hand value."""
    cards = rng.permutation(52)
    flop = cards[:3]
    two = np.array([rng.choice(cards[3:], 2, replace=False) for _ in range(40)])
    sample = np.column_stack([np.tile(flop, (40, 1)), two])
    S = B.percentile_rows(B.eval_boards(sample), B.board_ok(sample))
    keep = B.PT[np.arange(NT), np.argmax(S[B.PT], axis=1)]
    fm = sum(1 << int(c) for c in flop)
    for _ in range(RUNS):
        tr = rng.choice(cards[3:], 2, replace=False)
        v = B.eval_boards(np.concatenate([flop, tr])[None, :])[0]
        bm = fm | (1 << int(tr[0])) | (1 << int(tr[1]))
        yield (B.TMASK & bm) == 0, v[keep].astype(np.float64)


def percentiles(w1, c1):
    eq = w1 / c1
    sizes = np.bincount(B.CLS, minlength=B.NCLS).astype(float)
    order = np.argsort(eq)
    cum = np.cumsum(sizes[order])
    pct = np.empty(B.NCLS)
    pct[order] = (cum - sizes[order] / 2) / cum[-1]
    return eq, pct


if mode in ("1", "2"):
    flops, rng, out = int(sys.argv[3]), np.random.default_rng(int(sys.argv[4])), sys.argv[5]
    if mode == "1":
        st = {"w1": np.zeros(B.NCLS), "c1": np.zeros(B.NCLS)}
        zero = np.zeros(NT, dtype=int)
        for _ in range(flops):
            for ok, vals in deal(rng):
                win, cnt, idx = disjoint(ok, vals, zero, 1)
                st["w1"] += np.bincount(B.CLS[idx], win[idx, 0] / cnt[idx, 0], B.NCLS)
                st["c1"] += np.bincount(B.CLS[idx], minlength=B.NCLS)
    else:
        p1 = np.load(sys.argv[6])
        _, pct = percentiles(p1["w1"], p1["c1"])
        bucket = np.minimum((pct[B.CLS] * N).astype(int), N - 1)
        st = {"w2": np.zeros((B.NCLS, N)), "c2": np.zeros((B.NCLS, N))}
        for _ in range(flops):
            for ok, vals in deal(rng):
                win, cnt, idx = disjoint(ok, vals, bucket, N)
                np.add.at(st["w2"], B.CLS[idx], win[idx])
                np.add.at(st["c2"], B.CLS[idx], cnt[idx])
    np.savez(out, **st)
    print(out, "written")
elif mode == "merge":
    parts = [np.load(p) for p in sys.argv[4:]]
    np.savez(sys.argv[3], **{k: sum(p[k] for p in parts) for k in parts[0].files})
    print(sys.argv[3], "merged from", len(parts))
elif mode == "embed":
    p1, p2 = np.load(sys.argv[3]), np.load(sys.argv[4])
    eq, pct = percentiles(p1["w1"], p1["c1"])
    table = p2["w2"] / np.maximum(p2["c2"], 1)
    raw = np.concatenate([pct, table.ravel()])
    blob = base64.b64encode(zlib.compress(np.round(np.clip(raw, 0, 1) * 65535).astype(np.uint16).tobytes(), 9)).decode()
    src = open(sys.argv[1], newline="").read()
    start = src.index('PRE_DATA = "') + len('PRE_DATA = "')
    end = src.index('"', start)
    new = src[:start] + blob + src[end:]
    compile(new, sys.argv[5], "exec")
    open(sys.argv[5], "w", newline="").write(new)
    print("embedded", len(blob), "chars; flop samples per class min", p1["c1"].min(), "per class-bucket min", p2["c2"].min())
elif mode == "test":
    # brute force on a few random boards: for sampled heroes, count disjoint triples directly
    rng = np.random.default_rng(1)
    for _ in range(2):
        ok = np.zeros(NT, bool)
        bm = sum(1 << int(c) for c in rng.choice(52, 5, replace=False))
        ok = (B.TMASK & bm) == 0
        vals = rng.integers(0, 40, NT).astype(float)  # many ties on purpose
        bucket = rng.integers(0, 4, NT)
        win, cnt, idx = disjoint(ok, vals, bucket, 4)
        for h in rng.choice(idx, 30, replace=False):
            o = idx[(B.TMASK[idx] & B.TMASK[h]) == 0]
            bw = np.bincount(bucket[o], (vals[o] < vals[h]) + .5 * (vals[o] == vals[h]), 4)
            bc = np.bincount(bucket[o], minlength=4)
            assert np.allclose(win[h], bw) and np.allclose(cnt[h], bc), (h, win[h], bw, cnt[h], bc)
    print("overlap removal matches brute force on 60 heroes")
