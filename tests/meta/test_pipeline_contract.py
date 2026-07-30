"""Meta layer: the properties of the pipeline that the evidence rests on.

Every claim the published site makes about how promotion is blocked, and about
who may write the ledger, is a property of a workflow file. These cases read
those files. They are here so that a change which quietly removes the property
fails the build rather than quietly removing the meaning of the badge.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
POST_MERGE = (WORKFLOWS / "post-merge.yml").read_text(encoding="utf-8")
PR_GATE = (WORKFLOWS / "pr-gate.yml").read_text(encoding="utf-8")


def test_promotion_depends_on_verification():
    """`promote` carries `needs: verify`.

    Layer: meta
    Covers: REQ-3.1, REQ-3.2
    Why this layer: the rule is enforced by GitHub reading a YAML file, so the
    only place it can be asserted is that file. No test of the service can see
    it, which is exactly why REQ-3 is a declared gap in the suite.
    """
    assert "needs: verify" in POST_MERGE


def test_promotion_can_only_happen_from_main():
    """A run on any other branch exercises verification and stops.

    Layer: meta
    Covers: REQ-3.3
    Why this layer: it is the guard that makes a deliberately failing branch run
    safe, and it lives in the workflow rather than in the service.
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
