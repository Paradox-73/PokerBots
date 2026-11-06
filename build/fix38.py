"""Time-panic fix. With under 1000 ms of bank left, on_discard returns a discard at once, before the flop tables
(h.Pk) exist; the next discard_result then raised TypeError at `h.Pk[sel, col]`. The error was caught, so replies
were unaffected, but it wrote a stderr line every hand. discard_result now stops at that line when there are no flop
tables, so the hand state is exactly what the caught error left (only in that time panic; normal play builds the
tables before every discard). results/time_panic_cand49.txt: 181 stderr lines before, 0 after.
usage: fix38.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        pairs = PT[sel, col]
        w = np.bincount(pairs, h.W3[sel] * h.Pk[sel, col], NP)''', '''        pairs = PT[sel, col]
        if h.Pk is None:  # a time panic skipped the flop tables: nothing to weigh
            return
        w = np.bincount(pairs, h.W3[sel] * h.Pk[sel, col], NP)''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
