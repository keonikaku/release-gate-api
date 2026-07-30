"""Captured request and response pairs, and how they are written and read.

Evidence is a side effect of running the suite. Nothing here is authored: the
exchanges are the bytes the tests actually sent and received, the assertion is
the docstring the test states about itself, and the outcome is what pytest
reported. If the suite does not run, there is no evidence, and the pages that
read it say so rather than showing yesterday's.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CAPTURE_ENV = "RELEASE_GATE_EVIDENCE"
UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class Exchange:
    """One request and the response it got."""

    method: str
    path: str
    request_body: Any | None
    status: int
    response_body: Any | None


@dataclass
class CapturedCase:
    """Every exchange one test made, with the trace back to the requirement."""

    node_id: str
    layer: str
    summary: str
    covers: list[str]
    outcome: str = "unknown"
    commit_sha: str = ""
    run_id: str = ""
    captured_at: str = ""
    exchanges: list[Exchange] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str) + "\n"


def filename_for(node_id: str) -> str:
    """A stable filename for a node ID, safe on every filesystem."""
    return UNSAFE.sub("_", node_id).strip("_") + ".json"


def write(directory: str | Path, case: CapturedCase) -> Path:
    """Write one captured case. Overwrites, so a rerun replaces its evidence."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    path = target / filename_for(case.node_id)
    path.write_text(case.to_json(), encoding="utf-8")
    return path


def load(directory: str | Path) -> list[CapturedCase]:
    """Read every captured case, ordered by node ID."""
    target = Path(directory)
    if not target.exists():
        return []
    cases = []
    for path in sorted(target.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        cases.append(
            CapturedCase(
                node_id=raw["node_id"],
                layer=raw["layer"],
                summary=raw["summary"],
                covers=list(raw.get("covers", [])),
                outcome=raw.get("outcome", "unknown"),
                commit_sha=raw.get("commit_sha", ""),
                run_id=raw.get("run_id", ""),
                captured_at=raw.get("captured_at", ""),
                exchanges=[Exchange(**exchange) for exchange in raw.get("exchanges", [])],
            )
        )
    return sorted(cases, key=lambda case: case.node_id)


def by_requirement(cases: list[CapturedCase]) -> dict[str, list[CapturedCase]]:
    """Captured cases grouped by the requirement they claim to cover."""
    grouped: dict[str, list[CapturedCase]] = {}
    for case in cases:
        for requirement in case.covers:
            grouped.setdefault(requirement, []).append(case)
    return grouped
