# Jira Writeback

Writing the assessment to the ticket under investigation is an authorized part of running this skill; don't ask for per-write approval on routine updates. Do ask when a mapping is ambiguous, or stop when a human decision conflicts (below).

Investigating one ticket authorizes writing to **that ticket only**. Other tickets require an explicitly requested batch.

## What each validity outcome writes

| Validity | Severity label | Priority field | Comment |
| --- | --- | --- | --- |
| **Valid** | Set the discovered `severity-<band>` mapping (see below): add your one band, remove any *conflicting* `severity-*`, preserve all unrelated labels. | Set the absolute band (below). | Full assessment. |
| **Not a vulnerability** | **No new severity band.** **Preserve** existing `severity-*` labels (do not remove them unless an approved policy permits it); do not add `severity-low`. In the comment, **explain any discrepancy** between an existing label and your not-a-vulnerability finding. | **Leave unchanged.** | State validity + evidence; a supported **recommendation** to Reject is permitted; executing Rejection is not. Note no bounty/reporter action taken. |
| **Unresolved** | **Do not add an ordinary `severity-critical`/`severity-high` label that makes an unproven allegation look confirmed.** Preserve existing labels. Keep **provisional** severity in the *comment*, clearly marked provisional, unless Jira later gains an unambiguous provisional field. **Do not downgrade an existing assessment solely because reproduction is blocked.** | Leave unchanged (or a provisional band only with a stated reason); drive the next step via **investigation urgency** in the comment. | Provisional assessment, explicit assumptions, reproduction=blocked, **investigation urgency**. |

There is no Jira field for **validity**, **investigation urgency**, **relative order**, or **provisional-vs-confirmed severity** — they live in the comment. Kaltura expresses "not a vulnerability" through the **Rejected status** (a human workflow action this skill must not take) plus a comment; recommend it, don't do it.

### Confirmed vs provisional severity
A plain `severity-*` label reads as a **confirmed** assessment. Only apply one for a **Valid** finding. For **Unresolved**, the label would misrepresent an allegation as confirmed — keep the provisional band in the comment instead. This is the single most important severity-handling rule.

### Dry-run label diff (always show before writing)
Before any label change, output the exact diff so it is reviewable:
`labels: add [severity-high]; remove [severity-medium]; keep [hackerone, h1-report-1234]`.
Never leave two `severity-*` labels on a Valid finding (prevent conflicting bands). Show the same add/remove/keep diff in read-only dry-run mode even though nothing is written.

### Components — tag every finished handling with two
On every ticket you finish handling (any validity outcome — Valid, Not a vulnerability, or Unresolved), **add two components**, never removing existing ones:
1. **`Agent Check`** (id 61351) — always, as the marker that this skill handled the ticket.
2. **Exactly one team component**, chosen from where the actual issue / fix lives:
   | Component | id | Area (repos) |
   | --- | --- | --- |
   | `Sec-KMS` | 61353 | KMS / MediaSpace front side (`mediaspace`, `mediaspace-react-components`, `kms-react`) |
   | `Sec-EP` | 61354 | Event Platform (`eventplatform`, event portal) |
   | `Sec-BE` | 61352 | Backend / api_v3 / core `server` — **the default for most findings** |
   | `Devops OVP-Sec` | 61248 | DevOps OVP (helm/terraform/argocd/nginx infra) |
   | `Devops OTT-Sec` | 61249 | DevOps OTT infra |

Choose the team component from the root-cause location you traced in GitHub (which repo/layer the fix belongs to), not from the reporter's wording. If the issue spans layers, pick the one that owns the fix; if genuinely unclear, default to `Sec-BE` and say why in the comment. Preserve all pre-existing components; add with the `add` operation (or `set` to the union) and never duplicate one already present. Show the component add/keep diff in the dry-run alongside the label diff.

### Prior automated assessment vs explicit human decision
Distinguish this skill's **own** previous assessment comment/labels (which a routine rerun may update in place, without stopping) from an **explicit human decision** — a severity/priority set by a person, or a person's triage/closure comment. Only a *human* decision triggers the stop-and-surface guard below; recognizing your own prior output prevents routine reruns from always halting unnecessarily.

