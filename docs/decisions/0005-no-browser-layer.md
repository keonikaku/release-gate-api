# 0005: no browser layer, no performance layer, no security scanning

**Date:** 2026-07-29
**Status:** accepted

## The decision

Three layers of tests plus a meta layer. No UI to drive, no load test, no
dependency or code scanning.

## Why no browser layer

A thin UI would have to be built purely so it could be recorded, which is a whole
build surface added to a repository whose point is the test design. It would also
undercut the argument the project is making. A suite that drives a browser to
assert a rule that a function call could assert is the definition of a test at
the wrong layer, and this repository fails its own build for that.

The visual artifact is the pipeline: a merge, a run graph, a promotion that
either happens or is skipped.

## Why no performance or load testing

It is the most common suggestion at this point in a portfolio and it evidences
nothing anyone is asking about here. The requirements state no throughput or
latency criterion, so there is no threshold to test against, and a load test with
an invented threshold is decoration.

## Why no security scanning

Not a claim being made. The credential guard in
`tests/meta/test_prose_guards.py` exists because the service needs no secret and
that should stay true, which is a different and much narrower thing than a
security posture.

## Consequence

These absences are written into the stated gaps section of `docs/test-design.md`
rather than left for a reviewer to notice.
