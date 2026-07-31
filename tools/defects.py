"""Defect reports, parsed from the files they are written in.

A defect report is analysis, so the prose is written by a person. What the prose
must not do is restate facts that live somewhere checkable: commit messages,
timestamps, the status a run returned, the order two commits landed in. The
report names commits and runs by identifier, and everything else about them is
read from GitHub at build time.

That split is the point. If the report says the regression test was committed
before the fix, the page proves it with two timestamps it fetched, not with the
sentence in the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFECTS_DIR = REPO_ROOT / "docs" / "defects"

FIELD = re.compile(r"^\*\*(?P<name>[^:*]+):\*\*\s*(?P<value>.*)$")
SECTION = re.compile(r"^## (?P<title>.+)$")
KEY = re.compile(r"^# (?P<key>DEF-\d+)\s*$", re.MULTILINE)

#: Fields the report must carry. Keoni's list, plus the four additions, plus the
#: two adaptations for an API with no login. A report missing any of them does
#: not publish, because a bug report with holes in it is what this page exists to
#: argue against.
REQUIRED_FIELDS = (
    "Issue type",
    "Summary",
    "Status",
    "Priority",
    "Reproducibility",
    "Environment",
    "Components",
    "Existing case that should have caught it",
)

REQUIRED_SECTIONS = (
    "Description",
    "Errant behaviour",
    "Expected behaviour",
    "Steps to reproduce",
    "Attachment",
)

#: The environments a defect can be found in. A runner description is not an
#: environment: a tester picks from the promotion path.
ENVIRONMENTS = ("DEV", "SIT", "INT", "non-live", "production")

#: Fields that are part of the template and may honestly have no value on a
#: given defect. A report is a form as well as a record: a field carrying N/A
#: shows the structure exists and that this defect did not need it, which is
#: more useful than a field stretched to fit.
MAY_BE_NOT_APPLICABLE = (
    "Accounts impacted",
    "Existing case that should have caught it",
)

#: The fields the page prints as a block, in the order a tracker shows them.
#: Every required field appears here or is rendered in its own row with a link,
#: and a meta test fails the build if one is parsed but never shown.
DISPLAY_FIELDS = (
    "Issue type",
    "Status",
    "Resolution",
    "Priority",
    "Reproducibility",
    "Environment",
    "Components",
    "Labels",
    "Affects version",
    "Fix version",
)

#: Required fields the renderer shows as the heading of the record rather than
#: as a row.
HEADING_FIELDS = ("Summary",)

#: Required fields that the renderer handles individually rather than in the
#: block above, because each one resolves to a link.
LINKED_FIELDS = (
    "Existing case that should have caught it",
    "Failing test",
)


#: A ticket carries what a tester needs to reproduce a defect and act on it.
#: Why it was deferred, what the risk is and who agreed to carry it are a
#: conversation the team has, not fields. A field that explains why rather than
#: what does not belong here, which is why root cause, coverage analysis,
#: detection, resolution and the deferral rationale are all absent.
#:
#: Neither does a field the team does not use, however standard it is
#: elsewhere. Severity was here and came out for that reason: it is in every
#: guide and it was in nobody's workflow, and a field its owner would have to
#: hedge about is worth less than one they can walk a reader through cold.
#:
#: Statuses that mean the defect is still live. A deferred defect is open: the
#: status and the fix version record the decision, which is how a tracker
#: records it too.
OPEN_STATUSES = ("Open", "Deferred", "In progress", "Reopened")


@dataclass(frozen=True)
class Defect:
    """One defect report: its fields, its sections and where it came from."""

    key: str
    path: Path
    fields: dict[str, str] = field(default_factory=dict)
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return self.fields.get("Summary", "")

    @property
    def is_open(self) -> bool:
        """True when this defect is still live, deferral included."""
        return self.fields.get("Status", "") in OPEN_STATUSES

    @property
    def failing_test(self) -> str:
        """Node ID of the test that currently fails because of this defect."""
        return self.fields.get("Failing test", "")

    @property
    def problems(self) -> list[str]:
        """Everything missing or wrong in this report."""
        missing_fields = [f for f in REQUIRED_FIELDS if not self.fields.get(f)]
        missing_sections = [s for s in REQUIRED_SECTIONS if not self.sections.get(s)]
        faults = [f"{self.key}: no {name}" for name in missing_fields + missing_sections]

        environment = self.fields.get("Environment", "")
        if environment and environment not in ENVIRONMENTS:
            faults.append(
                f"{self.key}: Environment is {environment!r}, not one of "
                f"{', '.join(ENVIRONMENTS)}"
            )
        if self.is_open and not self.fields.get("Fix version"):
            faults.append(f"{self.key}: is open and names no fix version")
        return faults


def parse(path: Path) -> Defect | None:
    """Read one defect report."""
    text = path.read_text(encoding="utf-8")
    key_line = KEY.search(text)
    if not key_line:
        return None

    fields: dict[str, str] = {}
    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []

    for line in text.splitlines():
        heading = SECTION.match(line)
        if heading:
            if current:
                sections[current] = "\n".join(body).strip()
            current = heading.group("title").strip()
            body = []
            continue
        if current is None:
            found = FIELD.match(line)
            if found:
                fields[found.group("name").strip()] = found.group("value").strip()
            continue
        body.append(line)

    if current:
        sections[current] = "\n".join(body).strip()

    return Defect(key=key_line.group("key"), path=path, fields=fields, sections=sections)


def load(directory: Path | None = None) -> tuple[Defect, ...]:
    """Every defect report, ordered by key."""
    target = DEFECTS_DIR if directory is None else directory
    if not target.exists():
        return ()
    found = [parse(path) for path in sorted(target.glob("DEF-*.md"))]
    return tuple(defect for defect in found if defect is not None)


def referenced_tests(directory: Path | None = None) -> list[str]:
    """Node IDs of the tests the reports name, failing or regression."""
    names = []
    for defect in load(directory):
        for field_name in ("Failing test", "Regression test"):
            value = defect.fields.get(field_name, "")
            if value and "::" in value:
                names.append(value)
    return names


def open_defects(directory: Path | None = None) -> tuple[Defect, ...]:
    """Defects that are still live, deferral included."""
    return tuple(defect for defect in load(directory) if defect.is_open)


def by_failing_test(directory: Path | None = None) -> dict[str, Defect]:
    """Node ID to the open defect that explains why it fails."""
    return {
        defect.failing_test: defect for defect in load(directory) if defect.failing_test
    }
