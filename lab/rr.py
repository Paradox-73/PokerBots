"""How each side's deep re-raises are sized and answered. A deep raise is a postflop raise of a raise
(3rd bet or later) or a preflop 4-bet or later, where the solver tree has only all-in.
usage: rr.py MATCH_LOG...  (A = our bot)"""
import collections
import sys

sys.argv, logs = sys.argv[:1], sys.argv[1:]
import dup  # noqa: E402  (dup.py's parser and size classes; it prints an empty table on import)

tally = collections.defaultdict(collections.Counter)
for path in logs:
    for did, legs in dup.parse(path).items():
        for leg, d in legs.items():
            role = {"A": "X", "B": "Y"}  # dup.classify works in roles X/Y; here X = our bot
            toks = dup.classify(d["acts"], role, role[d["button"]])
            level = 0
            for k, (tok, info) in enumerate(toks):
                if info is None:
                    level = 0
                    continue
                st, who, kind = info[0], info[1], info[2]
                if kind != "r":
                    continue
                level += 1
                # preflop the big blind is not in the action list, so the 3rd raise token is the 4-bet
                if level < 3 or info[4] == "allin":
                    continue
                nxt = next((t for t in toks[k + 1:] if t[1] is not None), None)
                resp = "none" if nxt is None else dup.label(nxt[1])
                tally[("us" if who == "X" else "opp", st, info[4])][resp] += 1
for key in sorted(tally):
    c = tally[key]
    n = sum(c.values())
    print("%s %-7s %-6s n %4d  " % (key + (n,)) + "  ".join("%s %.0f%%" % (r, 100 * v / n) for r, v in c.most_common()))
