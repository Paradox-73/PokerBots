"""Where our choices differ from the opponent's in identical spots, and what each difference costs.

Leg 2 replays every deal with cards and seats swapped, so on deal n the player holding cards X sits
in the same seat in both legs: our bot in leg 1, the opponent in leg 2. Written in those roles, the
two action lines agree until the first decision where we and the opponent chose differently with
the same cards and the same history. Every chip of the deal's duplicate total (our net in leg 1
plus our net in leg 2) comes from that point on, so totals grouped by that first difference show
which of our choices win or lose against this opponent.
usage: dup.py MATCH_LOG...  (A = our bot)"""
import collections
import os
import re
import sys

LINE = re.compile(r"^L(\d) #(\d+)\s+button (\w) \| (\w): ([^|]*?)  (\w): ([^|]*?) \| board ([^|]*?) "
                  r"(?:\| discards (\w):(\S+) (\w):(\S+) )?\| (.*) \| (fold|showdown)(?: \(.*\))? (\w) ([+-]\d+), (\w) ([+-]\d+)$")
STACK = 200


def parse(path):
    deals = collections.defaultdict(dict)
    for raw in open(path):
        m = LINE.match(raw.rstrip("\n"))
        if not m:
            continue
        g = m.groups()
        leg, did, button = int(g[0]), int(g[1]), g[2]
        cards = {g[3]: g[4].split(), g[5]: g[6].split()}
        disc = {g[8]: g[9], g[10]: g[11]} if g[8] else {}
        net = {g[14]: int(g[15]), g[16]: int(g[17])}
        deals[did][leg] = dict(button=button, cards=cards, disc=disc, acts=g[12].split(), net=net)
    return deals


def roles(h, leg):
    """Map engine letters to roles: X = whoever holds A's leg-1 cards."""
    return {"A": "X", "B": "Y"} if leg == 1 else {"B": "X", "A": "Y"}


def classify(acts, role, button_role):
    """Role-token list plus, per token, (street, actor, kind, facing, size)."""
    out = []
    st = "preflop"
    other = {"X": "Y", "Y": "X"}
    done = {"X": 0, "Y": 0}
    bet = {button_role: 1, other[button_role]: 2}
    for tok in acts:
        if tok.endswith(":"):
            for k in done:
                done[k] += bet[k]
            bet = {"X": 0, "Y": 0}
            st = tok[:-1]
            out.append((tok, None))
            continue
        who, kind, amt = role[tok[0]], tok[1], tok[2:]
        opp = other[who]
        facing = bet[opp] > bet[who]
        pot = done["X"] + done["Y"] + bet["X"] + bet["Y"]
        size = ""
        if kind == "r":
            to = int(amt)
            if done[who] + to >= STACK:
                size = "allin"
            else:
                frac = (to - bet[opp]) / max(1, pot + bet[opp] - bet[who])
                size = "small" if frac < 0.5 else "mid" if frac <= 1.05 else "big"
            bet[who] = to
        elif kind == "c":
            bet[who] = bet[opp]
        out.append((who + kind + amt, (st, who, kind, "facing" if facing else "open", size)))
    return out


def label(info):
    kind, size = info[2], info[4]
    return {"f": "fold", "x": "check", "c": "call"}.get(kind, "raise-" + size)


# KIND_ONLY=1: a raise of another size still counts as the same choice, so the lines are followed
# past size differences (later spots then have similar, not identical, pots)
KIND_ONLY = os.environ.get("KIND_ONLY") == "1"
groups = collections.defaultdict(lambda: [0, 0, 0])
same = 0
total = 0
for path in sys.argv[1:]:
    for did, legs in parse(path).items():
        if 1 not in legs or 2 not in legs:
            continue
        l1, l2 = legs[1], legs[2]
        assert l1["cards"]["A"] == l2["cards"]["B"], (path, did)
        r1, r2 = roles(l1, 1), roles(l2, 2)
        assert r1[l1["button"]] == r2[l2["button"]], (path, did)  # same seat for the same cards
        dup = l1["net"]["A"] + l2["net"]["A"]
        total += dup
        s1 = classify(l1["acts"], r1, r1[l1["button"]])
        s2 = classify(l2["acts"], r2, r2[l2["button"]])
        key = None
        for (t1, i1), (t2, i2) in zip(s1, s2):
            if (t1[:2] != t2[:2]) if KIND_ONLY else (t1 != t2):
                # i1 is our choice if X acted (leg 1: we hold X), else the opponent's
                ours, theirs = (i1, i2) if i1[1] == "X" else (i2, i1)
                key = (i1[0], ours[3], "%s / opp %s" % (label(ours), label(theirs)))
                break
        if key is None:
            if len(s1) != len(s2):
                key = ("?", "?", "line length")
            else:
                d1 = {r1[k]: v for k, v in l1["disc"].items()}
                d2 = {r2[k]: v for k, v in l2["disc"].items()}
                if KIND_ONLY and s1 != s2:
                    key = ("sizes", "-", "only raise sizes differ")
                elif d1 != d2:
                    key = ("discard", "-", "different discard")
                else:
                    same += 1
                    assert dup == 0, (path, did, dup)
                    continue
        g = groups[key]
        g[0] += 1
        g[1] += dup
        g[2] += dup * dup

print("deals with identical lines: %d (duplicate total 0 by construction); all deals total %+d" % (same, total))
print("%-8s %-7s %-34s %6s %8s %7s %6s" % ("street", "spot", "we / opponent, same cards", "deals", "chips", "per", "z"))
# z = total / its standard error (per-deal spread x sqrt(deals)); |z| under 2 is within luck
for key, (n, s, q) in sorted(groups.items(), key=lambda kv: kv[1][1]):
    se = max(1e-9, (max(0.0, q / n - (s / n) ** 2) * n) ** 0.5)
    if n >= 5 or abs(s) >= 300:
        print("%-8s %-7s %-34s %6d %+8d %+7.1f %+6.1f" % (key[0], key[1], key[2], n, s, s / n, s / se))
