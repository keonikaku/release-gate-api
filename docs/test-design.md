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

### REQ-1.2 and REQ-1.2a test evidence, and the emergency exemption

**Unit for the matrix, integration for one exemption case.** There are four
change classes crossed with three environments and a passed flag, which is a
table. Tables belong at the unit layer where a case costs a function call. The
exemption (emergency and hotfix drop BAT and keep everything else) gets one
integration case because it is the rule most likely to be broken by a change to
the endpoint rather than to the rule, for instance by an endpoint that
short circuits validation for emergencies.

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
design decision rather than an excuse. The traceability table reflects these.

**REQ-1.7 is partially covered.** The requirement says the fix version must not
contain open or unresolved tickets *that could reach the branch*. The service
checks the first half (tickets on the fix version that are not resolved or
closed) and does not check the second half at all, because reachability is a
question about version control and this service has no repository integration.
Covering it would mean either building a fake that proves nothing or calling a
real forge, which would make the badge depend on a third party. The traceability
table records REQ-1.7 as PARTIAL rather than green.

**REQ-3 is not covered by this suite at all.** REQ-3.1, REQ-3.2 and REQ-3.3 are
enforced by the pipeline, not by the service, so no pytest case can assert them.
The evidence for REQ-3 is the run graph of `post-merge.yml`: `promote` carries
`needs: verify`, so a failing suite leaves `promote` skipped and the previously
promoted tag in place. That is GitHub's record rather than this repository's
claim, and it is linked from the traceability table instead of a test ID.

**Concurrency is not tested.** Two submissions of the same change at the same
moment could both read Draft and both write Submitted. The service is
single process with one SQLite connection, so the window is small, and no
requirement states an idempotency or locking rule to test against. Recorded as a
known hole rather than quietly left out.

**No load, performance or security testing.** Out of scope in the requirements.

**The reference data is seeded, not integrated.** The roster and the ticket
tracker are fixed tables. Tests prove the rules read them correctly. Nothing here
proves the service would read a real directory or a real tracker correctly.

**Timezone handling is tested only through aware timestamps.** The schema
refuses naive datetimes, which is asserted, but no case crosses a daylight
saving boundary.

---

## Open questions

Flagged rather than resolved by invention.

**PENDING CLARIFICATION: does the emergency exemption reach REQ-1.5?**
REQ-1.2a exempts emergency and hotfix changes from "the BAT sign off
requirement" and says all other evidence is still required. That is unambiguous
for REQ-1.2 test evidence. It is not clear whether an emergency change must still
show a merge request at the BAT stage of the promotion path in REQ-1.5. The
service implements the narrow reading: the exemption applies to REQ-1.2 only, and
an emergency change still needs the full promotion path. A test pins that reading
so it cannot drift silently, and the test says in its docstring that it is
pinning an ambiguous decision rather than asserting a settled rule.

**PENDING CLARIFICATION: a fix version with no tickets recorded.**
REQ-1.7 refuses a fix version carrying unresolved tickets. A fix version the
tracker has never heard of carries none, so the current reading accepts it. The
opposite reading (an unknown fix version is itself unevidenced and should be
refused) is defensible. Pinned by a test, same treatment.
