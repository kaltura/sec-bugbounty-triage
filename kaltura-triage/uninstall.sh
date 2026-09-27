#!/usr/bin/env bash
# Stop and unstage the runner on this machine. Leaves data (state/cases/notes) in place.
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/com.kaltura.bugbounty-triage.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST" && echo "removed LaunchAgent $PLIST" || true
echo "Data left intact under ${KTRI_ROOT:-$HOME/.claude/kaltura-triage}. Delete it manually if desired."
