# Verdict Gates — Security QA Post-Fix Verification

Three possible verdicts. Each has explicit gates that must **all** pass.
If gates for neither READY FOR DEPLOYMENT nor RETURN TO OPEN are fully met,
the verdict is BLOCKED — NO VERDICT.

---

## READY FOR DEPLOYMENT

**Meaning:** The fix resolves the reported vulnerability. The exploit is blocked
by the intended security control. Recommend proceeding to production deployment.

**All gates must pass:**

| # | Gate | What constitutes passing |
|---|------|------------------------|
| G1 | Complete exploit attempted | The full original exploit sequence (or security-equivalent) was executed at runtime against the QA build, on the correct endpoint/path. Partial attempts or skipped steps fail this gate. |
| G2 | Intended control blocked it | The security control the fix introduced (or corrected) produced the expected denial response (e.g. `PARTNER_ACCESS_DENIED`, HTTP 403, empty result set, access denied). The denial must come from the **intended code path**, not a side-effect. |
| G3 | Positive control succeeded | A meaningful positive control — the same operation by an authorized actor on the same API path — returned the expected success response. This proves the code path is exercised and the denial is specific to the unauthorized case. |
| G4 | Correct context exercised | The test used the correct role, tenant/partner_id, feature flags, plugins, and configuration that the original report described. A test under different conditions does not validate the fix for the reported conditions. |
| G5 | Deployment correspondence | The QA build demonstrably contains the fix commit(s). Verified by: commit SHA in build metadata, deployment logs, or a code-level check that the patched code path is present. Version strings alone are insufficient without mapping to the fix commits. |
| G6 | Victim integrity verified | The victim's data (entries, metadata, permissions) was not leaked, modified, or corrupted during testing. Checked by re-reading victim objects after the exploit attempt. |
| G7 | Cleanup completed and verified | All test objects, sessions, and tokens created during the run were removed or reverted, and removal was verified. |

---

## RETURN TO OPEN

**Meaning:** The fix does not resolve the reported vulnerability. The exploit
still succeeds on the QA build. Recommend returning the ticket to Open for
further remediation.

**All gates must pass:**

| # | Gate | What constitutes passing |
|---|------|------------------------|
| R1 | Real boundary reproduced | The actual security boundary violation described in the report (or the equivalent claimed impact) was reproduced at runtime on the QA build. The reproduction must match the report's described exploit path, not a different vulnerability. |
| R2 | Real controlled objects | The exploit used real, existing objects (entries, users, partners) in the QA environment — not fabricated IDs, placeholder values, or nonexistent resources. |
| R3 | Positive control succeeded | A positive control confirmed the test path is valid and the environment is functioning correctly. Without this, an exploit "success" could be a test-environment artifact. |
| R4 | Impact independently verified | The impact was verified independently of the exploit request itself. For example: confirming that cross-tenant data was actually returned, that a privilege escalation actually persists, that modified data is visible to the victim. |
| R5 | Cleanup completed or documented | Either cleanup was completed, or the exact items remaining and the person/action required to clean them up are documented in evidence and the Jira comment. |

---

## BLOCKED — NO VERDICT

**Meaning:** Insufficient runtime evidence exists to conclude either way.
The ticket remains in its current state pending resolution of the blocker(s).

This is the **default** verdict. It applies whenever:
- Any gate for READY FOR DEPLOYMENT is not met, AND
- Any gate for RETURN TO OPEN is not met.

The verdict comment must state:
- Which specific gate(s) could not be satisfied.
- What evidence is missing.
- What action is needed to unblock (and by whom).

---

## Prohibited verdict bases

The following are **never** sufficient on their own to issue READY FOR DEPLOYMENT
or RETURN TO OPEN. Each may be supporting evidence but cannot be the sole basis.

| Prohibited basis | Why it is insufficient | What to do instead |
|-----------------|----------------------|-------------------|
| **Source-code review alone** | Code shows intent, not runtime behavior. A fix may be correct in source but not deployed, not reached, or bypassed by a different path. | Use code review to plan the exploit attempt, then execute at runtime. |
| **Unit tests alone** | Unit tests verify isolated logic, not the full request path through auth, middleware, and deployment configuration. | Unit test results are supporting evidence; runtime verification is required. |
| **Open/merged PR state alone** | A merged PR may not be deployed to QA, may be reverted, or may not cover the full exploit path. | Confirm deployment correspondence (G5) and then test at runtime. |
| **`SERVICE_FORBIDDEN` before reaching the intended code path** | This typically means the service/action is disabled or the KS type is wrong — not that the security control works. The exploit never reached the vulnerable code. | Identify why SERVICE_FORBIDDEN fires and whether it is the fix or a configuration issue. Adjust the test to reach the intended path. |
| **`INTERNAL_SERVER_ERROR`** | A server crash is not a security control. It may mask the vulnerability (the data might still leak before the crash) or indicate a regression. | Investigate the error. A crash does not prove the fix works; it proves something is broken. |
| **Fabricated or nonexistent IDs** | Testing with `0_doesnotexist` proves the system handles missing objects, not that it enforces the security boundary for real objects. | Use real controlled test objects that exist in the QA environment. |
| **Same-partner-only controls** | If the report claims cross-tenant access, testing only within the attacker's own tenant proves nothing about the tenant boundary. | Use a separate victim tenant/partner_id. |
| **Endpoint unavailability** | An endpoint returning 404 or being unroutable is not a fix — it may be a deployment gap, a routing change, or a temporary state. | Confirm whether the endpoint should exist. If it was intentionally removed as the fix, verify removal is the documented remediation and it is permanent. |
| **Version strings without deployment mapping** | A version number or build tag does not prove the fix commit is included. Build pipelines, cherry-picks, and reverts can produce version numbers that do not contain the expected code. | Map the version/build to specific commit SHAs and verify the fix diff is present. |
| **Different role/route/product/feature configuration** | Testing a different role (e.g. admin when the report used a regular user), a different API route, a different product surface, or different feature-flag state does not validate the fix for the reported conditions. | Match the original report's context exactly. |

---

## Verdict comment format (Jira internal comment)

```
h4. Security QA verdict — {READY FOR DEPLOYMENT | RETURN TO OPEN | BLOCKED — NO VERDICT}

*Ticket:* {SECF-XXXXX}
*QA host:* {hostname}
*QA build:* {version/commit}
*Verdict:* {READY FOR DEPLOYMENT | RETURN TO OPEN | BLOCKED — NO VERDICT}

*Positive control:* {passed | failed | not attempted} — {one line summary}
*Exploit attempt:* {BLOCKED | REPRODUCED | PARTIAL | INCONCLUSIVE | not attempted} — {one line summary}
*Impact verification:* {verified | failed | not attempted} — {one line summary}
*Deployment correspondence:* {confirmed | unconfirmed} — {how verified}
*Victim integrity:* {verified | not verified} — {one line summary}
*Cleanup:* {completed | partial | not attempted} — {what remains}

*Evidence summary:*
{2-4 sentences: what was tested, what happened, why the verdict follows.
Reference the evidence file for full request/response details.}

*Gates:*
{For READY FOR DEPLOYMENT: G1-G7 status}
{For RETURN TO OPEN: R1-R5 status}
{For BLOCKED: which gates failed and what is needed}

*Recommendation:* {Proceed to production / Return to development with <specific gap> / Awaiting <specific blocker>}
```
