"""Request and response schemas.

Schema level validation (types, required fields, timezone aware timestamps) is
deliberately separated from rule level validation in `app/rules.py`. A malformed
payload is a 422 from this layer. A well formed payload that the gate refuses is
a 400 from that one. See `docs/decisions/0002-status-codes.md`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain import (
    ChangeClass,
    PromotionStage,
    ReleaseType,
    Role,
    State,
    TestEnvironment,
)


class TestEvidence(BaseModel):
    """One claim of testing in one environment (REQ-1.2)."""

    model_config = ConfigDict(extra="forbid")

    environment: TestEnvironment
    passed: bool
    reference: str = Field(min_length=1, max_length=200)


class MergeRequestRecord(BaseModel):
    """A merge request raised at one stage of the promotion path (REQ-1.5)."""

    model_config = ConfigDict(extra="forbid")

    stage: PromotionStage
    url: str = Field(min_length=1, max_length=500)
    merged_at: AwareDatetime


class OnCallAssignment(BaseModel):
    """A named person covering a role for a window of time (REQ-1.6)."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    name: str = Field(min_length=1, max_length=120)
    window_start: AwareDatetime
    window_end: AwareDatetime


class ChangeSubmission(BaseModel):
    """The payload a submitter sends.

    Fields whose absence is itself a rule violation are optional here on
    purpose. If `rollback_plan` were required by the schema, REQ-1.1 could never
    be reached and the rule would be untestable through the API.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    release_type: ReleaseType
    change_class: ChangeClass
    scrum_team: str = Field(min_length=1, max_length=80)
    submitter: str = Field(min_length=1, max_length=120)
    fix_version: str = Field(min_length=1, max_length=40)
    implementation_start: AwareDatetime
    implementation_end: AwareDatetime

    # Optional at the schema layer, checked by the rules layer.
    rollback_plan: str | None = None
    jira_ticket: str | None = None
    test_evidence: list[TestEvidence] = Field(default_factory=list)
    merge_requests: list[MergeRequestRecord] = Field(default_factory=list)
    on_call: list[OnCallAssignment] = Field(default_factory=list)


class Violation(BaseModel):
    """One reason the gate refused. `rule` is the requirement ID verbatim."""

    model_config = ConfigDict(extra="forbid")

    rule: str
    message: str


class ChangeRecord(BaseModel):
    """A stored change request and its current state."""

    model_config = ConfigDict(extra="forbid")

    id: str
    state: State
    created_at: datetime
    updated_at: datetime
    submission: ChangeSubmission


class TransitionRequest(BaseModel):
    """Ask for a state change (REQ-2)."""

    model_config = ConfigDict(extra="forbid")

    to_state: State


class RejectionDetail(BaseModel):
    """Body of a 400 when the gate refuses a submission (REQ-1)."""

    model_config = ConfigDict(extra="forbid")

    code: str = "submission_rejected"
    violations: list[Violation]


class TransitionErrorDetail(BaseModel):
    """Body of a 409 when a transition is not legal (REQ-2)."""

    model_config = ConfigDict(extra="forbid")

    code: str = "illegal_transition"
    rule: str
    from_state: State
    to_state: State
    allowed: list[State]


class NotFoundDetail(BaseModel):
    """Body of a 404."""

    model_config = ConfigDict(extra="forbid")

    code: str = "not_found"


class RejectionResponse(BaseModel):
    """The 400 envelope. Declared so the OpenAPI document describes refusals as
    well as successes: a spec that only documents the happy path is a spec a
    consumer cannot write error handling against."""

    model_config = ConfigDict(extra="forbid")

    detail: RejectionDetail


class TransitionErrorResponse(BaseModel):
    """The 409 envelope."""

    model_config = ConfigDict(extra="forbid")

    detail: TransitionErrorDetail


class NotFoundResponse(BaseModel):
    """The 404 envelope."""

    model_config = ConfigDict(extra="forbid")

    detail: NotFoundDetail


class Health(BaseModel):
    """Liveness plus the version the instance is running."""

    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
