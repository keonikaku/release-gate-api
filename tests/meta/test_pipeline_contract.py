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
