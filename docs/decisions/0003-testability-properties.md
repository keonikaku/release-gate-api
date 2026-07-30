# 0003: the service is built for testability, and the properties are asserted

**Date:** 2026-07-29
**Status:** accepted

## The decision

Three properties, each one enforced by a test rather than described in a README.

| Property | How it is built | What holds it true |
|---|---|---|
| No hidden clock | `app/clock.py` is the only module that reads wall time; everything else takes a clock argument | `tests/unit/test_testability_properties.py` parses `app/` and fails if any other module calls `now`, `utcnow` or `today` |
| Deterministic state | the roster and the ticket tracker are fixed tables in `app/reference.py`, and both are injectable into `evaluate` | unit cases supply their own roster and tickets, so they cannot pass because of the seed |
| Machine readable errors | every violation carries a requirement ID; every error body has a `code` | the contract layer validates each error body against the schema the spec declares |

## Why it is written down rather than left implicit

A reviewer's fair objection to any self built target is that the tests pass
because the author made them easy. The answer is not to deny it. Designing for
testability is a QA leadership skill, so the properties are named, and each one
is held in place by something that fails the build when it stops being true.

## What was rejected

An in memory dictionary instead of SQLite. It would have been simpler and it
would have removed the one interesting integration question in the project:
whether a state written by one request is read by the next.
