# Test design

Written before the suite was built. That ordering is the point: a layer choice
made after the tests exist is a description, not a decision.

Three layers, and every test states which one it is in and why it is not in a
different one. A test whose layer choice cannot be justified is at the wrong
layer.

| Layer | Marker | What it runs against | What it is for |
|---|---|---|---|
| Unit | `unit` | imported functions, no HTTP, no database | rule logic and boundaries |
| Contract | `contract` | the generated OpenAPI document and live response bodies | the shape of the interface, both directions |
| Integration | `integration` | the running application through HTTP | the endpoint, the store and the rules working together |
| Meta | `meta` | the repository itself | gates that keep the other three honest |

The suite has no performance layer, no security scanning and no browser layer.
Those are out of scope in `docs/requirements.md` and adding them here would be
coverage of a claim nobody is making.

---

## Layer choice per rule

The second column is the one that carries the argument. "Why not another layer"
is answered for every rule rather than for the set as a whole.

### REQ-1.1 rollback plan

**Unit, with one integration case.** The rule is a single predicate over one
field, so the cheapest honest place to test it is the function. The integration
case exists for a different reason: to prove the violation reaches the caller in
the response body with the rule ID attached. Testing all of REQ-1.1 through HTTP
would buy nothing and cost a request per assertion.

### REQ-1.2 test evidence

**Unit for the table, integration for one case.** Three environments crossed
with a passed flag is a subset table, and tables belong at the unit layer where
a case costs a function call rather than an HTTP round trip. One case is
repeated at the integration layer because the failure mode it catches lives in
the endpoint rather than the rule: an endpoint that short circuits on an earlier
violation would never reach this rule, and no unit test can see that.

The table is the full subset of three environments rather than a sampling. It is
eight rows, every one of them cheap, and the exhaustive version removes the
question of which omission was worth testing.

### REQ-1.3 team membership

**Unit.** The roster is injected into `evaluate`, so the unit test supplies its
own roster and does not depend on the seeded data. No integration case: nothing
about HTTP changes the answer, and an integration case here would be testing the
seed rather than the rule.

### REQ-1.4 linked Jira ticket

**Unit.** Absent, blank and malformed are three cases against one regular
expression. The interesting content is the boundary between "a string" and "a
tracker key", which is invisible at the HTTP layer.

### REQ-1.5 and REQ-1.5a promotion path

**Unit.** Two failure modes (a missing stage, and stages merged out of order)
and both need constructed timestamps. Constructing those through JSON payloads
would make the case harder to read without testing anything the function does
not already decide.

### REQ-1.6 on call matrix

**Unit for the matrix and the window boundaries, integration for the SPA row.**
The matrix is four release types by five roles, which is unit work. The window
coverage rule has a real boundary (a window that starts one second after
implementation starts does not cover it) and boundary pairs are written on both
sides at the unit layer.

The SPA row gets an integration case on purpose. It is the row a lazy
implementation gets wrong, because "Prod Support is always required" is the
plausible wrong rule, and the case that catches it is worth having at the layer
a reviewer actually reads.

### REQ-1.7 fix version

**Unit, and partially uncovered. See stated gaps.** The implemented half (a fix
version carrying tickets that are neither resolved nor closed is refused) is a
predicate over seeded reference data, so it is unit work.

### REQ-2 state machine

**Unit for the graph, integration for the status code.** Every illegal
transition is a negative case, and there are more than fifty pairs. Enumerating
them at the HTTP layer would be fifty requests to learn what fifty function calls
already prove, so the unit layer walks the whole matrix and asserts that legality
matches the table.

Integration covers a much smaller thing that unit cannot see: that an illegal
move is a 409 with a machine readable body naming the refusing rule, and that a
legal move persists. REQ-2.1, REQ-2.2 and REQ-2.3 each get their own integration
case because those three are named in the requirements and a reviewer will look
for them by name.

### The interface itself

**Contract.** Response bodies are validated against the schema in the generated
OpenAPI document, resolved through its references. This is a separate layer from
integration because it answers a different question: integration asks whether
the endpoint behaves, contract asks whether the published description of the
endpoint is true. A service can pass every integration test while publishing a
spec that lies, and consumers read the spec.

The spec is generated from the application, never hand maintained, so the
contract layer can only be satisfied by changing the application.

### The gates

**Meta.** Endpoint coverage in both directions, the layer declaration
convention, the requirement to test traceability, and the em dash guard run
against the repository rather than against the service. They are marked `meta`
so they can be reported separately: they are checks on the suite, and counting
them as coverage of the service would inflate the number.

---

## Stated gaps

What this suite does not cover, written before the suite existed so it is a
design decision rather than an excuse.

**Every entry below is machine checked.** Each one names the requirements it is
about, whether they are untested or partly tested, and the reason. Three rules
are enforced by `tests/meta/test_traceability.py` and fail the build:

