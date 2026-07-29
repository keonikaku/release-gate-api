"""Submission builders shared by every layer.

One baseline that the gate accepts, and keyword overrides to break exactly one
thing at a time. A test that builds its own payload from scratch hides which
field it is actually about, so no test in this suite does.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import ChangeSubmission

# The implementation window every fixture is written around.
WINDOW_START = datetime(2026, 8, 1, 22, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 2, 2, 0, tzinfo=UTC)

# A clock pinned for tests, so record timestamps are asserted rather than
# tolerated.
PINNED_NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)

FULL_ON_CALL = ("devops", "prod_support", "dev", "tech_lead", "business")


def on_call_entry(
    role: str,
    name: str = "j.okafor",
    start: datetime = WINDOW_START,
    end: datetime = WINDOW_END,
) -> dict[str, Any]:
    """One on call assignment covering the implementation window by default."""
    return {
        "role": role,
        "name": name,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
    }


def valid_payload(**overrides: Any) -> dict[str, Any]:
    """A submission the gate accepts, as JSON ready values.

    Every role in the on call matrix is staffed, so a test can narrow the list
    to prove a specific row of REQ-1.6 rather than widen it.
    """
    payload: dict[str, Any] = {
        "title": "Payments service 4.2 sprint release",
        "release_type": "sprint",
        "change_class": "normal",
        "scrum_team": "payments",
        "submitter": "a.rivera",
        "fix_version": "2026.07.1",
        "implementation_start": WINDOW_START.isoformat(),
        "implementation_end": WINDOW_END.isoformat(),
        "rollback_plan": "Redeploy 4.1.3 from the previous tag, verify smoke suite.",
        "jira_ticket": "PAY-1150",
        "test_evidence": [
            {"environment": "dev", "passed": True, "reference": "run-9001"},
            {"environment": "qa", "passed": True, "reference": "run-9002"},
            {"environment": "bat", "passed": True, "reference": "run-9003"},
        ],
        "merge_requests": [
            {
                "stage": "reg_sit",
                "url": "https://forge.example/mr/101",
                "merged_at": "2026-07-20T09:00:00+00:00",
            },
            {
                "stage": "int",
                "url": "https://forge.example/mr/102",
                "merged_at": "2026-07-22T09:00:00+00:00",
            },
            {
                "stage": "bat",
                "url": "https://forge.example/mr/103",
                "merged_at": "2026-07-24T09:00:00+00:00",
            },
        ],
        "on_call": [on_call_entry(role) for role in FULL_ON_CALL],
    }
    payload.update(overrides)
    return payload


def valid_submission(**overrides: Any) -> ChangeSubmission:
    """The same baseline as a validated model, for the unit layer."""
    return ChangeSubmission.model_validate(valid_payload(**overrides))
