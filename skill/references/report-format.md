# Internal Assessment Comment Format

One internal comment per assessment (or a short delta on reruns). Concise and scannable — a triage lead should grasp validity and the verdict in the first lines. Redact secrets, tokens, full KS values, and full exploit payloads.

Lead with **validity**, because it governs everything else.

```
h4. Security triage assessment — validity: {Valid | Not a vulnerability | Unresolved}

*Validity:* {Valid | Not a vulnerability (intended behaviour / no defect) | Unresolved (insufficient evidence)}
*Assessed severity:* {Critical|High|Medium|Low | n/a for not-a-vulnerability | provisional: <band> (assumptions below)}
*Confidence:* {high|medium|low}
*Reproduction:* {reproduced | partially-reproduced | blocked | not-attempted} — {why}
*Remediation priority:* {1-Essential|2-High|3-Medium|4-Low|5 - Not prioritized | not set (see investigation urgency)}   (reporter's original severity: {value or n/a})
*Components:* Agent Check + {Sec-KMS|Sec-EP|Sec-BE|Devops OVP-Sec|Devops OTT-Sec} — {one line: why this team owns the fix}

*Summary:* {1–2 sentences: the boundary violation (or why there is none), and whether it holds.}

*Evidence (demonstrated):* {What was actually reproduced — environment (test tenant / prod), sanitized request/response shape, the control case and whether it covered the claimed path/role/build. No raw secrets.}

*Plausible (not demonstrated):* {Credible downstream impact you did not prove. Kept separate from demonstrated.}

*Business impact:* {Kaltura-specific: tenant isolation, data sensitivity, shared infra, exposure. Supported facts only — no invented customer counts, contracts, or data volumes.}

*Root cause:* {repo @ commit SHA, file:line, path entry → auth → authz/partner_id → logic. Deployment correspondence: confirmed | unknown.}

*Proposed fix & retest:* {Underlying fix, regression tests, retest procedure. Omit or mark n/a for not-a-vulnerability.}

*Remediation effort:* {rough effort — informs sequencing, not severity.}

*Investigation urgency (if Unresolved):* {what to investigate next and how urgently, from credible potential impact; note Jira has no field for this.}

*Relative order (batch only):* {ahead of / behind which tickets and why, including ordering within a shared priority band.}

*Recommended disposition (advisory — not performed):* {e.g. "recommend Reject as not-a-vulnerability" / "keep open, investigate". Never a bounty or reporter decision.}

*Open questions / blockers:* {Anything unresolved; if provisional, name the blocker.}
```

Notes:
- **Not a vulnerability:** set `*Assessed severity:* n/a`, no severity label, and recommend Reject under disposition — do not write `severity-low`.
- **Unresolved:** never fill priority with `4-Low`/`5` to mean "unproven"; use the investigation-urgency line and, if you defer prioritization, say why.
- If a human decision already exists on the ticket, do not post a conflicting overwrite — surface it to the user instead (see `jira-writeback.md`).
- Don't paste a working exploit chain; summarize the mechanism and point to the attachment already on the ticket.