1. An entry with no reason does not declare anything. Pasting a requirement ID
   under this heading is not a gap declaration, so it cannot silently turn an
   untested requirement into an accepted one.
2. An entry that says `Coverage: none` must stay true. The moment any test
   claims one of its requirements, the build fails and the entry has to be
   rewritten or removed. That is per entry, not "at least one gap somewhere".
3. An entry that says `Coverage: partial` must have at least one test on each
   requirement it names, so a partial claim cannot cover a total absence.

A gap may also name a test that guards the mechanism the requirement depends on.
That is not coverage of the requirement and it is not counted as coverage
anywhere. It is the difference between "we test this rule" and "we test that the
thing enforcing this rule is still wired up".

### GAP-1: REQ-3 is enforced by the pipeline, so no test in this repository can assert it

**Requirements:** REQ-3, REQ-3.1, REQ-3.2, REQ-3.3
**Coverage:** none
**Guarded by:** tests/meta/test_pipeline_contract.py::test_promotion_depends_on_verification
**Reason:** REQ-3 says a change reaches production only when the regression suite
passes against the merged result. That is enforced by `promote` carrying
`needs: verify` in the workflow, and by nothing inside the service. A pytest case
can read the workflow file, which is what the guard above does, but reading a
file is not the same as observing that GitHub refused to promote. The only
evidence that carries the claim is a post-merge run on `main` in which
verification failed and promotion did not run. A run on a `ci/**` branch cannot
carry it, because promotion is also skipped there by the branch condition, so the
outcome would be identical with a green suite.

### GAP-2: REQ-1.7 does not check whether a ticket could reach the branch

**Requirements:** REQ-1.7
**Coverage:** partial
**Reason:** The requirement says the fix version must not contain open or
unresolved tickets that could reach the branch. The service checks the first half
(tickets on the fix version that are neither resolved nor closed) and does not
check the second half at all, because reachability is a question about version
control and this service has no repository integration. Covering it would mean
building a fake that proves nothing, or calling a real forge, which would make
the badge depend on a third party.

### GAP-3: concurrent submissions are not tested

**Requirements:** none
**Coverage:** none
**Reason:** Two submissions of the same change at the same moment could both read
Draft and both write Submitted. The service is single process with one SQLite
connection so the window is small, and no requirement states an idempotency or
locking rule to test against. It is recorded as a known hole rather than left
out quietly, because the absence of a requirement is not the same as the absence
of a risk.

### GAP-4: no load, performance or security testing

**Requirements:** none
**Coverage:** none
**Reason:** All three are out of scope in the requirements, and the reasoning is
in `docs/decisions/0005-no-browser-layer.md`. There is no stated throughput or
latency criterion to test against, and a load test with an invented threshold
measures nothing. Security scanning is not a claim this project makes.

### GAP-5: the reference data is seeded, not integrated

**Requirements:** none
**Coverage:** none
**Reason:** The team roster and the ticket tracker are fixed tables in
`app/reference.py`. The tests prove the rules read them correctly. Nothing here
proves the service would read a real directory or a real tracker correctly, and
the seams where that would break (authentication, pagination, partial failure)
have no coverage at all.

### GAP-6: timezone handling is tested only through aware timestamps

**Requirements:** none
**Coverage:** none
**Reason:** The schema refuses naive datetimes and that is asserted, but no case
crosses a daylight saving boundary or an implementation window that spans one.
The on call window comparison in REQ-1.6 is where that would matter.

---

## Open questions

Flagged rather than resolved by invention.

**RESOLVED BY REMOVAL, 2026-07-29: does the emergency exemption reach REQ-1.5?**
The question was whether an emergency change, exempt from the BAT sign off under
REQ-1.2a, still had to show a merge request at the BAT stage of the promotion
path in REQ-1.5. It was pinned by a test rather than answered.

It is now moot. Keoni removed emergency and hotfix changes from the service
entirely, so there is no exempt class and no exemption to scope. Recorded here
because the distinction matters: the ambiguity was not resolved by choosing a
reading, it was removed by deleting the feature that created it. If emergency
changes ever return, the question returns with them unanswered.

**OPEN, DECIDED BY THE TEAM RATHER THAN BY THE AUTHOR: a fix version with no
tickets recorded.** REQ-1.7 refuses a fix version carrying unresolved tickets. A
fix version the tracker has never heard of carries none, so the current reading
accepts it. The opposite reading is defensible and arguably stronger: an unknown
fix version means REQ-1.7 cannot be evaluated at all, and a gate that cannot
evaluate its own rule should not pass the change.

The current behaviour is pinned by a test. **The call to leave it as accept was
made by the team, not by the author of the requirements**, and it is recorded
that way so it can be overturned without anyone having to dig for who decided
it. If it is overturned, the test that pins it is the one that changes.
