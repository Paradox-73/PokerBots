"""How opponents answer our first bet on a postflop street, by bet size (fraction of the pot at the street's start).
Reads engine match.log files where bot A is ours. usage: sizeresp.py LOGDIR_GLOB..."""
import collections, glob, re, sys
BANDS = [(0.25, 0.45, "0.33"), (0.55, 0.80, "0.66"), (0.88, 1.15, "1.00"), (1.30, 1.75, "1.50")]
cnt = collections.defaultdict(collections.Counter)
for pat in sys.argv[1:]:
    for fn in glob.glob(pat):
        for line in open(fn):
            if not re.match(r"L[0-9]+ +#", line):
                continue
            parts = line.split(" | ")
            btn = re.search(r"button ([AB])", parts[0]).group(1)
            acts = next((p for p in parts if p.startswith("preflop:")), None)
            if acts is None:
                continue
            total = {"A": 0, "B": 0}
            street, lvl = None, None
            for tok in acts.split():
                if tok.endswith(":"):
                    if street is not None:
                        m = max(lvl.values()); total["A"] += m; total["B"] += m
                    street = tok[:-1]
                    lvl = {"A": 0, "B": 0}
                    if street == "preflop":
                        lvl = {btn: 1, ("B" if btn == "A" else "A"): 2}
                    pend = None
                    continue
                who, kind, amt = tok[0], tok[1], tok[2:]
                if street != "preflop" and pend is not None and who == "B":
                    cnt[(street, pend)][kind] += 1
                    pend = None
                if kind == "r":
                    x = int(amt)
                    if street != "preflop" and who == "A" and max(lvl.values()) == 0:
                        r = x / max(1, total["A"] + total["B"])
                        pend = next((n for lo, hi, n in BANDS if lo <= r <= hi), None)
                    lvl[who] = x
                elif kind == "c":
                    lvl[who] = int(amt)
for street in ("flop", "turn", "river"):
    for _, _, n in BANDS:
        c = cnt[(street, n)]
        t = sum(c.values())
        if t:
            print("%-5s bet %s  n=%4d  fold %.2f  call %.2f  raise %.2f" % (street, n, t, c["f"] / t, c["c"] / t, c["r"] / t))
