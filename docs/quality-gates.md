# Quality gates

What has to be green before a change lands, what happens when something goes
red, and who actually enforces each rule. Every rule below names the file that
implements it, so the two can be checked against each other.

**On enforcement, plainly.** Two of the rules here are enforced by the platform
and the rest are enforced by the person merging. Each row says which. A document
that claims an enforcement mechanism it does not have is worse than one that
admits the mechanism is a human.

---

## The gates

| Gate | File | Enforced by | Required green to merge |
|---|---|---|---|
| Lint and format | `.github/workflows/pr-gate.yml` | the workflow, on every pull request | yes |
| All four test layers | `.github/workflows/pr-gate.yml` | the workflow | yes |
| Collection integrity | `.github/workflows/pr-gate.yml` | the workflow | yes |
| Traceability | `tests/meta/test_traceability.py` | the suite, so both workflows | yes |
| Endpoint coverage | `tests/meta/test_endpoint_coverage.py` | the suite | yes |
| Layer declaration | `tests/meta/test_layer_declarations.py` | the suite | yes |
| No em dash, no credential literal | `tests/meta/test_prose_guards.py` | the suite | yes |
| Post-merge verification | `.github/workflows/post-merge.yml`, job `verify` | the workflow | runs after the merge |
| Promotion | `.github/workflows/post-merge.yml`, job `promote` | `needs: verify`, so by GitHub | not applicable |
| Evidence publishing | `.github/workflows/post-merge.yml`, job `publish` | the workflow, on `main` only | runs after every post-merge run, green or red |
| Evidence history cannot be rewritten | branch protection on `gh-pages` | GitHub: force pushes and deletions refused | not applicable |
| The ledger is machine written | `tools/provenance.py`, `tools/runs.py` | the publish job, which stops if the branch carries a commit CI did not write, or if a row names a run GitHub has no record of | yes |
| Not squash merging | repository setting | GitHub: squash and rebase merging are disabled | yes, by the platform |
| Regression test written before its fix | convention | the person writing it | yes, by convention |

---

## What each gate is for

### The PR gate: is this safe to land

Runs on Python 3.12 and 3.13. Lint, format, the four layers separately so a
failure names the layer, then collection integrity. Collection integrity is the
one worth explaining: it counts the tests in each layer and fails if the totals
do not add up, which catches a test that arrived without a layer marker and
would otherwise be reported in no layer at all. It also fails if the unit layer
stops being the widest, so the pyramid is a measurement rather than a drawing.

### Post-merge `verify`: is main shippable right now

The full suite, then a smoke run against a freshly built instance served over
HTTP on a database that did not exist a moment ago (`tools/smoke.py`). The suite
drives the application in process, which is fast and proves nothing about
serving. Both are worth having and they answer different questions.

### Post-merge `publish`: what the run leaves behind

Runs whether verification passed or failed, and whether promotion happened or was
skipped. It appends one row to the ledger on `gh-pages` and regenerates the
evidence site from this run's artifacts: the JUnit report, the captured
exchanges, the generated OpenAPI document, and GitHub's own record of the runs.

A dashboard that only updates on green days would show a pass rate of one hundred
percent and evidence nothing, so the failing runs are recorded too. See
`docs/decisions/0006-evidence-lives-on-its-own-branch.md`.

### Post-merge `promote`: does this version go to production

Carries `needs: verify`. There is no hosting in this project and none is wanted,
so production is concretely the newest promoted tag. When verification fails,
promotion is skipped by GitHub, the previously promoted tag stays the newest
one, and `main` sits ahead of production until a fix lands. That is REQ-3.1,
REQ-3.2 and REQ-3.3, and the evidence is the run graph.

---

## The documented response when post-merge goes red

**Revert first, fix forward.** The merge commit is reverted so `main` returns to
a shippable state, then the fix goes through the defect cycle on a branch. That
is a release management instinct rather than an engineering one, and it is
written here so the response is a procedure rather than a judgement call made
under pressure.

The defect cycle, from the first defect onward:

1. Name the existing test case that should have caught it, and say why it
   missed. That step is the one that changes the suite rather than just the
   code.
2. Write the regression test first. CI goes red.
3. Fix. CI goes green.
4. Row in the defect log, linking the red run and the green run.

**Write the regression test before the fix.** The value is not tidiness, it is
that GitHub's timestamped run history then shows red before green in that order,
and nobody can retrofit that ordering later. This property must not be tidied
away by squashing or by amending the red commit out of existence.

---

## History rules

**No squash merging, and no amending away a wrong first attempt.** The instinct
is to tidy history. Tidying history destroys the only evidence that the review
step is real. Correction commits stay, and their messages say what was wrong.

**CI runs on pull requests and on `main`.** A deliberately red run on a branch is
visible in run history and cannot reach the badge, which is pinned to `main`.
That property is what makes the defect cycle safe to run in public, so it should
not be "fixed" later.
