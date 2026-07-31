"""Contract layer: does the published description of this service tell the
truth about what it returns.

Integration asks whether the endpoint behaves. This layer asks whether the
OpenAPI document a consumer would code against matches the bytes on the wire.
A service can pass every integration case while publishing a spec that lies,
and consumers read the spec.

Every model in `app/models.py` sets `extra="forbid"`, which becomes
`additionalProperties: false` in the schema. That is what makes the check work
in both directions: a response carrying a field the spec does not declare fails
validation here, not just a response missing one.
"""

from __future__ import annotations

import jsonschema
import pytest

from app.domain import SERVICE_VERSION
from tests.factories import valid_payload


def schema_for(openapi: dict, path: str, method: str, status: str) -> dict:
    """The response schema the spec declares, ready for validation.

    `components` is carried along so that internal `$ref` pointers resolve
    against the document they came from.
    """
    operation = openapi["paths"][path][method]
    content = operation["responses"][status]["content"]["application/json"]
    return {**content["schema"], "components": openapi["components"]}


def assert_matches(openapi: dict, path: str, method: str, status: str, body) -> None:
    """Fail with the offending field named, rather than with a bare False."""
    jsonschema.validate(instance=body, schema=schema_for(openapi, path, method, status))


def created_change(client, **overrides) -> dict:
    """Create a change and return the response body."""
    response = client.post("/changes", json=valid_payload(**overrides))
    assert response.status_code == 201
    return response.json()


def test_the_service_publishes_an_openapi_document(openapi):
    """Confirm the service publishes a spec a consumer can code against.

    The spec is served by the application, generated from the code.

    Case: API-13
    Expects: 200
    Priority: Medium
    Type: Functional
    Preconditions: The service is running.
    Steps: 1. Request GET /openapi.json. 2. Read the OpenAPI version and the service
        title.
    Expected result: The service returns 200 and publishes an OpenAPI 3.1 document
        titled Release Gate API.
    Layer: contract
    Covers: none
    Why this layer: the spec is the artifact this layer validates against, so
    its existence is this layer's first assertion. No file in the repository is
    hand maintained to make this pass.
    """
    assert openapi["openapi"].startswith("3.1")
    assert openapi["info"]["title"] == "Release Gate API"


def test_the_published_version_matches_the_service_version(openapi):
    """Confirm the spec version matches the version the service is running.

    The version in the spec is the version the service reports at /healthz.

    Case: API-12
    Expects: 200
    Priority: Medium
    Type: Functional
    Preconditions: The service is running.
    Steps: 1. Request GET /openapi.json and read the version in the document. 2.
        Compare it with the version the service reports.
    Expected result: The document returns 200 and the version in it matches the version
        the service runs, so the published description cannot drift from the build.
    Layer: contract
    Covers: none
    Why this layer: two published values that must agree. A drift here is
    exactly the class of defect this layer exists to catch.
    """
    assert openapi["info"]["version"] == SERVICE_VERSION


def test_health_response_matches_the_documented_schema(client, openapi):
    """Confirm the health response matches what the spec promises.

    /healthz returns what the spec says it returns.

    Case: API-05
    Expects: 200
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json and read the schema for the health response. 2.
        Request GET /healthz. 3. Validate the response against that schema.
    Expected result: The health endpoint returns 200 and the body matches the published
        schema.
    Layer: contract
    Covers: none
    Why this layer: the endpoint a deployment check calls is the one most likely
    to be changed without updating anything else.
    """
    response = client.get("/healthz")
    assert response.status_code == 200
    assert_matches(openapi, "/healthz", "get", "200", response.json())


def test_created_change_matches_the_documented_schema(client, openapi):
    """Confirm a created change matches what the spec promises.

    The 201 body validates against the declared ChangeRecord schema.

    Case: API-02
    Expects: 201
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. POST /changes with a complete submission
        body. 3. Validate the returned record against the schema the document declares
        for a 201 response.
    Expected result: The service returns 201 and the record matches the published
        schema field for field.
    Layer: contract
    Covers: REQ-2
    Why this layer: the record and its state are what every consumer reads.
    """
    assert_matches(openapi, "/changes", "post", "201", created_change(client))


def test_read_change_matches_the_documented_schema(client, openapi):
    """Confirm a change read back matches what the spec promises.

    The 200 body from a read validates against the declared schema.

    Case: API-08
    Expects: 200
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. POST /changes with a complete submission
        body. 3. Read the change back with GET /changes/{id}. 4. Validate the response
        against the published schema.
    Expected result: The read returns 200 and the record matches the published schema,
        which is a different code path from the one that created it.
    Layer: contract
    Covers: REQ-2
    Why this layer: create and read serialise the same model through different
    code paths, so both are checked rather than assumed identical.
    """
    change = created_change(client)
    response = client.get(f"/changes/{change['id']}")
    assert response.status_code == 200
    assert_matches(openapi, "/changes/{change_id}", "get", "200", response.json())


def test_submitted_change_matches_the_documented_schema(client, openapi):
    """Confirm an accepted submission matches what the spec promises.

    The 200 body from a successful submission validates.

    Case: API-11
    Expects: 200
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. POST /changes with a complete submission
        body. 3. Submit it. 4. Validate the returned record against the published
        schema.
    Expected result: The submission is accepted with 200 and the record matches the
        published schema.
    Layer: contract
    Covers: REQ-1, REQ-2
    Why this layer: the success path of the endpoint that carries the gate
    decision.
    """
    change = created_change(client)
    response = client.post(f"/changes/{change['id']}/submit")
    assert response.status_code == 200
    assert_matches(openapi, "/changes/{change_id}/submit", "post", "200", response.json())


