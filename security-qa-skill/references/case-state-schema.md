# Case State Schema — `qa-state.json`

Each ticket under QA verification gets `cases/<TICKET>/qa-state.json`.
This file is the single source of truth for resuming after compaction.

## Schema

```json
{
  "schema_version": 1,
  "ticket_key": "SECF-XXXXX",
  "ticket_updated_at": "2026-10-21T12:00:00Z",
  "ticket_summary": "One-line summary of the finding and fix",

  "current_phase": "READ_TICKET | PREFLIGHT | PREREQUISITES | POSITIVE_CONTROL | EXECUTE_EXPLOIT | IMPACT_VERIFICATION | CLEANUP | VERDICT | BLOCKED | COMPLETED",

  "qa_host": "qa-host.kaltura.com",
  "qa_build": "version or commit SHA",

  "attacker_partner_id": 12345,
  "victim_partner_id": 67890,

  "session_types": {
    "attacker_ks_type": "user | admin | none | app_token",
    "attacker_ks_validated": false,
    "victim_ks_type": "user | admin | none | app_token",
    "victim_ks_validated": false
  },

  "required_plugins": ["pluginName"],
  "required_feature_flags": ["flagName=value"],
  "required_roles": {
    "attacker": "role description",
    "victim": "role description"
  },

  "controlled_objects": [
    {
      "type": "entry | playlist | category | user | other",
      "id": "0_abc12345",
      "owner_partner_id": 67890,
      "purpose": "victim media for cross-tenant access test",
      "created_by_skill": true,
      "cleanup_required": true
    }
  ],

  "preflight": {
    "jira_access": "pass | fail | not_checked",
    "burp_available": "pass | fail | not_checked | n/a",
    "browser_available": "pass | fail | not_checked | n/a",
    "github_access": "pass | fail | not_checked",
    "qa_host_reachable": "pass | fail | not_checked",
    "attacker_tenant_ready": "pass | fail | not_checked",
    "victim_tenant_ready": "pass | fail | not_checked",
    "ks_types_available": "pass | fail | not_checked",
    "roles_available": "pass | fail | not_checked",
    "plugins_enabled": "pass | fail | not_checked | n/a",
    "feature_flags_set": "pass | fail | not_checked | n/a",
    "controlled_objects_exist": "pass | fail | not_checked",
    "oob_infrastructure": "pass | fail | not_checked | n/a"
  },

  "positive_control_status": "passed | failed | not_attempted",
  "positive_control_summary": "One line: what was tested and the result",

  "exploit_status": "BLOCKED | REPRODUCED | PARTIAL | INCONCLUSIVE | not_attempted",
  "exploit_summary": "One line: what was attempted and the result",

  "impact_verification_status": "verified | failed | not_attempted",
  "impact_verification_summary": "One line: what was verified",

  "deployment_correspondence": "confirmed | unconfirmed | not_checked",
  "deployment_evidence": "How correspondence was established",

  "victim_integrity": "verified | not_verified | not_checked",

  "cleanup_status": "completed | partial | not_attempted",
  "cleanup_details": "What was cleaned up, what remains",

  "blocker": null,
  "blocker_details": {
    "phase": "phase where blocker occurred",
    "description": "what is missing",
    "required_from": "who must provide it",
    "action_needed": "what they must do"
  },

  "verdict": null,
  "verdict_gates": {
    "G1_complete_exploit": null,
    "G2_intended_control": null,
    "G3_positive_control": null,
    "G4_correct_context": null,
    "G5_deployment_correspondence": null,
    "G6_victim_integrity": null,
    "G7_cleanup_verified": null,
    "R1_boundary_reproduced": null,
    "R2_real_objects": null,
    "R3_positive_control": null,
    "R4_impact_verified": null,
    "R5_cleanup_documented": null
  },

  "evidence_file": "cases/SECF-XXXXX/evidence.md",
  "started_at": "2026-10-21T12:00:00Z",
  "last_checkpoint": "2026-10-21T12:05:00Z",
  "completed_at": null
}
```

## Field rules

### Identifiers
- `ticket_key`: The SECF Jira key. Immutable after creation.
- `ticket_updated_at`: ISO 8601 timestamp from Jira `updated` field. Used to
  detect ticket changes and avoid re-reading unchanged tickets.

### Phases
- `current_phase`: The phase the skill is currently in or was in when it last
  checkpointed. After compaction, resume from this phase.
- Phase `BLOCKED` means a blocker was hit; `blocker` and `blocker_details`
  describe it. When the user resolves the blocker, the skill resumes from the
  phase recorded in `blocker_details.phase`.
- Phase `COMPLETED` means the verdict has been issued.

### Tenants and sessions
- Partner IDs are integers (Kaltura tenant identifiers).
- `session_types.*.validated` means the skill confirmed it can generate or
  use that KS type in the QA environment.
- **Never store raw KS values.** Store only the type, whether it was validated,
  and the partner_id it belongs to.

### Controlled objects
- Each entry records `type`, `id`, `owner_partner_id`, `purpose`,
  `created_by_skill` (whether this skill created it), and `cleanup_required`.
- During CLEANUP, mark each as cleaned or note what remains.
- **Never store fabricated IDs.** Every object ID must be verified to exist.

### Preflight
- Each check is `pass`, `fail`, `not_checked`, or `n/a`.
- `n/a` means the check is not required for this specific exploit
  (e.g. `oob_infrastructure` when no OOB callback is needed).
- All required checks must be `pass` before leaving PREFLIGHT.

### Verdict gates
- Each gate is `true` (passed), `false` (failed), or `null` (not yet evaluated).
- The verdict logic is:
  - If G1–G7 are all `true` → READY FOR DEPLOYMENT
  - If R1–R5 are all `true` → RETURN TO OPEN
  - Otherwise → BLOCKED — NO VERDICT

### Timestamps
- `started_at`: When the skill run began.
- `last_checkpoint`: Updated at every phase transition and before long tool calls.
- `completed_at`: Set when the verdict is issued.

## Checkpoint procedure

At every phase transition:
1. Update `current_phase` to the new phase.
2. Update `last_checkpoint` to current time.
3. Update any fields that changed during the completed phase.
4. Write the file atomically (write to temp, rename).

Before a long tool call (Burp request, browser navigation, large GitHub search):
1. Update `last_checkpoint`.
2. Write any accumulated state changes.

## After compaction — resume procedure

1. Read `cases/<TICKET>/qa-state.json`.
2. Read `cases/<TICKET>/evidence.md`.
3. Set `current_phase` from state and continue from that phase.
4. Compare `ticket_updated_at` against current Jira; re-read only if changed.
5. Do not re-execute phases that are already recorded as complete in the
   evidence file and whose results are in the state.
6. If `current_phase` is `BLOCKED`, re-present the blocker to the user.
