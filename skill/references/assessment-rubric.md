# Assessment Rubric — validity, severity, confidence, priority

Four independent axes, plus investigation urgency (when validity is unresolved) and relative order (in batches). Decide validity first; it changes what the other axes even mean. Always preserve the **reporter's original severity** separately from anything you assess.

This is a **proposed** rubric for evaluation, not established company policy. Do not invent response-time SLAs or numeric precision the evidence can't support.

---

## 1. Validity (decide this first)

| Validity | What it means | What to record |
| --- | --- | --- |
| **Valid** | Evidence supports a real security defect / trust-boundary violation. | Severity band + confidence + priority (below). |
| **Not a vulnerability** | Evidence shows intended behaviour or no defect (e.g. content deliberately public, an operation gated by a control that genuinely covers the claimed path). | State validity + cite the establishing evidence. Assign **no severity band**. **Recommend** (do not perform) moving the ticket to Rejected. Do not set `severity-low`. |
| **Unresolved** | Reproduction blocked, prerequisites missing, or deployment correspondence unknown — you cannot yet confirm or disprove. | Preserve existing assessed severity; if none, give a **provisional** severity with explicit assumptions. Set **investigation urgency**. Do not auto-downgrade to Low / 5-Not prioritized. |

Two traps to avoid:
- **Do not use Low severity as a filing cabinet.** If there is no security defect, the answer is "not a vulnerability," not "Low." Kaltura has no non-vulnerability severity label; the team expresses this with the **Rejected status + an explanatory comment** (verified: a real cross-tenant-read report that was actually public via `displayInSearch=2` kept its `severity-high` label and was moved to Rejected with a comment). Since this skill may not change status, record the determination in the comment and recommend Rejection.
- **Do not treat "unproven" as "invalid" or "negligible."** Missing evidence keeps validity Unresolved and lowers *confidence*, not severity.

### Disproving a claim (validity → not a vulnerability) requires care
A passing control case and an apparent authorization check do **not** automatically disprove a report. Before concluding "not a vulnerability," confirm the code/control actually addresses:
- the **actual exploit path** the reporter described (not a neighbouring one);
- the relevant **roles / privileges / configuration** (e.g. the right KS type, the right account state);
- a **deployment that corresponds to production** (not only an unaffected build).

If the control tested a different path/role/build, validity stays **Unresolved**. If the evidence genuinely disproves the *claimed* defect but a *separate, narrower* defect remains, assess that residual defect on its own evidence rather than passing or failing the whole report.

---

## 2. Severity (only for a valid — or provisionally assumed — defect)

Judge the demonstrated (and clearly plausible) boundary violation on four factors: attacker prerequisites/privileges; attack complexity & user interaction; CIA impact; and scope of the boundary crossed (single object → tenant → cross-tenant → shared infrastructure).

| Band | Typical shape |
| --- | --- |
| **Critical** | Unauth/low-priv RCE on prod/shared infra; auth bypass or account takeover at scale; cross-tenant read/write of private data or admin capability; broad scalable data exposure. |
| **High** | In-tenant privilege escalation; access to another user's private data in-tenant; KS/token disclosure→takeover with prerequisites; SSRF to internal/cloud metadata. |
| **Medium** | Bounded IDOR on non-sensitive objects; XSS with real but limited impact; hardening gaps with a constrained exploit path. |
| **Low** | Genuinely minimal *demonstrated* impact of a **real** defect, or defense-in-depth gaps. Low is for small real defects — never for "not a vulnerability" and never for "we couldn't prove the big claim." |

Severity is written as a label: `severity-critical` / `severity-high` / `severity-medium` / `severity-low` — **only for valid findings** (or a provisional call on an unresolved one, clearly flagged). Replace only the `severity-*` label; leave others intact. For "not a vulnerability," write no severity label.

If asked for CVSS, give version, full vector, and assumptions; give a range when facts are missing rather than a false-precision score. Do not invent CVE IDs.

---

## 3. Confidence & reproduction (tracked separately, never a severity downgrade)

- **Reproduction:** `reproduced` / `partially-reproduced` / `blocked` / `not-attempted` — with why.
- **Confidence:** `high` / `medium` / `low` in the current validity+severity determination.

