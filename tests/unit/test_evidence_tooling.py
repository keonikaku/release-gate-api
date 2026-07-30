"""The tooling that produces the published evidence, tested like the service.

The pages a reviewer reads are only as trustworthy as the code that generates
them. These cases cover the parts where a mistake would publish something untrue:
a ledger that accepts a hand edited row, a readout that treats an unevaluated
criterion as green, a results parser that reports a partly failing case as passed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from tools import (
    build_site,
    evidence,
    provenance,
    readout,
    render,
    results,
    risk,
    runs,
    traceability,
)

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
<testsuite name="pytest" tests="4" time="1.5">
<testcase classname="tests.unit.test_rules" name="test_alpha" time="0.1"/>
<testcase classname="tests.unit.test_rules" name="test_beta[one]" time="0.1"/>
<testcase classname="tests.unit.test_rules" name="test_beta[two]" time="0.1">
<failure message="boom">assert 1 == 2</failure>
</testcase>
<testcase classname="tests.integration.test_api" name="test_gamma" time="0.2">
<skipped message="no"/>
</testcase>
</testsuite>
</testsuites>
"""


@pytest.fixture
def junit_file(tmp_path):
    """A JUnit report with a pass, a partly failing parametrised case and a skip."""
    path = tmp_path / "junit.xml"
    path.write_text(JUNIT, encoding="utf-8")
    return path


def row(number: int, result: str = runs.RESULT_PASS) -> runs.RunRow:
    """A ledger row with everything but the run number held constant."""
    return runs.RunRow(
        run_number=number,
        run_id=f"id-{number}",
        commit_sha="a" * 40,
        branch="main",
        started_at="2026-07-30T01:15:02+00:00",
        result=result,
        total=145,
        passed=145,
        failed=0,
        skipped=0,
        duration_seconds=1.5,
        promoted_version="v0.1.3",
    )


# Results ---------------------------------------------------------------------


def test_junit_outcomes_are_read_per_case(junit_file):
    """Passes, failures and skips are counted from the report.

    Layer: unit
    Covers: none
    Why this layer: the parser is a pure function over a file, and every
    published pass count is downstream of it.
    """
    parsed = results.parse_junit(junit_file)
    assert parsed.total == 4
    assert parsed.passed == 2
    assert parsed.failed == 1
    assert parsed.skipped == 1
    assert parsed.green is False


def test_one_failing_instance_fails_the_written_case(junit_file):
    """A parametrised case with one red instance is reported as failed.

    Layer: unit
    Covers: none
    Why this layer: this is the mistake that would publish a green traceability
    row for a rule that is partly broken, and it is invisible from any page.
    """
    parsed = results.parse_junit(junit_file)
    assert parsed.outcome_for("tests/unit/test_rules.py::test_beta") == results.FAILED
    assert parsed.outcome_for("tests/unit/test_rules.py::test_alpha") == results.PASSED


def test_a_case_that_did_not_run_is_not_reported_as_passed(junit_file):
    """A case missing from the report comes back as None.

    Layer: unit
    Covers: none
    Why this layer: the alternative default is to treat absence as success, which
    is how a deleted test becomes a green row.
    """
    parsed = results.parse_junit(junit_file)
    assert parsed.outcome_for("tests/unit/test_rules.py::test_missing") is None


def test_layer_counts_come_from_the_node_id(junit_file):
    """Executed cases are counted per layer directory.

    Layer: unit
    Covers: none
    Why this layer: the pyramid on the dashboard is this function's output.
    """
    assert results.counts_by_layer(results.parse_junit(junit_file)) == {
        "unit": 3,
        "integration": 1,
    }


# The ledger ------------------------------------------------------------------


def test_a_run_can_be_appended_and_read_back(tmp_path):
    """A ledger round trips through CSV.

    Layer: unit
    Covers: none
    Why this layer: the ledger is a file format, and the dashboard is built from
    what comes back out of it.
    """
    ledger = tmp_path / "runs.csv"
    runs.append_run(ledger, row(1))
    runs.append_run(ledger, row(2))
    assert [r.run_number for r in runs.read_runs(ledger)] == [1, 2]


