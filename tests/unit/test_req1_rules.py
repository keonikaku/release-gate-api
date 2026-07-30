"""REQ-1 submission validation, at the rule layer.

Every case here calls `evaluate` or a single rule function directly. The
reasoning for testing REQ-1 at this layer, and for the handful of cases that are
duplicated at the integration layer, is in `docs/test-design.md`.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.domain import ON_CALL_MATRIX, ReleaseType, Role, TicketStatus
from app.reference import TEAM_ROSTER, Ticket
from app.rules import evaluate
from tests.factories import (
    WINDOW_END,
    WINDOW_START,
    on_call_entry,
    valid_submission,
)


def rules_broken(submission) -> set[str]:
    """The set of rule IDs that refused this submission."""
    return {violation.rule for violation in evaluate(submission)}


def test_baseline_submission_is_accepted():
    """The baseline fixture passes all seven rules.

    Layer: unit
    Covers: REQ-1
    Why this layer: if the baseline were only proved through HTTP, every
    negative case below would carry an unstated dependency on the endpoint. The
    fixture is proved clean where it is defined.
    """
    assert evaluate(valid_submission()) == []


# REQ-1.1 ---------------------------------------------------------------------


@pytest.mark.parametrize("plan", [None, "", "   "])
def test_missing_rollback_plan_is_refused(plan):
    """A blank or absent rollback plan is refused.

    Layer: unit
    Covers: REQ-1.1
    Why this layer: one predicate over one field. Whitespace only is the case a
    naive truthiness check gets wrong, and it costs a function call here.
    """
    assert "REQ-1.1" in rules_broken(valid_submission(rollback_plan=plan))


# REQ-1.2 ---------------------------------------------------------------------


def evidence(*environments, passed=True):
    """Evidence entries for the given environments."""
    return [
        {"environment": env, "passed": passed, "reference": f"run-{i}"}
        for i, env in enumerate(environments)
    ]


@pytest.mark.parametrize(
    ("environments", "refused"),
    [
        # Every environment is required and there are no exemptions, so each
        # single omission is its own rejection.
        ((), True),
        (("dev",), True),
        (("qa",), True),
        (("bat",), True),
        (("dev", "qa"), True),
        (("dev", "bat"), True),
        (("qa", "bat"), True),
        (("dev", "qa", "bat"), False),
    ],
)
def test_test_evidence_requires_every_environment(environments, refused):
    """Dev, QA and BAT are all required. Only the complete set is accepted.

    Layer: unit
    Covers: REQ-1.2
    Why this layer: this is the full subset table for three environments, and a
    table costs one function call per row here against one HTTP round trip per
    row at the integration layer. The accepting row is repeated in integration
    to prove the endpoint reaches this rule at all.
    """
    submission = valid_submission(test_evidence=evidence(*environments))
    assert ("REQ-1.2" in rules_broken(submission)) is refused


def test_failed_evidence_does_not_count_as_evidence():
    """Evidence recorded as failed is not evidence of testing.

    Layer: unit
    Covers: REQ-1.2
    Why this layer: the rule is about the `passed` flag, which is invisible in a
    status code. This is the case an implementation that counts rows rather than
    passing rows gets wrong.
    """
    submission = valid_submission(
        test_evidence=[
            {"environment": "dev", "passed": True, "reference": "run-1"},
            {"environment": "qa", "passed": False, "reference": "run-2"},
            {"environment": "bat", "passed": True, "reference": "run-3"},
        ]
    )
    assert "REQ-1.2" in rules_broken(submission)


# REQ-1.3 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("team", "submitter", "refused"),
    [
        ("payments", "a.rivera", False),
        ("payments", "m.tanaka", True),
        ("identity", "m.tanaka", False),
        ("mystery-squad", "a.rivera", True),
        ("payments", "A.RIVERA", True),
    ],
)
def test_submitter_must_be_on_the_owning_team(team, submitter, refused):
    """A submitter outside the owning team is refused, and so is a team the gate
    has no roster for.

    Layer: unit
    Covers: REQ-1.3
    Why this layer: the roster is an injected mapping, so the rule can be proved
    without depending on the seeded reference data. Nothing about HTTP changes
    the answer.
    """
    submission = valid_submission(scrum_team=team, submitter=submitter)
    assert ("REQ-1.3" in rules_broken(submission)) is refused


def test_membership_is_checked_against_the_supplied_roster():
    """The rule reads the roster it is given, not a global.

    Layer: unit
    Covers: REQ-1.3
    Why this layer: injection is the property being asserted, and it is only
    visible from inside the process.
    """
    submission = valid_submission(scrum_team="payments", submitter="new.joiner")
    assert "REQ-1.3" in rules_broken(submission)
    roster = {"payments": frozenset({"new.joiner"})}
    assert evaluate(submission, roster=roster) == []


def test_seeded_roster_is_not_empty():
    """The seeded roster has teams and members.

    Layer: unit
    Covers: REQ-1.3
    Why this layer: guards against a seed that silently empties, which would
    make every membership case pass for the wrong reason.
    """
    assert TEAM_ROSTER
    assert all(members for members in TEAM_ROSTER.values())


# REQ-1.4 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ticket", "refused"),
    [
        ("PAY-1150", False),
        ("AB-1", False),
        ("WEB2-33", False),
        (None, True),
        ("", True),
        ("   ", True),
        ("PAY-", True),
        ("P-1", True),
        ("pay-1150", True),
        ("see the email thread", True),
    ],
)
def test_linked_jira_ticket_must_be_a_tracker_key(ticket, refused):
    """A ticket reference that is not a tracker key is not a linked ticket.

    Layer: unit
    Covers: REQ-1.4
    Why this layer: the boundary is between a string and a key, which is a
    regular expression and not an HTTP concern. `AB-1` and `P-1` are the
    deliberate pair either side of the two letter minimum.
    """
    assert ("REQ-1.4" in rules_broken(valid_submission(jira_ticket=ticket))) is refused


# REQ-1.5 and REQ-1.5a --------------------------------------------------------


def merges(*stages_and_times):
    """Merge request records from (stage, ISO timestamp) pairs."""
    return [
        {"stage": stage, "url": f"https://forge.example/mr/{i}", "merged_at": when}
        for i, (stage, when) in enumerate(stages_and_times)
    ]


def test_full_promotion_path_in_order_is_accepted():
    """REG/SIT then INT then BAT, merged in that order, satisfies the rule.

    Layer: unit
    Covers: REQ-1.5, REQ-1.5a
    Why this layer: the positive half of the boundary pair below. Both sides are
    written, and both live where the timestamps can be constructed directly.
    """
    assert "REQ-1.5" not in rules_broken(valid_submission())


@pytest.mark.parametrize(
    "missing",
    ["reg_sit", "int", "bat"],
)
def test_a_missing_promotion_stage_is_refused(missing):
    """A gap anywhere in the promotion path is refused.

    Layer: unit
    Covers: REQ-1.5
    Why this layer: three cases over a list, and the assertion is about which
    stage is named in the message rather than about transport.
    """
    kept = [
        record
        for record in valid_submission().merge_requests
        if record.stage.value != missing
    ]
    submission = valid_submission(
        merge_requests=[
            {
                "stage": record.stage.value,
                "url": record.url,
                "merged_at": record.merged_at.isoformat(),
            }
            for record in kept
        ]
    )
    violations = evaluate(submission)
    assert "REQ-1.5" in {v.rule for v in violations}
    assert missing in next(v.message for v in violations if v.rule == "REQ-1.5")


def test_promotion_stages_merged_out_of_order_are_refused():
    """Every stage present, merged in the wrong sequence, is still refused.

    Layer: unit
    Covers: REQ-1.5a
    Why this layer: this is the case an implementation that only checks for
    presence gets wrong, and it needs constructed timestamps to express.
    """
    submission = valid_submission(
        merge_requests=merges(
            ("reg_sit", "2026-07-22T09:00:00+00:00"),
            ("int", "2026-07-20T09:00:00+00:00"),
            ("bat", "2026-07-24T09:00:00+00:00"),
        )
    )
    assert "REQ-1.5" in rules_broken(submission)


def test_stages_merged_at_the_same_instant_are_accepted():
    """Identical merge timestamps are in order, not out of order.

    Layer: unit
    Covers: REQ-1.5a
    Why this layer: the boundary of the ordering comparison. A strict less than
    would refuse this, and only a case written at the boundary catches it.
    """
    same = "2026-07-20T09:00:00+00:00"
    submission = valid_submission(
        merge_requests=merges(("reg_sit", same), ("int", same), ("bat", same))
    )
    assert "REQ-1.5" not in rules_broken(submission)


def test_a_change_missing_the_bat_stage_fails_the_promotion_path():
    """The promotion path is checked stage by stage, and BAT is a stage of it.

    Layer: unit
    Covers: REQ-1.5
    Why this layer: it is rule logic over an ordered list, so it belongs beside
    the logic. REQ-1.2 and REQ-1.5 both involve BAT and this case proves they
    are evaluated independently: evidence can be complete while the promotion
    path is not.
    """
    submission = valid_submission(
        test_evidence=evidence("dev", "qa", "bat"),
        merge_requests=merges(
            ("reg_sit", "2026-07-20T09:00:00+00:00"),
            ("int", "2026-07-22T09:00:00+00:00"),
        ),
    )
    broken = rules_broken(submission)
    assert "REQ-1.2" not in broken
    assert "REQ-1.5" in broken


# REQ-1.6 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("release_type", "roles"),
    [
        ("small", ("dev", "business")),
        ("sprint", ("devops", "prod_support", "dev", "tech_lead")),
        ("monorepo", ("devops", "prod_support")),
        ("spa", ("devops", "tech_lead")),
    ],
)
def test_exactly_the_required_on_call_roles_are_enough(release_type, roles):
    """Staffing exactly the required roles for a release type is sufficient.

    Layer: unit
    Covers: REQ-1.6
    Why this layer: the matrix is four rows by five roles. Reading the same
    table the service reads keeps the test honest about what is required.
    """
    submission = valid_submission(
        release_type=release_type,
        on_call=[on_call_entry(role) for role in roles],
    )
    assert "REQ-1.6" not in rules_broken(submission)


def test_spa_release_does_not_require_prod_support():
    """The SPA row: DevOps and Tech Lead only.

    Layer: unit
    Covers: REQ-1.6
    Why this layer: the rule is a lookup in the matrix, so the wrong answer
    ("Prod Support is always required") is caught cheapest here. The same case
    is repeated at the integration layer because it is the row a reviewer will
    check by hand.
    """
    submission = valid_submission(
        release_type="spa",
        on_call=[on_call_entry("devops"), on_call_entry("tech_lead")],
    )
    assert "REQ-1.6" not in rules_broken(submission)


def test_sprint_release_does_require_prod_support():
    """The negative half of the SPA pair: the same missing role, refused.

    Layer: unit
    Covers: REQ-1.6
    Why this layer: written directly beside its positive twin so the pair reads
    as one decision rather than two unrelated cases.
    """
    submission = valid_submission(
        release_type="sprint",
        on_call=[
            on_call_entry("devops"),
            on_call_entry("tech_lead"),
            on_call_entry("dev"),
        ],
    )
    assert "REQ-1.6" in rules_broken(submission)


@pytest.mark.parametrize("release_type", list(ReleaseType))
def test_dropping_any_required_role_is_refused(release_type):
    """For every release type, removing one required role refuses the change.

    Layer: unit
    Covers: REQ-1.6
    Why this layer: walks the whole matrix, which is only affordable in process.
    """
    required = ON_CALL_MATRIX[release_type]
    for dropped in required:
        staffed = [role for role in required if role is not dropped]
        submission = valid_submission(
            release_type=release_type.value,
            on_call=[on_call_entry(role.value) for role in staffed],
        )
        assert "REQ-1.6" in rules_broken(submission), f"{release_type} missing {dropped}"


def test_on_call_window_matching_the_implementation_window_exactly_is_covered():
    """A window with the same start and end as the implementation is coverage.

    Layer: unit
    Covers: REQ-1.6
    Why this layer: the inclusive edge. Written directly beside the two cases
    below that sit one second outside it.
    """
    submission = valid_submission(
        release_type="monorepo",
        on_call=[
            on_call_entry("devops", start=WINDOW_START, end=WINDOW_END),
            on_call_entry("prod_support", start=WINDOW_START, end=WINDOW_END),
        ],
    )
    assert "REQ-1.6" not in rules_broken(submission)


@pytest.mark.parametrize(
    ("start_shift", "end_shift"),
    [
        (timedelta(seconds=1), timedelta(0)),
        (timedelta(0), timedelta(seconds=-1)),
    ],
)
def test_on_call_window_one_second_short_is_not_coverage(start_shift, end_shift):
    """A window that starts a second late, or ends a second early, does not
    cover the implementation window.

    Layer: unit
    Covers: REQ-1.6
    Why this layer: a one second boundary is not expressible through a status
    code, and both sides of it are written.
    """
    submission = valid_submission(
        release_type="monorepo",
        on_call=[
            on_call_entry(
                "devops",
                start=WINDOW_START + start_shift,
                end=WINDOW_END + end_shift,
            ),
            on_call_entry("prod_support"),
        ],
    )
    assert "REQ-1.6" in rules_broken(submission)


def test_the_required_role_must_be_named():
    """A role listed with a blank name has no named on call.

    Layer: unit
    Covers: REQ-1.6
    Why this layer: the rule says named, and whitespace is the case a presence
    check gets wrong.
    """
    submission = valid_submission(
        release_type="monorepo",
        on_call=[
            on_call_entry("devops", name="  "),
            on_call_entry("prod_support"),
        ],
    )
    assert "REQ-1.6" in rules_broken(submission)


def test_on_call_matrix_covers_every_release_type():
    """Every release type has a row, and every row names known roles.

    Layer: unit
    Covers: REQ-1.6
    Why this layer: a structural check on the table itself, which no
    integration case would notice until a release type was submitted.
    """
    assert set(ON_CALL_MATRIX) == set(ReleaseType)
    for roles in ON_CALL_MATRIX.values():
        assert roles
        assert all(isinstance(role, Role) for role in roles)


# REQ-1.7 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fix_version", "refused"),
    [
        ("2026.07.1", False),
        ("2026.07.2", True),
        ("2026.08.0", True),
    ],
)
def test_fix_version_carrying_unsettled_tickets_is_refused(fix_version, refused):
    """A fix version is clean only when every ticket on it is resolved or
    closed.

    Layer: unit
    Covers: REQ-1.7
    Why this layer: the seeded versions are chosen to give one clean case, one
    carrying an open ticket and one carrying work in progress. Only the first
    half of REQ-1.7 is covered at any layer. See stated gaps.
    """
    submission = valid_submission(fix_version=fix_version)
    assert ("REQ-1.7" in rules_broken(submission)) is refused


def test_unknown_fix_version_is_accepted():
    """PINNED AMBIGUOUS DECISION, not a settled rule.

    A fix version the tracker has never heard of carries no unresolved tickets,
    so the current reading accepts it. The opposite reading is defensible and is
    recorded as an open question in `docs/test-design.md`.

    Layer: unit
    Covers: REQ-1.7
    Why this layer: pins an interpretation of rule logic beside the logic.
    """
    assert "REQ-1.7" not in rules_broken(valid_submission(fix_version="9999.99.9"))


def test_ticket_statuses_are_read_from_the_supplied_tracker():
    """The rule reads the tickets it is given, not a global.

    Layer: unit
    Covers: REQ-1.7
    Why this layer: injection again, and it lets the case state the status it
    means rather than relying on the seed staying as it is.
    """
    submission = valid_submission(fix_version="2026.07.1")
    open_ticket = [Ticket("PAY-9999", "2026.07.1", TicketStatus.OPEN)]
    assert "REQ-1.7" in {v.rule for v in evaluate(submission, tickets=open_ticket)}


# The shape of a rejection ----------------------------------------------------


def test_every_broken_rule_is_reported_at_once():
    """A submission that breaks four rules is refused with four violations.

    Layer: unit
    Covers: REQ-1
    Why this layer: the aggregation behaviour belongs to `evaluate`. Proving it
    through HTTP would test the same list twice.
    """
    submission = valid_submission(
        rollback_plan=None,
        jira_ticket=None,
        test_evidence=[],
        scrum_team="mystery-squad",
    )
    assert rules_broken(submission) == {
        "REQ-1.1",
        "REQ-1.2",
        "REQ-1.3",
        "REQ-1.4",
    }


def test_violations_are_ordered_by_rule_id():
    """Violations come back in rule order, so a rejection body is stable.

    Layer: unit
    Covers: REQ-1
    Why this layer: ordering is a property of the function, and a stable body is
    what lets integration cases assert on the first element without flaking.
    """
    submission = valid_submission(
        test_evidence=[],
        rollback_plan=None,
        jira_ticket=None,
    )
    rules = [violation.rule for violation in evaluate(submission)]
    assert rules == sorted(rules)
