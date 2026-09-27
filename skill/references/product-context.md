# Kaltura Product & Security Context Notes

Reusable notes to speed up investigations. **This is a retrieval aid, not fixed truth** — re-check the cited sources when a report depends on them, and record the retrieval date. Keep public-documentation facts separate from verified deployment facts and internal business context. Do not infer customer counts, contracts, production configuration, or affected data volume from public docs.

Sources: `https://knowledge.kaltura.com` (product/admin), `https://developer.kaltura.com` (API, KS, partner concepts). Add specific page URLs + dates as you use them.

---

## Core concepts (fill in / verify as you go)

### Tenant model — `partner_id`
- Kaltura is multi-tenant; each account is a **partner** identified by `partner_id`. Cross-`partner_id` read/write of private resources is the canonical tenant-isolation boundary — a confirmed crossing is typically critical/high.
- _Verify against docs/code per report; note the specific service/filter that must enforce `partnerIdEqual` scoping._

### Kaltura Session (KS) tokens
- KS is the auth token for api_v3. Concepts to establish per report: KS type (user vs admin), privileges string, expiry, entitlement flags. KS forgery, disclosure to arbitrary origins, or privilege escalation via KS is high/critical depending on prerequisites.
- _Record KS version/structure facts from developer.kaltura.com with date._

### api_v3 / services
- REST-style API at `/api_v3/service/<service>/action/<action>`. Object IDs like entries `0_xxxxxxxx`. IDOR/BOLA and missing authz checks are common report classes.

### Front-end surfaces
- KMC (management console) and KMS/MediaSpace (end-user portal). `postMessage` origin-validation issues, XSS, and KS leakage to arbitrary web origins show up here.

---

## Repo map (kaltura org — verify current paths with `gh search code`)
- `server` — core PHP backend; api_v3, KS handling, partner scoping.
- `server-saas-code` — Java services.
- `mediaspace`, `mediaspace-react-components`, `kms-react` — KMS/KMC front end.
- `selfserve`, `kava`, `ovp-*` microservices — supporting services.

## Verified deployment / triage facts (keep separate from public docs)
Append dated, evidence-backed facts here as you confirm them. These outrank public documentation for triage.
- `YYYY-MM-DD` — Entries with `displayInSearch=2` are **fully public**: their data/captions/etc. can be fetched without any KS. A report of "unauthenticated access" to such an entry is intended behaviour, not a vulnerability. (Source: SECF-30277 engineering comment.)
- `YYYY-MM-DD` — "Not a vulnerability" is recorded by moving the ticket to **status = Rejected** plus an explanatory comment; the `severity-*` label and Priority are typically left as-is, and `resolution` stays null. This skill recommends Rejection but does not perform status changes.

## Related internal references
- Confluence: "How to Manage an Inbound Bug Bounty Report" (space KCU, page 6574112816) — the Cyber Unit runbook. Useful for process context; this skill's scope is narrower (Jira + GitHub + safe repro + writeback) and its rules here take precedence for what this skill writes.
- Confluence severity pages exist across spaces; when a canonical company security-severity rubric is confirmed, cite it here and prefer it over the generic bands in the rubric file.

---

## Investigation log (append short entries)
Format: `YYYY-MM-DD | ticket | product/feature | boundary | outcome | source URLs`
