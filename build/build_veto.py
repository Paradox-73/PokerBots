"""Merge the solver into the EV bot as one bot.py: the EV bot plays every hand, but drops any
option whose kind (fold, check/call, raise) the solver gives under VETO_P at that spot.
usage: build_veto.py EV_BOT SOLVER_DIR KINDS MIN_STREET OUT [VETO_P, default 0.05] [BLEND, default 0]
  BLEND > 0 also weights the near-best options by (solver frequency of their kind) ** BLEND
  [LOCK_MIN, default off]: off = no lock (two-leg rules); a number keeps the lock, engaged only
  when folding out the leg still leaves that many chips
  [RUNOUT_CAP, default 240]: most board run-outs sampled per street for the hand tables
  KINDS: "r" = only raises can be dropped, "fcr" = any kind; MIN_STREET: 0 preflop, 1 flop"""
import sys

ev_path, sdir, kinds, min_st, out = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
veto_p = float(sys.argv[6]) if len(sys.argv) > 6 else 0.05
blend = float(sys.argv[7]) if len(sys.argv) > 7 else 0.0
lock_min = int(sys.argv[8]) if len(sys.argv) > 8 and sys.argv[8] != "off" else None
runout_cap = int(sys.argv[9]) if len(sys.argv) > 9 else 240
src = open(ev_path, newline="").read()
mods = {name: open("%s/%s.py" % (sdir, f)).read()
        for name, f in (("abstraction", "abstraction"), ("strategy", "strategy"), ("solver_bot", "bot"))}
for s in mods.values():
    assert "'''" not in s and not s.rstrip().endswith("\\")


def to_base64(strategy_src, bot_src):
    """Base85 has '-' and so can spell words like blocked words by chance; base64 cannot. Same bytes."""
    import base64
    g = {}
    exec(strategy_src, g)
    raw = base64.b85decode(g["BLOB"])
    text = base64.b64encode(raw).decode()
    assert base64.b64decode(text) == raw
    head = strategy_src.split("\nBLOB = (\n", 1)[0]
    rows = "".join("    '%s'\n" % text[i:i + 100] for i in range(0, len(text), 100))
    old = 'base64.b85decode("".join(BLOB))'
    assert bot_src.count(old) == 1
    return head + "\nBLOB = (\n" + rows + ")\n", bot_src.replace(old, 'base64.b64decode("".join(BLOB))')


assert mods["strategy"].rstrip().endswith(")") and mods["strategy"].count("\nBLOB = (\n") == 1
mods["strategy"], mods["solver_bot"] = to_base64(mods["strategy"], mods["solver_bot"])


def patch(name, old, new):
    assert mods[name].count(old) == 1, old
    mods[name] = mods[name].replace(old, new)


# Speed, same results (checked by pb/check_fast.py): the rank-count masks per holding are the
# board's masks corrected at the two hole ranks, instead of a (boards, 1326, 13) product.
patch("abstraction", '''    c = cnt[:, None, :] + _PAIR_RANKS                       # (n, 1326, 13) rank counts
    m1, m2, m3, m4 = ((c >= k) @ _POW2 for k in (1, 2, 3, 4))
''', '''    ca = cnt[:, _RA] + _SAME + 1                            # (n, 1326) count of each hole rank
    cb = cnt[:, _RB] + _SAME + 1
    m1, m2, m3, m4 = (((cnt >= k) @ _POW2)[:, None] & _NOT_HOLE | np.where(ca >= k, _RA_BIT, 0)
                      | np.where(cb >= k, _RB_BIT, 0) for k in (1, 2, 3, 4))
''')
patch("abstraction", '''_PAIR_SUIT_BITS = np.array(''', '''_RA, _RB = PA >> 2, PB >> 2
_SAME = (_RA == _RB).astype(np.int64)
_RA_BIT, _RB_BIT = 1 << _RA, 1 << _RB
_NOT_HOLE = ~(_RA_BIT | _RB_BIT)
_PAIR_SUIT_BITS = np.array(''')
# A flop table depends only on the three flop cards, so recent ones are kept for reuse.
patch("solver_bot", '''        if self.hand.flop is None:
            self.hand.flop = A.FlopTable(board[:3])
''', '''        if self.hand.flop is None:
            key = tuple(sorted(board[:3]))
            if key not in FLOP_CACHE:
                if len(FLOP_CACHE) >= 8:
                    FLOP_CACHE.pop(next(iter(FLOP_CACHE)))
                FLOP_CACHE[key] = A.FlopTable(board[:3])
            self.hand.flop = FLOP_CACHE[key]
''')
patch("solver_bot", "\nclass Bot:\n", "\nFLOP_CACHE = {}\n\n\nclass Bot:\n")


