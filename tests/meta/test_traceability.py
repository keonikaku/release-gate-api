"""Meta layer: requirement to test traceability, machine enforced.

Three directions, and the third is the one that matters.

1. Every requirement in `docs/requirements.md` is covered by a test, or it is
   named in the stated gaps section of `docs/test-design.md`.
2. Every requirement a test claims to cover exists in the requirements.
3. At least one requirement is honestly recorded as uncovered. A traceability
   table where everything is green and nothing is missing reads as fabricated,
   and this repository would rather fail the build than publish one.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"
REQUIREMENTS = REPO_ROOT / "docs" / "requirements.md"
TEST_DESIGN = REPO_ROOT / "docs" / "test-design.md"

REQ_ID = re.compile(r"REQ-\d+(?:\.\d+[a-z]?)?")


def requirement_ids() -> set[str]:
    """Every requirement ID stated in the requirements document."""
    return set(REQ_ID.findall(REQUIREMENTS.read_text(encoding="utf-8")))


def covered_ids() -> dict[str, set[str]]:
    """Requirement ID to the tests that claim to cover it."""
    claims: dict[str, set[str]] = {}
    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
                continue
            doc = ast.get_docstring(node) or ""
            match = re.search(r"^\s*Covers:(.*)$", doc, flags=re.MULTILINE)
            if not match:
                continue
            for requirement in REQ_ID.findall(match.group(1)):
                claims.setdefault(requirement, set()).add(
                    f"{path.relative_to(REPO_ROOT)}::{node.name}"
                )
    return claims


def stated_gap_ids() -> set[str]:
    """Requirement IDs named in the stated gaps section of the test design."""
    text = TEST_DESIGN.read_text(encoding="utf-8")
    start = text.index("## Stated gaps")
    end = text.index("## Open questions")
    return set(REQ_ID.findall(text[start:end]))


REQUIREMENTS_IDS = requirement_ids()
COVERAGE = covered_ids()
GAPS = stated_gap_ids()


def test_the_requirements_document_was_read():
    """Requirement IDs were found. Guards the checks below.

    Layer: meta
    Covers: none
    Why this layer: it reads a document rather than the service, and a
    traceability check that silently finds nothing to trace is worse than none.
    """
    assert len(REQUIREMENTS_IDS) >= 10
    assert "REQ-1.6" in REQUIREMENTS_IDS
    assert "REQ-3.2" in REQUIREMENTS_IDS


def test_every_requirement_is_covered_or_declared_as_a_gap():
    """No requirement is silently untested.

    Layer: meta
    Covers: none
    Why this layer: the mapping is between two documents and the source of the
    suite. Nothing in a running service can answer it.
    """
    untraced = sorted(REQUIREMENTS_IDS - set(COVERAGE) - GAPS)
    assert untraced == [], f"requirements with neither a test nor a stated gap: {untraced}"


def test_no_test_claims_a_requirement_that_does_not_exist():
    """The reverse direction: a typo in a `Covers:` line fails the build.

    Layer: meta
    Covers: none
    Why this layer: without this, traceability could be satisfied by inventing
    requirement IDs in docstrings.
    """
    invented = sorted(set(COVERAGE) - REQUIREMENTS_IDS)
    assert invented == [], f"tests claim requirements that do not exist: {invented}"


def test_at_least_one_requirement_is_honestly_uncovered():
    """The traceability table is not all green, and says so on purpose.

    Layer: meta
    Covers: none
    Why this layer: it is a statement about the suite as a whole. REQ-3 is
    enforced by the pipeline rather than by the service, so no case in this
    repository can assert it, and the gaps section says that in plain words
    rather than leaving a green row that would be untrue.
    """
    assert GAPS, "no requirement is recorded as a gap"
    uncovered = sorted(GAPS - set(COVERAGE))
    assert uncovered, "every stated gap is also covered, so the gaps list is stale"


def test_the_named_rules_all_have_tests():
    """Every rule with its own row in the requirements tables is covered.

    Layer: meta
    Covers: none
    Why this layer: names the specific IDs a reviewer will look for, so a
    reorganisation of the suite that drops one is caught by name rather than by
    a count.
    """
    expected = {
        "REQ-1.1",
        "REQ-1.2",
        "REQ-1.2a",
        "REQ-1.3",
        "REQ-1.4",
        "REQ-1.5",
        "REQ-1.5a",
        "REQ-1.6",
        "REQ-1.7",
        "REQ-2.1",
        "REQ-2.2",
        "REQ-2.3",
    }
    missing = sorted(expected - set(COVERAGE))
    assert missing == [], f"rules with no test: {missing}"


def test_requirement_three_is_traced_to_the_pipeline_not_to_a_test():
    """REQ-3 is evidenced by the workflow, and the workflow says so.

    Layer: meta
    Covers: none
    Why this layer: the evidence for REQ-3 is a file in `.github/workflows`, so
    the check has to read that file. It fails if the promotion job stops
    depending on verification, which is the one property REQ-3 rests on.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "post-merge.yml").read_text(
        encoding="utf-8"
    )
    assert "needs: verify" in workflow
    assert "REQ-3" in workflow
    for requirement in ("REQ-3.1", "REQ-3.2", "REQ-3.3"):
        assert requirement in GAPS, f"{requirement} is not recorded as a suite gap"
