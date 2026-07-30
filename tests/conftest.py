"""Shared fixtures, and the rule that assigns every test its layer.

Layer markers are applied from the directory a test lives in, so a test cannot
be filed under the wrong layer by forgetting a decorator. The docstring still
has to say the layer out loud, and `tests/meta/test_layer_declarations.py` fails
the build when the two disagree.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clock import fixed_clock
from app.main import app, get_clock, get_store
from app.store import Store
from tests.factories import PINNED_NOW

LAYER_DIRECTORIES = {
    "unit": "unit",
    "contract": "contract",
    "integration": "integration",
    "meta": "meta",
}

REPO_ROOT = Path(__file__).resolve().parent.parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test with the layer of the directory it lives in."""
    for item in items:
        parts = Path(str(item.fspath)).parts
        for directory, marker in LAYER_DIRECTORIES.items():
            if directory in parts:
                item.add_marker(getattr(pytest.mark, marker))
                break


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    """A database per test. No shared state between cases, ever."""
    instance = Store(tmp_path / "release-gate.db")
    yield instance
    instance.close()


@pytest.fixture
def client(store: Store) -> Iterator[TestClient]:
    """The application with the store and the clock injected.

    The clock is pinned so `created_at` is an asserted value rather than a
    field the tests agree not to look at.
    """
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_clock] = lambda: fixed_clock(PINNED_NOW)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def openapi(client: TestClient) -> dict:
    """The generated OpenAPI document, read from the running application."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def repo_root() -> Path:
    """The repository root, for the meta layer."""
    return REPO_ROOT
