"""API test cases: what each one checks, and what the service actually returned.

The published case list is a join between two things that are produced
separately and cannot be edited into agreement.

The **case** comes from the test source: its ID, the sentence describing what it
verifies, the endpoint it exercises and the status it declares it expects. The
**result** comes from a real run: the requests that went out, the responses that
came back, and whether pytest passed the case.

If a case declares `Expects: 404` and the run recorded a 200, that is a
disagreement and the build fails. Without that check the page would be
publishing a docstring rather than a result.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools import traceability
from tools.evidence import CapturedCase, Exchange

#: The status codes this suite exercises, and what each one means here. The
#: order is the order the page presents them: the happy path first, then every
#: way a request can be refused, then the failure the smoke step catches.
STATUS_MEANING: dict[int, str] = {
    201: "Created. The change was recorded and the service says where it is.",
    200: "Accepted. The gate ran the rules, or the lifecycle move was legal.",
    400: "Refused. The request was read and understood, and a rule said no.",
    404: "No such change. The identifier does not name anything.",
    409: "Conflict. The request is legal in general and not from this state.",
    422: "Unreadable. The request could not be parsed into a change at all.",
    500: "The service failed. It says so rather than reporting success.",
}

#: The pair worth explaining to anyone reading the list. Most services collapse
#: these two, and collapsing them makes a caller with a bug and a change that is
#: not ready look identical in every log and metric built on status codes.
CONTRASTING_PAIR = (400, 422)


@dataclass(frozen=True)
class ApiCase:
    """One published API test case, joined to what the run recorded."""

    case_id: str
    node_id: str
    name: str
    title: str
    layer: str
    endpoint: str | None
    expects: int | None
    observed: int | None
    outcome: str
    exchanges: tuple[Exchange, ...]
    commit_sha: str = ""

    @property
    def subject(self) -> Exchange | None:
        """The call the case is about, which is the last one it made."""
        return self.exchanges[-1] if self.exchanges else None

    @property
    def setup(self) -> tuple[Exchange, ...]:
        """The calls made to reach the state the case is about."""
        return self.exchanges[:-1] if len(self.exchanges) > 1 else ()

    @property
    def passed(self) -> bool:
        return self.outcome == "passed"

    @property
    def agrees(self) -> bool:
        """True when the run returned the status the case says it expects."""
        if self.expects is None or self.observed is None:
            return False
        return self.expects == self.observed

    @property
    def sort_key(self) -> tuple[int, str]:
        return (self.expects or 0, self.case_id)


def build(
    cases: tuple[traceability.TestCase, ...] | None = None,
    captured: list[CapturedCase] | None = None,
) -> tuple[ApiCase, ...]:
    """Join every annotated case to the run that exercised it.

    A case with no captured run still appears, with no observed status. It is
    reported as not run rather than dropped, because a case that silently
    disappears from the list is how coverage goes missing.
    """
    cases = traceability.test_cases() if cases is None else cases
    captured = [] if captured is None else captured
    recorded = {case.node_id: case for case in captured}

    joined = []
    for case in cases:
        if not case.case_id:
            continue
        run = recorded.get(case.node_id)
        exchanges = tuple(run.exchanges) if run else ()
        joined.append(
            ApiCase(
                case_id=case.case_id,
                node_id=case.node_id,
                name=case.name,
                title=case.summary,
                layer=case.layer,
                endpoint=case.endpoint,
                expects=case.expects,
                observed=exchanges[-1].status if exchanges else None,
                outcome=run.outcome if run else "not run",
                exchanges=exchanges,
                commit_sha=run.commit_sha if run else "",
            )
        )
    return tuple(sorted(joined, key=lambda c: c.sort_key))


def disagreements(api_cases: tuple[ApiCase, ...]) -> list[str]:
    """Cases whose declared status is not the one the run returned.

    Only cases that both ran and passed are judged. A failing case is already
    reported as failing, and a case with no run has nothing to disagree with.
    """
    return [
        f"{case.case_id} ({case.name}) declares Expects: {case.expects} "
        f"and the run returned {case.observed}"
        for case in api_cases
        if case.passed and case.observed is not None and case.expects != case.observed
    ]


def duplicate_ids(api_cases: tuple[ApiCase, ...]) -> list[str]:
    """Case IDs used more than once."""
    seen: dict[str, int] = {}
    for case in api_cases:
        seen[case.case_id] = seen.get(case.case_id, 0) + 1
    return sorted(case_id for case_id, count in seen.items() if count > 1)


def missing_expectations(api_cases: tuple[ApiCase, ...]) -> list[str]:
    """Cases carrying an ID but no declared status."""
    return [case.case_id for case in api_cases if case.expects is None]


def by_status(api_cases: tuple[ApiCase, ...]) -> dict[int, list[ApiCase]]:
    """Cases grouped by the status they expect, in the documented order."""
    grouped: dict[int, list[ApiCase]] = {}
    for case in api_cases:
        if case.expects is not None:
            grouped.setdefault(case.expects, []).append(case)

    ordered = {}
    for status in STATUS_MEANING:
        if status in grouped:
            ordered[status] = grouped[status]
    for status in sorted(grouped):
        if status not in ordered:
            ordered[status] = grouped[status]
    return ordered


def observed_counts(api_cases: tuple[ApiCase, ...]) -> dict[int, int]:
    """How many responses of each status the run actually recorded."""
    counts: dict[int, int] = {}
    for case in api_cases:
        for exchange in case.exchanges:
            counts[exchange.status] = counts.get(exchange.status, 0) + 1
    return dict(sorted(counts.items()))