## Field model (SECF — verified)

- **Site / cloudId:** `kaltura.atlassian.net` / `9cebaf06-de33-468b-b9eb-8c450353db6b`.
- **Severity label:** `severity-critical` / `severity-high` / `severity-medium` / `severity-low`. Set with the `set` operation after re-reading current labels, keeping every unrelated label and swapping only the one `severity-*` value.
- **Priority field** — absolute bands (see `assessment-rubric.md`), IDs:
  | Value | id |
  | --- | --- |
  | `1-Essential` | 16 |
  | `2-High` | 12 |
  | `3-Medium` | 13 |
  | `4-Low` | 14 |
  | `5 - Not prioritized` | 15 |
- **Comment:** one internal comment per assessment in the `references/report-format.md` format. SECF comments are internal to the security project (not reporter-facing), so no special visibility flag is needed; still redact secrets/tokens/full KS and full exploit payloads.
- **Priority Rank (`customfield_19161`, values 1–7):** audit-program findings only (`security_audit`). Do **not** write it for HackerOne triage unless the user asks.
- Do **not** treat Jira Rank (board rank) as a security field or reorder unrelated engineering work.
- **Resolution:** not used for these (verified: rejected reports carry `resolution: null`). Don't set it.

If a ticket's issue type/workflow differs from the above, re-discover with `getJiraIssueTypeMetaWithFields` / the issue `editmeta` before writing, and confirm any new mapping with the user.

## Human-override guard (do this every write)

1. **Re-read first.** Immediately before writing, fetch current `labels`, `priority`, `status`, recent `comment`s, `reporter` (`getJiraIssue`).
2. **Detect a human decision.** A human-set severity/priority, or a comment recording a triage/validity/closure decision by a person (not by this skill), is a decision you must not silently overwrite — even if you disagree. Distinguish it from this skill's own prior comment (which you may update).
3. **If a human decision conflicts with yours: stop and surface it.** Report both the human decision and your differing assessment to the user, and let them decide. Do not overwrite it, and do not overwrite a confirmed assessment with an unsupported downgrade.
4. If there is no conflict, proceed.

## Procedure

1. **Recheck eligibility**, then re-read + run the human-override guard. Before writing, confirm the ticket is still in scope (still under the intake epic, still an eligible status, not closed/rejected by a human). If it moved out of scope, do not write — surface it.
2. **Check comment visibility before composing.** Verify whether the comment will be internal-only or reporter-visible, and whether the project synchronizes comments/fields to HackerOne. SECF comments are currently internal-only (verified earlier), but the HackerOne↔Jira integration is being established, so confirm per run. **If visibility cannot be established, block the comment write and explain why** — never risk putting internal code detail or sensitive evidence in a reporter-visible field. Keep exploit specifics/secrets out regardless.
3. Apply the writes for the validity outcome (table above), showing the dry-run label diff first. Compute a Valid label change as *current labels − conflicting `severity-*` + your one band*, `set` operation, preserving unrelated labels.
4. Set the Priority field only when the outcome calls for it: `editJiraIssue` `fields.priority = { "id": "<id>" }`.
5. Add the internal comment (`addCommentToJiraIssue`), **idempotently**: if a prior skill assessment comment is unchanged, skip; if it changed, post a short delta referencing the previous one. Never post a duplicate, and avoid unnecessary field writes when the value is already correct.
6. **Detect partial failures and read back** every changed field/comment before reporting success; report before→after to the user. Assessing one ticket authorizes changes to **that ticket only** — comparing against the backlog never authorizes rewriting others; broader reprioritization is an explicitly selected batch.

## Never (via writeback)

- Change `status`/workflow, close, resolve, or move to Rejected (recommend only).
- Make bounty decisions or write anything addressed to the reporter.
- Touch fields other than the severity label (when warranted), Priority (when warranted), and your comment.
- Reprioritize other tickets outside an explicitly named batch.
