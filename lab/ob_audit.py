"""Our answers to big bets in engine match logs (we are seat A): for every opponent bet or raise of at least
1.2x the pot before it, what we did and what that hand then gained compared with folding at that moment
(net result + chips we had already put in). Grouped by street, our answer, and bet size.
usage: ob_audit.py MATCH_LOG..."""
import collections
import re
import sys

LINE = re.compile(r"^L\d #\d+\s+button (\w) \|.*?\| (preflop: .*) \| (?:fold|showdown).* A ([+-]\d+)")
agg = collections.defaultdict(lambda: [0, 0.0, 0.0])  # n, sum gain, sum gain^2
for path in sys.argv[1:]:
    for raw in open(path):
        m = LINE.match(raw)
        if not m:
            continue
        button, acts, net = m.group(1), m.group(2).split(), int(m.group(3))
        prev = {"A": 0, "B": 0}  # chips in from earlier streets
        bet = {"A": 0, "B": 0}
        street, pending = None, None
        for t in acts:
            if t.endswith(":"):
                street = t[:-1]
                for k in prev:
                    prev[k] += bet[k]
                bet = {"A": 0, "B": 0} if street != "preflop" else {button: 1, ("B" if button == "A" else "A"): 2}
                pending = None
                continue
            who, kind, amt = t[0], t[1], int(t[2:]) if len(t) > 2 else None
            if who == "A" and pending is not None:
                ratio, before = pending
                ans = {"c": "call", "f": "fold", "r": "raise"}.get(kind, kind)
                size = "1.2-2x" if ratio < 2 else "2-4x" if ratio < 4 else "4x+"
                g = net + before
                for key in ((street, ans, size), (street, ans, "all"), ("all", ans, "all")):
                    a = agg[key]
                    a[0] += 1; a[1] += g; a[2] += g * g
                pending = None
            if kind == "r":
                pot = prev["A"] + prev["B"] + bet["A"] + bet["B"]
                faced = amt - bet["A" if who == "B" else "B"]
                if who == "B" and faced / max(1, pot) >= 1.2:
                    pending = (faced / max(1, pot), prev["A"] + bet["A"])
                bet[who] = amt
            elif kind == "c":
                bet[who] = amt
for key in sorted(agg):
    n, s, s2 = agg[key]
    var = max(0.0, s2 / n - (s / n) ** 2)
    print("%-8s %-6s %-7s n %4d  gain vs folding %+7.1f per spot (se %5.1f)  total %+7.0f" % (key + (n, s / n, (var / n) ** .5, s)))
