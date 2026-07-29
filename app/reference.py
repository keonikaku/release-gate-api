"""Reference data the gate decides against.

In a real deployment these come from the HR directory and the ticket tracker.
Here they are a fixed, seeded table, because a gate whose answer depends on a
third party cannot be tested deterministically. This is one of the testability
properties the README claims, and it is a deliberate design choice rather than a
shortcut. See `docs/decisions/0003-testability-properties.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import TicketStatus


@dataclass(frozen=True, slots=True)
class Ticket:
    """A ticket in the tracker, on exactly one fix version (REQ-1.7)."""

    key: str
    fix_version: str
    status: TicketStatus


# REQ-1.3. Team name to the members the gate will accept a submission from.
TEAM_ROSTER: dict[str, frozenset[str]] = {
    "payments": frozenset({"a.rivera", "j.okafor", "s.lindqvist"}),
    "identity": frozenset({"m.tanaka", "d.abara"}),
    "web-platform": frozenset({"p.novak", "l.moreau", "c.silva"}),
}

# REQ-1.7. Three fix versions with deliberately different shapes:
# one entirely settled, one carrying an open ticket, one carrying work in
# progress. Boundary cases are written against all three.
TICKETS: tuple[Ticket, ...] = (
    Ticket("PAY-1101", "2026.07.1", TicketStatus.CLOSED),
    Ticket("PAY-1102", "2026.07.1", TicketStatus.RESOLVED),
    Ticket("IDN-2201", "2026.07.1", TicketStatus.CLOSED),
    Ticket("PAY-1201", "2026.07.2", TicketStatus.CLOSED),
    Ticket("PAY-1202", "2026.07.2", TicketStatus.OPEN),
    Ticket("WEB-3301", "2026.08.0", TicketStatus.IN_PROGRESS),
    Ticket("WEB-3302", "2026.08.0", TicketStatus.RESOLVED),
)


def tickets_for(fix_version: str) -> tuple[Ticket, ...]:
    """Every ticket recorded against a fix version. Empty tuple if unknown."""
    return tuple(t for t in TICKETS if t.fix_version == fix_version)
