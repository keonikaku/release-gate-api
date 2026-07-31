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
    api_cases,
    build_site,
    defects,
    evidence,
    provenance,
    readout,
    render,
    results,
    risk,
    runs,
    smoke,
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


def test_a_non_json_error_body_is_reported_rather_than_raised():
    """A plain text 500 from a served instance is readable in the run log.

    Layer: unit
    Covers: none
    Why this layer: the decoder is a pure function, and the run log of a blocked
    deployment is something people read. A traceback about JSON in place of the
    failing check hides which call failed.
    """
    assert smoke.decode(b"") == {}
    assert smoke.decode(b'{"code": "x"}') == {"code": "x"}
    plain = smoke.decode(b"Internal Server Error")
    assert "Internal Server Error" in plain["unparsed_body"]


# The blocked run, described from its own record --------------------------------


VERIFY_JOB = {
    "name": "Verify main",
    "conclusion": "failure",
    "steps": [
        {"name": "Lint", "conclusion": "success"},
        {"name": "Full suite", "conclusion": "success"},
        {"name": "Smoke the freshly built instance", "conclusion": "failure"},
        {"name": "Export the OpenAPI document", "conclusion": "skipped"},
    ],
}


def test_the_failing_step_is_named_from_the_run_record():
    """The page reports which step failed, not which one it assumes failed.

    Layer: unit
    Covers: none
    Why this layer: the page said a test failed when the suite was green and the
    smoke step was what went red. The correction is only durable if the name
    comes from the record rather than from a sentence someone wrote once.
    """
    run = {"jobs": [VERIFY_JOB]}
    assert build_site.failed_steps(run, "Verify") == ["Smoke the freshly built instance"]
    assert build_site.failed_steps(run, "Promote") == []


def test_the_step_summary_says_where_a_job_failed():
    """A job row carries its step outcomes.

    Layer: unit
    Covers: none
    Why this layer: a job conclusion alone does not say what went wrong, which
    is how the page came to describe it wrongly in prose.
    """
    summary = build_site.step_summary(VERIFY_JOB)
    assert "Smoke the freshly built instance" in summary
    assert "failed at" in summary

    green = {"steps": [{"name": "Lint", "conclusion": "success"}]}
    assert build_site.step_summary(green) == "1 step, all passed"

    two = {"steps": [{"name": "Lint", "conclusion": "success"}] * 2}
    assert build_site.step_summary(two) == "2 steps, all passed"


def test_skipped_steps_are_left_out_of_the_count():
    """A step that never ran is not counted as one the job did.

    Layer: unit
    Covers: none
    Why this layer: the count reads lower than the row count in GitHub's own
    view, which is a deliberate convention the page states, so it is pinned
    rather than left to look like an off by one.
    """
    job = {
        "steps": [
            {"name": "Lint", "conclusion": "success"},
            {"name": "Export", "conclusion": "skipped"},
        ]
    }
    assert build_site.step_summary(job) == "1 step, all passed"


def test_a_failed_run_with_a_green_suite_is_explained():
    """A `fail` row beside a full pass count gets a line saying why.

    Layer: unit
    Covers: none
    Why this layer: the pairing looks like a broken ledger to anyone reading the
    dashboard, and the explanation has to appear exactly when the pairing does.
    """
    green_and_failed = runs.RunRow(
        run_number=6,
        run_id="30518441807",
        commit_sha="a" * 40,
        branch="main",
        started_at="2026-07-30T03:00:00+00:00",
        result=runs.RESULT_FAIL,
        total=201,
        passed=201,
        failed=0,
        skipped=0,
        duration_seconds=1.0,
        promoted_version="",
    )
    note = build_site.green_suite_but_failed_note([green_and_failed])
    assert "run 6" in note
    assert "not a contradiction" in note

    assert build_site.green_suite_but_failed_note([row(1)]) == ""


def blocked_run(steps: list[dict], run_id: str = "30518441807") -> dict:
    """A post-merge run on main whose verify job failed at the given steps."""
    return {
        "databaseId": int(run_id),
        "headBranch": "main",
        "jobs": [
            {"name": "Verify main", "conclusion": "failure", "steps": steps},
            {"name": "Promote to production", "conclusion": "skipped", "steps": []},
        ],
    }


def ledger_row(run_id: str, passed: int, total: int) -> runs.RunRow:
    """A ledger row for a failed run with the given case counts."""
    return runs.RunRow(
        run_number=6,
        run_id=run_id,
        commit_sha="a" * 40,
        branch="main",
        started_at="2026-07-30T03:00:00+00:00",
        result=runs.RESULT_FAIL,
        total=total,
        passed=passed,
        failed=total - passed,
        skipped=0,
        duration_seconds=1.0,
        promoted_version="",
    )


