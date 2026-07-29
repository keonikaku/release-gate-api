# 0004: the published badge is the post-merge workflow

**Date:** 2026-07-29
**Status:** accepted

## The fork

Badge the pre-merge gate, which is the common choice, or badge the post-merge
verification.

## The decision

Post-merge, first badge in the README. The PR gate is second.

## Why

A pre-merge badge says the last pull request passed its checks. A post-merge
badge says the code on `main` right now passes. The second is the claim worth
making, because merge is not done.

It is only safe to make because the service under test is in this repository.
Nothing in the job touches a third party, so red means the code is genuinely
broken. A badge wired to something the author does not control teaches everyone
who looks at it to ignore it, at which point it costs credibility rather than
earning it.

## Risk accepted

A red badge on a public profile costs something while its owner is job hunting.
The PR gate makes a red `main` unlikely, and when it happens the documented
response in `docs/quality-gates.md` is revert first and fix forward. The recovery
is itself the demonstration.

## Consequence

Deliberately red runs (the defect cycle, and the second run of the two run demo)
happen on branches. CI runs on pull requests and on `main`, and the badge is
pinned to `main`, so a red branch run is fully visible in run history and can
never reach the badge. That separation is load bearing and must not be
simplified away.
