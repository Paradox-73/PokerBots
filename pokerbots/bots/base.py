"""Bot interface.  Strategies subclass Bot and implement act()."""

from pokerbots.core.evaluator import hand_value
from pokerbots.core.types import Action, CHECK, CALL


class Bot:
    name = "base"

    def on_game_start(self, info):
        """info: GameInfo.  Called once before the first hand."""

    def on_hand_start(self, view):
        """view: HandView with hole cards set."""

    def on_event(self, view, event):
        """Every post / action / board / showdown event, own actions included."""

    def act(self, view):
        """Return an Action.  Illegal actions are mapped to check/fold."""
        return Action.check() if CHECK in view.legal else Action.call()

    def discard(self, view):
        """Return the hole card (int) to discard after the flop betting.
        Default: keep the two cards that make the best hand on the flop."""
        return max(view.hole, key=lambda c: hand_value([x for x in view.hole if x != c],
                                                       view.board))

    def on_hand_end(self, view, my_delta):
        """my_delta: chips won (+) or lost (-) this hand."""

    def on_game_end(self):
        pass
