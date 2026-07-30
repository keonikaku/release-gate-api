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

**It keeps the ledger out of the way of ordinary work.** The file is not on the
branch people commit to, so it is not touched by a normal change.

**It keeps `main` readable.** A repository whose history is half machine written
publish commits is harder to inspect, and inspectable history is one of the
things this project is evidence of.

## Correction, 2026-07-30: what is actually enforced

The first version of this record said the branch layout made "written only by CI"
structural. **It did not, and the sentence was doing work the mechanism could not
support.** Review found that `gh-pages` had no protection at all, that force
pushes and deletions were unrestricted, and that a human commit (the one that
created the branch) was already sitting on it.

A repository ruleset that allows only the Actions app to push is not available
here: GitHub refuses the Actions integration as a bypass actor on a personal
repository, so a rule that blocked people would block the publish job too. What
is in place instead, and what the site now claims, is exactly this:

| Control | Enforced by |
|---|---|
| History on `gh-pages` cannot be rewritten or deleted | branch protection: force pushes and deletions refused |
| A commit CI did not write stops the next publish | `tools/provenance.py`, run before anything is appended |
| A row naming a run GitHub has no record of stops the publish | `tools/runs.py`, cross checked against the run list |
| Run numbers only ever increase | `tools/runs.py` |
| The ledger and the site never appear on `main` | `tests/meta/test_pipeline_contract.py` |

A person with write access can still push to the branch. What they cannot do is
push to it and have the next publish carry on as though nothing happened, or
remove the evidence that they did. That is a weaker claim than the one this
document originally made, and it is the true one.

## Consequence

The dashboard is regenerated in full on every post-merge run, including runs
where verification failed. That is deliberate: a ledger that only grows on green
days would show a pass rate of one hundred percent and evidence nothing.
