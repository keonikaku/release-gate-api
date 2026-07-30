"""Shared fixtures, the rule that assigns every test its layer, and the capture
that turns a run into evidence.

Layer markers are applied from the directory a test lives in, so a test cannot
be filed under the wrong layer by forgetting a decorator. The docstring still
has to say the layer out loud, and `tests/meta/test_layer_declarations.py` fails
the build when the two disagree.

**Evidence capture is off unless asked for.** Setting `RELEASE_GATE_EVIDENCE` to
a directory makes every test that uses the `client` fixture record what it sent,
what came back, what it claims to cover and whether it passed. CI sets it. A
local `pytest` writes nothing, so the fast path stays fast and evidence only
ever comes from a run someone asked to keep.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.clock import fixed_clock
from app.main import app, get_clock, get_store
from app.store import Store
from tests.factories import PINNED_NOW
from tools.evidence import CAPTURE_ENV, CapturedCase, Exchange, write

LAYER_DIRECTORIES = {
    "unit": "unit",
    "contract": "contract",
    "integration": "integration",
    "meta": "meta",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTCOME_KEY = pytest.StashKey[str]()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test with the layer of the directory it lives in."""
    for item in items:
        parts = Path(str(item.fspath)).parts
        for directory, marker in LAYER_DIRECTORIES.items():
            if directory in parts:
                item.add_marker(getattr(pytest.mark, marker))
                break


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Remember what pytest decided, so captured evidence records the real
    outcome rather than assuming the test passed."""
    report = yield
    if report.when == "call":
        item.stash[OUTCOME_KEY] = report.outcome
    return report


class RecordingClient(TestClient):
    """A test client that keeps what it sent and what came back.

    Subclassed rather than wrapped because every verb funnels through
    `request`, so one override catches all of them and no test has to opt in.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.exchanges: list[Exchange] = []

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any):
        response = super().request(method, url, *args, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = None
        self.exchanges.append(
            Exchange(
                method=str(method).upper(),
                path=str(url),
                request_body=kwargs.get("json"),
                status=response.status_code,
                response_body=body,
            )
        )
        return response


def _covers(doc: str) -> list[str]:
    """Requirement IDs the test says it covers, read from its own docstring."""
    import re  # noqa: PLC0415 - only needed on the capture path

    match = re.search(r"^\s*Covers:(.*)$", doc, flags=re.MULTILINE)
    if not match:
        return []
    return list(dict.fromkeys(re.findall(r"REQ-\d+(?:\.\d+[a-z]?)?", match.group(1))))


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    """A database per test. No shared state between cases, ever."""
    instance = Store(tmp_path / "release-gate.db")
    yield instance
    instance.close()


def _wired_client(
    store: Store,
    request: pytest.FixtureRequest,
    raise_server_exceptions: bool,
) -> Iterator[RecordingClient]:
    """The application with the store and the clock injected."""
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_clock] = lambda: fixed_clock(PINNED_NOW)
    with RecordingClient(
        app, raise_server_exceptions=raise_server_exceptions
    ) as test_client:
        yield test_client
        _capture(request, test_client)
    app.dependency_overrides.clear()


@pytest.fixture
def client(store: Store, request: pytest.FixtureRequest) -> Iterator[RecordingClient]:
    """The application with the store and the clock injected.

    The clock is pinned so `created_at` is an asserted value rather than a
    field the tests agree not to look at.

    Server exceptions are re-raised, so a failing case shows the traceback that
    caused it rather than a bare 500. That is the right default for tests about
    behaviour, and the wrong one for tests about what a caller is told: see
    `caller_client`.
    """
    yield from _wired_client(store, request, raise_server_exceptions=True)


@pytest.fixture
def caller_client(
    store: Store, request: pytest.FixtureRequest
) -> Iterator[RecordingClient]:
    """The application as a real HTTP client meets it.

    The default test client re-raises an unhandled server exception instead of
    returning the response the framework would actually send. That is a
    debugging convenience, and it means a suite that only uses the default
    client can never observe its own 500s. This fixture turns it off, so an
    error path case asserts the status a caller would receive.
    """
    yield from _wired_client(store, request, raise_server_exceptions=False)


def _capture(request: pytest.FixtureRequest, client: RecordingClient) -> None:
    """Hand this test's exchanges to the reporter, and write them if asked.

    The attributes are attached whether or not capture is switched on, because
    the live reporter reads them to print one line per case and it has to work
    on a plain local run.
    """
    node = request.node
    node._api_exchanges = list(client.exchanges)  # noqa: SLF001 - read by the reporter
    node._api_outcome = node.stash.get(OUTCOME_KEY, "unknown")  # noqa: SLF001
    statuses = getattr(node.config, "_api_statuses", None)
    if statuses is None:
        statuses = []
        node.config._api_statuses = statuses  # noqa: SLF001
    statuses.extend(exchange.status for exchange in client.exchanges)

    directory = os.environ.get(CAPTURE_ENV)
    if not directory or not client.exchanges:
        return

    doc = node.function.__doc__ or ""
    node_id = str(node.nodeid)
    write(
        directory,
        CapturedCase(
            node_id=node_id,
            layer=next((p for p in node_id.split("/") if p in LAYER_DIRECTORIES), ""),
            summary=doc.strip().splitlines()[0] if doc.strip() else "",
            covers=_covers(doc),
            outcome=node.stash.get(OUTCOME_KEY, "unknown"),
            commit_sha=os.environ.get("GITHUB_SHA", ""),
            run_id=os.environ.get("GITHUB_RUN_ID", ""),
            captured_at=datetime.now(UTC).isoformat(),
            exchanges=list(client.exchanges),
        ),
    )


@pytest.fixture
def openapi(client: RecordingClient) -> dict:
    """The generated OpenAPI document, read from the running application."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def repo_root() -> Path:
    """The repository root, for the meta layer."""
    return REPO_ROOT
