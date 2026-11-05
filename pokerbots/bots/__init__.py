"""Bot registry.  Add new strategies to BOTS."""

EXTRA = {}   # bots registered at run time; test opponents add themselves here


def _registry():
    from pokerbots.bots.simple import CallBot, ManiacBot, RandomBot, StarterBot, TagBot
    from pokerbots.bots.equity_bot import EquityBot
    from pokerbots.bots.range_bot import RangeBot
    return {"random": RandomBot, "call": CallBot, "starter": StarterBot, "maniac": ManiacBot,
            "tag": TagBot, "equity": EquityBot, "range": RangeBot, **EXTRA}


def bot_names():
    return sorted(_registry())


def make_bot(name):
    reg = _registry()
    if name not in reg:
        raise KeyError("unknown bot %r (known: %s)" % (name, ", ".join(sorted(reg))))
    return reg[name]()
