"""Style-switch test opponents: the first half of each leg is played by one bot, the second half by another.
The target's opponent counters never forget, so this measures how long it keeps playing against the first
style after the change. Each output bot.py is a router that runs the two bots as child processes; the second
is started ten hands before the switch and sent the leg's init message, so its start-up is not charged to a reply.
usage: sw_gen.py OUT_DIR NAME=FIRST_BOT,SECOND_BOT ...      writes OUT_DIR/NAME/bot.py"""
import os
import sys

ROUTER = '''"""Style-switch test opponent: hands 1..total/2 of each leg by FIRST, the rest by SECOND."""
import json
import subprocess
import sys

FIRST, SECOND = %r, %r


def spawn(path, init):
    p = subprocess.Popen([sys.executable, path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    p.stdin.write(init + "\\n")
    p.stdin.flush()
    return p


def main():
    first = second = cur = None
    init, n, total = None, 0, 100
    for line in sys.stdin:
        s = line.strip()
        if not s:
            continue
        msg = json.loads(s)
        t = msg.get("type")
        if t == "init":
            init, total = s, msg.get("total_hands", total)
            cur = first = spawn(FIRST, s)
            continue
        if t == "new_hand":
            n += 1
            if n == max(1, total // 2 - 10):
                second = spawn(SECOND, init)
            if n == total // 2 + 1:
                if second is None:
                    second = spawn(SECOND, init)
                first.terminate()
                cur = second
        cur.stdin.write(s + "\\n")
        cur.stdin.flush()
        if t in ("action_request", "discard_request"):
            sys.stdout.write(cur.stdout.readline())
            sys.stdout.flush()
        if t == "match_end":
            break
    for p in (first, second):
        if p is not None and p.poll() is None:
            p.terminate()


main()
'''

for arg in sys.argv[2:]:
    name, pair = arg.split("=", 1)
    a, b = pair.split(",")
    assert os.path.isfile(a) and os.path.isfile(b), (a, b)
    src = ROUTER % (a, b)
    compile(src, name, "exec")
    os.makedirs(os.path.join(sys.argv[1], name), exist_ok=True)
    open(os.path.join(sys.argv[1], name, "bot.py"), "w", newline="").write(src)
    print(name, "written:", a, "->", b)
