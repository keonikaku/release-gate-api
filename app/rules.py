"""REQ-1 submission validation.

Pure functions. No database handle, no clock, no request object. Every rule
returns zero or one violation, and `evaluate` returns them ordered by rule ID so
that a rejection body is stable enough to assert on.

Each rule below names the requirement it implements in its docstring. The
reasoning for which test layer covers each rule is in `docs/test-design.md`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from app.domain import (
    PROMOTION_PATH,
    SETTLED_TICKET_STATUSES,
    Role,
    required_roles,
    required_test_environments,
)
from app.models import ChangeSubmission, Violation
from app.reference import TEAM_ROSTER, Ticket, tickets_for

# REQ-1.4. A linked ticket means a tracker key, not any string. Two or more
# leading letters, a hyphen, then digits.
JIRA_KEY = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def check_rollback_plan(submission: ChangeSubmission) -> Violation | None:
    """REQ-1.1. Rejected if no rollback plan is attached."""
    plan = (submission.rollback_plan or "").strip()
    if not plan:
        return Violation(
            rule="REQ-1.1",
            message="No rollback plan is attached.",
        )
    return None


def check_test_evidence(submission: ChangeSubmission) -> Violation | None:
    """REQ-1.2. Rejected without passing evidence in every required environment.
    There are no exemptions."""
    required = required_test_environments()
    passed = {e.environment for e in submission.test_evidence if e.passed}
    missing = [env.value for env in required if env not in passed]
    if missing:
        return Violation(
            rule="REQ-1.2",
            message=f"No passing test evidence for: {', '.join(missing)}.",
        )
    return None


def check_team_membership(
    submission: ChangeSubmission,
    roster: Mapping[str, frozenset[str]],
) -> Violation | None:
    """REQ-1.3. Rejected if the submitter is not a member of the owning team.
    An unknown team is also a rejection: the gate cannot confirm membership of a
    team it has no roster for."""
    members = roster.get(submission.scrum_team)
    if members is None:
        return Violation(
            rule="REQ-1.3",
            message=f"No roster for owning team '{submission.scrum_team}'.",
        )
    if submission.submitter not in members:
        return Violation(
            rule="REQ-1.3",
            message=(
                f"Submitter '{submission.submitter}' is not a member of "
                f"'{submission.scrum_team}'."
            ),
        )
    return None


def check_jira_ticket(submission: ChangeSubmission) -> Violation | None:
    """REQ-1.4. Rejected if no Jira ticket is linked. A value that is not a
    tracker key is treated as not linked, because an unresolvable reference
    evidences nothing."""
    ticket = (submission.jira_ticket or "").strip()
    if not ticket:
        return Violation(rule="REQ-1.4", message="No Jira ticket is linked.")
    if not JIRA_KEY.match(ticket):
        return Violation(
            rule="REQ-1.4",
            message=f"Linked ticket '{ticket}' is not a tracker key.",
        )
    return None


def check_promotion_path(submission: ChangeSubmission) -> Violation | None:
    """REQ-1.5 and REQ-1.5a. Rejected unless a merge request exists at every
    lower stage, merged in path order. Out of order merges mean the change did
    not follow the promotion path even though every stage has a record."""
    merged_at = {}
    for record in submission.merge_requests:
        first = merged_at.get(record.stage)
        if first is None or record.merged_at < first:
            merged_at[record.stage] = record.merged_at

    missing = [stage.value for stage in PROMOTION_PATH if stage not in merged_at]
    if missing:
        return Violation(
            rule="REQ-1.5",
            message=f"No merge request at promotion stage: {', '.join(missing)}.",
        )

    ordered = [merged_at[stage] for stage in PROMOTION_PATH]
    for earlier, later, stage_a, stage_b in zip(
        ordered, ordered[1:], PROMOTION_PATH, PROMOTION_PATH[1:], strict=False
    ):
        if later < earlier:
            return Violation(
                rule="REQ-1.5",
                message=(
                    f"Promotion path out of order: {stage_b.value} merged before "
                    f"{stage_a.value}."
                ),
            )
    return None


def check_on_call(submission: ChangeSubmission) -> Violation | None:
    """REQ-1.6. Rejected if a role required for the declared release type has no
    named on call covering the whole implementation window. Coverage is
    inclusive: a window that starts exactly when implementation starts and ends
    exactly when it ends is covered."""
    covered: set[Role] = set()
    for assignment in submission.on_call:
        if not assignment.name.strip():
            continue
        starts_early_enough = assignment.window_start <= submission.implementation_start
        ends_late_enough = assignment.window_end >= submission.implementation_end
        if starts_early_enough and ends_late_enough:
            covered.add(assignment.role)

    missing = [
        role.value
        for role in required_roles(submission.release_type)
        if role not in covered
    ]
    if missing:
        return Violation(
            rule="REQ-1.6",
            message=(
                f"No named on call for the implementation window: {', '.join(missing)}."
            ),
        )
    return None


def check_fix_version(
    submission: ChangeSubmission,
    tickets: Sequence[Ticket],
) -> Violation | None:
    """REQ-1.7. Rejected if the fix version carries tickets that are neither
    resolved nor closed. A fix version with no tickets recorded against it is
    not a rejection: there is nothing unresolved on it. That reading is recorded
    as an open question in `docs/test-design.md`."""
    unsettled = sorted(t.key for t in tickets if t.status not in SETTLED_TICKET_STATUSES)
    if unsettled:
        return Violation(
            rule="REQ-1.7",
            message=(
                f"Fix version '{submission.fix_version}' has unresolved tickets: "
                f"{', '.join(unsettled)}."
            ),
        )
    return None


def evaluate(
    submission: ChangeSubmission,
    roster: Mapping[str, frozenset[str]] | None = None,
    tickets: Sequence[Ticket] | None = None,
) -> list[Violation]:
    """Run every REQ-1 rule and return the violations, ordered by rule ID.

    All seven rules are evaluated on every call. The gate reports every reason
    it refused rather than the first one, because a submitter who fixes one
    problem and is refused again for the next has learned nothing about the
    quality of the submission.
    """
    roster = TEAM_ROSTER if roster is None else roster
    tickets = tickets_for(submission.fix_version) if tickets is None else tickets

    results = [
        check_rollback_plan(submission),
        check_test_evidence(submission),
        check_team_membership(submission, roster),
        check_jira_ticket(submission),
        check_promotion_path(submission),
        check_on_call(submission),
        check_fix_version(submission, tickets),
    ]
    return sorted((v for v in results if v is not None), key=lambda v: v.rule)
