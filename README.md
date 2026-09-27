# sec-bugbounty-triage

Kaltura HackerOne / coordinated-disclosure triage tooling. Two separable pieces:

- **`skill/`** → install to `~/.claude/skills/kaltura-bug-bounty-triage/`. Standalone; use it for
  manual triage in the Claude desktop app. This is the minimum you need.
- **`kaltura-triage/`** → install to `~/.claude/kaltura-triage/`. Optional local automation: a launchd
  **detector** that queues new-to-scope SECF-29234 tickets, plus a REST **writeback** CLI.

## Install
```bash
cp -R skill ~/.claude/skills/kaltura-bug-bounty-triage
cp -R kaltura-triage ~/.claude/kaltura-triage
bash ~/.claude/kaltura-triage/install.sh
```
Then follow **`kaltura-triage/HANDOFF.md`** to enable it (each person uses their own Jira token in their
own Keychain; nothing here contains secrets, tokens, `state.db`, `cases/`, or logs).

## Architecture note
On Macs running AgenShield (endpoint-security), a bare `claude` exec is held, so unattended headless
investigation can't run — the tooling is **detector + manual** there (auto-detect/queue; investigate in
the desktop app; writeback over REST). See `kaltura-triage/README.md` and `HANDOFF.md`.

Reproduction is a standard step of every triage, always attempted **safely** (security test tenant,
synthetic accounts/data, non-destructive, no unsafe/DoS payloads, no production auth against real accounts).
