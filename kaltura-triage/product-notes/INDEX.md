# Kaltura Product Notes — Index

Source-backed, reusable product knowledge for bug-bounty triage. **A retrieval aid, not fixed truth** — re-verify sources when a report depends on a fact. Local only; never pushed to a remote without instruction.

Separate three kinds of statements, and never let a report-specific verdict become a general product rule:
- **Documented behaviour** — from knowledge.kaltura.com / developer.kaltura.com (cite URL + retrieval date).
- **Observed deployment fact** — confirmed in an environment or from an engineering statement (cite the ticket/source + date).
- **Hypothesis** — not yet verified; mark clearly.

Do **not** store secrets, session tokens, customer data, or raw exploit attachments here. Case evidence lives sanitized under `../cases/`, not in these notes.

Each note is one file under `products/`. Add a row here when you create one.

| Note | Product / feature | Kind | Last verified |
| --- | --- | --- | --- |
| [products/partner-isolation.md](products/partner-isolation.md) | Tenant model / `partner_id` isolation | mixed | 2026-09-27 |
| [products/kaltura-session.md](products/kaltura-session.md) | Kaltura Session (KS) tokens | mixed | 2026-09-27 |
| [products/entry-access-control.md](products/entry-access-control.md) | Entry access control / `displayInSearch` | deployment-fact | 2026-09-27 |

## How to use during an investigation
1. Read the relevant existing notes here first.
2. Retrieve and verify the sources this specific report needs.
3. Use current evidence to resolve conflicts (current evidence wins; record the conflict).
4. When new, supported product knowledge is established, update the note (and this index) and commit with `git -C ~/.claude/kaltura-triage/product-notes commit`.