def test_a_run_number_that_does_not_advance_is_refused(tmp_path):
    """Appending an earlier or repeated run number raises.

    Layer: unit
    Covers: none
    Why this layer: run numbers come from GitHub and only increase, so this is
    the check that catches a reordered or hand written ledger.
    """
    ledger = tmp_path / "runs.csv"
    runs.append_run(ledger, row(2))
    with pytest.raises(runs.LedgerRejected):
        runs.append_run(ledger, row(2))
    with pytest.raises(runs.LedgerRejected):
        runs.append_run(ledger, row(1))


def test_a_hand_edited_ledger_is_not_appended_to(tmp_path):
    """A ledger whose rows are out of order is rejected rather than extended.

    Layer: unit
    Covers: none
    Why this layer: this is the property that makes "written only by CI" checkable
    rather than promised, and it can only be exercised against a file.
    """
    ledger = tmp_path / "runs.csv"
    runs.append_run(ledger, row(1))
    runs.append_run(ledger, row(5))
    text = ledger.read_text(encoding="utf-8").replace("5,id-5", "0,id-5")
    ledger.write_text(text, encoding="utf-8")
    with pytest.raises(runs.LedgerRejected):
        runs.append_run(ledger, row(6))


def test_a_ledger_with_the_wrong_header_is_rejected(tmp_path):
    """A CSV that is not this ledger is refused on read.

    Layer: unit
    Covers: none
    Why this layer: the failure mode is a file replaced by something else with the
    same name, and the parser is where that has to be caught.
    """
    ledger = tmp_path / "runs.csv"
    ledger.write_text("date,value\n2026-07-30,7\n", encoding="utf-8")
    with pytest.raises(runs.LedgerRejected):
        runs.read_runs(ledger)


def test_a_missing_ledger_is_empty_rather_than_an_error(tmp_path):
    """The first run ever has nothing to read.

    Layer: unit
    Covers: none
    Why this layer: the first publish would otherwise fail, and a first run that
    cannot record itself is a ledger that never starts.
    """
    assert runs.read_runs(tmp_path / "nothing.csv") == []


def test_pass_rate_counts_failures(tmp_path):
    """Pass rate is passes over runs, and a failed run pulls it down.

    Layer: unit
    Covers: none
    Why this layer: it is arithmetic on the ledger, and the dashboard publishes
    the number.
    """
    assert runs.pass_rate([row(1), row(2, runs.RESULT_FAIL)]) == 0.5
    assert runs.pass_rate([]) == 0.0


# The readout -----------------------------------------------------------------


def test_a_criterion_that_could_not_be_evaluated_blocks_the_go():
    """Not evaluated is treated as NO-GO, never as GO.

    Layer: unit
    Covers: none
    Why this layer: it is the single most consequential rule in the readout, and
    it is a property of one function rather than of a page.
    """
    criterion = readout.blocker_criterion(None)
    assert criterion.verdict == "NOT EVALUATED"
    assert criterion.blocks is True


def test_all_five_criteria_met_gives_a_go():
    """Every criterion met gives GO, with nothing blocking.

    Layer: unit
    Covers: none
    Why this layer: the positive half of the pair, computed from constructed
    inputs rather than read off a page.
    """
    passing = results.RunResults(
        cases=(
            results.CaseResult(
                node_id="tests/unit/test_x.py::test_y",
                function="test_y",
                outcome=results.PASSED,
                duration=0.1,
            ),
        ),
        duration=0.1,
    )
    decision = readout.compute(
        results=passing,
        rows=(traceability.RequirementRow(requirement="REQ-1.1", cases=(), gap=True),),
        documented_endpoints=("GET /healthz",),
        claimed_endpoints={"GET /healthz": ["tests/integration/test_api.py::test_x"]},
        claimed_requirements=(),
        open_blockers=0,
        commit_sha="abc1234",
        generated_at=datetime.now(UTC).isoformat(),
        run_id="1",
    )
    assert decision.decision == readout.GO
    assert decision.blocking == ()


