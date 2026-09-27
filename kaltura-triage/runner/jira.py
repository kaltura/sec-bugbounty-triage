"""Jira access for the runner.

Live access goes through the Claude Code CLI (`claude -p`) so it reuses the
Atlassian connector rather than a stored API token. IMPORTANT: the connector must
be added to the CLI (`claude mcp add ...`) — `runner.py doctor` checks this. Until
then, live polling/investigation is BLOCKED by design (the pilot is read-only and
not activated).

Writes are NOT performed here in the pilot; writeback (when enabled) is done by
runner.writeback against a client, after review.
"""
from __future__ import annotations
import json, re, subprocess


class NotConfigured(RuntimeError):
    pass


class CliJira:
    def __init__(self, cfg):
        self.cfg = cfg
        self.bin = cfg["investigator"]["claude_bin"]
        self.model = cfg["investigator"].get("model")

    def _claude(self, prompt: str, timeout: int = 300) -> str:
        cmd = [self.bin, "-p", prompt, "--output-format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        # read-only tool set for polling/reads
        cmd += ["--permission-mode", "plan"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            raise NotConfigured(f"claude -p failed (rc={p.returncode}): {p.stderr[:400]}")
        return p.stdout

    @staticmethod
    def _extract_json(text: str):
        # tolerate a fenced ```json block or the CLI's own json envelope
        m = re.search(r"```json\s*(.+?)```", text, re.S)
        blob = m.group(1) if m else text
        try:
            return json.loads(blob)
        except Exception:  # noqa: BLE001
            m2 = re.search(r"(\[.*\]|\{.*\})", blob, re.S)
            if not m2:
                raise
            return json.loads(m2.group(1))

    def search(self, jql: str, fields=None) -> list[dict]:
        fields = fields or ["summary", "status", "labels", "created", "updated"]
        prompt = (
            "Use the Atlassian tools. Run this Jira JQL search and print ONLY a fenced "
            "```json array of objects with keys key, status, labels, created, updated. "
            f"cloudId {self.cfg['jira']['cloud_id']}. JQL: {jql}")
        return self._extract_json(self._claude(prompt))

    def get_issue(self, key: str, fields=None) -> dict:
        prompt = (
            "Use the Atlassian tools. Fetch this Jira issue and print ONLY a fenced ```json "
            "object with keys key, version, and fields (summary, description, status, labels, "
            "priority, comment, attachment). "
            f"cloudId {self.cfg['jira']['cloud_id']}. issue {key}")
        return self._extract_json(self._claude(prompt))


def make_client(cfg):
    backend = cfg["investigator"].get("backend", "rest")
    if backend == "rest":
        from runner.jira_rest import RestJira
        return RestJira(cfg)
    if backend == "cli":
        return CliJira(cfg)
    raise NotConfigured(f"unknown backend {backend!r}")
