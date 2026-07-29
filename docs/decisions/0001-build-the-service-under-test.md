# 0001: build the service under test rather than testing a public API

**Date:** 2026-07-29
**Status:** accepted

## The fork

Test a third party practice API, or build the service being tested.

## The decision

Build it. FastAPI and SQLite, no auth provider, no hosting, no frontend.

## Why

1. **Post-merge testing requires that a merge changes something.** If the target
   were somebody else's API, a merge here would not affect it and the post-merge
   pipeline would be theatre. This reason alone settles it.
2. **Contract testing requires owning the contract.** You cannot honestly
   contract test a service whose OpenAPI document you do not control.
3. **A defect can be introduced deliberately** to prove the gate catches it. You
   cannot do that to a third party.
4. **No third party flakiness in the badge.** Red means the code is wrong.

## The counter, and the answer

A reviewer may say: of course the tests pass, the service was designed to be
testable. That is true and it is the point. Deterministic state, an injectable
clock and machine readable errors are properties a QA lead asks engineering for,
so the service has them on purpose and says so. See decision 0003.

## Cost accepted

The service is a fixture, so effort spent deepening the domain is effort not
spent on the test design. The rule set is capped at what
`docs/requirements.md` states and no more.