def test_rejection_body_matches_the_documented_schema(client, openapi):
    """Confirm a refused submission matches what the spec promises.

    A refusal is described by the spec, not just returned by the code.

    Case: API-09
    Expects: 400
    Priority: High
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. POST /changes with a submission that has no
        rollback plan and no Jira ticket. 3. Submit it. 4. Validate the refusal body
        against the schema declared for a 400.
    Expected result: The submission is refused with 400 and the refusal body matches
        the published schema, so a consumer can read the violations programmatically.
    Layer: contract
    Covers: REQ-1
    Why this layer: a consumer writing error handling reads the 400 schema. If
    refusals were undocumented, the consumer would be coding against a guess.
    """
    change = created_change(client, rollback_plan=None, jira_ticket=None)
    response = client.post(f"/changes/{change['id']}/submit")
    assert response.status_code == 400
    assert_matches(openapi, "/changes/{change_id}/submit", "post", "400", response.json())


def test_illegal_transition_body_matches_the_documented_schema(client, openapi):
    """Confirm a refused transition matches what the spec promises.

    A 409 carries the rule, both states and the legal alternatives, exactly as documented.

    Case: API-06
    Expects: 409
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. POST /changes to create a change in Draft.
        3. Request a transition straight to Closed. 4. Validate the refusal body
        against the schema declared for a 409.
    Expected result: The transition is refused with 409 and the refusal body matches
        the published schema, including the rule and the states involved.
    Layer: contract
    Covers: REQ-2
    Why this layer: the 409 body is the machine readable part of the state
    machine, and its shape is a promise to callers.
    """
    change = created_change(client)
    response = client.post(
        f"/changes/{change['id']}/transition", json={"to_state": "closed"}
    )
    assert response.status_code == 409
    assert_matches(
        openapi, "/changes/{change_id}/transition", "post", "409", response.json()
    )


def test_not_found_body_matches_the_documented_schema(client, openapi):
    """Confirm a not found response matches what the spec promises.

    A 404 body is documented too.

    Case: API-07
    Expects: 404
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. Request GET /changes/does-not-exist. 3.
        Validate the response against the schema declared for a 404.
    Expected result: The service returns 404 and the body matches the published schema.
    Layer: contract
    Covers: none
    Why this layer: the cheapest error to leave undocumented, and the one a
    consumer hits first.
    """
    response = client.get("/changes/does-not-exist")
    assert response.status_code == 404
    assert_matches(openapi, "/changes/{change_id}", "get", "404", response.json())


def test_schema_error_body_matches_the_documented_schema(client, openapi):
    """Confirm a malformed request error matches what the spec promises.

    A malformed payload returns the framework's documented 422 shape.

    Case: API-10
    Expects: 422
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. POST /changes with a body that is missing
        most required fields. 3. Validate the error against the schema declared for a
        422.
    Expected result: The service returns 422 and the body matches the published schema
        for a validation error.
    Layer: contract
    Covers: none
    Why this layer: 422 and 400 mean different things in this service (see
    `docs/decisions/0002-status-codes.md`), so the 422 shape is pinned here to
    keep the distinction visible.
    """
    response = client.post("/changes", json={"title": "no other fields"})
    assert response.status_code == 422
    assert_matches(openapi, "/changes", "post", "422", response.json())


def test_a_response_carrying_an_undocumented_field_would_fail(client, openapi):
    """Confirm a response with an undeclared field is caught as a contract break.

    The check runs in both directions: an extra field is a contract break.

    Case: API-01
    Expects: 201
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json and read the schema for a created change. 2.
        POST /changes with a complete submission body. 3. Add a field to the returned
        record that the schema does not declare. 4. Validate the altered record against
        the schema.
    Expected result: The altered record fails validation with 201 recorded for the
        original response, proving the schema refuses fields it does not declare.
    Layer: contract
    Covers: none
    Why this layer: proves the validator is not permissive. Without this, every
    other case in this file could pass against a schema that allows anything.
    """
    body = created_change(client)
    body["undocumented_field"] = "surprise"
    with pytest.raises(jsonschema.ValidationError):
        assert_matches(openapi, "/changes", "post", "201", body)


def test_every_operation_declares_a_summary(openapi):
    """Confirm every operation the spec lists is named.

    Every documented operation carries a summary, taken from its docstring.

    Case: API-04
    Expects: 200
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. Read every documented operation. 3. Check
        each one carries a summary.
    Expected result: The document returns 200 and no operation is unnamed.
    Layer: contract
    Covers: none
    Why this layer: a spec whose operations are unnamed is technically valid and
    practically useless, and nothing else in the suite would notice.
    """
    missing = [
        f"{method.upper()} {path}"
        for path, operations in openapi["paths"].items()
        for method, operation in operations.items()
        if not operation.get("summary")
    ]
    assert missing == []


def test_every_error_response_declares_a_schema(openapi):
    """Confirm every error the spec lists describes the body it returns.

    Every 4xx the spec lists has a body schema attached.

    Case: API-03
    Expects: 200
    Priority: Medium
    Type: Functional
    Preconditions: The service is running and publishes its OpenAPI document.
    Steps: 1. Request GET /openapi.json. 2. List every response in the 400 and 500
        ranges that the document declares. 3. Check each one names a body schema.
    Expected result: The document returns 200 and every declared error response carries
        a body schema, so a consumer can write error handling against it.
    Layer: contract
    Covers: none
    Why this layer: a documented status code with no documented body is the
    half finished state this layer is for.
    """
    undescribed = [
        f"{method.upper()} {path} {status}"
        for path, operations in openapi["paths"].items()
        for method, operation in operations.items()
        for status, response in operation["responses"].items()
        if status.startswith("4") and "content" not in response
    ]
    assert undescribed == []
