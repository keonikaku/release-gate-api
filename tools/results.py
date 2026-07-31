"""Read a JUnit XML report into something the evidence surfaces can join on.

The report is written by pytest during the run. Nothing here invents a result:
if a case is not in the XML it did not run, and it is reported as not run rather
than assumed green.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path

PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"
ERROR = "error"
XFAILED = "xfailed"


@dataclass(frozen=True)
class CaseResult:
    """One executed case, including one parametrised instance of a case."""

    node_id: str
    function: str
    outcome: str
    duration: float

    @property
    def base_node_id(self) -> str:
        """The node ID without the parametrisation suffix.

        `test_x[spa-roles3]` and `test_x[small-roles0]` are instances of one
        written case, and the traceability table is about written cases.
        """
        return self.node_id.split("[", 1)[0]


@dataclass(frozen=True)
class RunResults:
    """Every case in one run, plus the totals the ledger records."""

    cases: tuple[CaseResult, ...]
    duration: float

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.outcome == PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for case in self.cases if case.outcome in (FAILED, ERROR))

    @property
    def skipped(self) -> int:
        return sum(1 for case in self.cases if case.outcome == SKIPPED)

    @property
    def expected_failures(self) -> tuple[CaseResult, ...]:
        """Cases that ran, failed, and are tracked against a known defect."""
        return tuple(case for case in self.cases if case.outcome == XFAILED)

    @property
    def green(self) -> bool:
        """True when every case that ran passed and at least one case ran."""
        return self.total > 0 and self.failed == 0

    def outcome_for(self, base_node_id: str) -> str | None:
        """The outcome of a written case, aggregated over its instances.

        One failing parametrised instance fails the case. Anything else would
        publish a green row for a case that is partly red.
        """
        instances = [c for c in self.cases if c.base_node_id == base_node_id]
        if not instances:
            return None
        for outcome in (ERROR, FAILED, XFAILED, SKIPPED):
            if any(case.outcome == outcome for case in instances):
                return outcome
        return PASSED


def _classname_to_path(classname: str) -> str:
    """`tests.unit.test_rules` becomes `tests/unit/test_rules.py`."""
    return classname.replace(".", "/") + ".py"


def parse_junit(path: str | Path) -> RunResults:
    """Read a JUnit XML file written by pytest."""
    root = ElementTree.parse(Path(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)

    cases: list[CaseResult] = []
    duration = 0.0
    for suite in suites:
        duration += float(suite.get("time", 0.0))
        for case in suite.iter("testcase"):
            classname = case.get("classname", "")
            name = case.get("name", "")
            outcome = PASSED
            skipped = case.find("skipped")
            if case.find("failure") is not None:
                outcome = FAILED
            elif case.find("error") is not None:
                outcome = ERROR
            elif skipped is not None:
                # pytest records an expected failure as a skip with a type of
                # pytest.xfail. The two mean opposite things: a skip did not
                # run, an expected failure ran and failed against a tracked
                # defect. Collapsing them would let a skip hide behind a defect
                # ID, or a tracked defect fail the no-skips criterion.
                outcome = XFAILED if skipped.get("type") == "pytest.xfail" else SKIPPED
            cases.append(
                CaseResult(
                    node_id=f"{_classname_to_path(classname)}::{name}",
                    function=name.split("[", 1)[0],
                    outcome=outcome,
                    duration=float(case.get("time", 0.0)),
                )
            )
    return RunResults(cases=tuple(cases), duration=duration)


def counts_by_layer(results: RunResults) -> dict[str, int]:
    """Executed cases per layer, taken from the path in the node ID."""
    counts: dict[str, int] = {}
    for case in results.cases:
        parts = case.node_id.split("/")
        layer = parts[1] if len(parts) > 2 else "unknown"
        counts[layer] = counts.get(layer, 0) + 1
    return counts
