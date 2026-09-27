# Entry access control / `displayInSearch`

- **Product / feature:** OVP entries — access control for `baseEntry.get`, `caption.list`, `playManifest`.
- **Intended behaviour:** an entry's reachability without a KS is governed by its access-control configuration.
- **Roles / permissions / tenant boundary:** anonymous vs authenticated (KS); per-`partner_id`.
- **Version / configuration applicability:** api_v3 (version not pinned).
- **Last verified:** 2026-09-27

## Documented behaviour (cite URL + retrieval date)
- Access Control Profiles govern who can play/read an entry; the default profile permits anonymous playback, and restriction requires a profile with domain/country/authentication limits. (knowledge.kaltura.com "Access Control Profiles" — retrieved 2026-09-27; re-verify exact URL when used.)

## Observed deployment facts (cite ticket/source + date)
- An entry with `displayInSearch=2` is **fully public**: its data/captions/etc. can be fetched **without any KS**. A report of "unauthenticated access" to such an entry is intended behaviour, not a vulnerability. (Source: SECF-30277 engineering comment, 2026-09-27.)
- "Not a vulnerability" is recorded by moving the ticket to **status = Rejected** + an explanatory comment; the `severity-*` label and Priority are typically left as-is and `resolution` stays null. (Observed on SECF-30277 / SECF-30283 / SECF-30303 / SECF-30310, 2026-09-27.)

## Hypotheses / unresolved questions / contradictions
- Whether `displayInSearch` and `accessControlProfile` interactions have edge cases (e.g. `entitledUsersView`) that a report could exploit — verify per report (see SECF-30310, an IDOR claim on these same checks, marked Rejected).

## Relevant code references (repo @ commit, file:line)
- (fill in when traced) `server` api_v3 baseEntry / access-control enforcement path.
