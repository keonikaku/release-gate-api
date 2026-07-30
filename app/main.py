"""The release gate API.

Five endpoints. The gate answers one question: is this change allowed to
proceed. It answers it on testing evidence (REQ-1) and it refuses moves that are
not on the lifecycle graph (REQ-2). REQ-3, the rule that a change only reaches
production when the regression suite passes, is enforced by the pipeline rather
than by this service. That split is deliberate and it is stated in
`docs/test-design.md` under stated gaps.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status

from app.clock import Clock, system_clock
from app.domain import SERVICE_VERSION, TRANSITIONS, State
from app.models import (
    ChangeRecord,
    ChangeSubmission,
    Health,
    NotFoundResponse,
    RejectionResponse,
    TransitionErrorResponse,
    TransitionRequest,
)
from app.rules import evaluate
from app.state import IllegalTransition, transition
from app.store import Store

DB_PATH_ENV = "RELEASE_GATE_DB"

# Support a configurable data directory, so the database does not sit in the
# working directory of whoever started the process.
DATA_DIR_ENV = "RELEASE_GATE_DATA_DIR"
DEFAULT_DATA_DIR = "/var/lib/release-gate"

# Declared on every endpoint that reads a change, so the spec describes the
# refusal paths and not only the happy one.
NOT_FOUND = {404: {"model": NotFoundResponse, "description": "No such change."}}

app = FastAPI(
    title="Release Gate API",
    version=SERVICE_VERSION,
    summary="Decides whether a proposed change may proceed to production.",
    description=(
        "The gate validates a submission against the rules in REQ-1 and enforces "
        "the lifecycle in REQ-2. Rejections are machine readable: every violation "
        "carries the requirement ID that refused it."
    ),
)

_store: Store | None = None


def get_store() -> Iterator[Store]:
    """Process wide store, opened once against the configured database path.

    Overridden in tests with a per test database, which is why it is a
    dependency rather than a module level import.
    """
    global _store  # noqa: PLW0603 - one process, one connection
    if _store is None:
        directory = Path(os.environ.get(DATA_DIR_ENV, DEFAULT_DATA_DIR))
        configured = Path(os.environ.get(DB_PATH_ENV, "release-gate.db"))
        _store = Store(directory / configured.name)
    yield _store


def get_clock() -> Clock:
    """The clock, injected so record timestamps can be pinned in a test."""
    return system_clock


StoreDep = Annotated[Store, Depends(get_store)]
ClockDep = Annotated[Clock, Depends(get_clock)]


@app.get("/healthz", response_model=Health, tags=["service"])
def healthz() -> Health:
    """Liveness, and the version this instance is running."""
    return Health(status="ok", version=SERVICE_VERSION)


@app.post(
    "/changes",
    response_model=ChangeRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["changes"],
)
def create_change(
    submission: ChangeSubmission,
    store: StoreDep,
    clock: ClockDep,
) -> ChangeRecord:
    """Record a change in Draft. No rules run here.

    Drafting is not submitting. The gate evaluates REQ-1 when the change is
    submitted, which is what makes a rejection a decision about a submission
    rather than a schema error.
    """
    return store.create(str(uuid.uuid4()), submission, clock())


@app.get(
    "/changes/{change_id}",
    response_model=ChangeRecord,
    tags=["changes"],
    responses=NOT_FOUND,
)
def read_change(change_id: str, store: StoreDep) -> ChangeRecord:
    """Read one change record."""
    record = store.get(change_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "not_found"})
    return record


@app.post(
    "/changes/{change_id}/submit",
    response_model=ChangeRecord,
    tags=["changes"],
    responses={
        **NOT_FOUND,
        400: {
            "model": RejectionResponse,
            "description": "The gate refused the submission (REQ-1).",
        },
        409: {
            "model": TransitionErrorResponse,
            "description": "The change is not in Draft (REQ-2).",
        },
    },
)
def submit_change(
    change_id: str,
    store: StoreDep,
    clock: ClockDep,
) -> ChangeRecord:
    """Run REQ-1 against the change and move it to Submitted if it passes.

    A refusal is a 400 carrying every violation, not the first one. A change
    that is not in Draft cannot be submitted, and that is a 409 from REQ-2.
    """
    record = store.get(change_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "not_found"})

    if record.state is not State.DRAFT:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "illegal_transition",
                "rule": "REQ-2",
                "from_state": record.state.value,
                "to_state": State.SUBMITTED.value,
                "allowed": [s.value for s in _allowed_from(record.state)],
            },
        )

    violations = evaluate(record.submission)
    if violations:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "submission_rejected",
                "violations": [v.model_dump() for v in violations],
            },
        )

    return store.set_state(change_id, State.SUBMITTED, clock())


@app.post(
    "/changes/{change_id}/transition",
    response_model=ChangeRecord,
    tags=["changes"],
    responses={
        **NOT_FOUND,
        409: {
            "model": TransitionErrorResponse,
            "description": "The move is not on the lifecycle graph (REQ-2).",
        },
    },
)
def transition_change(
    change_id: str,
    request: TransitionRequest,
    store: StoreDep,
    clock: ClockDep,
) -> ChangeRecord:
    """Move a change along the lifecycle (REQ-2).

    Draft to Submitted is not available here: it goes through `/submit`, so the
    validation cannot be stepped around.
    """
    record = store.get(change_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "not_found"})

    if record.state is State.DRAFT and request.to_state is State.SUBMITTED:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "validation_required",
                "rule": "REQ-1",
                "from_state": record.state.value,
                "to_state": request.to_state.value,
                "allowed": [State.CANCELLED.value],
            },
        )

    try:
        new_state = transition(record.state, request.to_state)
    except IllegalTransition as refused:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "illegal_transition",
                "rule": refused.rule,
                "from_state": refused.from_state.value,
                "to_state": refused.to_state.value,
                "allowed": [s.value for s in refused.allowed],
            },
        ) from refused

    return store.set_state(change_id, new_state, clock())


def _allowed_from(state: State) -> list[State]:
    """States reachable from `state`, for error bodies."""
    return sorted(TRANSITIONS[state])