def test_an_empty_run_is_not_a_go():
    """A run that executed nothing is NO-GO, not vacuously green.

    Layer: unit
    Covers: none
    Why this layer: zero cases passing zero cases is the classic vacuous pass,
    and the guard against it lives in the criterion.
    """
    decision = readout.compute(
        results=results.RunResults(cases=(), duration=0.0),
        rows=(),
        documented_endpoints=("GET /healthz",),
        claimed_endpoints={"GET /healthz": ["x"]},
        claimed_requirements=(),
        open_blockers=0,
        commit_sha="abc1234",
        generated_at=datetime.now(UTC).isoformat(),
        run_id="1",
    )
    assert decision.decision == readout.NO_GO
    assert [c.id for c in decision.blocking] == ["C1"]


def test_an_untraced_requirement_blocks_the_go():
    """A requirement with no test and no stated gap fails C3.

    Layer: unit
    Covers: none
    Why this layer: the criterion is a function of the traceability rows, and the
    row type can be constructed directly.
    """
    rows = (traceability.RequirementRow(requirement="REQ-9.9", cases=(), gap=False),)
    criterion = readout.traceability_criterion(rows, claimed=())
    assert criterion.met is False
    assert "REQ-9.9" in criterion.detail


def test_an_undocumented_endpoint_blocks_the_go():
    """A test pointing at an endpoint the spec does not document fails C4.

    Layer: unit
    Covers: none
    Why this layer: both directions of the endpoint check are pure set logic.
    """
    criterion = readout.endpoint_criterion(
        documented=("GET /healthz",),
        claimed={"GET /nope": ["tests/integration/test_api.py::test_x"]},
    )
    assert criterion.met is False
    assert "GET /healthz" in criterion.detail
    assert "GET /nope" in criterion.detail


def test_a_skipped_case_blocks_the_go(junit_file):
    """A skipped case means a pass is not the whole suite passing.

    Layer: unit
    Covers: none
    Why this layer: skips are the quietest way for coverage to disappear, and the
    criterion reads them straight from the report.
    """
    criterion = readout.no_skips_criterion(results.parse_junit(junit_file))
    assert criterion.met is False


# Captured evidence -----------------------------------------------------------


def test_a_captured_case_round_trips(tmp_path):
    """What is written is what is read back.

    Layer: unit
    Covers: none
    Why this layer: the format is the join between the run and the evidence page.
    """
    case = evidence.CapturedCase(
        node_id="tests/integration/test_api.py::test_x",
        layer="integration",
        summary="A summary.",
        covers=["REQ-1.6"],
        outcome="passed",
        commit_sha="abc1234",
        exchanges=[
            evidence.Exchange(
                method="POST",
                path="/changes",
                request_body={"title": "x"},
                status=201,
                response_body={"id": "1"},
            )
        ],
    )
    evidence.write(tmp_path, case)
    loaded = evidence.load(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].node_id == case.node_id
    assert loaded[0].exchanges[0].status == 201


def test_a_node_id_becomes_a_safe_filename():
    """Node IDs with slashes and brackets do not escape the directory.

    Layer: unit
    Covers: none
    Why this layer: a path traversal in a filename is a property of the function,
    and it is cheaper to assert than to discover.
    """
    name = evidence.filename_for("tests/unit/test_x.py::test_y[../../etc/passwd]")
    assert "/" not in name
    assert name.endswith(".json")


def test_evidence_from_a_run_that_captured_nothing_is_empty(tmp_path):
    """No capture directory means no evidence, not an error.

    Layer: unit
    Covers: none
    Why this layer: the page has to distinguish "nothing captured" from "stale
    data", and this is where that distinction starts.
    """
    assert evidence.load(tmp_path / "missing") == []


def test_captured_cases_group_by_requirement():
    """Evidence is indexed by the requirement each case claims.

    Layer: unit
    Covers: none
    Why this layer: the grouping is what makes the evidence page traceable rather
    than a pile of requests.
    """
    case = evidence.CapturedCase(
        node_id="a", layer="integration", summary="", covers=["REQ-1.1", "REQ-2"]
    )
    grouped = evidence.by_requirement([case])
    assert set(grouped) == {"REQ-1.1", "REQ-2"}


# Traceability ----------------------------------------------------------------


