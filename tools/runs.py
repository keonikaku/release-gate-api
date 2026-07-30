"""The run ledger: one row per post-merge run, appended by CI only.

The ledger lives on the `gh-pages` branch rather than on `main`. That is what
makes "written only by CI" a structural fact rather than a promise: the file is
not on the branch anyone commits to, and the only writer is the publish job.

Appending still checks two things, because a structural guarantee that nothing
verifies is just another promise. Run numbers must increase and run IDs must be
unique. A ledger that fails either check is rejected rather than extended, and
the publish job fails with it.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

RESULT_PASS = "pass"
RESULT_FAIL = "fail"


@dataclass(frozen=True)
class RunRow:
    """One post-merge run, as the dashboard reads it."""

    run_number: int
    run_id: str
    commit_sha: str
    branch: str
    started_at: str
    result: str
    total: int
    passed: int
    failed: int
    skipped: int
    duration_seconds: float
    promoted_version: str

    @property
    def short_sha(self) -> str:
        return self.commit_sha[:7]


HEADER = tuple(field.name for field in fields(RunRow))


class LedgerRejected(Exception):
    """Raised when the ledger is not in a state that can be appended to."""


def read_runs(path: str | Path) -> list[RunRow]:
    """Read the ledger. A missing file is an empty ledger, not an error."""
    file = Path(path)
    if not file.exists():
        return []

    with file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != HEADER:
            raise LedgerRejected(
                f"ledger header is {reader.fieldnames}, expected {list(HEADER)}"
            )
        rows = [
            RunRow(
                run_number=int(row["run_number"]),
                run_id=row["run_id"],
                commit_sha=row["commit_sha"],
                branch=row["branch"],
                started_at=row["started_at"],
                result=row["result"],
                total=int(row["total"]),
                passed=int(row["passed"]),
                failed=int(row["failed"]),
                skipped=int(row["skipped"]),
                duration_seconds=float(row["duration_seconds"]),
                promoted_version=row["promoted_version"],
            )
            for row in reader
        ]
    return rows


def validate(rows: list[RunRow]) -> list[str]:
    """Everything wrong with a ledger, or an empty list.

    Run numbers come from GitHub and only ever increase. A ledger where they do
    not is either hand edited or reordered, and either way it is not evidence.
    """
    problems = []
    seen_ids: set[str] = set()
    previous = None
    for row in rows:
        if previous is not None and row.run_number <= previous:
            problems.append(f"run number {row.run_number} does not follow {previous}")
        if row.run_id in seen_ids:
            problems.append(f"run id {row.run_id} appears more than once")
        if row.result not in (RESULT_PASS, RESULT_FAIL):
            problems.append(f"run {row.run_number} has result {row.result!r}")
        seen_ids.add(row.run_id)
        previous = row.run_number
    return problems


def append_run(path: str | Path, row: RunRow) -> list[RunRow]:
    """Append one run, refusing to write onto a ledger that is already wrong."""
    file = Path(path)
    existing = read_runs(file)

    problems = validate(existing)
    if problems:
        raise LedgerRejected("; ".join(problems))
    if existing and row.run_number <= existing[-1].run_number:
        raise LedgerRejected(
            f"run number {row.run_number} does not follow {existing[-1].run_number}"
        )

    file.parent.mkdir(parents=True, exist_ok=True)
    write_header = not file.exists()
    with file.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(HEADER))
        if write_header:
            writer.writeheader()
        writer.writerow(asdict(row))
    return [*existing, row]


def pass_rate(rows: list[RunRow]) -> float:
    """Share of runs that passed, as a fraction. Zero runs is zero."""
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.result == RESULT_PASS) / len(rows)
