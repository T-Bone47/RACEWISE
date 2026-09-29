"""Phase 6T: bounded persistence for autonomous investigation runs.

The deterministic 6N engine is derived-on-read with zero storage growth;
the only artifacts an autonomous run needs to persist are the run record
itself (stage ledger, decision trace, budget ledger, engine reference,
memory derivation) so it can be retrieved, continued across budget
boundaries and replayed.

This store is deliberately minimal and self-contained: one SQLite table,
append-mostly (insert + status update), zero writes to any legacy store.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional


def get_autonomous_run_store(db_path: Optional[str] = None) \
        -> "AutonomousRunStore":
    if db_path is None:
        data_dir = Path(
            os.environ.get(
                "RACEWISE_DATA_DIR",
                str(Path.cwd() / ".racewise")))
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(Path(data_dir) / "autonomous_runs.db")
    return AutonomousRunStore(db_path)


class AutonomousRunStore:
    """SQLite persistence for Phase 6T run records (bounded, append-only)."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autonomous_runs (
                    run_id TEXT PRIMARY KEY,
                    question_text TEXT NOT NULL,
                    context TEXT NOT NULL,
                    constraints TEXT NOT NULL,
                    status TEXT NOT NULL,
                    failed_stage TEXT,
                    engine_investigation_id TEXT,
                    engine_output_hash TEXT,
                    record TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def upsert_run(self, record: dict[str, Any]) -> None:
        run_id = str(record["run_id"])
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO autonomous_runs
                    (run_id, question_text, context, constraints, status,
                     failed_stage, engine_investigation_id,
                     engine_output_hash, record, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    failed_stage = excluded.failed_stage,
                    engine_investigation_id =
                        excluded.engine_investigation_id,
                    engine_output_hash = excluded.engine_output_hash,
                    record = excluded.record,
                    updated_at = excluded.updated_at
                """,
                (
                    run_id,
                    str(record.get("question_text") or ""),
                    json.dumps(record.get("context") or {}),
                    json.dumps(record.get("budget") or {}),
                    str(record.get("status") or ""),
                    record.get("failed_stage"),
                    (record.get("engine_result_ref") or {}).get(
                        "investigation_id"),
                    (record.get("engine_result_ref") or {}).get("output_hash"),
                    json.dumps(record, sort_keys=True),
                    now, now,
                ),
            )

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT record FROM autonomous_runs WHERE run_id = ?",
                (run_id,)).fetchone()
        if row is None:
            return None
        return json.loads(row["record"])

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT run_id, question_text, status, failed_stage, "
                "engine_investigation_id, engine_output_hash, created_at, "
                "updated_at FROM autonomous_runs "
                "ORDER BY updated_at DESC LIMIT ?",
                (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def count_runs(self) -> int:
        with self._conn() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM autonomous_runs").fetchone()[0])
