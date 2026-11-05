"""Run a registered bot over stdin/stdout:  python -m pokerbots.bots <name>"""

import sys

from pokerbots.bots import make_bot
from pokerbots.engine.protocol import BotAdapter


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "equity"
    BotAdapter(make_bot(name)).run()


if __name__ == "__main__":
    main()
