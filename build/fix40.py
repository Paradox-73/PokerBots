"""Input guard. main() called msg.get("type") outside its try block, so a stdin line holding valid JSON that is not
an object (a list, a number, null) would raise AttributeError and end the process: a forfeit. The organisers'
engine sends only objects, so play is unchanged; the line is now skipped like any other unreadable line.
usage: fix40.py IN_BOT OUT_BOT"""
import sys

src = open(sys.argv[1], newline="").read()


def cut(old, new):
    global src
    assert src.count(old) == 1, old
    src = src.replace(old, new)


cut('''        except ValueError:
            continue
        t = msg.get("type")''', '''        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        t = msg.get("type")''')
compile(src, sys.argv[2], "exec")
open(sys.argv[2], "w", newline="").write(src)
print(sys.argv[2], "written")
