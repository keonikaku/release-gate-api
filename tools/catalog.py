"""The published test case catalog, generated from the suite.

The cases are written in the test docstrings and read out of them here, so a
case and the test that runs it cannot drift apart. Editing the case means
editing the test, which is the property this project keeps needing.

Columns match the ones Keoni's published manual cases use: Title,
Preconditions, Steps, Expected Result, Priority, Type. The derived columns
(Suite, ID, Automated, Automated Test) are added the same way the ShopSmart
page adds them, and they are marked as derived rather than authored.

The engineering notes in a docstring (`Layer` and `Why this layer`) stay out of
the catalog. They are about where a test belongs, which is a conversation for
the repository and not part of a test case. `Covers` stays out too: the mapping
from case to requirement is what the traceability page is for.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from tools import traceability

#: The vocabulary the published manual cases use. Anything else fails the build
#: rather than quietly introducing a fourth priority nobody uses.
PRIORITIES = ("Critical", "High", "Medium", "Low")
TYPES = ("Functional", "Smoke")

#: Written columns first, in the order the manual cases use them, then the
#: columns this repository derives.
AUTHORED_COLUMNS = (
    "Title",
    "Preconditions",
    "Steps",
    "Expected Result",
    "Priority",
    "Type",
)
DERIVED_COLUMNS = ("Suite", "ID", "Automated", "Automated Test")
COLUMNS = AUTHORED_COLUMNS + DERIVED_COLUMNS

#: Suites, keyed on the layer the test lives at. A reader does not care what a
#: contract layer is, so the suite says what the cases are about instead.
SUITES = {
    "integration": "Change lifecycle and gate rules",
    "contract": "Published interface",
}


@dataclass(frozen=True)
class CatalogCase:
    """One published case, joined to the test that runs it."""

    case_id: str
    title: str
    preconditions: str
    steps: str
    expected_result: str
    priority: str
    kind: str
    suite: str
    node_id: str
    automated: str = "Yes"

    @property
    def test_name(self) -> str:
        return self.node_id.split("::")[-1]

    @property
    def numbered_steps(self) -> list[str]:
        """Steps split back into the list they were written as."""
        parts = []
        current = ""
        for token in self.steps.split():
            if token[:-1].isdigit() and token.endswith(".") and current:
                parts.append(current.strip())
                current = ""
            current += token + " "
        if current.strip():
            parts.append(current.strip())
        return [p for p in parts if p]

    def as_row(self) -> dict[str, str]:
        """The case as one row of the export."""
        return {
            "Title": self.title,
            "Preconditions": self.preconditions,
            "Steps": self.steps,
            "Expected Result": self.expected_result,
            "Priority": self.priority,
            "Type": self.kind,
            "Suite": self.suite,
            "ID": self.case_id,
            "Automated": self.automated,
            "Automated Test": self.test_name,
        }


def build(
    cases: tuple[traceability.TestCase, ...] | None = None,
) -> tuple[CatalogCase, ...]:
    """Every annotated case, ordered by ID."""
    cases = traceability.test_cases() if cases is None else cases
    catalog = [
        CatalogCase(
            case_id=case.case_id,
            title=case.summary.rstrip("."),
            preconditions=case.preconditions,
            steps=case.steps,
            expected_result=case.expected_result,
            priority=case.priority,
            kind=case.kind,
            suite=SUITES.get(case.layer, case.layer),
            node_id=case.node_id,
        )
        for case in cases
        if case.case_id
    ]
    return tuple(sorted(catalog, key=lambda c: c.case_id))


def problems(catalog: tuple[CatalogCase, ...]) -> list[str]:
    """Everything wrong with the catalog, named per case."""
    faults = []
    for case in catalog:
        for label, value in (
            ("preconditions", case.preconditions),
            ("steps", case.steps),
            ("expected result", case.expected_result),
            ("title", case.title),
        ):
            if not value.strip():
                faults.append(f"{case.case_id}: no {label}")
        if case.priority not in PRIORITIES:
            faults.append(
                f"{case.case_id}: priority {case.priority!r} is not one of "
                f"{', '.join(PRIORITIES)}"
            )
        if case.kind not in TYPES:
            faults.append(
                f"{case.case_id}: type {case.kind!r} is not one of {', '.join(TYPES)}"
            )
        if not case.steps.strip().startswith("1."):
            faults.append(f"{case.case_id}: steps are not numbered from 1")
    return faults


def counts(catalog: tuple[CatalogCase, ...]) -> dict[str, int]:
    """The headline numbers, derived so they cannot be typed in wrong."""
    totals = {"cases": len(catalog)}
    for priority in PRIORITIES:
        totals[priority.lower()] = sum(1 for c in catalog if c.priority == priority)
    for kind in TYPES:
        totals[kind.lower()] = sum(1 for c in catalog if c.kind == kind)
    totals["suites"] = len({c.suite for c in catalog})
    totals["automated"] = sum(1 for c in catalog if c.automated == "Yes")
    return totals


def by_suite(catalog: tuple[CatalogCase, ...]) -> dict[str, list[CatalogCase]]:
    """Cases grouped by suite, in the order the suites are declared."""
    grouped: dict[str, list[CatalogCase]] = {}
    for name in SUITES.values():
        members = [case for case in catalog if case.suite == name]
        if members:
            grouped[name] = members
    for case in catalog:
        if case.suite not in grouped:
            grouped.setdefault(case.suite, []).append(case)
    return grouped


def to_csv(catalog: tuple[CatalogCase, ...], columns: tuple[str, ...] = COLUMNS) -> str:
    """The catalog as CSV text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for case in catalog:
        row = case.as_row()
        writer.writerow({column: row[column] for column in columns})
    return buffer.getvalue()
