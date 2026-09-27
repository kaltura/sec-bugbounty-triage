# Kaltura Bug-Bounty Triage — local runner

Local, on-your-Mac intake for HackerOne/coordinated-disclosure reports that land in
Jira epic **SECF-29234** ("Bug Bounty H1 Program"). No cloud, no AWS, no server — a
launchd user agent runs one detection cycle every ~7 min while you are logged in and
awake.

## Architecture: DETECTOR + MANUAL
This machine runs corporate endpoint-security tooling (**AgenShield**, a macOS
Endpoint Security system extension, plus a `headroom` LLM egress proxy and OX hooks).
That tooling **holds a bare `claude` process at exec**, so an unattended headless
`claude -p` launched by launchd or a plain terminal cannot start (this is below the
auth layer — no token/env fixes it, and bypassing an endpoint-security control is out
of scope). Verified empirically: `claude --debug` emits zero bytes and hangs unless it
inherits a sanctioned desktop-app session's environment.

So the runner is split:
- **Detector (automated, launchd):** polls Jira over REST for new-to-scope Backlog
  tickets under SECF-29234 and queues them in `state.db`. Never runs `claude`.
- **Investigation (manual, desktop app):** you open the `kaltura-bug-bounty-triage`
  skill in the Claude desktop app (the sanctioned path) on each queued ticket. The
  skill investigates and writes `cases/<KEY>/assessment.json`.
- **Writeback (manual, REST):** `writeback <KEY> --apply` applies the reviewed
  assessment to Jira with the full safety plan. Automation never writes.

The skill remains fully usable on its own for ad-hoc manual triage.

## Layout (`~/.claude/kaltura-triage/`)
- `config.json` — modes, epic/status/field model, limits. Everything that could act is OFF by default.
- `state.db` — SQLite queue/state (pending→running→completed/needs_input/failed), claims, retries, usage.
- `product-notes/` — source-backed reusable product knowledge (own local git repo; never pushed).
- `cases/<KEY>/assessment.md` — per-ticket sanitized assessment output (case evidence, kept out of product-notes).
- `runner/` — the code; `runner/tests/` — mock-Jira operational-risk tests.
- `launchd/com.kaltura.bugbounty-triage.plist` — the schedule (staged, NOT loaded).
- `logs/` — poll stdout/stderr.

## Commands (run from `~/.claude/kaltura-triage`)
```bash
python3 -m runner.runner doctor        # preflight; READY (detector + manual) / BLOCKED
python3 -m runner.runner activate      # record activation baseline (only new-to-scope after now)
python3 -m runner.runner set-mode scheduler_enabled true
python3 -m runner.runner start | stop  # launchctl load/unload the DETECTOR agent
python3 -m runner.runner poll --force  # run one detection cycle now (no claude)
python3 -m runner.runner run-ticket SECF-1234   # stage a ticket + print manual steps
#   -> investigate in the desktop app, which writes cases/SECF-1234/assessment.json
python3 -m runner.runner writeback SECF-1234           # dry-run diff of the writeback
python3 -m runner.runner writeback SECF-1234 --apply   # perform it (manual only)
python3 -m runner.runner done SECF-1234       # mark handled without a runner writeback
python3 -m runner.runner status | queue | fail-summary
python3 -m runner.tests.test_operational_risks   # safety checks
```
`run-ticket --headless` still runs the in-process `claude -p` investigator, but only
where a bare `claude` exec is permitted (a non-AgenShield machine, or once allowlisted).

## Modes (independently controllable)
- `scheduler_enabled` — whether the launchd detector polls + queues. Detection only; never runs claude.
- `reproduction_enabled` — **true**: reproduction is a standard step of every triage (manual and, where the investigator can run, automatic). Always *attempts* a **safe** reproduction — security **test tenant**, synthetic accounts/data, non-destructive, no unsafe/DoS payloads, no production auth against real accounts. If a safe repro isn't possible → `reproduction: blocked` + **needs-input**, never skipped and never unsafe.
- `writeback_enabled` — allow **manual** `writeback` to set assessment fields + one internal comment. Currently **true** (for manual writeback on tickets you choose).
- `scheduler_writeback` — inert in this architecture (automation neither investigates nor writes).

Manual writeback within policy runs without extra approval; anything outside policy
(human-override present, visibility not established, version changed, non-eligible
status) → refused / **needs input**, never a silent overwrite.

## Eligibility & activation (as configured)
- Intake JQL: `parent = SECF-29234 AND status = "Backlog"` (verified: `parent` and `"Epic Link"` return the same children).
- Activation policy: **only new-to-scope after activation** — `activate` snapshots current epic membership + timestamp; those are treated as pre-existing. New tickets (created, added to the epic, or entering Backlog after the baseline) are eligible. Not "created in the last 10 min".
- Downtime catch-up: launchd runs a missed interval once on wake; the watermark + membership snapshot re-detect anything missed while asleep. Sleep settings are never changed.

## Jira access — direct REST + Keychain token (no MCP connector)
Jira access uses the Jira Cloud REST API with an API token stored in the **macOS
Keychain** (service `kaltura-triage-jira`, account = `jira_rest.account_email`). The
token is never in config, argv, or logs; the runner reads it only to build the auth
header. The detector and the manual `writeback` both use this. Manual investigation in
the desktop app reads the ticket via its own tools (or `cases/<KEY>/input.json`).

One-time setup:
```bash
# 1) create a token at https://id.atlassian.com/manage-profile/security/api-tokens
# 2) store it (paste-proof; reads from stdin, never argv):
claude setup-token >/dev/null 2>&1 || true   # (not needed for detector+manual)
python3 -m runner.runner set-token           # paste the Jira token at the hidden prompt
# 3) verify:
python3 -m runner.runner doctor              # expect READY (detector + manual) + "Jira REST reachable"
```
The Claude CLI OAuth token (`set-claude-token`) is **optional** — it only matters for
`run-ticket --headless`, which AgenShield blocks on this machine. Detector + manual
does not use it; `doctor` shows the headless line as an informational `[--]`/`[ok]`
note that never gates READY.

The token acts as your Jira identity, so its reach is bounded by your permissions; the
code additionally refuses any ticket outside project SECF and only sets the approved
fields + one comment.

## Safety properties (enforced in code, tested against a mock)
Human-override preservation · optimistic-concurrency (re-read + version check) · duplicate-comment
prevention · unrelated-label preservation · provisional-vs-confirmed severity (Unresolved never gets
a plain `severity-*` label) · internal-vs-reporter-visible comment gate · partial-failure detection +
recoverable state · interruption recovery without duplicate processing. See
`runner/tests/test_operational_risks.py` (24/24 passing).

Limits actually enforced locally: per-run timeout, max attempts, retry backoff, stale-claim recovery,
daily run cap. `per_run_token_budget` is advisory telemetry (depends on the CLI honoring it).
