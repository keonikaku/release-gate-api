"""Append one row to the run ledger from the artifacts of this run.

Separate from the site builder on purpose: this is the only code that writes to
the ledger, and the builder only ever reads it. A generator that also mutates
its own input is a generator whose output nobody can check.

Usage:
    python -m tools.record_run --junit reports/junit.xml \\
        --ledger results/runs.csv --run-number 12 --run-id 30505108364 \\
        --sha $GITHUB_SHA --branch main --result pass
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from tools import results, runs


def build_row(
    junit: Path,
    run_number: int,
    run_id: str,
    sha: str,
    branch: str,
    result: str,
    started_at: str,
    promoted_version: str,
) -> runs.RunRow:
    """Assemble the row. Counts come from the report, never from an argument."""
    parsed = results.parse_junit(junit) if junit.exists() else None
    return runs.RunRow(
        run_number=run_number,
        run_id=run_id,
        commit_sha=sha,
        branch=branch,
        started_at=started_at or datetime.now(UTC).isoformat(),
        result=result,
        total=parsed.total if parsed else 0,
        passed=parsed.passed if parsed else 0,
        failed=parsed.failed if parsed else 0,
        skipped=parsed.skipped if parsed else 0,
        duration_seconds=round(parsed.duration, 3) if parsed else 0.0,
        promoted_version=promoted_version,
    )


def main() -> None:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", default="reports/junit.xml", type=Path)
    parser.add_argument("--ledger", default="results/runs.csv", type=Path)
    parser.add_argument("--run-number", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--result", choices=[runs.RESULT_PASS, runs.RESULT_FAIL])
    parser.add_argument("--started-at", default="")
    parser.add_argument("--production", type=Path, default=Path("reports/production.json"))
    parser.add_argument("--known-runs", type=Path, default=Path("reports/gh-runs.json"))
    args = parser.parse_args()

    promoted = ""
    if args.production.exists():
        try:
            promoted = json.loads(args.production.read_text(encoding="utf-8")).get(
                "version", ""
            )
        except json.JSONDecodeError:
            promoted = ""

    # Cross check what is already recorded against GitHub's own list of runs
    # before adding to it. A fabricated row carries a run ID that no run has.
    if args.known_runs.exists():
        known = {
            str(run["databaseId"])
            for run in json.loads(args.known_runs.read_text(encoding="utf-8"))
        }
        unknown = runs.unknown_run_ids(runs.read_runs(args.ledger), known)
        if unknown:
            raise SystemExit(
                f"ledger holds runs GitHub has no record of: {', '.join(unknown)}"
            )

    row = build_row(
        junit=args.junit,
        run_number=args.run_number,
        run_id=args.run_id,
        sha=args.sha,
        branch=args.branch,
        result=args.result,
        started_at=args.started_at,
        promoted_version=promoted,
    )
    ledger = runs.append_run(args.ledger, row)
    print(f"recorded run {row.run_number}: {row.result}, {row.passed}/{row.total}")
    print(f"ledger now holds {len(ledger)} runs")


if __name__ == "__main__":
    main()
