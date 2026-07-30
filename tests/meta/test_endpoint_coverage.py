"""Meta layer: endpoint coverage, in both directions.

A documented endpoint with no integration case fails the build. An integration
case claiming an endpoint the spec does not document fails it too. The second
direction is the one that catches a test left behind after an endpoint is
renamed.
"""

from __future__ import annotations

from app.main import app
from tools import traceability


def documented_endpoints() -> set[str]:
    """Every operation in the generated OpenAPI document."""
    spec = app.openapi()
    return {
        f"{method.upper()} {path}"
        for path, operations in spec["paths"].items()
        for method in operations
    }


DOCUMENTED = documented_endpoints()
CLAIMED = traceability.claimed_endpoints()


def test_the_spec_declares_endpoints():
    """The spec was read and it has operations in it.

    Layer: meta
    Covers: none
    Why this layer: both checks below compare sets, and two empty sets are
    equal. This is what stops that from counting as a pass.
    """
    assert len(DOCUMENTED) >= 5
    assert "GET /healthz" in DOCUMENTED


def test_every_documented_endpoint_has_an_integration_test():
    """No endpoint ships untested through HTTP.

    Layer: meta
    Covers: none
    Why this layer: it compares the generated spec against the markers on the
    suite, which is a property of the repository rather than of a request.
    """
    untested = sorted(DOCUMENTED - set(CLAIMED))
    assert untested == [], f"documented endpoints with no integration test: {untested}"


def test_no_test_claims_an_endpoint_the_spec_does_not_document():
    """The reverse direction, which catches a renamed route.

    Layer: meta
    Covers: none
    Why this layer: same comparison, other way round. A test left pointing at a
    dead path would otherwise keep passing against a 404.
    """
    unknown = sorted(set(CLAIMED) - DOCUMENTED)
    assert unknown == [], f"tests claim undocumented endpoints: {unknown}"


def test_the_gate_endpoints_carry_more_than_one_case():
    """The two endpoints that carry the gate decision are not covered by a
    single case each.

    Layer: meta
    Covers: none
    Why this layer: a coverage count is a property of the suite. One case per
    endpoint satisfies the check above while proving very little, and this is
    the check that says so.
    """
    for endpoint in (
        "POST /changes/{change_id}/submit",
        "POST /changes/{change_id}/transition",
    ):
        assert len(CLAIMED[endpoint]) >= 3, endpoint
