"""Durable local state for the Kaltura triage runner (SQLite, single-writer).

State machine per ticket: pending -> running -> {completed | needs_input | failed}.
failed/needs_input can return to pending on retry / new evidence.

This module owns durability, atomic claiming, interruption recovery, bounded
retries with backoff, and daily run caps. It has no Jira or Claude dependency,
so it is unit-testable on its own.
"""
from __future__ import annotations
import os, sqlite3, time, json, hashlib, contextlib
from datetime import datetime, timezone

PENDING, RUNNING, NEEDS_INPUT, COMPLETED, FAILED = (
    "pending", "running", "needs_input", "completed", "failed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS tickets (
  key TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  fingerprint TEXT,
  run_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  claimed_by TEXT,
  claimed_at REAL,
  first_seen REAL,
  updated_at REAL,
  next_earliest REAL DEFAULT 0,
  assessment_path TEXT,
  writeback_outcome TEXT,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  ticket TEXT,
  started_at REAL,
  ended_at REAL,
  status TEXT,
  tokens INTEGER DEFAULT 0,
  note TEXT
);
CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, runs INTEGER NOT NULL DEFAULT 0);
"""


def now() -> float:
    return time.time()


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def report_fingerprint(issue: dict) -> str:
    """Fingerprint the REPORT side only, so the runner's own comments/labels/
    priority never look like a substantive update. Used to detect real new
    evidence and to avoid reprocessing unchanged tickets."""
    f = issue.get("fields", issue)
    parts = {
        "summary": f.get("summary"),
        "description": f.get("description"),
        # attachments (ids) and non-skill comment ids/bodies
        "attachments": sorted([a.get("id") for a in (f.get("attachment") or [])]),
        "comments": [
            {"id": c.get("id"), "body": c.get("body")}
            for c in (((f.get("comment") or {}).get("comments")) or [])
            if "Security triage assessment" not in str(c.get("body", ""))
        ],
    }
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


class Store:
    def __init__(self, path: str):
        self.path = path
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL;")
        self.db.executescript(SCHEMA)

    # ---- kv (watermark, baseline) ----
    def kv_get(self, key, default=None):
        r = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def kv_set(self, key, value):
        self.db.execute("INSERT INTO kv(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value)))

    # ---- ticket lifecycle ----
    def upsert_pending(self, key: str, fingerprint: str) -> str:
        """Enqueue a ticket, or re-open it if the report fingerprint changed
        (substantive update). Returns 'new' | 'updated' | 'unchanged'."""
        row = self.db.execute("SELECT status,fingerprint FROM tickets WHERE key=?", (key,)).fetchone()
        t = now()
        if row is None:
            self.db.execute(
                "INSERT INTO tickets(key,status,fingerprint,first_seen,updated_at) VALUES(?,?,?,?,?)",
                (key, PENDING, fingerprint, t, t))
            return "new"
        if row["fingerprint"] != fingerprint:
            # substantive change -> re-open for a fresh investigation
            self.db.execute(
                "UPDATE tickets SET status=?,fingerprint=?,updated_at=?,attempts=0,next_earliest=0,"
                "claimed_by=NULL,claimed_at=NULL WHERE key=?",
                (PENDING, fingerprint, t, key))
            return "updated"
        return "unchanged"

    def claim_next(self, worker: str, daily_cap: int) -> sqlite3.Row | None:
        """Atomically claim one eligible pending ticket (respects backoff and the
        daily run cap). Single-writer via BEGIN IMMEDIATE."""
        t = now()
        with self._tx():
            if self._runs_today() >= daily_cap:
                return None
            row = self.db.execute(
                "SELECT key FROM tickets WHERE status=? AND next_earliest<=? "
                "ORDER BY first_seen LIMIT 1", (PENDING, t)).fetchone()
            if not row:
                return None
            rid = f"run-{time.time_ns()}-{row['key']}"
            n = self.db.execute(
                "UPDATE tickets SET status=?,claimed_by=?,claimed_at=?,run_id=?,attempts=attempts+1 "
                "WHERE key=? AND status=?",
                (RUNNING, worker, t, rid, row["key"], PENDING)).rowcount
            if n != 1:
                return None
            self.db.execute("INSERT INTO runs(run_id,ticket,started_at,status) VALUES(?,?,?,?)",
                            (rid, row["key"], t, RUNNING))
            self._bump_runs_today()
            return self.db.execute("SELECT * FROM tickets WHERE key=?", (row["key"],)).fetchone()

    def finish(self, key, status, assessment_path=None, writeback_outcome=None,
               error=None, tokens=0, backoff=(300, 1800, 7200), max_attempts=3):
        t = now()
        row = self.db.execute("SELECT run_id,attempts FROM tickets WHERE key=?", (key,)).fetchone()
        final = status
        next_earliest = 0
        if status == FAILED and row and row["attempts"] < max_attempts:
            # schedule a retry with backoff instead of terminal failure
            idx = min(row["attempts"] - 1, len(backoff) - 1)
            next_earliest = t + backoff[max(idx, 0)]
            final = PENDING
        self.db.execute(
            "UPDATE tickets SET status=?,claimed_by=NULL,claimed_at=NULL,updated_at=?,"
            "next_earliest=?,assessment_path=COALESCE(?,assessment_path),"
            "writeback_outcome=COALESCE(?,writeback_outcome),last_error=? WHERE key=?",
            (final, t, next_earliest, assessment_path, writeback_outcome, error, key))
        if row and row["run_id"]:
            self.db.execute("UPDATE runs SET ended_at=?,status=?,tokens=?,note=? WHERE run_id=?",
                            (t, status, tokens, error, row["run_id"]))

    def recover_abandoned(self, stale_seconds: int) -> list[str]:
        """Reset RUNNING claims older than stale_seconds back to PENDING
        (interrupted runs / crashed worker). Idempotent."""
        cutoff = now() - stale_seconds
        rows = self.db.execute("SELECT key FROM tickets WHERE status=? AND claimed_at<?",
                               (RUNNING, cutoff)).fetchall()
        for r in rows:
            self.db.execute(
                "UPDATE tickets SET status=?,claimed_by=NULL,claimed_at=NULL WHERE key=?",
                (PENDING, r["key"]))
            self.db.execute("UPDATE runs SET status='recovered',ended_at=? "
                            "WHERE ticket=? AND status=?", (now(), r["key"], RUNNING))
        return [r["key"] for r in rows]

    def needs_input(self, key, reason):
        self.db.execute("UPDATE tickets SET status=?,claimed_by=NULL,claimed_at=NULL,"
                        "last_error=?,updated_at=? WHERE key=?",
                        (NEEDS_INPUT, reason, now(), key))
        row = self.db.execute("SELECT run_id FROM tickets WHERE key=?", (key,)).fetchone()
        if row and row["run_id"]:
            self.db.execute("UPDATE runs SET status=?,ended_at=?,note=? WHERE run_id=?",
                            (NEEDS_INPUT, now(), reason, row["run_id"]))

    def counts(self) -> dict:
        rows = self.db.execute("SELECT status,COUNT(*) c FROM tickets GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rows}

    def list_by_status(self, status) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM tickets WHERE status=? ORDER BY updated_at DESC",
                               (status,)).fetchall()

    def all_tickets(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM tickets ORDER BY updated_at DESC").fetchall()

    # ---- helpers ----
    @contextlib.contextmanager
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _runs_today(self) -> int:
        r = self.db.execute("SELECT runs FROM usage WHERE day=?", (_day(),)).fetchone()
        return r["runs"] if r else 0

    def _bump_runs_today(self):
        self.db.execute("INSERT INTO usage(day,runs) VALUES(?,1) "
                        "ON CONFLICT(day) DO UPDATE SET runs=runs+1", (_day(),))

    def close(self):
        self.db.close()
