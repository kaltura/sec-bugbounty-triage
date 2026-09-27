# sec-bugbounty-triage

Kaltura HackerOne / coordinated-disclosure triage tooling. Two separable pieces:

- **`skill/`** → install to `~/.claude/skills/kaltura-bug-bounty-triage/`. Standalone; use it for
  manual triage in the Claude desktop app. This is the minimum you need.
- **`kaltura-triage/`** → install to `~/.claude/kaltura-triage/`. The runner CLI (detection, REST
  writeback, durable state) plus the full-automation guide.

## Install
```bash
cp -R skill ~/.claude/skills/kaltura-bug-bounty-triage
cp -R kaltura-triage ~/.claude/kaltura-triage
bash ~/.claude/kaltura-triage/install.sh
```
Then follow **`kaltura-triage/HANDOFF.md`** to enable it (each person uses their own Jira token in their
own Keychain; nothing here contains secrets, tokens, `state.db`, `cases/`, or logs).

## Two ways to run it
- **Full automation (recommended):** a Claude desktop-app **scheduled task** that runs the whole loop
  hourly and hands-off — detect new SECF-29234 tickets → investigate with the skill → write the
  assessment back to Jira (severity, components, priority, comment). Setup + prompt in
  **`kaltura-triage/automation/autotriage-task.md`**.
- **Manual:** run the skill on a ticket in the desktop app, then `writeback <KEY> --apply`.

The investigator runs inside an **app-launched session** (scheduled task), not a launchd `claude -p`:
on a Mac where the desktop app brokers Claude auth over an IPC socket, a cold `claude` launched by
launchd/terminal has no auth channel and stalls at startup. This is an auth constraint, not a security
block. The launchd runner still works as an optional queue-only detector. See `kaltura-triage/README.md`.

## Safety
- Writeback preserves human decisions, checks eligibility + version, and never duplicates comments.
- Reproduction is a standard step, always attempted **safely** — security test tenant, synthetic
  accounts/data, non-destructive, no unsafe/DoS payloads, no production auth against real accounts;
  when it can't be done safely it records `blocked` and proceeds on code evidence.
- Scope is **new-to-scope after activation** — the pre-existing backlog is never auto-processed.
