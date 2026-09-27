# Handoff — running the Kaltura triage skill on another employee's Mac

This moves two things to the other person's machine:
1. **The skill** → `~/.claude/skills/kaltura-bug-bounty-triage/` (works standalone for manual triage in the Claude Code desktop app).
2. **The local runner** (automatic intake) → `~/.claude/kaltura-triage/`.

The skill is usable on its own; the runner is optional automation on top.

---

## What the other machine needs first (prerequisites)
- **macOS** with **Claude Code** installed and signed in (`claude --version`).
- **GitHub CLI** authenticated to the `kaltura` org: `gh auth login` (scopes: repo, read:org).
- **python3** (macOS ships it; 3.9+).
- **Jira access** to project **SECF** for that person's account, and a **Jira API token** they create (stored in their own Keychain — see Enable). No MCP connector is needed; the runner talks to Jira over REST.

Each person operates under **their own** Jira/GitHub identity and permissions. Nothing here shares credentials, and no secrets are copied in the bundle.

---

## Choose a transfer method

### Option A — Bundle (pure files), simplest
On the source machine:
```bash
bash ~/.claude/kaltura-triage/package.sh          # writes ~/Downloads/kaltura-triage-bundle.tgz
```
`package.sh` includes the skill, runner code, config (reset to safe defaults), docs, and the product-notes **content** — and **excludes** `state.db`, `cases/` (internal per-ticket assessments), `logs/`, and git history. Send the `.tgz` over an approved internal channel. On the target machine:
```bash
mkdir -p ~/extract && tar -xzf kaltura-triage-bundle.tgz -C ~/extract
cp -R ~/extract/skill ~/.claude/skills/kaltura-bug-bounty-triage
cp -R ~/extract/kaltura-triage ~/.claude/kaltura-triage
bash ~/.claude/kaltura-triage/install.sh
```

### Option B — Private GitHub repo (recommended for 2+ people / ongoing updates)
Put `skill/` + `kaltura-triage/` (same exclusions as the bundle) in a **private** repo under the org, e.g. `kaltura/sec-bugbounty-triage`. Each person:
```bash
git clone git@github.com:kaltura/sec-bugbounty-triage.git
cp -R sec-bugbounty-triage/skill ~/.claude/skills/kaltura-bug-bounty-triage
cp -R sec-bugbounty-triage/kaltura-triage ~/.claude/kaltura-triage
bash ~/.claude/kaltura-triage/install.sh
```
Keep `state.db`, `cases/`, `logs/`, and product-notes `.git/` out of the repo (a `.gitignore` with those entries). Product-notes **content** can be shared and even centralized in the repo so everyone benefits from accumulated knowledge; each clone keeps its own local commits. **Never** commit secrets, tokens, customer data, or raw exploit attachments. I can create this repo for you with `gh` on request.

### Option C — Skill only (.skill file)
If the other person only needs manual triage (no automation), package just the skill with the skill-creator packager and they import it; skip the runner entirely.

---

## What is machine-specific (never copy as-is)
- `state.db` — that machine's queue/claims. Recreated automatically.
- `cases/` — internal per-ticket assessments (keep on the machine that produced them).
- `logs/` — local logs.
- `config.json` absolute paths + `investigator.claude_bin` — `install.sh` rewrites these for the new machine (and the runner falls back to `which claude` at runtime).
- `~/Library/LaunchAgents/com.kaltura.bugbounty-triage.plist` — generated per machine by `install.sh` from the template.
- The activation **baseline** — each machine records its own the first time it activates.

---

## How automation runs (read this first)
There are two ways to run the pipeline; pick per operator:

- **Full automation (recommended): a Claude desktop-app scheduled task.** It runs the whole
  loop unattended — detect → investigate (skill) → write back to Jira — because it runs as
  an app-launched session with working Claude auth. See **`automation/autotriage-task.md`**
  for the prompt and setup. Runs while the app is open.
- **Manual:** run the `kaltura-bug-bounty-triage` skill on a ticket in the desktop app, then
  apply the writeback over REST (`writeback KEY --apply`).

