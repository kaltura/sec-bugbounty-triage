# sec-bugbounty-triage

Kaltura security triage and post-fix QA tooling. Three separable pieces:

- **`skill/`** → install to `~/.claude/skills/kaltura-bug-bounty-triage/`. Initial triage of
  inbound HackerOne / coordinated-disclosure reports. Use for new findings that need
  investigation, reproduction, root-cause analysis, and severity assessment.
- **`security-qa-skill/`** → install to `~/.claude/skills/kaltura-security-qa/`. Post-fix
  verification of tickets in "In Security QA". Use when a fix is deployed to QA and needs
  runtime exploit verification. Strict state machine, preflight checks, verdict gates.
- **`kaltura-triage/`** → install to `~/.claude/kaltura-triage/`. The runner CLI (detection, REST
  writeback, durable state) plus the full-automation guide.

## Which skill to use

| Situation | Skill |
|-----------|-------|
| New inbound report needs triage | `kaltura-bug-bounty-triage` |
| Reporter says "is this real?", "how bad is this?" | `kaltura-bug-bounty-triage` |
| Batch prioritization of findings | `kaltura-bug-bounty-triage` |
| Ticket is "In Security QA" — verify a deployed fix | `kaltura-security-qa` |
| User says "QA this", "check the fix", "is this fixed?" | `kaltura-security-qa` |
| Retest / validate a patch on a QA build | `kaltura-security-qa` |

## Install

```bash
# Install both skills
cp -R skill ~/.claude/skills/kaltura-bug-bounty-triage
cp -R security-qa-skill ~/.claude/skills/kaltura-security-qa

# Install the runner (optional — for automation)
cp -R kaltura-triage ~/.claude/kaltura-triage
bash ~/.claude/kaltura-triage/install.sh
```

Or use the install script which handles both skills and the runner:

```bash
bash install.sh
```

Then follow **`kaltura-triage/HANDOFF.md`** to enable the runner (each person uses their own Jira
token in their own Keychain; nothing here contains secrets, tokens, `state.db`, `cases/`, or logs).

## Two ways to run it
- **Full automation (recommended):** a Claude desktop-app **scheduled task** that runs the whole loop
  hourly and hands-off — detect new SECF-29234 tickets → investigate with the skill → write the
  assessment back to Jira (severity, components, priority, comment). Setup + prompt in
  **`kaltura-triage/automation/autotriage-task.md`**.
- **Manual:** run either skill on a ticket in the Claude desktop app.

The investigator runs inside an **app-launched session** (scheduled task), not a launchd `claude -p`:
on a Mac where the desktop app brokers Claude auth over an IPC socket, a cold `claude` launched by
launchd/terminal has no auth channel and stalls at startup. This is an auth constraint, not a security
block. The launchd runner still works as an optional queue-only detector. See `kaltura-triage/README.md`.

## Safety
- Writeback preserves human decisions, checks eligibility + version, and never duplicates comments.
- Reproduction is a standard step, always attempted **safely** — security test tenant, synthetic
  accounts/data, non-destructive, no unsafe/DoS payloads, no production auth against real accounts;
  when it can't be done safely it records `blocked` and proceeds on code evidence.
- Security QA verdicts require runtime evidence — source-code review, unit tests, and PR state alone
  are never sufficient for a verdict.
- Scope is **new-to-scope after activation** — the pre-existing backlog is never auto-processed.
