"""Meta layer: the properties of the pipeline that the evidence rests on.

Every claim the published site makes about how promotion is blocked, and about
who may write the ledger, is a property of a workflow file. These cases read
those files. They are here so that a change which quietly removes the property
fails the build rather than quietly removing the meaning of the badge.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
POST_MERGE = (WORKFLOWS / "post-merge.yml").read_text(encoding="utf-8")
PR_GATE = (WORKFLOWS / "pr-gate.yml").read_text(encoding="utf-8")


def test_promotion_depends_on_verification():
    """`promote` carries `needs: verify`.

    This guards the mechanism REQ-3 depends on. It does not cover REQ-3, and it
    deliberately does not claim to: reading a workflow file is not the same as
    observing that GitHub refused to promote. GAP-1 in the test design names this
    case as the guard and still records REQ-3 as uncovered.

    Layer: meta
    Covers: none
    Why this layer: the property is a line in a YAML file, so a file is the only
    place it can be asserted. No test of the service can see it.
    """
    assert "needs: verify" in POST_MERGE


def test_promotion_can_only_happen_from_main():
    """A run on any other branch exercises verification and stops.

    This is also the reason a run on a `ci/**` branch cannot demonstrate the
    promotion block: promotion is skipped there by this condition whatever
    verification did, so the outcome is identical with a green suite. Only a
    post-merge run on `main` carries that claim.

    Layer: meta
    Covers: none
    Why this layer: it is the guard that keeps a deliberately failing branch run
    from tagging anything, and it lives in the workflow rather than the service.
    """
    assert "if: github.ref == 'refs/heads/main'" in POST_MERGE


def test_the_publish_job_runs_even_when_verification_failed():
    """The dashboard records the runs that failed as well as the ones that
    passed.

    Layer: meta
    Covers: none
    Why this layer: a ledger that only grows on green days shows a pass rate of
    one hundred percent and evidences nothing. The property is a condition in
    the workflow.
    """
    assert "if: always() && github.ref == 'refs/heads/main'" in POST_MERGE
    assert "needs: [verify, promote]" in POST_MERGE


def test_evidence_capture_is_switched_on_in_the_verify_job():
    """Captured exchanges come from the post-merge run.

    Layer: meta
    Covers: none
    Why this layer: capture is off by default, so the published evidence depends
    on one environment variable being set in one job.
    """
    assert "RELEASE_GATE_EVIDENCE: reports/evidence" in POST_MERGE


def test_the_pr_gate_builds_the_site_before_the_merge():
    """A broken site generator is caught before it can turn the badge red.

    Layer: meta
    Covers: none
    Why this layer: the ordering is a property of which workflow runs the
    builder, and the point of it is to protect the published badge.
    """
    assert "python -m tools.build_site" in PR_GATE


def test_the_ledger_is_not_on_the_branch_people_commit_to():
    """`results/runs.csv` is not tracked on `main`.

    Layer: meta
    Covers: none
    Why this layer: the site says the ledger is written only by CI, and this is
    the structural fact behind that sentence. If the file ever appears on
    `main`, the sentence stops being true and this fails.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "results"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert tracked == "", f"the ledger is tracked on main: {tracked}"


