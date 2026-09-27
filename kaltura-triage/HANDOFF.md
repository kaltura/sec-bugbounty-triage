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

## Endpoint-security note (read this first)
If the target Mac runs **AgenShield** (a macOS Endpoint Security system extension) or
similar tooling that mediates Claude — as the source machine does — a bare `claude`
process launched by launchd or a plain terminal is **held at exec** and unattended
headless `claude -p` cannot run. That is expected and is why the runner is
**detector + manual**: the launchd agent only detects and queues new tickets; you
investigate each in the Claude desktop app (the sanctioned path) and apply writeback
over REST. On a machine WITHOUT such tooling, `run-ticket --headless` and fuller
automation can work, but detector + manual is the supported default.

## Enable (same on any machine; nothing acts until you do these)
`install.sh` leaves everything OFF. Set `jira_rest.account_email` in `config.json` to the
operator's email first. Then:
1. Create a Jira API token at https://id.atlassian.com/manage-profile/security/api-tokens and store it in the Keychain (paste into the hidden `security` prompt):
   ```bash
   cd ~/.claude/kaltura-triage && python3 -m runner.runner set-token
   ```
   (Optional, only for `run-ticket --headless` on a non-AgenShield machine: `claude setup-token` then `python3 -m runner.runner set-claude-token`. Not needed for detector + manual.)
2. `python3 -m runner.runner doctor`  → expect **READY (detector + manual)** + "Jira REST reachable". The headless line is an informational `[--]`/`[ok]` note and never gates READY.
3. Stage a ticket and investigate it in the desktop app:
   ```bash
   python3 -m runner.runner run-ticket SECF-XXXX     # stages cases/SECF-XXXX/input.json + prints the steps
   # open the desktop app, run the kaltura-bug-bounty-triage skill on it → writes cases/SECF-XXXX/assessment.json
   python3 -m runner.runner writeback SECF-XXXX       # dry-run diff (no writes)
   ```
4. `python3 -m runner.runner activate` → records the baseline so only tickets that become **new-to-scope after now** are detected.
5. `python3 -m runner.runner set-mode scheduler_enabled true` then `python3 -m runner.runner start` (loads the LaunchAgent detector; polls every ~7 min while awake, queueing new tickets — never running claude).
6. `writeback_enabled` is on for **manual** writeback (`writeback SECF-XXXX --apply`). `reproduction_enabled` is **on**: reproduction is a standard step of every triage, always *attempted* but bounded to a **safe** path (security test tenant, synthetic accounts/data, non-destructive, no unsafe/DoS payloads, no production auth against real accounts); if it can't be done safely it records `reproduction: blocked` + needs-input. The automation never investigates or writes to Jira on this machine (detector-only).

Each operator uses **their own** token (their Keychain, their Jira identity). Never share tokens or copy `state.db`/`cases/`.

Stop anytime: `python3 -m runner.runner stop`. Status: `python3 -m runner.runner status | queue | fail-summary`.
Per-ticket manual loop: `run-ticket <KEY>` → skill in desktop app → `writeback <KEY> [--apply]` (or `done <KEY>`).

---

## Operating notes
- The LaunchAgent detector runs **only while the person is logged in and the Mac is awake**; it does not change sleep settings and catches up on wake (missed interval + watermark/baseline). It only detects + queues — it never runs `claude`.
- Investigation is manual in the desktop app; manual writeback is over REST (`writeback`). This is by design where AgenShield blocks headless `claude`.
- Components: every finished handling adds **Agent Check** + one team component (Sec-KMS / Sec-EP / Sec-BE / Devops OVP-Sec / Devops OTT-Sec) based on where the fix lives. These already exist in SECF.
- Safety logic (human-override, provisional-vs-confirmed severity, idempotency, unrelated-label/component preservation, comment-visibility gate, recovery) is covered by `python3 -m runner.tests.test_operational_risks` (run it after install; expect all checks passing).