A serious report you could not reproduce is a **high-severity, low-confidence, Unresolved** finding — not a Low one.

---

## 4. Remediation priority — absolute bands (Jira Priority field)

Priority is business urgency of remediation, decided on evidence in context. **Do not** derive it from the severity band, the reporter's rating, a CVSS number, or batch rank.

| Priority (field value) | Meaning |
| --- | --- |
| **1-Essential** | Immediate response or expedited remediation is justified by the business risk. Examples: credible active exploitation; reachable production RCE with substantial impact; significant exposure of private cross-tenant data. |
| **2-High** | Prompt remediation is warranted, but the evidence does not justify the immediate-response band. |
| **3-Medium** | Address through the normal remediation process. |
| **4-Low** | Limited demonstrated impact and low urgency. |
| **5 - Not prioritized** | **No prioritization decision has been made.** Not a synonym for unconfirmed, invalid, or negligible. Use it only when you are deliberately deferring the prioritization decision (e.g. handing off), and say why. |

Consequences of "absolute":
- **A High-severity finding can be 1-Essential** — e.g. an internet-facing account-takeover or auth bypass that is readily exploitable, even if you rated the defect High rather than Critical.
- **A Critical finding can sit below 1-Essential** when *verified deployment conditions* materially reduce immediate exposure (a confirmed prod control, a component not reachable in production). Say so explicitly and name the control that lowers urgency and the risk if it fails.
- Weigh: active exploitation; internet exposure & attacker access needed; practical exploitability; data sensitivity and *supported* blast radius; shared-service/tenant-isolation impact; verified mitigating controls; genuinely time-sensitive business context the user supplies.

Track **remediation effort** separately (a one-line fix vs a framework change) so an easy fix doesn't outrank a more dangerous hard one — effort informs sequencing, not severity or band.

### Relative order (separate from the band)
Multiple findings may share the same severity **and** the same priority band and still need a clear fix order. Record it in the comment ("ahead of SECF-X because unauthenticated; behind SECF-Y because Y is actively exploited"). The Priority field is coarse; the comment carries the fine-grained order.

---

## 5. Investigation urgency (when validity is Unresolved)

When you cannot yet confirm the report, remediation priority is premature — but *doing nothing* is a decision too. Record **what must be investigated next and how urgently**, driven by credible potential impact:
- An unverified but credible RCE, auth bypass, or cross-tenant exposure warrants **urgent** investigation even while unconfirmed.
- A low-plausibility claim can be investigated in normal course.

Jira has no investigation-urgency field. State it in the comment (e.g. "Investigation urgency: HIGH — credible unauthenticated RCE; next step: obtain a safe repro in the security test tenant / confirm the endpoint is reachable in prod"). Note there that no dedicated field exists. Do not encode urgency by inflating severity or by setting a misleading remediation priority.

---

## Worked examples (iteration-2 model)

- **Confirmed unauth cross-tenant read of private media**, reproduced with a failing control → **Valid**, severity **Critical**, confidence **high**, priority **1-Essential**.
- **High-severity account takeover, internet-facing, readily exploitable** → **Valid**, severity **High**, confidence **high**, priority **1-Essential** (High *can* be Essential — urgency comes from exposure, not the severity word).
- **Two confirmed Criticals**, both **1-Essential**: one shows signs of active exploitation, the other doesn't → same band, but **relative order** puts the actively-exploited one first; explain in each comment.
- **Credible unauth RCE, reproduction blocked** (missing a prerequisite the reporter didn't supply) → **Unresolved**, reproduction **blocked**, preserve/**provisional severity Critical with stated assumptions**, confidence **low**, **investigation urgency HIGH**; do **not** set Low/5. Priority may be left provisional with the reason, driven by the investigation-urgency note.
- **Intended public sharing** (entries deliberately public; control on a restricted entry correctly denies) → **Not a vulnerability**, **no severity band**, confidence **high**; recommend Reject (human action); no bounty/reporter action taken. It is *not* "Low."
- **Reported critical priv-esc that the control seems to refute** → before calling it not-a-vulnerability, verify the control exercised the *same* path/role/build the reporter used. If it did → not a vulnerability (recommend Reject). If it only covered a neighbouring path → **Unresolved**, investigate the actual path. If a smaller real defect remains → assess that on its own.
