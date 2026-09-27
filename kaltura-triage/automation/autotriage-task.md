# Full automation — the scheduled task

This is the hands-off pipeline: **detect new bounty tickets → investigate → write the
assessment back to Jira**, with no human in the loop. It runs as a **Claude desktop-app
scheduled task**, not as a launchd job. Read the "why" below before copying the prompt.

## Why a scheduled task, not launchd + `claude -p`
The investigator is the `kaltura-bug-bounty-triage` skill — i.e. Claude itself tracing
code and assessing. Running that unattended needs a working Claude session. On a machine
where the desktop app brokers Claude auth over an IPC socket (env vars like
`CLAUDE_CODE_MESSAGING_SOCKET` / `CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH`), a **cold
`claude -p`** launched by launchd or a plain terminal has no such channel and stalls at
startup — it can't obtain credentials. A **scheduled task runs as an app-launched
session**, so it inherits that auth channel and works. That's the whole reason the
automation lives here and not in the launchd runner.

Consequences:
- The task runs **only while the desktop app is open** (it catches up on next launch).
  This is local automation, not a 24/7 server.
- The launchd runner (`runner.py start`) is **optional/legacy** — a standalone detector.
  For full automation you don't need it; the scheduled task does detection itself via
  `poll --force`. Keep `scheduler_enabled=false` to avoid two pollers.

## What each run does
1. `python3 -m runner.runner poll --force` — detect new-to-scope SECF-29234 Backlog
   tickets and queue them (state.db). New-to-scope = appeared **after** your activation
   baseline (see below), so the pre-existing backlog is never touched.
2. For each pending ticket: stage it, invoke the `kaltura-bug-bounty-triage` skill to
   fully triage it (report + `gh` code trace; safe reproduction if a test tenant is
   configured, else recorded `blocked` and it proceeds on code evidence), then
   `python3 -m runner.runner writeback KEY --apply` to set severity label, components
   (`Agent Check` + one team), priority, and one internal comment.
3. The writeback keeps its safety guards: preserves human decisions, checks eligibility +
   version, prevents duplicate comments. On any conflict/needs-input it leaves the ticket
   for a human and moves on.

## Set it up (each operator, on their own machine)
1. Install the skill + runner and enable Jira access (see `../HANDOFF.md`). Set the
   activation baseline so only future tickets are in scope:
   ```bash
   cd ~/.claude/kaltura-triage
   python3 -m runner.runner set-mode reproduction_enabled true
   python3 -m runner.runner set-mode writeback_enabled true
   python3 -m runner.runner activate      # everything currently in the epic = pre-existing
   ```
   (Exclude any tickets already queued from a prior detector run before you flip the
   automation on — clear them from `state.db` or they'll be processed. `activate` alone
   only stops *re-queuing*; it does not empty an existing queue.)
2. Create a scheduled task in the desktop app (Scheduled / routines section, or ask
   Claude to create one). Use an hourly cron like `17 * * * *` and paste the prompt
   below. **Replace the path** with your own `~/.claude/kaltura-triage` absolute path.
3. Click **Run now** once to confirm it fires and to pre-approve the tools it uses
   (Bash for the runner, `gh`, the skill, file writes). Do this while the queue is empty
   so the validation run is a no-op — or on a single ticket you're happy to have written.
4. It then runs automatically every hour while the app is open.

## The task prompt (paste this)
```
Autonomous Kaltura bug-bounty triage. Do every step below without asking for confirmation; this is an unattended run.

Work in $HOME/.claude/kaltura-triage (cd there first; use your own absolute path). The Jira token and Claude auth are already configured; use `python3 -m runner.runner` for detection and writeback, and the `kaltura-bug-bounty-triage` skill for investigation.

1. Detect + queue new-to-scope tickets:
   Run:  cd $HOME/.claude/kaltura-triage && python3 -m runner.runner poll --force
2. List the queue:
   Run:  python3 -m runner.runner queue
   If NO tickets are in the "pending" state, print "no new tickets this run" and stop.
3. For EACH pending ticket KEY (handle all of them, one at a time):
   a. Stage it:  python3 -m runner.runner run-ticket KEY
   b. Invoke the kaltura-bug-bounty-triage skill to FULLY triage KEY: use cases/KEY/input.json as the report (do not call Jira from the skill); trace root cause in the kaltura GitHub org via gh (cite repo@sha, file:line); reproduction only against a security TEST tenant if configured, else record "blocked (no safe test target)" and continue on code evidence (NEVER reproduce against production or a real account); decide validity/severity/confidence/remediation-priority and the components (Agent Check + one team). Write cases/KEY/assessment.md and cases/KEY/assessment.json with keys: validity, severity, priority, team_component, comment (begin with "Security triage assessment:"), visibility_established, conflicts_with_human.
   c. Write it back to Jira:  python3 -m runner.runner writeback KEY --apply
      If it reports needs_input, a version conflict, a human-override stop, or any error, DO NOT retry or force it — leave that ticket for human review and continue.
4. Print a one-line summary per ticket: KEY — validity / severity / priority / writeback outcome.

Hard limits (never violate): do NOT close tickets, change workflow status, contact reporters, make bounty/payout decisions, modify source code, or reproduce against production. Only tickets the detector queued as new-to-scope are in scope.
```

## Controls
- **Pause:** disable the scheduled task (routines UI), or `set-mode writeback_enabled false`
  to keep it assessing into `cases/` without writing to Jira.
- **Change cadence:** edit the task's schedule.
- **Watch:** the Scheduled section shows recent runs; each run prints a per-ticket summary.
- **Reproduction:** off by default here means "blocked, proceed on code evidence." To get
  real reproductions, configure a security test tenant target (never production).
