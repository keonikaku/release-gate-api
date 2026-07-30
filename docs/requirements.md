# Release Gate API: requirements

**Author:** Keoni Kakugawa
**Status:** Agreed 2026-07-29
**Purpose:** The service under test. The domain is a release gate; the thing being demonstrated is QA management.

---

## Scope

The gate answers one question: **is this change allowed to proceed to production?**

It answers it on testing evidence. Risk scoring, freeze windows, approval routing and conflict detection are deliberately out of scope. Those are release-manager concerns and they are not what this project is evidencing.

---

## REQ-1: Submission validation

A change request is rejected if any of the following is true.

| ID | Rule |
|---|---|
| REQ-1.1 | No rollback plan is attached. |
| REQ-1.2 | No evidence of testing in dev, QA and BAT. |
| REQ-1.3 | The submitter is not a member of the owning scrum team. |
| REQ-1.4 | No Jira ticket is linked. |
| REQ-1.5 | No merge request exists in a lower environment, meaning the change did not follow the promotion path. |
| REQ-1.6 | A role required for the release type has no named on-call for the implementation window. |
| REQ-1.7 | The fix version contains open or unresolved tickets that could reach the branch. |

There are no exemptions. Every change carries the full evidence requirement. An
earlier draft exempted emergency and hotfix changes from the BAT sign off; that
class of change was removed from the service entirely on 2026-07-29, so the
exemption no longer exists rather than having been resolved one way or the other.

**REQ-1.5a** The promotion path is REG/SIT, then INT, then non-live/BAT, then production. Each stage must be evidenced in order.

### REQ-1.6 on-call matrix

| Release type | Required on call |
|---|---|
| Small (one-line change, or 2 to 3 small bug fixes) | Dev, Business |
| Sprint | DevOps, Prod Support, Dev, Tech Lead |
| Monorepo deployment | DevOps, Prod Support |
| SPA | DevOps, Tech Lead |

Release type is declared by the submitter. The system trusts the declaration and validates the roles against it.

Note the SPA row: Prod Support is deliberately not required. An implementation that always requires Prod Support is wrong.

---

## REQ-2: State machine

Draft → Submitted → Approved → Scheduled → Implementing → Verified → Closed

| ID | Rule |
|---|---|
| REQ-2.1 | A change may be cancelled from any state before Implementing. |
| REQ-2.2 | Once Implementing has started, the change cannot return to Approved. |
| REQ-2.3 | Failed verification moves to Rolled Back. It never moves straight to Closed. |

---

## REQ-3: The QA gate

| ID | Rule |
|---|---|
| REQ-3.1 | A change may only be promoted to production if the regression suite passes against the merged result. |
| REQ-3.2 | If any test in the suite fails, promotion does not run. |
| REQ-3.3 | A blocked promotion leaves production on the previously promoted version. |

This is the rule the whole project exists to demonstrate. It is enforced by the pipeline, not by the service.

---

## Out of scope, deliberately

Risk scoring. Freeze windows. Approval routing and approver counts. Conflict detection between overlapping changes. Performance testing. Security scanning. Browser UI.

Each was considered and cut. The reasons are in the decision log.
