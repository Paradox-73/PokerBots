"""a code review: the trainer bucketed card features after rounding them to 1/65535 (solver/train.py, uint16 storage), the
bot bucketed the raw value, so about 0.2% of flop and river lookups landed in the next bucket. Round the same way
(as float32, the type of the shipped edges, so a value on an edge compares equal as it did in training).
usage: fix33.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()
old = '''def bucket_1d(x, edges):
    return int(np.searchsorted(edges, x, "right"))'''
new = '''def bucket_1d(x, edges):
    x = np.float32(round(min(max(float(x), 0.0), 1.0) * 65535) / 65535)  # as the trainer's uint16 features
    return int(np.searchsorted(edges, x, "right"))'''
assert src.count(old) == 1
src = src.replace(old, new)
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