def test_a_requirement_with_tests_and_a_gap_is_partial():
    """Covered and declared as a gap means partial, not green.

    Layer: unit
    Covers: none
    Why this layer: REQ-1.7 is exactly this case, and publishing it as COVERED
    would overstate the suite.
    """
    partial = traceability.RequirementRow(
        requirement="REQ-1.7",
        cases=(
            traceability.TestCase(
                node_id="tests/unit/test_x.py::test_y",
                name="test_y",
                layer="unit",
                summary="",
                covers=("REQ-1.7",),
            ),
        ),
        gap=True,
    )
    assert partial.status == "PARTIAL"
    assert partial.traced is True


def test_a_requirement_with_only_a_gap_is_a_declared_gap_not_untraced():
    """A requirement with no test but a written reason is traced.

    Layer: unit
    Covers: none
    Why this layer: REQ-3 is exactly this case. Treating it as untraced would
    fail the build forever; treating it as covered would be a lie. It is its own
    state and this is where that state is decided.
    """
    declared = traceability.RequirementRow(requirement="REQ-3.1", cases=(), gap=True)
    assert declared.status == "DECLARED GAP"
    assert declared.traced is True

    silent = traceability.RequirementRow(requirement="REQ-9.9", cases=(), gap=False)
    assert silent.status == "NOT COVERED"
    assert silent.traced is False


def test_endpoint_markers_are_resolved_through_module_constants():
    """`@pytest.mark.endpoint(SUBMIT)` resolves to the string SUBMIT holds.

    Layer: unit
    Covers: none
    Why this layer: the traceability module reads source rather than importing it,
    so constant resolution is its own risk and needs its own case.
    """
    claimed = traceability.claimed_endpoints()
    assert "POST /changes/{change_id}/submit" in claimed
    assert claimed["POST /changes/{change_id}/submit"]


def test_the_published_table_and_the_gate_read_the_same_rows():
    """Every requirement in the document appears in the table exactly once.

    Layer: unit
    Covers: none
    Why this layer: the table is generated from these rows and the build gate is
    enforced from these rows, so their agreement is the property worth pinning.
    """
    rows = traceability.rows()
    assert [row.requirement for row in rows] == list(traceability.requirement_ids())
    assert len({row.requirement for row in rows}) == len(rows)


def test_layer_counts_are_written_cases_not_instances():
    """The written case count is smaller than the executed count.

    Layer: unit
    Covers: none
    Why this layer: the two numbers are different and the site labels them
    differently, so the difference is asserted rather than assumed.
    """
    counts = traceability.layer_counts()
    assert counts["unit"] > 0
    assert counts["meta"] > 0
    assert sum(counts.values()) == len(traceability.test_cases())


def test_gaps_are_read_from_the_test_design(tmp_path):
    """The published gaps are the entries from the document, not a copy.

    Layer: unit
    Covers: none
    Why this layer: if the site restated the gaps in its own words they could
    drift from the document the build gate reads.
    """
    entries = traceability.gap_entries()
    assert entries
    assert any("REQ-3" in gap.requirements for gap in entries)
    assert all(gap.reason for gap in entries)


def test_a_requirement_id_in_loose_prose_declares_nothing(tmp_path):
    """Pasting an ID under the gaps heading does not make it a declared gap.

    Layer: unit
    Covers: none
    Why this layer: this is the silent absorption path. It was one line of text
    wide, and the parser is the only place it can be closed.
    """
    design = tmp_path / "test-design.md"
    design.write_text(
        "## Stated gaps\n\nREQ-9.9 is fine, honestly.\n\n## Open questions\n",
        encoding="utf-8",
    )
    assert traceability.gap_entries(design) == ()
    assert traceability.stated_gaps(design) == ()


def test_a_gap_entry_without_a_reason_declares_nothing(tmp_path):
    """An entry that states no reason is not a declaration.

    Layer: unit
    Covers: none
    Why this layer: the cost of declaring a gap is writing down why, and the
    parser is what charges it.
    """
    design = tmp_path / "test-design.md"
    design.write_text(
        "## Stated gaps\n\n### GAP-1: no reason given\n\n"
        "**Requirements:** REQ-9.9\n**Coverage:** none\n**Reason:** because\n\n"
        "## Open questions\n",
        encoding="utf-8",
    )
    entry = traceability.gap_entries(design)[0]
    assert entry.problems
    assert traceability.stated_gaps(design) == ()


