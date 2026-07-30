"""Domain vocabulary for the release gate.

Every constant here is a rule from `docs/requirements.md` expressed once, so a
test can import the same table the service decides from. Nothing in this module
reads the clock, the database, or the environment.
"""

from __future__ import annotations

from enum import StrEnum

SERVICE_VERSION = "0.1.0"


class ReleaseType(StrEnum):
    """Declared by the submitter. The gate trusts the declaration (REQ-1.6)."""

    SMALL = "small"
    SPRINT = "sprint"
    MONOREPO = "monorepo"
    SPA = "spa"


class Role(StrEnum):
    """On call roles. The required set depends on release type (REQ-1.6)."""

    DEV = "dev"
    BUSINESS = "business"
    DEVOPS = "devops"
    PROD_SUPPORT = "prod_support"
    TECH_LEAD = "tech_lead"


class TestEnvironment(StrEnum):
    """Environments that testing evidence is claimed against (REQ-1.2)."""

    DEV = "dev"
    QA = "qa"
    BAT = "bat"


class PromotionStage(StrEnum):
    """Stages of the promotion path (REQ-1.5a). Production is the destination,
    so it is not a stage that can be evidenced in advance."""

    REG_SIT = "reg_sit"
    INT = "int"
    BAT = "bat"


class State(StrEnum):
    """States of a change record (REQ-2)."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    IMPLEMENTING = "implementing"
    VERIFIED = "verified"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class TicketStatus(StrEnum):
    """Ticket lifecycle in the tracker the fix version is read from (REQ-1.7)."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


# REQ-1.6. Ordered tuples rather than sets so rejection messages are stable and
# a diff to this table is readable. Note the SPA row: Prod Support is not
# required. An implementation that always requires Prod Support is wrong.
ON_CALL_MATRIX: dict[ReleaseType, tuple[Role, ...]] = {
    ReleaseType.SMALL: (Role.DEV, Role.BUSINESS),
    ReleaseType.SPRINT: (Role.DEVOPS, Role.PROD_SUPPORT, Role.DEV, Role.TECH_LEAD),
    ReleaseType.MONOREPO: (Role.DEVOPS, Role.PROD_SUPPORT),
    ReleaseType.SPA: (Role.DEVOPS, Role.TECH_LEAD),
}

# REQ-1.5a. Order matters: each stage must be evidenced, and in this sequence.
PROMOTION_PATH: tuple[PromotionStage, ...] = (
    PromotionStage.REG_SIT,
    PromotionStage.INT,
    PromotionStage.BAT,
)

# REQ-1.2. Evidence required from every change. There are no exemptions: every
# change is a standard change and carries the full evidence requirement.
REQUIRED_TEST_EVIDENCE: tuple[TestEnvironment, ...] = (
    TestEnvironment.DEV,
    TestEnvironment.QA,
    TestEnvironment.BAT,
)

# REQ-1.7. A fix version is clean when every ticket on it has landed in one of
# these states. Anything else could still reach the branch.
SETTLED_TICKET_STATUSES: frozenset[TicketStatus] = frozenset(
    {TicketStatus.RESOLVED, TicketStatus.CLOSED}
)

# REQ-2. The legal transition graph. Read as: from this state, to any of these.
TRANSITIONS: dict[State, frozenset[State]] = {
    State.DRAFT: frozenset({State.SUBMITTED, State.CANCELLED}),
    State.SUBMITTED: frozenset({State.APPROVED, State.CANCELLED}),
    State.APPROVED: frozenset({State.SCHEDULED, State.CANCELLED}),
    State.SCHEDULED: frozenset({State.IMPLEMENTING, State.CANCELLED}),
    # REQ-2.2: no route back to Approved. REQ-2.3: failure lands on Rolled Back,
    # never straight on Closed.
    State.IMPLEMENTING: frozenset({State.VERIFIED, State.ROLLED_BACK}),
    State.VERIFIED: frozenset({State.CLOSED}),
    State.ROLLED_BACK: frozenset({State.CLOSED}),
    State.CLOSED: frozenset(),
    State.CANCELLED: frozenset(),
}

# REQ-2.1. Cancellation is legal from any state before Implementing, which is
# the same thing the table above says. Kept as its own name because the rule is
# stated separately and tests reference it by rule ID.
CANCELLABLE_FROM: frozenset[State] = frozenset(
    {State.DRAFT, State.SUBMITTED, State.APPROVED, State.SCHEDULED}
)


def required_roles(release_type: ReleaseType) -> tuple[Role, ...]:
    """Roles that need a named on call for this release type (REQ-1.6)."""
    return ON_CALL_MATRIX[release_type]


def required_test_environments() -> tuple[TestEnvironment, ...]:
    """Environments that need passing evidence (REQ-1.2)."""
    return REQUIRED_TEST_EVIDENCE