def inputs_with(ledger: list[runs.RunRow], gh_runs: list[dict]) -> object:
    """Site inputs carrying only what these cases read."""
    return build_site.Inputs(
        rows=(),
        cases=(),
        run_results=None,
        ledger=ledger,
        captured=[],
        openapi=None,
        gh_runs=gh_runs,
        failure_log=None,
        commits={},
        pulls={},
        production=None,
        open_blockers=None,
        sha="a" * 40,
        run_id="1",
        generated_at=datetime.now(UTC),
    )


SMOKE_FAILED = [
    {"name": "Full suite", "conclusion": "success"},
    {"name": build_site.SMOKE_STEP, "conclusion": "failure"},
]
SUITE_FAILED = [
    {"name": "Full suite", "conclusion": "failure"},
    {"name": build_site.SMOKE_STEP, "conclusion": "skipped"},
]


def test_the_note_reports_the_case_count_from_the_ledger():
    """The number in the prose comes from the run, never from the page.

    Layer: unit
    Covers: none
    Why this layer: "no number on this site is typed in" is a claim the site
    makes about itself, and this note is prose with a number in it.
    """
    blocked = blocked_run(SMOKE_FAILED)
    data = inputs_with([ledger_row("30518441807", 201, 201)], [blocked])
    note = build_site.suite_passed_note(build_site.smoke_only_failure(data, blocked))
    assert "All 201 of 201 cases were green" in note
    assert build_site.SMOKE_STEP in note


def test_the_narrative_does_not_render_when_a_real_test_failed():
    """A run where the suite went red gets no paragraph saying it passed.

    Layer: unit
    Covers: none
    Why this layer: this is the failure this predicate exists to prevent. The
    old check asked whether something failed rather than what, so a future run
    with a red suite would have published a confident paragraph asserting the
    opposite of the truth, and the fallback wording made it read as derived.
    """
    blocked = blocked_run(SUITE_FAILED)
    data = inputs_with([ledger_row("30518441807", 180, 201)], [blocked])
    assert build_site.smoke_only_failure(data, blocked) is None
    assert build_site.suite_passed_note(None) == ""
    assert build_site.smoke_claim_rows(None) == ""


def test_the_narrative_does_not_render_without_a_ledger_row():
    """No recorded counts means no claim about the counts.

    Layer: unit
    Covers: none
    Why this layer: the paragraph asserts every case passed, and without the
    row there is nothing that says so. Degrading to vaguer wording was the
    mistake: it kept the assertion and dropped the evidence.
    """
    blocked = blocked_run(SMOKE_FAILED)
    assert build_site.smoke_only_failure(inputs_with([], [blocked]), blocked) is None


def test_the_narrative_does_not_render_when_cases_failed():
    """A ledger row showing failures contradicts the paragraph.

    Layer: unit
    Covers: none
    Why this layer: the smoke step can fail in a run where cases failed too, and
    the paragraph is only true when every case passed.
    """
    blocked = blocked_run(SMOKE_FAILED)
    data = inputs_with([ledger_row("30518441807", 200, 201)], [blocked])
    assert build_site.smoke_only_failure(data, blocked) is None


def test_the_claim_rows_and_the_narrative_stand_or_fall_together():
    """One predicate decides all three claims about that run shape.

    Layer: unit
    Covers: none
    Why this layer: they were decided separately, which is how the rows came to
    render unconditionally while the card said the run had not happened yet.
    """
    blocked = blocked_run(SMOKE_FAILED)
    data = inputs_with([ledger_row("30518441807", 201, 201)], [blocked])
    row = build_site.smoke_only_failure(data, blocked)
    assert row is not None
    assert build_site.suite_passed_note(row)
    assert build_site.smoke_claim_rows(row)

    assert build_site.smoke_only_failure(inputs_with([], []), None) is None
    assert build_site.suite_passed_note(None) == ""
    assert build_site.smoke_claim_rows(None) == ""


# The published case list ------------------------------------------------------


def api_case(case_id="API-01", expects=404, observed=404, outcome="passed"):
    """One joined case, for the checks below."""
    return api_cases.ApiCase(
        case_id=case_id,
        node_id="tests/integration/test_x.py::test_y",
        name="test_y",
        title="A case.",
        layer="integration",
        endpoint="GET /changes/{change_id}",
        expects=expects,
        observed=observed,
        outcome=outcome,
        exchanges=(
            evidence.Exchange(
                method="GET",
                path="/changes/nope",
                request_body=None,
                status=observed,
                response_body={"detail": {"code": "not_found"}},
            ),
        )
        if observed is not None
        else (),
    )