@pytest.mark.parametrize("directory", ["site", "published"])
def test_generated_output_is_not_committed(directory):
    """The generated site is never committed to `main`.

    Layer: meta
    Covers: none
    Why this layer: a committed copy of a generated page is the thing that goes
    stale while looking current, and the guard belongs where the repository can
    be inspected.
    """
    tracked = subprocess.run(
        ["git", "ls-files", directory],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert tracked == "", f"{directory} is tracked: {tracked}"


def test_the_workflow_still_names_the_step_the_demo_page_describes():
    """The smoke step keeps the name three published claims are about.

    Layer: meta
    Covers: none
    Why this layer: the demo page asserts that the suite passed and this
    specific step failed, and it decides whether to say so by matching the step
    name in GitHub's record. If the workflow renames the step, the page would
    quietly stop making a true claim rather than making a false one, which is
    safe but silent. This fails the build instead, so the rename and the page
    are corrected together.
    """
    from tools.build_site import SMOKE_STEP  # noqa: PLC0415 - only needed here

    assert f"name: {SMOKE_STEP}" in POST_MERGE


def test_the_pages_render_without_leaking_markdown(tmp_path):
    """No page publishes literal bold markers or backticks in its prose.

    Layer: meta
    Covers: none
    Why this layer: the gaps and the open questions are published verbatim from
    the test design so they cannot drift from the document the build gate reads.
    That is the right decision and it is what made raw markdown reach the page,
    so the guard belongs on the built output rather than on the renderer alone.
    """
    from tools import build_site  # noqa: PLC0415 - only needed by this case

    written = build_site.build(
        reports=tmp_path / "no-reports",
        ledger=tmp_path / "no-ledger.csv",
        out=tmp_path / "site",
        sha="0" * 40,
        run_id="1",
    )
    pages = [path for path in written if path.suffix == ".html"]
    assert pages

    leaks = []
    for path in pages:
        body = path.read_text(encoding="utf-8").split('<main class="wrap">')[1]
        # Code spans legitimately contain characters like the ci/** glob, so
        # they are removed before the prose is checked.
        prose = re.sub(r"<code>.*?</code>", "", body, flags=re.DOTALL)
        for marker in ("**", "`"):
            if marker in prose:
                leaks.append(f"{path.name} publishes {marker!r}")
    assert leaks == [], "\n".join(leaks)


def test_every_api_case_carries_an_id_and_an_expected_status():
    """A case in the published list declares what it checks for.

    Layer: meta
    Covers: none
    Why this layer: the page is generated from these annotations, so a case
    without them would either vanish from the list or appear with a blank
    expectation. Agreement with the run itself is checked by
    tools/check_api_cases.py, which runs against real captured evidence in both
    workflows.
    """
    from tools import api_cases  # noqa: PLC0415 - only needed by this case

    cases = api_cases.build()
    assert len(cases) >= 30
    assert api_cases.duplicate_ids(cases) == []
    assert api_cases.missing_expectations(cases) == []
    assert all(case.case_id.startswith("API-") for case in cases)


def test_the_case_list_covers_the_status_codes_the_page_explains():
    """Every status the page gives a meaning for has at least one case.

    Layer: meta
    Covers: none
    Why this layer: the page prints a meaning per status code, and a meaning
    with no case behind it is a claim about coverage that does not exist.
    """
    from tools import api_cases  # noqa: PLC0415 - only needed by this case

    declared = {case.expects for case in api_cases.build()}
    missing = sorted(set(api_cases.STATUS_MEANING) - declared)
    assert missing == [], f"status codes explained but never exercised: {missing}"


def test_every_defect_report_carries_the_required_fields():
    """A report with holes in it does not publish.

    Layer: meta
    Covers: none
    Why this layer: the page argues that this is what a handover looks like, so
    a missing field is a defect in the argument as well as in the document.
    """
    from tools import defects  # noqa: PLC0415 - only needed by this case

    reports = defects.load()
    assert reports, "no defect reports were parsed"
    problems = [problem for report in reports for problem in report.problems]
    assert problems == [], "\n".join(problems)


def test_every_open_defect_names_a_failing_test_that_exists():
    """An open defect points at the case that currently fails because of it.

    Layer: meta
    Covers: none
    Why this layer: that link is what makes the defect live rather than a note.
    It is also what the pipeline reads to decide whether an expected failure is
    tracked, so a stale node ID would turn a tracked failure into an untracked
    one silently.
    """
    from tools import defects, traceability  # noqa: PLC0415 - only needed here

    known = {case.node_id for case in traceability.test_cases()}
    for defect in defects.open_defects():
        assert defect.failing_test, f"{defect.key} is open and names no failing test"
        assert defect.failing_test in known, (
            f"{defect.key} names a test that does not exist: {defect.failing_test}"
        )


def test_every_expected_failure_is_tracked_by_an_open_defect():
    """No test is marked as an expected failure without a defect behind it.

    Layer: meta
    Covers: none
    Why this layer: an xfail with no defect is a test nobody will look at
    again. This reads the markers in the source and the reports on disk, and
    neither is visible from a run.
    """
    import re as regex  # noqa: PLC0415 - only needed by this case

    from tools import defects  # noqa: PLC0415 - only needed by this case

    tracked = defects.by_failing_test()
    marked = []
    for path in (REPO_ROOT / "tests").rglob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        for match in regex.finditer(r"@pytest\.mark\.xfail", text):
            following = text[match.start() : match.start() + 900]
            name = regex.search(r"def (test_\w+)", following)
            if name:
                marked.append(f"{path.relative_to(REPO_ROOT)}::{name.group(1)}")

    untracked = sorted(set(marked) - set(tracked))
    assert untracked == [], f"expected failures with no open defect: {untracked}"


def test_every_defect_names_a_regression_test_that_exists():
    """The case a defect says now covers it is a real case.

    Layer: meta
    Covers: none
    Why this layer: the traceability matrix links the defect to that node ID. A
    rename would leave the matrix pointing at nothing, which is the failure the
    matrix exists to prevent.
    """
    from tools import defects, traceability  # noqa: PLC0415 - only needed here

    known = {case.node_id for case in traceability.test_cases()}
    missing = [node_id for node_id in defects.referenced_tests() if node_id not in known]
    assert missing == [], f"defect reports name tests that do not exist: {missing}"


def test_the_defect_page_says_it_is_a_format_not_an_export():
    """The page does not imply a Jira instance that does not exist.

    Layer: meta
    Covers: none
    Why this layer: it is the same class of care as labelling a practice
    exercise, and the sentence is easy to lose in an edit.
    """
    from tools import build_site  # noqa: PLC0415 - only needed by this case

    page = build_site.defect_page(
        build_site.gather(REPO_ROOT / "no-reports", REPO_ROOT / "no-ledger.csv", "", "")
    )
    assert "not exported from a Jira instance" in page


def test_every_required_defect_field_reaches_the_page():
    """A field the report requires is a field the reader sees.

    Layer: meta
    Covers: none
    Why this layer: the parser and the renderer keep separate lists of fields,
    and the first version of this page parsed Accounts impacted correctly and
    then never printed it. A required field that renders nowhere is worse than
    a missing one, because the document looks complete.
    """
    from tools import defects  # noqa: PLC0415 - only needed by this case

    rendered = (
        set(defects.DISPLAY_FIELDS)
        | set(defects.LINKED_FIELDS)
        | set(defects.HEADING_FIELDS)
    )
    missing = sorted(set(defects.REQUIRED_FIELDS) - rendered)
    assert missing == [], f"required fields that no page renders: {missing}"


def test_every_published_case_is_complete():
    """A case in the catalog has preconditions, numbered steps and a result.

    Layer: meta
    Covers: none
    Why this layer: the catalog is generated from the tests, so an incomplete
    case is a docstring nobody finished rather than a page nobody updated. It
    has to fail here, where it is written.
    """
    from tools import catalog  # noqa: PLC0415 - only needed by this case

    catalogue = catalog.build()
    assert len(catalogue) >= 30
    assert catalog.problems(catalogue) == [], "\n".join(catalog.problems(catalogue))


def test_the_catalog_and_the_suite_hold_the_same_cases():
    """Every annotated test appears in the catalog exactly once.

    Layer: meta
    Covers: none
    Why this layer: a case that exists in the suite and not on the page is
    coverage a reader cannot see, and a case on the page with no test behind it
    is a claim with nothing under it.
    """
    from tools import api_cases, catalog  # noqa: PLC0415 - only needed here

    published = {case.case_id for case in catalog.build()}
    running = {case.case_id for case in api_cases.build()}
    assert published == running
    assert len(published) == len(catalog.build())


def test_the_csv_export_carries_the_manual_case_columns():
    """The export uses the same columns as the published manual cases.

    Layer: meta
    Covers: none
    Why this layer: the point of matching the column set is that a reader can
    put the two side by side, and a renamed column would break that quietly.
    """
    from tools import catalog  # noqa: PLC0415 - only needed by this case

    header = catalog.to_csv(catalog.build()).splitlines()[0]
    assert header.startswith("Title,Preconditions,Steps,Expected Result,Priority,Type")
    for column in catalog.DERIVED_COLUMNS:
        assert column in header
