"""Integration layer: the endpoint, the store and the rules working together.

Deliberately thin. Rule tables are proved at the unit layer, so what is left
here is the behaviour only a running service can show: status codes, persistence
across requests, and the handful of rules that a reviewer will want to see
exercised through HTTP.

Every case carries an `endpoint` marker. `tests/meta/test_endpoint_coverage.py`
fails the build if a documented endpoint has no marked case, or if a case claims
an endpoint the spec does not document.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from tests.factories import PINNED_NOW, on_call_entry, valid_payload

CREATE = "POST /changes"
READ = "GET /changes/{change_id}"
SUBMIT = "POST /changes/{change_id}/submit"
TRANSITION = "POST /changes/{change_id}/transition"
HEALTH = "GET /healthz"


def create(client, **overrides) -> str:
    """Create a change and return its ID."""
    response = client.post("/changes", json=valid_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def advance(client, change_id: str, *states: str) -> None:
    """Walk a change forward through the given states, asserting each move."""
    for state in states:
        response = client.post(f"/changes/{change_id}/transition", json={"to_state": state})
        assert response.status_code == 200, response.text


@pytest.mark.endpoint(HEALTH)
def test_health_reports_the_running_version(client):
    """Health check on a running service.

    The service answers, and names the version it is running.

    Case: API-29
    Expects: 200
    Priority: Critical
    Type: Smoke
    Preconditions: The service is running.
    Steps: 1. Request GET /healthz.
    Expected result: The service returns 200 with a status of ok and the version it is
        running.
    Layer: integration
    Covers: none
    Why this layer: liveness is a property of the process. There is nothing to
    unit test here, and the pipeline waits on this endpoint before running the
    suite against a fresh instance.
    """
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["version"]


@pytest.mark.endpoint(CREATE)
def test_a_new_change_is_created_in_draft(client):
    """Create a change request with a complete submission.

    Creating a change records it in Draft with the injected timestamp.

    Case: API-20
    Expects: 201
    Priority: Critical
    Type: Smoke
    Preconditions: The service is running.
    Steps: 1. POST /changes with a complete submission body.
    Expected result: The service returns 201 with the change record, an identifier, and
        a state of draft.
    Layer: integration
    Covers: REQ-2
    Why this layer: the record is written by the store and read back through the
    endpoint. The pinned clock means `created_at` is asserted rather than
    ignored.
    """
    response = client.post("/changes", json=valid_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "draft"
    assert datetime.fromisoformat(body["created_at"]) == PINNED_NOW
    assert datetime.fromisoformat(body["updated_at"]) == PINNED_NOW


@pytest.mark.endpoint(CREATE)
def test_a_malformed_payload_is_a_schema_error_not_a_refusal(client):
    """Submit a change with a timestamp that has no timezone.

    A naive timestamp is a 422, not a 400.

    Case: API-19
    Expects: 422
    Priority: High
    Type: Functional
    Preconditions: The service is running.
    Steps: 1. POST /changes with a complete submission body, but give
        implementation_start a timestamp with no timezone.
    Expected result: The service returns 422 rather than 400, because the request could
        not be read at all rather than being read and refused by a rule.
    Layer: integration
    Covers: none
    Why this layer: the distinction between "I could not read this" and "I read
    it and the gate says no" only exists at the HTTP boundary. See
    `docs/decisions/0002-status-codes.md`.
    """
    payload = valid_payload(implementation_start="2026-08-01T22:00:00")
    assert client.post("/changes", json=payload).status_code == 422


@pytest.mark.endpoint(CREATE)
def test_an_unknown_field_is_rejected_by_the_schema(client):
    """Submit a change with a field the API does not define.

    A field the schema does not declare is refused rather than ignored.

    Case: API-26
    Expects: 422
    Priority: High
    Type: Functional
    Preconditions: The service is running.
    Steps: 1. POST /changes with a complete submission body and one extra field the API
        does not define, such as approved_by.
    Expected result: The service returns 422 and refuses the request, rather than
        accepting it and silently dropping the field.
    Layer: integration
    Covers: none
    Why this layer: silently dropping an unknown field is how a submitter comes
    to believe they supplied evidence they did not supply.
    """
    payload = valid_payload()
    payload["approved_by"] = "someone"
    assert client.post("/changes", json=payload).status_code == 422


@pytest.mark.endpoint(READ)
def test_a_change_can_be_read_back(client):
    """Read back a change that was just created.

    What was written is what is read.

    Case: API-15
    Expects: 200
    Priority: Critical
    Type: Smoke
    Preconditions: The service is running.
    Steps: 1. POST /changes with a complete submission body and note the identifier
        returned. 2. Request GET /changes/{id} with that identifier.
    Expected result: The read returns 200 and the record carries the same submission
        that was sent, so what was written is what is read.
    Layer: integration
    Covers: REQ-2
    Why this layer: persistence across two requests is invisible to a unit test.
    """
    change_id = create(client)
    body = client.get(f"/changes/{change_id}").json()
    assert body["id"] == change_id
    assert body["submission"]["scrum_team"] == "payments"


@pytest.mark.endpoint(READ)
def test_an_unknown_change_is_a_404(client):
    """Read a change that does not exist.

    Reading a change that does not exist is a 404 with a machine readable code.

    Case: API-25
    Expects: 404
    Priority: High
    Type: Functional
    Preconditions: The service is running. No change exists with the identifier used
        below.
    Steps: 1. Request GET /changes/ with an identifier that was never created.
    Expected result: The service returns 404 with a machine readable code of not_found.
    Layer: integration
    Covers: none
    Why this layer: status code mapping is an HTTP concern.
    """
    response = client.get("/changes/11111111-2222-3333-4444-555555555555")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


@pytest.mark.endpoint(SUBMIT)
def test_a_valid_submission_is_accepted_and_persisted(client):
    """Submit a change that meets every gate rule.

    A submission that passes all seven rules moves to Submitted and stays there.

    Case: API-23
    Expects: 200
    Priority: Critical
    Type: Smoke
    Preconditions: The service is running. A submission meets every gate rule.
    Steps: 1. POST /changes with a complete submission body. 2. Submit the change. 3.
        Read the change back.
    Expected result: The submission is accepted with 200 and the change reads back as
        submitted.
    Layer: integration
    Covers: REQ-1, REQ-2
    Why this layer: the happy path end to end, which is the case a reviewer
    reads first.
    """
    change_id = create(client)
    assert client.post(f"/changes/{change_id}/submit").status_code == 200
    assert client.get(f"/changes/{change_id}").json()["state"] == "submitted"


@pytest.mark.endpoint(SUBMIT)
def test_a_refused_submission_names_every_rule_it_broke(client):
    """Submit a change that breaks three gate rules at once.

    A refusal is a 400 listing every violation, and the change stays in Draft.

    Case: API-21
    Expects: 200
    Priority: Critical
    Type: Functional
    Preconditions: The service is running. A submission is missing its rollback plan,
        its Jira ticket and all testing evidence.
    Steps: 1. POST /changes with those three things missing. 2. Submit the change. 3.
        Read the change back.
    Expected result: The submission is refused with 400 listing all three violations at
        once, and the change reads back still in draft rather than advanced.
    Layer: integration
    Covers: REQ-1
    Why this layer: the rule set is proved at the unit layer. What is proved
    here is that the refusal reaches the caller intact and that a refused change
    is not quietly advanced.
    """
    change_id = create(client, rollback_plan=None, jira_ticket=None, test_evidence=[])
    response = client.post(f"/changes/{change_id}/submit")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "submission_rejected"
    assert {v["rule"] for v in detail["violations"]} == {
        "REQ-1.1",
        "REQ-1.2",
        "REQ-1.4",
    }
    assert client.get(f"/changes/{change_id}").json()["state"] == "draft"


@pytest.mark.endpoint(SUBMIT)
def test_a_spa_release_without_prod_support_is_accepted(client):
    """Submit a single page app release with no Prod Support on call.

    The SPA row of the on call matrix, exercised through the API.

    Case: API-22
    Expects: 200
    Priority: Critical
    Type: Functional
    Preconditions: The service is running. The release type is a single page app with
        DevOps and Tech Lead on call and no Prod Support.
    Steps: 1. POST /changes declaring release type spa with only those two roles on
        call. 2. Submit the change.
    Expected result: The submission is accepted with 200, because the on call matrix
        does not require Prod Support for a single page app release.
    Layer: integration
    Covers: REQ-1.6
    Why this layer: duplicated from the unit layer on purpose. It is the row a
    lazy implementation gets wrong, and it is worth having the proof at the
    layer a reviewer reads.
    """
    change_id = create(
        client,
        release_type="spa",
        on_call=[on_call_entry("devops"), on_call_entry("tech_lead")],
    )
    assert client.post(f"/changes/{change_id}/submit").status_code == 200


@pytest.mark.endpoint(SUBMIT)
def test_a_change_missing_bat_evidence_is_refused(client):
    """Submit a change with no BAT test evidence.

    REQ-1.2 through the API. There is no exemption from BAT.

    Case: API-18
    Expects: 400
    Priority: Critical
    Type: Functional
    Preconditions: The service is running. Testing evidence is available for dev and QA
        but not for BAT.
    Steps: 1. POST /changes with evidence for dev and QA only. 2. Submit the change.
    Expected result: The submission is refused with 400 and the violation names
        REQ-1.2, because evidence in all three environments is required.
    Layer: integration
    Covers: REQ-1.2
    Why this layer: proves the endpoint actually reaches this rule rather than
    short circuiting on an earlier one, which the unit layer cannot see.
    """
    change_id = create(
        client,
        test_evidence=[
            {"environment": "dev", "passed": True, "reference": "run-1"},
            {"environment": "qa", "passed": True, "reference": "run-2"},
        ],
    )
    response = client.post(f"/changes/{change_id}/submit")
    assert response.status_code == 400
    assert any(v["rule"] == "REQ-1.2" for v in response.json()["detail"]["violations"])


@pytest.mark.endpoint(SUBMIT)
def test_a_change_cannot_be_submitted_twice(client):
    """Submit the same change twice.

    Submitting an already submitted change is a 409.

    Case: API-17
    Expects: 409
    Priority: High
    Type: Functional
    Preconditions: The service is running. A change request has been created and
        submitted once.
    Steps: 1. Create a change with a complete submission body. 2. Submit it and confirm
        it is accepted. 3. Submit the same change a second time.
    Expected result: The second submission is refused with 409, because the change is
        no longer in Draft.
    Layer: integration
    Covers: REQ-2
    Why this layer: needs a stored state from a previous request.
    """
    change_id = create(client)
    assert client.post(f"/changes/{change_id}/submit").status_code == 200
    response = client.post(f"/changes/{change_id}/submit")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "illegal_transition"


@pytest.mark.endpoint(SUBMIT)
def test_submitting_an_unknown_change_is_a_404(client):
    """Submit a change that does not exist.

    Submitting a change that does not exist is a 404, not a 400.

    Case: API-30
    Expects: 404
    Priority: High
    Type: Functional
    Preconditions: The service is running. No change exists with the identifier used
        below.
    Steps: 1. POST /changes/{id}/submit using an identifier that was never created.
    Expected result: The service returns 404 rather than attempting to validate a
        change that does not exist.
    Layer: integration
    Covers: none
    Why this layer: the order of the checks inside the endpoint is only visible
    through it.
    """
    assert client.post("/changes/nope/submit").status_code == 404


@pytest.mark.endpoint(TRANSITION)
def test_the_lifecycle_can_be_walked_end_to_end(client):
    """Walk a change through every state from Draft to Closed.

    Draft to Closed through every legal state, one request at a time.

    Case: API-31
    Expects: 200
    Priority: Critical
    Type: Functional
    Preconditions: The service is running. A submission meets every gate rule.
    Steps: 1. Create a change and submit it. 2. Transition it in turn to Approved,
        Scheduled, Implementing, Verified and Closed.
    Expected result: Every transition returns 200 and the change ends in closed, with
        each state persisted so the next request sees what the previous one wrote.
    Layer: integration
    Covers: REQ-2
    Why this layer: the graph is proved at the unit layer. This proves each move
    is persisted, so the next request sees the state the previous one wrote.
    """
    change_id = create(client)
    assert client.post(f"/changes/{change_id}/submit").status_code == 200
    advance(client, change_id, "approved", "scheduled", "implementing", "verified")
    response = client.post(f"/changes/{change_id}/transition", json={"to_state": "closed"})
    assert response.status_code == 200
    assert response.json()["state"] == "closed"
    assert datetime.fromisoformat(response.json()["updated_at"]) == PINNED_NOW


@pytest.mark.endpoint(TRANSITION)
def test_a_change_can_be_cancelled_before_implementing(client):
    """Cancel a scheduled change before implementation starts.

    A scheduled change can still be cancelled.

    Case: API-14
    Expects: 200
    Priority: High
    Type: Functional
    Preconditions: The service is running. A change request has been created and
        submitted.
    Steps: 1. Create a change and submit it. 2. Transition it to Approved. 3.
        Transition it to Scheduled. 4. Transition it to Cancelled. 5. Read the change
        back.
    Expected result: Each transition returns 200 and the change reads back as
        cancelled, because cancellation is allowed at any point before implementation
        starts.
    Layer: integration
    Covers: REQ-2.1
    Why this layer: the positive half of REQ-2.1 through HTTP, beside its
    negative twin below.
    """
    change_id = create(client)
    client.post(f"/changes/{change_id}/submit")
    advance(client, change_id, "approved", "scheduled", "cancelled")
    assert client.get(f"/changes/{change_id}").json()["state"] == "cancelled"


@pytest.mark.endpoint(TRANSITION)
def test_a_change_cannot_be_cancelled_once_implementing(client):
    """Cancel a change after implementation has started.

    Cancelling during implementation is a 409 naming REQ-2.1.

    Case: API-16
    Expects: 409
    Priority: High
    Type: Functional
    Preconditions: The service is running. A change request has reached Implementing.
    Steps: 1. Create a change, submit it, and transition it through Approved and
        Scheduled to Implementing. 2. Request a transition to Cancelled.
    Expected result: The transition is refused with 409 naming REQ-2.1, because a
        change cannot be cancelled once implementation has started.
    Layer: integration
    Covers: REQ-2.1
    Why this layer: the negative half, and it asserts the rule ID a caller would
    act on.
    """
    change_id = create(client)
    client.post(f"/changes/{change_id}/submit")
    advance(client, change_id, "approved", "scheduled", "implementing")
    response = client.post(
        f"/changes/{change_id}/transition", json={"to_state": "cancelled"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["rule"] == "REQ-2.1"


@pytest.mark.endpoint(TRANSITION)
def test_an_implementing_change_cannot_return_to_approved(client):
    """Move a change backwards from Implementing to Approved.

    REQ-2.2 through HTTP, with the refusing rule in the body.

    Case: API-24
    Expects: 409
    Priority: High
    Type: Functional
    Preconditions: The service is running. A change request has reached Implementing.
    Steps: 1. Create a change, submit it, and transition it through Approved and
        Scheduled to Implementing. 2. Request a transition back to Approved.
    Expected result: The transition is refused with 409 naming REQ-2.2, because there
        is no route back once implementation has started.
    Layer: integration
    Covers: REQ-2.2
    Why this layer: named in the requirements, so a reviewer will look for it at
    the layer they can run by hand.
    """
    change_id = create(client)
    client.post(f"/changes/{change_id}/submit")
    advance(client, change_id, "approved", "scheduled", "implementing")
    response = client.post(
        f"/changes/{change_id}/transition", json={"to_state": "approved"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["rule"] == "REQ-2.2"


@pytest.mark.endpoint(TRANSITION)
def test_failed_verification_cannot_close_without_rolling_back(client):
    """Close a change straight from Implementing without rolling back.

    REQ-2.3 through HTTP: Implementing to Closed is refused, Implementing to
    Rolled Back is allowed.

    Case: API-28
    Expects: 200
    Priority: High
    Type: Functional
    Preconditions: The service is running. A change request has reached Implementing.
    Steps: 1. Create a change, submit it, and transition it through Approved and
        Scheduled to Implementing. 2. Request a transition straight to Closed. 3.
        Request a transition to Rolled Back.
    Expected result: The move to Closed is refused with 409 naming REQ-2.3, and the
        move to Rolled Back is accepted with 200, because failed verification rolls
        back rather than closing.
    Layer: integration
    Covers: REQ-2.3
    Why this layer: both halves in one case because the second move is what
    makes the first refusal meaningful rather than a dead end.
    """
    change_id = create(client)
    client.post(f"/changes/{change_id}/submit")
    advance(client, change_id, "approved", "scheduled", "implementing")
    refused = client.post(f"/changes/{change_id}/transition", json={"to_state": "closed"})
    assert refused.status_code == 409
    assert refused.json()["detail"]["rule"] == "REQ-2.3"
    advance(client, change_id, "rolled_back")


@pytest.mark.endpoint(TRANSITION)
def test_validation_cannot_be_stepped_around_with_a_transition(client):
    """Move a draft straight to Submitted, bypassing the gate rules.

    Moving a draft straight to Submitted is refused, so REQ-1 cannot be skipped.

    Case: API-34
    Expects: 200
    Priority: Critical
    Type: Functional
    Preconditions: The service is running. A change request exists in Draft with no
        rollback plan.
    Steps: 1. Create a change with no rollback plan. 2. Request a transition straight
        to Submitted, bypassing the submit endpoint. 3. Read the change back.
    Expected result: The transition is refused with 409 and a code of
        validation_required, and the change reads back still in draft, so the gate
        rules cannot be stepped around.
    Layer: integration
    Covers: REQ-1, REQ-2
    Why this layer: this is a hole in the interface rather than in the rules.
    Only a request can prove the hole is closed.
    """
    change_id = create(client, rollback_plan=None)
    response = client.post(
        f"/changes/{change_id}/transition", json={"to_state": "submitted"}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "validation_required"
    assert client.get(f"/changes/{change_id}").json()["state"] == "draft"


@pytest.mark.endpoint(TRANSITION)
def test_an_unknown_target_state_is_a_schema_error(client):
    """Request a transition to a state the API does not define.

    A state that does not exist is a 422 from the schema, not a 409 from the graph.

    Case: API-27
    Expects: 422
    Priority: High
    Type: Functional
    Preconditions: The service is running. A change request exists in Draft.
    Steps: 1. Create a change. 2. Request a transition to a state the API does not
        define, such as shipped.
    Expected result: The service returns 422 from the schema rather than 409 from the
        lifecycle, because the value is not a state at all.
    Layer: integration
    Covers: none
    Why this layer: which layer refuses the value is an interface decision, and
    it is asserted so a later change cannot quietly turn it into a 409.
    """
    change_id = create(client)
    response = client.post(f"/changes/{change_id}/transition", json={"to_state": "shipped"})
    assert response.status_code == 422


@pytest.mark.endpoint(TRANSITION)
def test_transitioning_an_unknown_change_is_a_404(client):
    """Request a transition on a change that does not exist.

    A transition on a change that does not exist is a 404.

    Case: API-32
    Expects: 404
    Priority: High
    Type: Functional
    Preconditions: The service is running. No change exists with the identifier used
        below.
    Steps: 1. POST /changes/{id}/transition using an identifier that was never created.
    Expected result: The service returns 404.
    Layer: integration
    Covers: none
    Why this layer: completes the status code matrix for this endpoint.
    """
    response = client.post("/changes/nope/transition", json={"to_state": "approved"})
    assert response.status_code == 404


@pytest.mark.endpoint(CREATE)
def test_two_changes_do_not_share_state(client):
    """Advance one change and confirm a second is unaffected.

    Two changes created in the same instance advance independently.

    Case: API-33
    Expects: 200
    Priority: High
    Type: Functional
    Preconditions: The service is running.
    Steps: 1. Create two separate change requests. 2. Submit the first one only. 3.
        Read both back.
    Expected result: The first reads back as submitted and the second as draft, so the
        two records do not share state.
    Layer: integration
    Covers: REQ-2
    Why this layer: shared state between records is a storage defect, and it
    only shows up with more than one record in play.
    """
    first = create(client)
    second = create(client)
    assert first != second
    client.post(f"/changes/{first}/submit")
    assert client.get(f"/changes/{first}").json()["state"] == "submitted"
    assert client.get(f"/changes/{second}").json()["state"] == "draft"


@pytest.mark.endpoint(CREATE)
def test_the_real_store_wiring_opens_a_usable_database(tmp_path, monkeypatch):
    """Create and read a change against the database the service configures.

    REGRESSION, run 2 of the demo. The dependency that wires the real store
    honours the configured database path and opens something usable.

    Every other case in this suite injects its own store, so `get_store` was
    executed by nothing. A change to it passed the whole gate and broke the
    first request against a served instance. This is the case that would have
    caught it.

    It builds the application without the store override, which is what makes it
    the only case here that exercises the production wiring.

    Layer: integration
    Covers: none
    Why this layer: the defect was in dependency wiring, which does not exist
    until the application is assembled and asked for a store. A unit test of
    `Store` passes with this defect present, because `Store` was never the
    broken part. Only a request through the assembled application shows it.
    """
    from app.main import app as real_app  # noqa: PLC0415 - deliberate, see below
    from app.main import get_clock, get_store  # noqa: PLC0415

    monkeypatch.setenv("RELEASE_GATE_DB", str(tmp_path / "wired.db"))
    monkeypatch.setattr("app.main._store", None)
    real_app.dependency_overrides.pop(get_store, None)
    real_app.dependency_overrides[get_clock] = lambda: lambda: PINNED_NOW

    try:
        with TestClient(real_app) as wired:
            response = wired.post("/changes", json=valid_payload())
            assert response.status_code == 201, response.text
            change_id = response.json()["id"]
            assert wired.get(f"/changes/{change_id}").status_code == 200
    finally:
        real_app.dependency_overrides.clear()

    assert (tmp_path / "wired.db").exists(), (
        "the configured database path was not the one used"
    )


@pytest.mark.endpoint(CREATE)
def test_a_database_failure_surfaces_as_a_500(caller_client, store):
    """Create a change while the database is unavailable.

    A change cannot be recorded when the database is unavailable, and the
    service says so with a 500 rather than reporting success.

    This is the error path nobody writes a case for. A service that swallows a
    storage failure and answers 201 has told the caller their change is
    recorded when it is not, and every downstream check inherits that lie.

    Case: API-35
    Expects: 500
    Priority: Critical
    Type: Functional
    Preconditions: The service is running. The database it writes to is unavailable.
    Steps: 1. Make the database unavailable to the running service. 2. POST /changes
        with a complete submission body.
    Expected result: The service returns 500 rather than reporting success, so a caller
        is never told a change was recorded when it was not.
    Layer: integration
    Covers: none
    Why this layer: the status code is produced by the framework's handling of
    an unhandled failure at the boundary, which does not exist until a request
    is served. A unit test can prove the store raises. Only a request can prove
    what the caller is told when it does.
    """
    store.close()
    response = caller_client.post("/changes", json=valid_payload())
    assert response.status_code == 500


@pytest.mark.endpoint(SUBMIT)
@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEF-002: the gate accepts an implementation window that ends before it "
        "starts. Deferred to 0.2.0. Strict, so this fails the build if the "
        "defect is fixed and nobody updates the report."
    ),
)
def test_an_implementation_window_that_ends_before_it_starts_is_refused(client):
    """Submit a change whose implementation window ends before it starts.

    This case fails today. It is tracked as DEF-002, deferred to 0.2.0, and
    marked as an expected failure rather than deleted or skipped. It still runs
    on every build and it still makes a real request.

    Case: API-36
    Expects: 400
    Priority: High
    Type: Functional
    Preconditions: The service is running. A submission carries an implementation
        window that ends before it starts.
    Steps: 1. POST /changes with implementation_start set four hours after
        implementation_end. 2. Submit the change.
    Expected result: The submission is refused with 400 naming the reversed window.
        This case currently fails: the gate accepts it and returns 200. Tracked as
        DEF-002 and deferred to 0.2.0.
    Layer: integration
    Covers: REQ-1
    Why this layer: the window is two fields that are individually valid and
    only wrong when compared, so the check belongs where a submission is
    assembled and judged as a whole.
    """
    change_id = create(
        client,
        implementation_start="2026-08-02T02:00:00+00:00",
        implementation_end="2026-08-01T22:00:00+00:00",
    )
    response = client.post(f"/changes/{change_id}/submit")
    assert response.status_code == 400, (
        "a change cannot be implemented before it starts, and the gate accepted it"
    )
