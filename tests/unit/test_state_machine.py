"""REQ-2 state machine, at the graph layer.

The whole transition matrix is walked here. Only the three named rules and the
status code they produce are repeated at the integration layer, for the reason
given in `docs/test-design.md`.
"""

from __future__ import annotations

import itertools

import pytest

from app.domain import CANCELLABLE_FROM, TRANSITIONS, State
from app.state import IllegalTransition, is_legal, refusing_rule, transition

LEGAL_SEQUENCE = [
    (State.DRAFT, State.SUBMITTED),
    (State.SUBMITTED, State.APPROVED),
    (State.APPROVED, State.SCHEDULED),
    (State.SCHEDULED, State.IMPLEMENTING),
    (State.IMPLEMENTING, State.VERIFIED),
    (State.VERIFIED, State.CLOSED),
]


@pytest.mark.parametrize(("from_state", "to_state"), LEGAL_SEQUENCE)
def test_the_happy_path_sequence_is_legal(from_state, to_state):
    """Draft to Submitted to Approved to Scheduled to Implementing to Verified
    to Closed.

    Layer: unit
    Covers: REQ-2
    Why this layer: the sequence is the graph, and the graph is a table. The
    same path is walked once through HTTP at the integration layer to prove it
    persists.
    """
    assert transition(from_state, to_state) is to_state


def test_every_state_appears_in_the_graph():
    """No state is missing a row, including the terminal ones.

    Layer: unit
    Covers: REQ-2
    Why this layer: a structural check on the table. A missing row would raise a
    KeyError at runtime, which is a worse way to find out.
    """
    assert set(TRANSITIONS) == set(State)


def test_closed_and_cancelled_are_terminal():
    """Nothing leaves Closed or Cancelled.

    Layer: unit
    Covers: REQ-2
    Why this layer: two lookups in the table the service reads, and a terminal
    state that stopped being terminal would show up here rather than as a
    surprising 200 somewhere else.
    """
    assert TRANSITIONS[State.CLOSED] == frozenset()
    assert TRANSITIONS[State.CANCELLED] == frozenset()


@pytest.mark.parametrize("from_state", sorted(CANCELLABLE_FROM))
def test_cancellation_is_legal_before_implementing(from_state):
    """Draft, Submitted, Approved and Scheduled can all be cancelled.

    Layer: unit
    Covers: REQ-2.1
    Why this layer: four cases against one rule, and the positive half of the
    pair below.
    """
    assert transition(from_state, State.CANCELLED) is State.CANCELLED


@pytest.mark.parametrize(
    "from_state",
    [State.IMPLEMENTING, State.VERIFIED, State.ROLLED_BACK, State.CLOSED],
)
def test_cancellation_is_refused_from_implementing_onward(from_state):
    """Once implementation starts, cancellation is not available.

    Layer: unit
    Covers: REQ-2.1
    Why this layer: the negative half, written beside its positive twin. The
    rule ID on the refusal is asserted, because a generic refusal would not tell
    a caller which rule stopped them.
    """
    with pytest.raises(IllegalTransition) as refused:
        transition(from_state, State.CANCELLED)
    assert refused.value.rule == "REQ-2.1"


def test_implementing_cannot_return_to_approved():
    """There is no route back from Implementing to Approved.

    Layer: unit
    Covers: REQ-2.2
    Why this layer: one edge that must not exist. Named in the requirements, so
    it gets its own case rather than being folded into the matrix walk.
    """
    with pytest.raises(IllegalTransition) as refused:
        transition(State.IMPLEMENTING, State.APPROVED)
    assert refused.value.rule == "REQ-2.2"


def test_failed_verification_goes_to_rolled_back():
    """Implementing can move to Rolled Back.

    Layer: unit
    Covers: REQ-2.3
    Why this layer: the positive half of the REQ-2.3 pair.
    """
    assert transition(State.IMPLEMENTING, State.ROLLED_BACK) is State.ROLLED_BACK


def test_implementing_cannot_move_straight_to_closed():
    """A change never moves from Implementing to Closed without passing through
    Verified or Rolled Back.

    Layer: unit
    Covers: REQ-2.3
    Why this layer: the negative half, and the rule ID matters because this is
    the transition an implementation is most likely to allow by accident.
    """
    with pytest.raises(IllegalTransition) as refused:
        transition(State.IMPLEMENTING, State.CLOSED)
    assert refused.value.rule == "REQ-2.3"


def test_rolled_back_can_be_closed_out():
    """A rolled back change can still be closed.

    Layer: unit
    Covers: REQ-2.3
    Why this layer: REQ-2.3 says failed verification never moves straight to
    Closed. It does not make Rolled Back terminal, and this case states the
    reading the service implements.
    """
    assert transition(State.ROLLED_BACK, State.CLOSED) is State.CLOSED


def test_the_whole_matrix_agrees_with_the_table():
    """Every ordered pair of states is legal if and only if the table says so.

    Layer: unit
    Covers: REQ-2
    Why this layer: eighty one pairs. At the HTTP layer this would be eighty one
    requests to learn what eighty one function calls already prove, which is the
    clearest example in this suite of a test that would be at the wrong layer.
    """
    for from_state, to_state in itertools.product(State, State):
        expected = to_state in TRANSITIONS[from_state]
        assert is_legal(from_state, to_state) is expected
        if expected:
            continue
        with pytest.raises(IllegalTransition):
            transition(from_state, to_state)


def test_a_refusal_names_the_states_it_could_have_moved_to():
    """The refusal carries the legal alternatives, in order.

    Layer: unit
    Covers: REQ-2
    Why this layer: the content of the exception is what the API turns into a
    response body, so it is asserted where it is produced.
    """
    with pytest.raises(IllegalTransition) as refused:
        transition(State.DRAFT, State.CLOSED)
    assert refused.value.allowed == sorted([State.CANCELLED, State.SUBMITTED])


@pytest.mark.parametrize(
    ("from_state", "to_state", "rule"),
    [
        (State.IMPLEMENTING, State.CANCELLED, "REQ-2.1"),
        (State.IMPLEMENTING, State.APPROVED, "REQ-2.2"),
        (State.IMPLEMENTING, State.CLOSED, "REQ-2.3"),
        (State.DRAFT, State.VERIFIED, "REQ-2"),
        (State.CLOSED, State.DRAFT, "REQ-2"),
    ],
)
def test_refusals_are_attributed_to_the_right_rule(from_state, to_state, rule):
    """Three named rules, and the sequence itself for everything else.

    Layer: unit
    Covers: REQ-2, REQ-2.1, REQ-2.2, REQ-2.3
    Why this layer: attribution is a pure function of the two states, and it is
    the part a caller reads when deciding what to do next.
    """
    assert refusing_rule(from_state, to_state) == rule
