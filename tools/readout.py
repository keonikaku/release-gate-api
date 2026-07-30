"""The release readiness readout: GO or NO-GO, computed rather than decided.

Five criteria, each one a function of data produced by the run. The readout
states what it computes and from what, and stops there. Nobody uses it to make a
decision on this project and it does not claim otherwise.

Two rules that shape the design:

**A criterion that could not be evaluated is NO-GO, not GO.** Unable to confirm
is not the same as confirmed, and in a release decision the two must never
collapse into each other.

**Every criterion carries its evidence.** A readout that says NO-GO without
naming the failing check is a mood, not a decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools import traceability
from tools.results import RunResults

GO = "GO"
NO_GO = "NO-GO"
FAILED_OUTCOMES = ("failed", "error")


@dataclass(frozen=True)
class Criterion:
    """One stated criterion and what the data said about it."""

    id: str
    statement: str
    met: bool | None
    detail: str

    @property
    def verdict(self) -> str:
        if self.met is True:
            return "MET"
        if self.met is False:
            return "NOT MET"
        return "NOT EVALUATED"

    @property
    def blocks(self) -> bool:
        """True when this criterion stops a GO, which includes not evaluated."""
        return self.met is not True


@dataclass(frozen=True)
class Readout:
    """The computed decision, stamped with what it was computed from."""

    criteria: tuple[Criterion, ...]
    commit_sha: str
    generated_at: str
    run_id: str

    @property
    def decision(self) -> str:
        return NO_GO if any(c.blocks for c in self.criteria) else GO

    @property
    def blocking(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if c.blocks)


def suite_criterion(results: RunResults | None) -> Criterion:
    """C1. Every case that ran on this commit passed."""
    if results is None:
        return Criterion(
            id="C1",
            statement="The full suite passes on this commit.",
            met=None,
            detail="No JUnit report was produced by this run.",
        )
    if results.green:
        return Criterion(
            id="C1",
            statement="The full suite passes on this commit.",
            met=True,
            detail=f"{results.passed} of {results.total} cases passed.",
        )
    return Criterion(
        id="C1",
        statement="The full suite passes on this commit.",
        met=False,
        detail=(
            f"{results.failed} failing: "
            + ", ".join(
                sorted(c.node_id for c in results.cases if c.outcome in (FAILED_OUTCOMES))[
                    :5
                ]
            )
        ),
    )


def no_skips_criterion(results: RunResults | None) -> Criterion:
    """C2. Nothing was skipped, so the pass count is the whole suite."""
    if results is None:
        return Criterion(
            id="C2",
            statement="No case was skipped, so a pass is the whole suite passing.",
            met=None,
            detail="No JUnit report was produced by this run.",
        )
    if results.skipped == 0:
        return Criterion(
            id="C2",
            statement="No case was skipped, so a pass is the whole suite passing.",
            met=True,
            detail=f"{results.total} cases ran, none skipped.",
        )
    return Criterion(
        id="C2",
        statement="No case was skipped, so a pass is the whole suite passing.",
        met=False,
        detail=f"{results.skipped} cases were skipped.",
    )


def traceability_criterion(
    rows: tuple[traceability.RequirementRow, ...],
    claimed: tuple[str, ...] = (),
) -> Criterion:
    """C3. Every requirement is covered or declared as a gap, and no test claims
    a requirement that does not exist.

    Both inputs are passed in rather than read from the repository, so the
    criterion is a function of the run it is reporting on.
    """
    untraced = [row.requirement for row in rows if not row.traced]
    invented = sorted(set(claimed) - {row.requirement for row in rows})
    if untraced or invented:
        return Criterion(
            id="C3",
            statement="Every requirement has a test or a stated gap, and no test "
            "claims a requirement that does not exist.",
            met=False,
            detail=(
                f"untraced: {untraced or 'none'}; "
                f"claiming a requirement that does not exist: {invented or 'none'}"
            ),
        )
    return Criterion(
        id="C3",
        statement="Every requirement has a test or a stated gap, and no test "
        "claims a requirement that does not exist.",
        met=True,
        detail=f"{len(rows)} requirements, all traced.",
    )


def endpoint_criterion(
    documented: tuple[str, ...],
    claimed: dict[str, list[str]],
) -> Criterion:
    """C4. Every documented endpoint has an integration case, and no case points
    at an endpoint the spec does not document."""
    untested = sorted(set(documented) - set(claimed))
    unknown = sorted(set(claimed) - set(documented))
    if not documented:
        return Criterion(
            id="C4",
            statement="Every documented endpoint is exercised, and no test points "
            "at an endpoint that is not documented.",
            met=None,
            detail="No OpenAPI document was produced by this run.",
        )
    if untested or unknown:
        return Criterion(
            id="C4",
            statement="Every documented endpoint is exercised, and no test points "
            "at an endpoint that is not documented.",
            met=False,
            detail=f"untested: {untested or 'none'}; undocumented: {unknown or 'none'}",
        )
    return Criterion(
        id="C4",
        statement="Every documented endpoint is exercised, and no test points "
        "at an endpoint that is not documented.",
        met=True,
        detail=f"{len(documented)} endpoints, all exercised.",
    )


def blocker_criterion(open_blockers: int | None) -> Criterion:
    """C5. No open release-blocker issue."""
    if open_blockers is None:
        return Criterion(
            id="C5",
            statement="No open issue is labelled release-blocker.",
            met=None,
            detail="The issue list could not be read during this run.",
        )
    if open_blockers == 0:
        return Criterion(
            id="C5",
            statement="No open issue is labelled release-blocker.",
            met=True,
            detail="Zero open release-blocker issues.",
        )
    return Criterion(
        id="C5",
        statement="No open issue is labelled release-blocker.",
        met=False,
        detail=f"{open_blockers} open release-blocker issues.",
    )


def compute(
    results: RunResults | None,
    rows: tuple[traceability.RequirementRow, ...],
    documented_endpoints: tuple[str, ...],
    claimed_endpoints: dict[str, list[str]],
    claimed_requirements: tuple[str, ...],
    open_blockers: int | None,
    commit_sha: str,
    generated_at: str,
    run_id: str,
) -> Readout:
    """Run every criterion and stamp the result."""
    return Readout(
        criteria=(
            suite_criterion(results),
            no_skips_criterion(results),
            traceability_criterion(rows, claimed_requirements),
            endpoint_criterion(documented_endpoints, claimed_endpoints),
            blocker_criterion(open_blockers),
        ),
        commit_sha=commit_sha,
        generated_at=generated_at,
        run_id=run_id,
    )
