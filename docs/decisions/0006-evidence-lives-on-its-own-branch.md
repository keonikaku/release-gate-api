# 0006: the ledger and the published site live on their own branch

**Date:** 2026-07-30
**Status:** accepted

## The fork

The run ledger has to be appended by CI on every post-merge run. It could be
committed to `main`, or it could live somewhere else.

## The decision

`results/runs.csv` and the generated site live on `gh-pages`. Neither is tracked
on `main`. The publish job is the only thing that writes them.

## Why

**Committing to `main` from CI creates a loop.** A push to `main` triggers the
post-merge workflow, which would push to `main` again. The usual answer is a
`[skip ci]` marker in the commit message, which works until someone changes the
message.

**It makes the claim structural rather than promised.** The site says the ledger
is written only by CI. On this arrangement that is not a policy anyone has to
follow: the file is not on the branch people commit to, so there is no ordinary
change in which a person could edit it.

**It keeps `main` readable.** A repository whose history is half machine written
publish commits is harder to inspect, and inspectable history is one of the
things this project is evidence of.

## What still checks it

The structural guarantee is not left on its own, because a guarantee nothing
verifies is another promise. `tools/runs.py` refuses to append to a ledger whose
run numbers do not increase or whose run IDs repeat, and the publish job fails
with it. `tests/meta/test_pipeline_contract.py` fails the build if the ledger or
the generated site ever appears on `main`.

## Consequence

The dashboard is regenerated in full on every post-merge run, including runs
where verification failed. That is deliberate: a ledger that only grows on green
days would show a pass rate of one hundred percent and evidence nothing.