def test_a_case_whose_declared_status_is_not_what_came_back_is_a_disagreement():
    """The page cannot publish a docstring that the run contradicts.

    Layer: unit
    Covers: none
    Why this layer: the join is the whole basis for the case list being a
    result rather than a description, and this is the check that makes it one.
    """
    assert api_cases.disagreements((api_case(),)) == []
    wrong = api_cases.disagreements((api_case(expects=200, observed=404),))
    assert len(wrong) == 1
    assert "declares Expects: 200" in wrong[0]
    assert "returned 404" in wrong[0]


def test_a_failing_case_is_not_also_reported_as_a_disagreement():
    """A red case is already reported as red.

    Layer: unit
    Covers: none
    Why this layer: reporting one defect twice under two names makes a build
    failure harder to read, not easier.
    """
    failing = api_case(expects=200, observed=500, outcome="failed")
    assert api_cases.disagreements((failing,)) == []


def test_a_case_that_did_not_run_still_appears_in_the_list():
    """A case with no captured run is listed as not run, never dropped.

    Layer: unit
    Covers: none
    Why this layer: a case that quietly disappears from the published list is
    how coverage goes missing without anyone noticing.
    """
    absent = api_case(observed=None, outcome="not run")
    assert absent.subject is None
    assert api_cases.disagreements((absent,)) == []


def test_duplicate_and_unannotated_cases_are_reported():
    """Two cases cannot share an ID, and an ID needs an expected status.

    Layer: unit
    Covers: none
    Why this layer: both would corrupt the published list, and neither is
    visible from the page itself.
    """
    assert api_cases.duplicate_ids((api_case(), api_case())) == ["API-01"]
    assert api_cases.missing_expectations((api_case(expects=None),)) == ["API-01"]


def test_cases_are_grouped_in_the_documented_status_order():
    """Created, accepted, then every way a request can be refused.

    Layer: unit
    Covers: none
    Why this layer: the order is the argument the page makes, so it is fixed in
    code rather than left to whatever order the cases happen to be written in.
    """
    grouped = api_cases.by_status(
        (
            api_case("API-01", expects=500, observed=500),
            api_case("API-02", expects=201, observed=201),
            api_case("API-03", expects=404, observed=404),
        )
    )
    assert list(grouped) == [201, 404, 500]


def test_every_status_the_page_explains_has_a_stated_meaning():
    """No status code is published without a plain language meaning.

    Layer: unit
    Covers: none
    Why this layer: the meanings are what make the list readable by someone who
    does not open the repository, which is the whole point of the page.
    """
    assert set(api_cases.STATUS_MEANING) >= {200, 201, 400, 404, 409, 422, 500}
    assert all(text.strip() for text in api_cases.STATUS_MEANING.values())


def test_the_walkthrough_names_cases_that_exist():
    """Every curated entry resolves to a real case.

    Layer: unit
    Covers: none
    Why this layer: the walkthrough is a hand chosen list, which is the one
    place on the page where a rename could silently drop a step out of the
    story rather than fail anything.
    """
    cases = api_cases.build()
    assert api_cases.missing_from_walkthrough(cases) == []
    assert len(api_cases.walkthrough(cases)) == len(api_cases.WALKTHROUGH)


def test_the_walkthrough_keeps_its_narrative_order():
    """The curated order is the order the page shows, not status order.

    Layer: unit
    Covers: none
    Why this layer: sorting by status would break the story the list tells,
    and the default ordering of a case list is by status.
    """
    walk = api_cases.walkthrough(api_cases.build())
    assert [case.name for case in walk] == list(api_cases.WALKTHROUGH)


def test_the_walkthrough_covers_every_status_the_page_explains():
    """The twelve cases between them show each kind of response.

    Layer: unit
    Covers: none
    Why this layer: the curated list is the page, so a status with no case in
    it is a claim the reader never sees evidence for.
    """
    shown = {case.expects for case in api_cases.walkthrough(api_cases.build())}
    assert shown == set(api_cases.STATUS_MEANING)


def test_the_assertion_reads_as_a_sentence():
    """A row says what it checked, not just what it got.

    Layer: unit
    Covers: none
    Why this layer: "404 PASS" makes a reader infer the assertion, and beside a
    500 it reads like a defect. This is the wording that removes the inference.
    """
    assert api_case(expects=404, observed=404).assertion == "expected 404, got 404"
    assert api_case(expects=500, observed=500).assertion == "expected 500, got 500"
    assert "did not run" in api_case(expects=404, observed=None).assertion


