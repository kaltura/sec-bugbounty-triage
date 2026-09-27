# Tenant model / `partner_id` isolation

- **Product / feature:** api_v3 multi-tenancy; every account is a partner (`partner_id`).
- **Intended behaviour:** private resources are scoped to their owning `partner_id`; cross-partner read/write of private data or admin capability is a trust-boundary violation.
- **Roles / permissions / tenant boundary:** the canonical boundary is `partner_id`. Server-side scoping must derive the effective partner from the KS, not from client-supplied `partnerId`.
- **Version / configuration applicability:** api_v3.
- **Last verified:** 2026-09-27

## Documented behaviour (cite URL + retrieval date)
- (fill in from developer.kaltura.com partner/multi-account docs when a report needs it.)

## Observed deployment facts (cite ticket/source + date)
- Multiple recent H1 reports concern cross-partner access (e.g. SECF-30292 cross-account write/delete, SECF-30283 vendor integration IDOR). Treat confirmed cross-`partner_id` read/write of private data as Critical unless verified controls reduce exposure.

## Hypotheses / unresolved questions / contradictions
- Which list/get services trust client-supplied `partnerId` vs derive from KS — audit per report.

## Relevant code references (repo @ commit, file:line)
- (fill in when traced) `server` api_v3 service filters / partner scoping.
