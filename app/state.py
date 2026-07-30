"""REQ-2 state machine.

Pure. The graph lives in `app/domain.py` so the service and the tests read the
same table. This module answers one question: is this move legal, and if not,
which rule refuses it.
"""

from __future__ import annotations

from app.domain import CANCELLABLE_FROM, TRANSITIONS, State


class IllegalTransition(Exception):
    """Raised when a move is not on the graph. Carries the rule that refused it
    so the API can return a machine readable body rather than prose."""

    def __init__(self, rule: str, from_state: State, to_state: State) -> None:
        super().__init__(f"{from_state} cannot move to {to_state} ({rule})")
        self.rule = rule
        self.from_state = from_state
        self.to_state = to_state

    @property
    def allowed(self) -> list[State]:
        """States the record could legally move to instead, ordered."""
        return sorted(TRANSITIONS[self.from_state])


def is_legal(from_state: State, to_state: State) -> bool:
    """True when the move is on the graph."""
    return to_state in TRANSITIONS[from_state]


def refusing_rule(from_state: State, to_state: State) -> str:
    """The requirement ID that refuses this move.

    Three of the rules are named in the requirements and the rest of the graph
    is the sequence itself, which is reported as REQ-2.
    """
    if to_state is State.CANCELLED and from_state not in CANCELLABLE_FROM:
        # REQ-2.1: cancellation is legal only before Implementing.
        return "REQ-2.1"
    if from_state is State.IMPLEMENTING and to_state is State.APPROVED:
        # REQ-2.2: once Implementing has started there is no route back.
        return "REQ-2.2"
    if from_state is State.IMPLEMENTING and to_state is State.CLOSED:
        # REQ-2.3: failed verification lands on Rolled Back, never on Closed.
        return "REQ-2.3"
    return "REQ-2"


def transition(from_state: State, to_state: State) -> State:
    """Return the new state, or raise `IllegalTransition`."""
    if not is_legal(from_state, to_state):
        raise IllegalTransition(
            rule=refusing_rule(from_state, to_state),
            from_state=from_state,
            to_state=to_state,
        )
    return to_state
