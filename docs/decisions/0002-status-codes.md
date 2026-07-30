# 0002: 422 means unreadable, 400 means refused

**Date:** 2026-07-29
**Status:** accepted

## The fork

A well formed submission that breaks a gate rule could return 422 (the same code
the framework uses for schema errors), 409, or 400.

## The decision

- **422**: the payload could not be read. Wrong type, missing required field,
  naive timestamp, unknown field. Produced by the framework.
- **400**: the payload was read and understood, and the gate refused it. Carries
  every violation with its requirement ID.
- **409**: the request conflicts with the current state of the record. Illegal
  transitions, and submitting something that is not in Draft.
- **404**: no such change.

## Why

Reusing 422 for refusals would make "I could not parse this" and "I read it and
the answer is no" indistinguishable in any metric, log filter or alert built on
status codes. Those are different events for different people: the first is a
caller with a bug, the second is a change that is not ready.

Returning 200 with `{"accepted": false}` was considered and rejected for the
same reason. A gate refusal that looks like a success in the access log is a
refusal nobody counts.

## Consequence

The status code matrix is 200, 201, 400, 404, 409 and 422, and every one of them
is documented in the OpenAPI spec with a body schema. The contract layer asserts
that, so an undocumented error shape fails the build.
