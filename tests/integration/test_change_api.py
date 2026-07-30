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
    """The service answers, and names the version it is running.

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
    """Creating a change records it in Draft with the injected timestamp.

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
    """A naive timestamp is a 422, not a 400.

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
    """A field the schema does not declare is refused rather than ignored.

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
    """What was written is what is read.

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
    """Reading a change that does not exist is a 404 with a machine readable
    code.

    Layer: integration
    Covers: none
    Why this layer: status code mapping is an HTTP concern.
    """
    response = client.get("/changes/11111111-2222-3333-4444-555555555555")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


@pytest.mark.endpoint(SUBMIT)
def test_a_valid_submission_is_accepted_and_persisted(client):
    """A submission that passes all seven rules moves to Submitted and stays
    there.

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
    """A refusal is a 400 listing every violation, and the change stays in
    Draft.

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
    """The SPA row of the on call matrix, exercised through the API.

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
    """REQ-1.2 through the API. There is no exemption from BAT.

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
    """Submitting an already submitted change is a 409.

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
    """Submitting a change that does not exist is a 404, not a 400.

    Layer: integration
    Covers: none
    Why this layer: the order of the checks inside the endpoint is only visible
    through it.
    """
    assert client.post("/changes/nope/submit").status_code == 404


@pytest.mark.endpoint(TRANSITION)
def test_the_lifecycle_can_be_walked_end_to_end(client):
    """Draft to Closed through every legal state, one request at a time.

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
    """A scheduled change can still be cancelled.

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
    """Cancelling during implementation is a 409 naming REQ-2.1.

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
    """REQ-2.2 through HTTP, with the refusing rule in the body.

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
    """REQ-2.3 through HTTP: Implementing to Closed is refused, Implementing to
    Rolled Back is allowed.

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
    """Moving a draft straight to Submitted is refused, so REQ-1 cannot be
    skipped.

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
    """A state that does not exist is a 422 from the schema, not a 409 from the
    graph.

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
    """A transition on a change that does not exist is a 404.

    Layer: integration
    Covers: none
    Why this layer: completes the status code matrix for this endpoint.
    """
    response = client.post("/changes/nope/transition", json={"to_state": "approved"})
    assert response.status_code == 404


@pytest.mark.endpoint(CREATE)
def test_two_changes_do_not_share_state(client):
    """Two changes created in the same instance advance independently.

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
    """REGRESSION, run 2 of the demo. The dependency that wires the real store
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
