"""Fail the build when a published case disagrees with the run that exercised it.

Run after the suite, against the evidence that run captured. The page joins a
case's declared status to the status the service returned, and without this
check that join could publish a docstring while the service did something else.

Usage:
    python -m tools.check_api_cases --evidence reports/evidence
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools import api_cases, evidence


def main() -> None:
    """Command line entry point. Non zero exit fails the job."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=Path("reports/evidence"))
    parser.add_argument(
        "--minimum-statuses",
        type=int,
        default=6,
        help="How many distinct status codes the suite must exercise.",
    )
    args = parser.parse_args()

    captured = evidence.load(args.evidence)
    if not captured:
        print(f"no captured evidence in {args.evidence}; nothing to check against")
        sys.exit(1)

    cases = api_cases.build(captured=captured)
    problems = []
    problems += [f"disagreement: {line}" for line in api_cases.disagreements(cases)]
    problems += [f"duplicate case id: {i}" for i in api_cases.duplicate_ids(cases)]
    problems += [
        f"case {i} declares no expected status"
        for i in api_cases.missing_expectations(cases)
    ]

    exercised = api_cases.by_status(cases)
    if len(exercised) < args.minimum_statuses:
        problems.append(
            f"the suite exercises {len(exercised)} status codes, fewer than "
            f"{args.minimum_statuses}"
        )

    if problems:
        print("The published case list disagrees with the run:")
        for problem in problems:
            print(f"  {problem}")
        sys.exit(1)

    counts = ", ".join(f"{s}: {len(c)}" for s, c in exercised.items())
    print(f"{len(cases)} cases, {len(exercised)} status codes ({counts})")


if __name__ == "__main__":
    main()
