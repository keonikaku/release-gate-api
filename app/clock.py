"""The clock, as an injectable dependency.

Record timestamps are the only thing in this service that is not a pure
function of the request, so the clock is passed in rather than read from inside
the logic. A test can pin it and assert on an exact value. There is no hidden
`datetime.now()` anywhere else in `app/`, and a unit test in
`tests/unit/test_testability_properties.py` fails the build if one appears.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    """Wall clock, in UTC. The only reader of the real time in this service."""
    return datetime.now(UTC)


def fixed_clock(moment: datetime) -> Clock:
    """A clock that always returns `moment`. Used by tests."""

    def _clock() -> datetime:
        return moment

    return _clock
