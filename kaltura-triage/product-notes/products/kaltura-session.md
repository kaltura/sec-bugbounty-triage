# Kaltura Session (KS) tokens

- **Product / feature:** KS is the api_v3 auth token; types include user vs admin; carries privileges and expiry.
- **Intended behaviour:** KS type/privileges gate what actions are allowed; different login flows may mint different KS.
- **Roles / permissions / tenant boundary:** admin KS grants partner-admin capability; a widget/anonymous KS is still a partner-minted token (not "no auth").
- **Version / configuration applicability:** KS v2 concepts; verify per report.
- **Last verified:** 2026-09-27

## Documented behaviour (cite URL + retrieval date)
- (fill in from developer.kaltura.com KS docs when a report needs it.)

## Observed deployment facts (cite ticket/source + date)
- Recent H1 reports concern KS disclosure / re-minting / logout invalidation (e.g. SECF-30280 extlogin re-mint to admin KS, SECF-30281 KS in public bundle, SECF-30287 postMessage KS disclosure, SECF-30285 KS not invalidated on logout). KS forgery/disclosure enabling takeover is High/Critical by prerequisites.

## Hypotheses / unresolved questions / contradictions
- Whether specific login flows (e.g. loginByLoginId) mint over-privileged KS — verify per report.

## Relevant code references (repo @ commit, file:line)
- (fill in when traced) `server` lib/session (kSessionUtils) + api_v3 permission annotations.