def test_open_questions_are_published_as_headline_and_body():
    """Every open question is readable outside the repository.

    Layer: unit
    Covers: none
    Why this layer: a question that only appears in a file nobody opens is filed
    rather than flagged, and the parser is what puts it on the page.
    """
    questions = traceability.open_questions()
    assert questions
    assert all(headline and body for headline, body in questions)


def test_the_readout_json_names_every_criterion(tmp_path):
    """The machine readable readout carries all five criteria.

    Layer: unit
    Covers: none
    Why this layer: the JSON is what anything downstream would read, and its
    shape is a promise.
    """
    decision = readout.compute(
        results=None,
        rows=(),
        documented_endpoints=(),
        claimed_endpoints={},
        claimed_requirements=(),
        open_blockers=None,
        commit_sha="abc",
        generated_at="2026-07-30T00:00:00+00:00",
        run_id="1",
    )
    payload = json.loads(json.dumps({"criteria": [c.id for c in decision.criteria]}))
    assert payload["criteria"] == ["C1", "C2", "C3", "C4", "C5"]
    assert decision.decision == readout.NO_GO


# Risk ratings ----------------------------------------------------------------


def test_a_placeholder_is_not_a_rating(tmp_path):
    """Only high, medium and low count. Anything else is unrated.

    Layer: unit
    Covers: none
    Why this layer: the parser decides what counts as a rating, and the whole
    point is that nothing infers one on the author's behalf.
    """
    ratings = tmp_path / "risk-ratings.md"
    ratings.write_text(
        "| Requirement | Risk | Reasoning |\n"
        "|---|---|---|\n"
        "| REQ-1.1 | pending | |\n"
        "| REQ-1.6 | high | An unstaffed window is a change nobody can roll back. |\n",
        encoding="utf-8",
    )
    parsed = risk.parse(ratings)
    assert len(parsed) == 2
    assert [r.requirement for r in parsed if r.recorded] == ["REQ-1.6"]


def test_recorded_ratings_carry_their_reasoning(tmp_path):
    """A rating without a reason is still a rating, and the reason is published
    when it is there.

    Layer: unit
    Covers: none
    Why this layer: the reasoning column is what makes the view arguable rather
    than decorative, and it is parsed here.
    """
    ratings = tmp_path / "risk-ratings.md"
    ratings.write_text(
        "| REQ-2.2 | medium | Illegal transitions are caught in review anyway. |\n",
        encoding="utf-8",
    )
    recorded = risk.recorded(ratings)
    assert recorded["REQ-2.2"].reasoning.startswith("Illegal transitions")


def test_missing_ratings_file_is_no_ratings(tmp_path):
    """No file means no view, not a crash.

    Layer: unit
    Covers: none
    Why this layer: the site builder skips the section on this result, so the
    empty case is the one that has to be right.
    """
    assert risk.parse(tmp_path / "nothing.md") == ()
    assert risk.recorded(tmp_path / "nothing.md") == {}


# Provenance and fabrication --------------------------------------------------


def test_a_commit_no_machine_wrote_stops_the_publish():
    """A human commit on the evidence branch is an offender.

    Layer: unit
    Covers: none
    Why this layer: the check is a pure function over a git log, and the
    published claim about who writes the ledger rests entirely on it.
    """
    log = (
        "aaa|41898282+github-actions[bot]@users.noreply.github.com|Publish evidence\n"
        "bbb|someone@example.com|Fix a number by hand\n"
    )
    offenders = provenance.offenders(provenance.parse_log(log))
    assert [commit.sha for commit in offenders] == ["bbb"]


def test_the_bootstrap_commit_is_allowed_by_sha_not_by_pattern():
    """The one human commit is allow listed individually.

    Layer: unit
    Covers: none
    Why this layer: an exception written as a pattern would widen to cover every
    future human commit, which is exactly what the check exists to catch.
    """
    bootstrap = next(iter(provenance.BOOTSTRAP_COMMITS))
    allowed = provenance.Commit(bootstrap, "keonikaku@gmail.com", "Create the branch")
    other = provenance.Commit("deadbee", "keonikaku@gmail.com", "Another one")
    assert allowed.allowed is True
    assert other.allowed is False