Why not a launchd `claude -p` for the investigator: on a Mac where the desktop app brokers
Claude auth over an IPC socket, a **cold `claude` launched by launchd or a plain terminal
has no auth channel and stalls at startup** — it can't get credentials. (This is an auth
issue, not a security block, and it's unrelated to whether MCP servers or AgenShield are
present.) So the *investigation* must run in an app session; the scheduled task is exactly
that. The launchd runner (`runner.py start`) still works as an optional standalone
**detector** (it only queues, never runs Claude), but for full automation you don't need it —
keep `scheduler_enabled=false` to avoid two pollers.

## Enable (same on any machine; nothing acts until you do these)
`install.sh` leaves everything OFF. Set `jira_rest.account_email` in `config.json` to the
operator's email first. Then:
1. Create a Jira API token at https://id.atlassian.com/manage-profile/security/api-tokens and store it in the Keychain (paste into the hidden `security` prompt):
   ```bash
   cd ~/.claude/kaltura-triage && python3 -m runner.runner set-token
   ```
2. `python3 -m runner.runner doctor` → expect **READY** + "Jira REST reachable". The
   headless `claude -p` line is informational and never gates READY (the scheduled task,
   not `claude -p`, is what runs the investigator).
3. Try one ticket manually first:
   ```bash
   python3 -m runner.runner run-ticket SECF-XXXX     # stages cases/SECF-XXXX/input.json + prints the steps
   # in the desktop app, run the kaltura-bug-bounty-triage skill on it → writes cases/SECF-XXXX/assessment.json
   python3 -m runner.runner writeback SECF-XXXX       # dry-run diff; add --apply to write
   ```
4. `python3 -m runner.runner activate` → baseline so only tickets **new-to-scope after now**
   are in scope. If a prior detector run left tickets queued, clear them first (they are
   pre-existing) — `activate` stops re-queuing but does not empty an existing queue.
5. Enable the modes and turn on full automation:
   ```bash
   python3 -m runner.runner set-mode reproduction_enabled true
   python3 -m runner.runner set-mode writeback_enabled true
   ```
   Then create the scheduled task per **`automation/autotriage-task.md`** (hourly; paste the
   prompt there) and click **Run now** once to validate + pre-approve its tools. That is the
   full detect→investigate→writeback loop, hands-off.
6. Leave the launchd detector **off** (`scheduler_enabled=false`) — the scheduled task does
   its own detection. Only use `runner.py start` if you specifically want the standalone
   launchd detector (queue-only) in addition.

**Modes:** `writeback_enabled` gates all Jira writes (manual and automated). `reproduction_enabled`
makes reproduction a standard, always-*attempted* step, bounded to a **safe** path (security test
tenant, synthetic accounts/data, non-destructive, no unsafe/DoS payloads, no production auth against
real accounts); when it can't be done safely it records `reproduction: blocked` and proceeds on code
evidence.

Each operator uses **their own** token (their Keychain, their Jira identity). Never share tokens or copy `state.db`/`cases/`.

Stop anytime: `python3 -m runner.runner stop`. Status: `python3 -m runner.runner status | queue | fail-summary`.
Per-ticket manual loop: `run-ticket <KEY>` → skill in desktop app → `writeback <KEY> [--apply]` (or `done <KEY>`).

---

## Operating notes
- The LaunchAgent detector runs **only while the person is logged in and the Mac is awake**; it does not change sleep settings and catches up on wake (missed interval + watermark/baseline). It only detects + queues — it never runs `claude`.
- Investigation is manual in the desktop app; manual writeback is over REST (`writeback`). This is by design where AgenShield blocks headless `claude`.
- Components: every finished handling adds **Agent Check** + one team component (Sec-KMS / Sec-EP / Sec-BE / Devops OVP-Sec / Devops OTT-Sec) based on where the fix lives. These already exist in SECF.
- Safety logic (human-override, provisional-vs-confirmed severity, idempotency, unrelated-label/component preservation, comment-visibility gate, recovery) is covered by `python3 -m runner.tests.test_operational_risks` (run it after install; expect all checks passing).
