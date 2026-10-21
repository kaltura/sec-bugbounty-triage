#!/usr/bin/env bash
# Top-level installer for Kaltura security skills (macOS/Linux).
# Installs both skills to ~/.claude/skills/ and optionally the runner.
# Idempotent — safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"
RUNNER_DIR="$HOME/.claude/kaltura-triage"

echo "== Kaltura security skills installer =="
echo "source: $SCRIPT_DIR"

# 1) Install kaltura-bug-bounty-triage skill
TRIAGE_DEST="$SKILLS_DIR/kaltura-bug-bounty-triage"
echo ""
echo "Installing kaltura-bug-bounty-triage → $TRIAGE_DEST"
mkdir -p "$TRIAGE_DEST"
cp -R "$SCRIPT_DIR/skill/"* "$TRIAGE_DEST/"
echo "  done."

# 2) Install kaltura-security-qa skill
QA_DEST="$SKILLS_DIR/kaltura-security-qa"
echo "Installing kaltura-security-qa → $QA_DEST"
mkdir -p "$QA_DEST"
cp -R "$SCRIPT_DIR/security-qa-skill/"* "$QA_DEST/"
echo "  done."

# 3) Verify both skills installed
echo ""
echo "Verifying installed skills:"
for SKILL in kaltura-bug-bounty-triage kaltura-security-qa; do
  SKILL_FILE="$SKILLS_DIR/$SKILL/SKILL.md"
  if [ -f "$SKILL_FILE" ]; then
    NAME=$(grep '^name:' "$SKILL_FILE" | head -1 | sed 's/^name: *//')
    echo "  [OK] $SKILL ($NAME)"
  else
    echo "  [FAIL] $SKILL — SKILL.md not found at $SKILL_FILE"
  fi
done

# 4) Optionally install the runner
if [ -d "$SCRIPT_DIR/kaltura-triage" ]; then
  echo ""
  echo "Installing runner → $RUNNER_DIR"
  mkdir -p "$RUNNER_DIR"
  cp -R "$SCRIPT_DIR/kaltura-triage/"* "$RUNNER_DIR/"
  if [ -f "$RUNNER_DIR/install.sh" ]; then
    echo "Running runner installer..."
    bash "$RUNNER_DIR/install.sh"
  fi
else
  echo ""
  echo "Runner directory not found — skipping runner install."
fi

echo ""
echo "== Installation complete =="
echo ""
echo "Installed skills:"
echo "  ~/.claude/skills/kaltura-bug-bounty-triage  (initial triage)"
echo "  ~/.claude/skills/kaltura-security-qa        (post-fix QA)"
echo ""
echo "Restart Claude desktop app or start a new conversation to pick up the skills."