def test_a_ledger_row_naming_an_unknown_run_is_caught():
    """A fabricated row carries a run ID GitHub has no record of.

    Layer: unit
    Covers: none
    Why this layer: the run number check only catches a number that goes
    backwards. A high fabricated number passes it, and the run ID is the field
    that cannot be invented.
    """

    def numbered(run_number: int, run_id: str) -> runs.RunRow:
        return runs.RunRow(
            run_number=run_number,
            run_id=run_id,
            commit_sha="a" * 40,
            branch="main",
            started_at="2026-07-30T01:15:02+00:00",
            result=runs.RESULT_PASS,
            total=1,
            passed=1,
            failed=0,
            skipped=0,
            duration_seconds=0.1,
            promoted_version="",
        )

    real = [numbered(10, "30500000010"), numbered(11, "30500000011")]
    known = {"30500000010", "30500000011"}
    assert runs.unknown_run_ids(real, known) == []

    fabricated = [*real, numbered(999, "99999999999")]
    assert runs.unknown_run_ids(fabricated, known) == ["99999999999"]


def test_rows_older_than_the_window_are_not_called_fabricated():
    """A run that has aged out of GitHub's list is not treated as invented.

    Layer: unit
    Covers: none
    Why this layer: the failure mode of the check above is accusing an old
    honest row, which would fail every publish forever.
    """
    old = runs.RunRow(
        run_number=1,
        run_id="1",
        commit_sha="a" * 40,
        branch="main",
        started_at="2026-07-30T01:15:02+00:00",
        result=runs.RESULT_PASS,
        total=1,
        passed=1,
        failed=0,
        skipped=0,
        duration_seconds=0.1,
        promoted_version="",
    )
    assert runs.unknown_run_ids([old], {"500", "501"}) == []


# Published prose -------------------------------------------------------------


def test_inline_markdown_renders_rather_than_printing_the_markers():
    """Bold and code from the documents become HTML, not literal asterisks.

    Layer: unit
    Covers: none
    Why this layer: the gaps are published verbatim from the test design so they
    cannot drift from it, which means the renderer is the only place the markup
    can be handled.
    """
    out = render.inline_markdown("**REQ-1.7 is partial.** See `app/rules.py`.")
    assert "<strong>REQ-1.7 is partial.</strong>" in out
    assert "<code>app/rules.py</code>" in out
    assert "**" not in out


def test_inline_markdown_escapes_before_it_renders():
    """Markup in a document cannot inject HTML into a page.

    Layer: unit
    Covers: none
    Why this layer: the input is a file anyone editing the repository can
    change, so escaping order is a property worth pinning.
    """
    out = render.inline_markdown("<script>alert(1)</script> **bold**")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<strong>bold</strong>" in out


def test_a_job_still_running_is_not_reported_as_not_run():
    """An in flight job renders as in progress.

    Layer: unit
    Covers: none
    Why this layer: the publish job generates the page while it is running, so
    it can never carry its own conclusion. Reporting that as "not run"
    contradicted GitHub's record of the same run.
    """
    assert "in progress" in render.outcome_pill(None, "in_progress")
    assert "not run" in render.outcome_pill(None, "")
    assert "success" in render.outcome_pill("success", "completed")


def test_a_single_run_is_not_published_as_a_pass_rate():
    """One run does not become "100% passed".

    Layer: unit
    Covers: none
    Why this layer: a percentage standing in for a sample of one reads as a
    claim about reliability and is not one.
    """
    assert "too few runs" in build_site.pass_rate_line([row(1)])
    assert "%" not in build_site.pass_rate_line([row(1)])
    many = [row(n) for n in range(1, 7)]
    assert "%" in build_site.pass_rate_line(many)


def test_both_pages_count_requirement_status_the_same_way():
    """The dashboard and the traceability page read one function.

    Layer: unit
    Covers: none
    Why this layer: the two pages disagreed once, and a shared counter is what
    stops them disagreeing again.
    """
    rows_in = (
        traceability.RequirementRow(requirement="REQ-3.1", cases=(), gap=True),
        traceability.RequirementRow(requirement="REQ-9.9", cases=(), gap=False),
    )
    counts = build_site.status_counts(rows_in)
    assert counts["DECLARED GAP"] == 1
    assert counts["NOT COVERED"] == 1
    assert sum(counts.values()) == len(rows_in)
