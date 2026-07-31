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
SHA = re.compile(r"^[0-9a-f]{7,40}$")

#: Fields the report must carry. Keoni's list, plus the four additions, plus the
#: two adaptations for an API with no login. A report missing any of them does
#: not publish, because a bug report with holes in it is what this page exists to
#: argue against.
REQUIRED_FIELDS = (
    "Issue type",
    "Accounts impacted",
    "Summary",
    "Priority",
    "Severity",
    "Reproducibility",
    "Status",
    "Components",
    "Affects commit",
    "Found on run",
    "Regression test",
    "Existing case that should have caught it",
    "Environment tested",
)

REQUIRED_SECTIONS = (
    "Scope of impact",
    "Errant behaviour",
    "Expected behaviour",
    "Steps to reproduce",
    "Root cause",
    "Detection",
    "Resolution",
)

#: Fields that are part of the template and may honestly have no value on a
#: given defect. A report is a form as well as a record: a field carrying N/A
#: shows the structure exists and that this defect did not need it, which is
#: more useful than a field stretched to fit.
MAY_BE_NOT_APPLICABLE = (
    "Accounts impacted",
    "Existing case that should have caught it",
)

#: Fields whose value is a commit SHA, resolved against GitHub at build time.
COMMIT_FIELDS = ("Affects commit", "Fix commit", "Regression commit")

#: Fields whose value is a pull request number.
PULL_FIELDS = ("Fix pull request", "Introduced by pull request")


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
    def problems(self) -> list[str]:
        """Everything missing from this report."""
        missing_fields = [f for f in REQUIRED_FIELDS if not self.fields.get(f)]
        missing_sections = [s for s in REQUIRED_SECTIONS if not self.sections.get(s)]
        return [f"{self.key}: no {name}" for name in missing_fields + missing_sections]

    def commits(self) -> dict[str, str]:
        """Field name to SHA, for the commit fields that are filled in."""
        return {
            name: self.fields[name]
            for name in COMMIT_FIELDS
            if SHA.match(self.fields.get(name, ""))
        }

    def pulls(self) -> dict[str, int]:
        """Field name to pull request number, for the fields that are filled in."""
        return {
            name: int(self.fields[name])
            for name in PULL_FIELDS
            if self.fields.get(name, "").isdigit()
        }


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


def referenced_commits(directory: Path | None = None) -> list[str]:
    """Every commit SHA named by any report, for the collector to resolve."""
    seen: dict[str, None] = {}
    for defect in load(directory):
        for sha in defect.commits().values():
            seen[sha] = None
    return list(seen)


def referenced_pulls(directory: Path | None = None) -> list[int]:
    """Every pull request number named by any report."""
    seen: dict[int, None] = {}
    for defect in load(directory):
        for number in defect.pulls().values():
            seen[number] = None
    return list(seen)


def referenced_tests(directory: Path | None = None) -> list[str]:
    """Node IDs of the regression tests the reports name."""
    return [
        defect.fields["Regression test"]
        for defect in load(directory)
        if defect.fields.get("Regression test")
    ]


def ordering(commits: dict, defect: Defect) -> tuple[str, str] | None:
    """The regression and fix timestamps, when both commits are known.

    Returned as a pair rather than a sentence so the page can show the two
    values and let the reader compare them.
    """
    regression = commits.get(defect.fields.get("Regression commit", ""))
    fix = commits.get(defect.fields.get("Fix commit", ""))
    if not regression or not fix:
        return None
    return regression["authored_at"], fix["authored_at"]
