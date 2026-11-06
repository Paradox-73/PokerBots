"""Copy the preflop table (the PRE_DATA string) from one built bot into another.
usage: copy_table.py FROM_BOT INTO_BOT OUT_BOT"""
import sys


def table(src):
    a = src.index('PRE_DATA = "') + len('PRE_DATA = "')
    return a, src.index('"', a)


new = open(sys.argv[1], newline="").read()
dst = open(sys.argv[2], newline="").read()
a, b = table(new)
c, d = table(dst)
out = dst[:c] + new[a:b] + dst[d:]
compile(out, sys.argv[3], "exec")
open(sys.argv[3], "w", newline="").write(out)
print(sys.argv[3], "written; table", b - a, "chars")
