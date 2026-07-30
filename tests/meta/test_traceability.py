"""Meta layer: requirement to test traceability, machine enforced.

Three directions, and the third is the one that matters.

1. Every requirement in `docs/requirements.md` is covered by a test, or it is
   named in the stated gaps section of `docs/test-design.md`.
2. Every requirement a test claims to cover exists in the requirements.
3. At least one requirement is honestly recorded as uncovered. A traceability
   table where everything is green and nothing is missing reads as fabricated,
   and this repository would rather fail the build than publish one.

The collection itself lives in `tools/traceability.py`, which is also what
generates the published table. One module, two consumers, so the table a
reviewer reads and the gate that fails the build cannot disagree.
"""

from __future__ import annotations

from pathlib import Path

from tools import traceability

REPO_ROOT = Path(__file__).resolve().parents[2]

CASES = traceability.test_cases()
REQUIREMENTS_IDS = set(traceability.requirement_ids())
COVERAGE = {
    requirement: {case.node_id for case in CASES if requirement in case.covers}
    for requirement in traceability.claimed_requirements(CASES)
}
GAPS = set(traceability.stated_gaps())


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


def test_every_gap_entry_is_well_formed():
    """A gap declares something only if it says what and why.

    Layer: meta
    Covers: none
    Why this layer: without this, pasting a requirement ID under the gaps
    heading would turn an untested requirement into an accepted one. The
    declaration has to cost a written reason, and the parser only reads entries,
    so loose prose under the heading declares nothing at all.
    """
    entries = traceability.gap_entries()
    assert entries, "no gap entry was parsed from the test design"
    problems = [problem for gap in entries for problem in gap.problems]
    assert problems == [], "\n".join(problems)


def test_a_gap_that_claims_no_coverage_has_no_coverage():
    """Per gap, not "at least one gap somewhere".

    Layer: meta
    Covers: none
    Why this layer: this is the guard the README claims. If any test starts
    claiming a requirement that an entry says is untested, the entry has become
    untrue and the build fails until it is rewritten. Checking that some gap
    somewhere is still uncovered would let every other gap rot.
    """
    broken = []
    for gap in traceability.gap_entries():
        if not gap.declares_no_coverage:
            continue
        for requirement in gap.requirements:
            covering = sorted(COVERAGE.get(requirement, ()))
            if covering:
                broken.append(
                    f"{gap.id} says {requirement} has no coverage, but it is "
                    f"claimed by: {', '.join(covering)}"
                )
    assert broken == [], "\n".join(broken)


def test_a_gap_that_claims_partial_coverage_has_some_coverage():
    """The other direction: partial cannot describe a total absence.

    Layer: meta
    Covers: none
    Why this layer: a requirement with no tests at all, filed as partly covered,
    would read on the published table as better than it is.
    """
    broken = [
        f"{gap.id} says {requirement} is partly covered, but no test claims it"
        for gap in traceability.gap_entries()
        if gap.coverage == traceability.COVERAGE_PARTIAL
        for requirement in gap.requirements
        if not COVERAGE.get(requirement)
    ]
    assert broken == [], "\n".join(broken)


def test_a_gap_that_names_a_guard_names_a_test_that_exists():
    """A guard reference points at a real case.

    Layer: meta
    Covers: none
    Why this layer: the guard line is published beside the gap, so a stale one
    would be a claim about a test that is not there.
    """
    known = {case.node_id for case in CASES}
    missing = [
        f"{gap.id} names a guard that does not exist: {gap.guarded_by}"
        for gap in traceability.gap_entries()
        if gap.guarded_by and gap.guarded_by not in known
    ]
    assert missing == [], "\n".join(missing)


def test_the_suite_still_has_something_it_does_not_cover():
    """At least one requirement is honestly uncovered.

    Layer: meta
    Covers: none
    Why this layer: a table where everything is green and nothing is missing
    reads as fabricated. This is the weakest of the gap checks on purpose: the
    three above are the ones that hold each individual gap honest.
    """
    assert GAPS, "no requirement is recorded as a gap"
    assert sorted(GAPS - set(COVERAGE)), "every declared gap is also covered"


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