def swap(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


swap('''            options = safe
        temp = max(0.25, 0.012 * P)''', '''            options = safe
        view = self.view
        if view is not None and STREET[req["street"]] >= VETO_MIN_STREET:
            # The solver's own choices bound ours: an option it (almost) never takes here
            # is one its balanced opponents punish, so it is dropped while another is left.
            kept = [o for o in options if KIND[o[1]] not in VETO_KINDS or view[KIND[o[1]]] >= VETO_P]
            if kept:
                options = kept
        temp = max(0.25, 0.012 * P)''')
swap('''        self.time_left = 60000
''', '''        self.time_left = 60000
        self.view = None  # solver's [fold, check/call, raise] probabilities at this decision
''')
# Folding this hand also loses the chips already in it, so the lock only holds once the budget
# covers them; locking below that folds the leg out to a draw or a one-chip loss.
if lock_min is None:
    swap('''        if not USE_LOCK or budget < 0 or budget >= 200:''',
         '''        if not USE_LOCK or budget < h.commit[0] or budget >= 200:''')
    # A match is two legs played by separate, freshly started processes (Rulebook 7.1, 5.9), so this
    # process never knows the match score: no folding out a lead and no score-aware all-in calls;
    # every decision maximises chips.
    swap('''USE_LOCK = True
''', '''USE_LOCK = False  # a leg cannot see the other leg's chips, so a lead is never safe to fold out
''')
    swap('''        if "fold" in legal and "call" in legal and tc >= req["my_stack"] and tc >= 20:
            options = self.match_call(options, eq, req)
''', '')
else:
    # Lock kept, but only on a lead that leaves at least LOCK_MIN chips after folding out the leg.
    swap('''        if not USE_LOCK or budget < 0 or budget >= 200:''',
         '''        if not USE_LOCK or budget < max(h.commit[0], %d) or budget >= max(200, %d):''' % (lock_min, 2 * lock_min))
if runout_cap != 240:
    # The run-out count already scales with measured speed and time left; the cap only binds
    # on a fast machine, where a higher one spends spare bank on more accurate hand tables.
    swap("np.clip(0.4 * per_hand / self.ms_runout, 12, 240)",
         "np.clip(0.4 * per_hand / self.ms_runout, 12, %d)" % runout_cap)
if blend:
    swap('''        probs[evs < evs.max() - 3 * temp] = 0.0
''', '''        probs[evs < evs.max() - 3 * temp] = 0.0
        if view is not None and STREET[req["street"]] >= VETO_MIN_STREET:
            # Among the near-best options, lean toward the kinds the solver plays more often.
            probs = probs * np.array([view[KIND[o[1]]] + 0.02 for o in options]) ** VETO_BLEND
''')

head, tail = src.split("\ndef main():\n", 1)
assert tail.rstrip().endswith('if __name__ == "__main__":\n    main()')
parts = [head, '''
# ---------------------------------------------------------------- solver check
# The solver (a precomputed equilibrium strategy, see solver/NOTES.md) follows every hand;
# at each decision it says how often it would fold, check/call or raise.
VETO_P = %r
VETO_KINDS = %r
VETO_MIN_STREET = %d
VETO_BLEND = %r
KIND = {"fold": 0, "check": 1, "call": 1, "raise": 2}
''' % (veto_p, tuple("fcr".index(k) for k in kinds), min_st, blend)]
for name, s in mods.items():
    parts.append("\nSOLVER_%s = r\'\'\'%s\'\'\'\n" % (name.upper(), s))
parts.append('''

def load_solver():
    # A submission is one file, so the solver's three modules travel here as source text
    # and are loaded as modules of their own (their names would clash with the code above).
    import types
    for name, s in (("abstraction", SOLVER_ABSTRACTION), ("strategy", SOLVER_STRATEGY),
                    ("solver_bot", SOLVER_SOLVER_BOT)):
        m = types.ModuleType(name)
        m.__file__ = __file__
        sys.modules[name] = m
        exec(compile(s, name, "exec"), m.__dict__)
    return sys.modules["solver_bot"].Bot()


def ask(solver, method, msg):
    if solver is not None:
        try:
            getattr(solver, method)(msg)
        except Exception as exc:
            print("solver error:", repr(exc), file=sys.stderr)


def solver_view(solver, req):
    """The solver's [fold, check/call, raise] probabilities here, or None off its tree."""
    if solver is None or solver.hand is None:
        return None
    try:
        sb = sys.modules["solver_bot"]
        node = solver.abstract_node(req)
        if node is None:
            return None
        street = sb.STREET[req["street"]]
        bucket, _ = solver.features(street, [sb.A.card_id(c) for c in req["board"]])
        p = solver.strategy.probs(node, bucket)
    except Exception as exc:
        print("solver error:", repr(exc), file=sys.stderr)
        return None
    view = [0.0, 0.0, 0.0]
    for code, q in zip(node.actions, p):
        kind = 2 if code not in ("f", "c") else 0 if code == "f" and req["to_call"] > 0 else 1
        view[kind] += float(q)
    return view


def main():
    bot = Bot()
    try:
        solver = load_solver()
    except Exception as exc:
        print("solver off:", repr(exc), file=sys.stderr)
        solver = None
    bank = bot.time_left
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        t = msg.get("type")
        reply = None
        try:
            if t == "init":
                bot.total = msg.get("total_hands", bot.total)
                bot.time_left = bank = msg.get("time_bank_ms", bot.time_left)
                ask(solver, "on_init", msg)
            elif t == "new_hand":
                bot.h = Hand(msg)
                ask(solver, "on_new_hand", msg)
            elif t == "action_request":
                # The solver spends only time the match is ahead of schedule on, where the
                # schedule uses 80% of the bank evenly over the hands (20% kept for slow spells).
                hands_left = bot.total - (bot.h.id if bot.h is not None else 0)
                pace = bank * (0.2 + 0.8 * hands_left / max(1, bot.total))
                bot.view = solver_view(solver, msg) if msg.get("time_left_ms", 10 ** 9) > pace else None
                reply = bot.on_action(msg)
            elif t == "discard_request":
                reply = bot.on_discard(msg)
            elif t == "discard_result":
                bot.on_discard_result(msg)
                ask(solver, "on_discard_result", msg)
            elif t == "hand_result":
                bot.on_result(msg)
                ask(solver, "on_hand_result", msg)
            elif t == "match_end":
                break
        except Exception as exc:  # a forfeit costs far more than one bad decision
            print("error:", repr(exc), file=sys.stderr)
            if t == "action_request":
                reply = panic_action(msg)
            elif t == "discard_request":
                reply = {"type": "discard", "card": msg["hole_cards"][0]}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
''')
open(out, "w", newline="").write("".join(parts))
compile(open(out).read(), out, "exec")
print(out, "written, veto kinds", kinds, "from street", min_st)
