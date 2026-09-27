#!/usr/bin/env bash
# Per-machine installer for the Kaltura bug-bounty triage runner (macOS).
# Idempotent. Does NOT enable the schedule or any write mode — it only wires paths,
# checks prerequisites, and stages the LaunchAgent. Run `runner.py doctor` afterwards.
set -euo pipefail

ROOT="${KTRI_ROOT:-$HOME/.claude/kaltura-triage}"
SKILL_DIR="$HOME/.claude/skills/kaltura-bug-bounty-triage"
LA_DIR="$HOME/Library/LaunchAgents"
PLIST="$LA_DIR/com.kaltura.bugbounty-triage.plist"

echo "== Kaltura triage installer =="
echo "data root: $ROOT"

# 1) sanity: files present
[ -f "$ROOT/config.json" ] || { echo "FATAL: $ROOT/config.json missing — copy the data root first."; exit 1; }
[ -f "$SKILL_DIR/SKILL.md" ] || echo "WARN: skill not found at $SKILL_DIR — copy the skill folder too (see HANDOFF.md)."

# 2) prerequisites
command -v python3 >/dev/null || { echo "FATAL: python3 not found"; exit 1; }
CLAUDE_BIN="$(command -v claude || true)"
[ -n "$CLAUDE_BIN" ] || echo "WARN: 'claude' CLI not on PATH — install Claude Code and re-run."
command -v gh >/dev/null || echo "WARN: 'gh' not found — install GitHub CLI and 'gh auth login' (kaltura org)."

# 3) point config.claude_bin at THIS machine's claude (runner also falls back at runtime)
if [ -n "$CLAUDE_BIN" ]; then
  python3 - "$ROOT/config.json" "$CLAUDE_BIN" <<'PY'
import json,sys
p,cbin=sys.argv[1],sys.argv[2]
c=json.load(open(p)); c["investigator"]["claude_bin"]=cbin; json.dump(c,open(p,"w"),indent=2)
print("set investigator.claude_bin =",cbin)
PY
fi

# 4) product-notes local git (never pushed)
if [ ! -d "$ROOT/product-notes/.git" ]; then
  git -C "$ROOT/product-notes" init -q && \
  git -C "$ROOT/product-notes" add -A && \
  git -C "$ROOT/product-notes" commit -q -m "init product notes on this machine" || true
fi

# 5) stage the LaunchAgent from the template (NOT loaded)
mkdir -p "$LA_DIR" "$ROOT/logs"
CLAUDE_DIR="$(dirname "${CLAUDE_BIN:-$HOME/.local/bin/claude}")"
sed -e "s#__ROOT__#$ROOT#g" -e "s#__CLAUDE_BIN_DIR__#$CLAUDE_DIR#g" \
    "$ROOT/launchd/com.kaltura.bugbounty-triage.plist.template" > "$PLIST"
echo "staged LaunchAgent: $PLIST (not loaded)"

# 6) self-test + doctor
( cd "$ROOT" && python3 -m runner.tests.test_operational_risks >/tmp/ktri_test.log 2>&1 \
  && echo "self-test: $(tail -1 /tmp/ktri_test.log)" || echo "self-test FAILED — see /tmp/ktri_test.log" )
echo; ( cd "$ROOT" && python3 -m runner.runner doctor ) || true

cat <<EOF

Next (manual, when you choose to activate — see HANDOFF.md):
  1) Add the Atlassian connector to the CLI so headless runs can reach Jira:
       claude mcp add --transport http atlassian https://mcp.atlassian.com/v1/sse   # then authenticate
  2) cd "$ROOT" && python3 -m runner.runner doctor          # expect READY
  3) python3 -m runner.runner run-ticket SECF-XXXX          # read-only smoke test
  4) python3 -m runner.runner activate                      # record baseline (only new-to-scope after now)
  5) python3 -m runner.runner set-mode scheduler_enabled true
  6) python3 -m runner.runner start                         # launchctl load
Writeback stays OFF until you explicitly: set-mode writeback_enabled true (after review).
EOF
