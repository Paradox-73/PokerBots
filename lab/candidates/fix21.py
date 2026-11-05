"""Solver check off on the turn and river against an opponent who does not discard the best card.
The solver's turn/river hand strength assumes the opponent's shown discard was its best keep
(opponent_holdings, RATIONAL mask), so against a fixed-rule discarder (the starter kit drops the
lowest rank) it overrates the opponent's hand and the check deletes calls the EV bot's own
discard model (disc_pi: smart / drop lowest / random, learnt from showdowns) says are right.
The prior gives smart 0.58, so the check stays on until showdowns show another rule.
usage: fix21.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()
old = '''                bot.view = solver_view(solver, msg) if msg.get("time_left_ms", 10 ** 9) > pace else None'''
new = '''                # The solver reads the opponent's shown discard as its best keep; after the flop
                # its hand strengths are wrong against an opponent who discards by another rule.
                smart = STREET[msg["street"]] < 2 or bot.opp.disc_pi()[0] >= 0.5
                bot.view = solver_view(solver, msg) if smart and msg.get("time_left_ms", 10 ** 9) > pace else None'''
assert src.count(old) == 1
src = src.replace(old, new)
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
