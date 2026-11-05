"""Card <-> string conversion.  Card id = rank_index * NUM_SUITS + suit_index."""

from pokerbots.core import rules

_NS = rules.NUM_SUITS


def rank_of(card):
    return card // _NS


def suit_of(card):
    return card % _NS


def card_to_str(card):
    return rules.RANKS[card // _NS] + rules.SUITS[card % _NS]


def str_to_card(text):
    text = text.strip()
    r = rules.RANKS.index(text[0].upper())
    s = rules.SUITS.index(text[1].lower())
    return r * _NS + s


def cards_to_str(cards, sep=","):
    return sep.join(card_to_str(c) for c in cards)


def str_to_cards(text, sep=","):
    text = text.strip()
    if not text or text == "-":
        return []
    return [str_to_card(t) for t in text.split(sep) if t]
