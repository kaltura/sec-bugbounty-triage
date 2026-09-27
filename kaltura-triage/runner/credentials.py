"""Credential access via the macOS Keychain — the Jira API token is NEVER stored
in config, argv, logs, or this repo. `set-token` lets the Keychain prompt for the
value (so it never passes through argv or this process); `get_token` reads it at
runtime only to build the Authorization header.

Guideline: secrets come from a secure store, are never hardcoded, and are never logged.
"""
from __future__ import annotations
import getpass, subprocess, sys

SERVICE = "kaltura-triage-jira"                 # Keychain service: Jira API token
SERVICE_CLAUDE = "kaltura-triage-claude-oauth"  # Keychain service: Claude Code OAuth token


def set_token_interactive(account: str, service: str = SERVICE, label: str = "Jira API token",
                          from_stdin: bool = False) -> int:
    """Store a secret in the Keychain under `service`. With from_stdin, the value is
    read from stdin (use `pbpaste | ... --stdin` — paste-proof, avoids hidden-prompt
    mangling of long tokens); otherwise it is read hidden via getpass. Clears any
    prior item first and verifies it round-trips. The value is held only in memory
    and passed once to `security`; never written to config, logs, or this repo."""
    if from_stdin:
        tok = sys.stdin.read().strip()
    else:
        try:
            tok = getpass.getpass(f"Paste {label} (input hidden), then Enter: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\naborted — nothing stored.")
            return 1
    if not tok:
        print("empty input — nothing stored.")
        return 1
    subprocess.run(["security", "delete-generic-password", "-s", service, "-a", account],
                   capture_output=True)
    p = subprocess.run(["security", "add-generic-password", "-U", "-s", service,
                        "-a", account, "-w", tok], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"security failed: {p.stderr.strip()[:200]}")
        return p.returncode
    return 0 if get_token(account, service) else 1


def get_token(account: str, service: str = SERVICE) -> str | None:
    """Read a secret from the Keychain. Returns None if absent. Never logs it."""
    try:
        p = subprocess.run(["security", "find-generic-password", "-s", service,
                            "-a", account, "-w"], capture_output=True, text=True, timeout=15)
    except Exception:  # noqa: BLE001
        return None
    if p.returncode != 0:
        return None
    tok = p.stdout.strip()
    return tok or None


def token_present(account: str, service: str = SERVICE) -> bool:
    return get_token(account, service) is not None
