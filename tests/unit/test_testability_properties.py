"""The properties that make this service testable, asserted rather than claimed.

The README says the service has deterministic state, an injectable clock and
machine readable errors, because those are the properties a QA lead asks
engineering for. A claim in a README rots. These cases are what keep it true.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.clock import fixed_clock, system_clock
from app.rules import evaluate
from tests.factories import PINNED_NOW, valid_submission

APP_DIRECTORY = Path(__file__).resolve().parents[2] / "app"

# The clock lives in exactly one module. Everywhere else takes it as an
# argument.
CLOCK_OWNER = "clock.py"


def test_the_clock_is_read_in_exactly_one_module():
    """No module in `app/` calls `datetime.now` except `app/clock.py`.

    Layer: unit
    Covers: none
    Why this layer: a static property of the source, checked by reading the
    source. No running service can show you an absent call.
    """
    offenders = []
    for path in sorted(APP_DIRECTORY.glob("*.py")):
        if path.name == CLOCK_OWNER:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if isinstance(function, ast.Attribute) and function.attr in {
                "now",
                "utcnow",
                "today",
            }:
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"hidden clock reads: {offenders}"


def test_a_fixed_clock_returns_the_moment_it_was_given():
    """The test clock is a value, not an approximation.

    Layer: unit
    Covers: none
    Why this layer: the test clock is test infrastructure, so it is proved in
    process. Every pinned timestamp assertion in the suite rests on it.
    """
    assert fixed_clock(PINNED_NOW)() == PINNED_NOW


def test_the_system_clock_is_timezone_aware():
    """The real clock returns an aware datetime, so stored timestamps are
    comparable with the aware timestamps in a submission.

    Layer: unit
    Covers: none
    Why this layer: reading the clock directly is the only way to see its
    timezone, and this is the one case in the suite that touches wall time.
    """
    assert system_clock().tzinfo is not None


def test_rule_evaluation_is_deterministic():
    """The same submission evaluated twice gives the same answer.

    Layer: unit
    Covers: REQ-1
    Why this layer: determinism is a property of the rule functions. If it were
    only checked through HTTP, a caching layer could hide a violation of it.
    """
    submission = valid_submission(rollback_plan=None, jira_ticket=None)
    first = [v.model_dump() for v in evaluate(submission)]
    second = [v.model_dump() for v in evaluate(submission)]
    assert first == second


@pytest.mark.parametrize(
    "field",
    ["rule", "message"],
)
def test_violations_are_machine_readable(field):
    """Every violation carries a rule ID and a message, both non empty.

    Layer: unit
    Covers: REQ-1
    Why this layer: the shape of the violation is decided here. The HTTP
    envelope that carries it is asserted at the contract layer.
    """
    violations = evaluate(valid_submission(rollback_plan=None, test_evidence=[]))
    assert violations
    assert all(getattr(v, field) for v in violations)
