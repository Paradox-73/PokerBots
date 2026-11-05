"""Slowplay rate learnt as P(passive | strong) instead of P(strong | passive).
A check or call is read with likelihood eps_pas for hands above the opponent's raise threshold, so
eps_pas must be the share of its strong hands that it played passively. It was learnt at showdown as
the share of its passive actions taken with a strong hand, which is smaller by about
P(strong) / P(passive): against an opponent that checks every strong hand (a trap), a check still
cut strong hands to ~0.12-0.25 weight and a later raise read as a medium hand.
Now every showdown event where the shown hand was above the raise threshold counts, and it counts as
passive if the action was. Same prior (0.12 over 8 pseudo-events), so play before any showdown is unchanged.
usage: fix23.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        self.pas_n, self.pas_off = [0.0] * 4, [0.0] * 4''',
    '''        self.pas_n, self.pas_off = [0.0] * 4, [0.0] * 4  # strong shown hands, and how many acted passively''')
cut('''            h.events.append((st, 0, thr, x))''', '''            h.events.append((st, 0, thr, x, thr_r))''')
cut('''            L = e + (1 - e) * sig(x, p[FOLD]) * (1 - 0.7 * sig(x, thr_r))
            h.events.append((st, 1, thr_r, x))''', '''            L = e + (1 - e) * sig(x, p[FOLD]) * (1 - 0.7 * sig(x, thr_r))
            h.events.append((st, 1, thr_r, x, thr_r))''')
cut('''            L = e + (1 - e) * (1 - sig(x, thr_r))
            h.events.append((st, 1, thr_r, x))''', '''            L = e + (1 - e) * (1 - sig(x, thr_r))
            h.events.append((st, 1, thr_r, x, thr_r))''')
cut('''        for st, kind, thr, x in h.events:
            v = x[tid] if len(x) == NT else x[pair]
            if kind == 0:
                o.agg_n[st] += 1
                o.agg_off[st] += v < thr - 0.1
            else:
                o.pas_n[st] += 1
                o.pas_off[st] += v > thr + 0.1''', '''        for st, kind, thr, x, thr_r in h.events:
            v = x[tid] if len(x) == NT else x[pair]
            if kind == 0:
                o.agg_n[st] += 1
                o.agg_off[st] += v < thr - 0.1
            if v > thr_r + 0.1:
                o.pas_n[st] += 1
                o.pas_off[st] += kind == 1''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