def test_a_long_response_body_is_trimmed_for_the_table():
    """A row does not dump an entire document into the page.

    Layer: unit
    Covers: none
    Why this layer: several rows previously printed the whole OpenAPI spec
    inline, which is the wall of text the page exists to avoid.
    """
    short = build_site.trimmed_body({"a": 1})
    assert "more characters" not in short
    long = build_site.trimmed_body({"k": "x" * 4000})
    assert "more characters" in long
    assert len(long) < 1100


def test_the_published_failure_numbers_come_out_of_the_log():
    """Expected and actual are parsed from the run log, not restated beside it.

    Layer: unit
    Covers: none
    Why this layer: those two numbers are the whole point of the failure
    section, and a hand written copy of them is exactly the drift this site
    keeps finding in its own prose.
    """
    lines = [
        "ok    healthz responds",
        "FAIL  a change is created: expected 201, got 500",
        "      the service said: {'unparsed_body': 'Internal Server Error'}",
    ]
    parsed = api_cases.parse_smoke_failure(lines)
    assert parsed == {
        "check": "a change is created",
        "expected": "201",
        "actual": "500",
    }
    assert api_cases.parse_smoke_failure(["ok    healthz responds"]) is None


# Defect reports ---------------------------------------------------------------


def write_defect(tmp_path, body: str):
    """A defect report file, for the parser cases below."""
    path = tmp_path / "DEF-001.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_defect_report_parses_into_fields_and_sections(tmp_path):
    """The report is data, so the page renders it rather than restating it.

    Layer: unit
    Covers: none
    Why this layer: the file is what a person edits, and everything the page
    shows about a defect passes through this parser.
    """
    path = write_defect(
        tmp_path,
        "# DEF-001\n\n**Issue type:** Bug\n**Summary:** A thing broke\n\n"
        "## Root cause\n\nIt was wired wrong.\n",
    )
    report = defects.parse(path)
    assert report.key == "DEF-001"
    assert report.fields["Issue type"] == "Bug"
    assert report.summary == "A thing broke"
    assert report.sections["Root cause"] == "It was wired wrong."


def test_a_report_missing_a_required_field_is_reported(tmp_path):
    """Every required field is named when it is absent.

    Layer: unit
    Covers: none
    Why this layer: the page claims this is what a complete handover looks
    like, so incompleteness has to fail rather than publish quietly.
    """
    report = defects.parse(write_defect(tmp_path, "# DEF-001\n\n**Issue type:** Bug\n"))
    problems = report.problems
    assert any("Severity" in problem for problem in problems)
    assert any("Steps to reproduce" in problem for problem in problems)


def test_commit_and_pull_references_are_identifiers(tmp_path):
    """Only values that look like a SHA or a number are resolved.

    Layer: unit
    Covers: none
    Why this layer: a prose value would render as unlinked text, which reads as
    a reference to something the reader cannot open.
    """
    report = defects.parse(
        write_defect(
            tmp_path,
            "# DEF-001\n\n**Affects commit:** 383565e\n**Fix commit:** not yet\n"
            "**Fix pull request:** 5\n**Introduced by pull request:** unknown\n",
        )
    )
    assert report.commits() == {"Affects commit": "383565e"}
    assert report.pulls() == {"Fix pull request": 5}


def test_the_ordering_pair_comes_from_the_commits(tmp_path):
    """Red before green is shown as two timestamps, not asserted in prose.

    Layer: unit
    Covers: none
    Why this layer: the claim is the strongest one the defect page makes, and
    it is only worth anything if the two values behind it are visible.
    """
    report = defects.parse(
        write_defect(
            tmp_path,
            "# DEF-001\n\n**Regression commit:** 5f05880\n**Fix commit:** 2e3dce5\n",
        )
    )
    commits = {
        "5f05880": {"authored_at": "2026-07-30T02:19:21Z"},
        "2e3dce5": {"authored_at": "2026-07-30T02:19:50Z"},
    }
    regression_at, fix_at = defects.ordering(commits, report)
    assert regression_at < fix_at
    assert defects.ordering({}, report) is None


def test_the_gap_between_two_commits_is_derived():
    """The page states how far apart the two commits were.

    Layer: unit
    Covers: none
    Why this layer: at minute resolution the two timestamps render identically,
    which leaves a published claim the reader cannot check from the values.
    """
    gap = build_site.seconds_between("2026-07-30T02:19:21Z", "2026-07-30T02:19:50Z")
    assert "29 seconds later" in gap
    assert build_site.seconds_between("2026-07-30T02:19:50Z", "2026-07-30T02:19:21Z") == ""
