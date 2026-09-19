"""SQLite-backed investigation store with full event sourcing support."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from racewise.domain.schemas import (
    Conclusion,
    Counterfactual,
    Evidence,
    EvidenceType,
    EventLogEntry,
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
    Observation,
    ReplayResult,
    ToolExecution,
)


_DB_LOCK = threading.Lock()
_STORE_INSTANCE: Optional["InvestigationStore"] = None


def get_store(db_path: Optional[str] = None) -> "InvestigationStore":
    """Get or create the singleton investigation store."""
    global _STORE_INSTANCE
    with _DB_LOCK:
        if _STORE_INSTANCE is None:
            _STORE_INSTANCE = InvestigationStore(db_path)
        return _STORE_INSTANCE


class InvestigationStore:
    """Persistent storage for investigations, evidence, provenance, and replay."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            data_dir = Path(os.environ.get("RACEWISE_DATA_DIR", Path.cwd() / ".racewise"))
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "investigations.db")
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema with all required tables."""
        with self._conn() as conn:
            # Session catalog table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_key TEXT PRIMARY KEY,
                    year INTEGER NOT NULL,
                    round INTEGER,
                    event TEXT NOT NULL,
                    session_type TEXT NOT NULL,
                    event_name TEXT,
                    circuit TEXT,
                    date TEXT,
                    total_laps INTEGER,
                    drivers TEXT DEFAULT '[]',
                    data_source TEXT DEFAULT 'fastf1',
                    availability TEXT NOT NULL DEFAULT 'AVAILABLE',
                    availability_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Investigations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS investigations (
                    investigation_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    session_type TEXT NOT NULL DEFAULT 'R',
                    driver TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    conclusion_id TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            # Hypotheses table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hypotheses (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    predicted_observables TEXT DEFAULT '[]',
                    required_evidence TEXT DEFAULT '[]',
                    potential_falsifiers TEXT DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'PROPOSED',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    supporting_evidence TEXT DEFAULT '[]',
                    contradicting_evidence TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id) ON DELETE CASCADE
                )
            """)

            # Observations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value TEXT NOT NULL,
                    unit TEXT,
                    time_window TEXT,
                    source TEXT NOT NULL,
                    method_version TEXT NOT NULL,
                    tool_execution_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id) ON DELETE CASCADE
                )
            """)

            # Evidence table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    observation_ids TEXT DEFAULT '[]',
                    tool_execution_id TEXT,
                    supports TEXT DEFAULT '[]',
                    contradicts TEXT DEFAULT '[]',
                    strength REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id) ON DELETE CASCADE
                )
            """)

            # Evidence relationships (graph edges)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence_relationships (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    provenance TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id) ON DELETE CASCADE
                )
            """)

            # Tool executions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_executions (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    tool_version TEXT NOT NULL,
                    input TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    output TEXT,
                    output_hash TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT,
                    timestamp TEXT NOT NULL,
                    duration_ms INTEGER,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id) ON DELETE CASCADE
                )
            """)

            # Counterfactuals table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS counterfactuals (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    baseline_id TEXT,
                    intervention TEXT NOT NULL,
                    assumptions TEXT DEFAULT '[]',
                    predicted_delta_s REAL,
                    uncertainty_s REAL,
                    simulator_version TEXT NOT NULL,
                    scenario_params TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id) ON DELETE CASCADE
                )
            """)

            # Conclusions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conclusions (
                    id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL UNIQUE,
                    statement TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    evidence_ids TEXT DEFAULT '[]',
                    counterfactual_ids TEXT DEFAULT '[]',
                    limitations TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id) ON DELETE CASCADE
                )
            """)

            # Event log (provenance) table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_log (
                    event_id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload TEXT DEFAULT '{}',
                    FOREIGN KEY (investigation_id) REFERENCES investigations(investigation_id) ON DELETE CASCADE
                )
            """)

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hypotheses_inv ON hypotheses(investigation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_observations_inv ON observations(investigation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_inv ON evidence(investigation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_executions_inv ON tool_executions(investigation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_counterfactuals_inv ON counterfactuals(investigation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_log_inv ON event_log(investigation_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_rels_inv ON evidence_relationships(investigation_id)")

    # -- Investigation CRUD ----------------------------------------------------

    def create_investigation(
        self,
        question: str,
        year: int,
        event: str,
        driver: str,
        session_type: str = "R",
        metadata: Optional[dict] = None,
    ) -> str:
        """Create a new investigation and return its ID."""
        investigation_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO investigations (investigation_id, question, year, event, session_type, driver, state, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (investigation_id, question, year, event, session_type, driver, InvestigationState.CREATED.value, now, now, json.dumps(metadata or {})),
            )
        return investigation_id

    def get_investigation(self, investigation_id: str) -> Optional[dict]:
        """Load investigation metadata."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM investigations WHERE investigation_id = ?", (investigation_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_investigation_state(self, investigation_id: str, state: InvestigationState) -> None:
        """Update investigation state and timestamp."""
        with self._conn() as conn:
            now = datetime.now(timezone.utc).isoformat()
            if state == InvestigationState.COMPLETED:
                conn.execute(
                    "UPDATE investigations SET state = ?, updated_at = ?, completed_at = ? WHERE investigation_id = ?",
                    (state.value, now, now, investigation_id),
                )
            else:
                conn.execute(
                    "UPDATE investigations SET state = ?, updated_at = ? WHERE investigation_id = ?",
                    (state.value, now, investigation_id),
                )

    def set_investigation_conclusion(self, investigation_id: str, conclusion_id: str) -> None:
        """Link conclusion to investigation."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE investigations SET conclusion_id = ? WHERE investigation_id = ?",
                (conclusion_id, investigation_id),
            )

    def list_investigations(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List investigations with pagination."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT investigation_id, question, year, event, driver, state, created_at, completed_at FROM investigations ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_investigation(self, investigation_id: str) -> bool:
        """Delete investigation and all related data (cascades)."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM investigations WHERE investigation_id = ?", (investigation_id,))
            return cursor.rowcount > 0

    # -- Hypotheses ------------------------------------------------------------

    def save_hypothesis(self, investigation_id: str, hypothesis: Hypothesis) -> None:
        """Insert or update a hypothesis."""
        with self._conn() as conn:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO hypotheses (id, investigation_id, statement, predicted_observables, required_evidence, potential_falsifiers, status, confidence, supporting_evidence, contradicting_evidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    statement = excluded.statement,
                    predicted_observables = excluded.predicted_observables,
                    required_evidence = excluded.required_evidence,
                    potential_falsifiers = excluded.potential_falsifiers,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    supporting_evidence = excluded.supporting_evidence,
                    contradicting_evidence = excluded.contradicting_evidence,
                    updated_at = excluded.updated_at
                """,
                (
                    hypothesis.id,
                    investigation_id,
                    hypothesis.statement,
                    json.dumps(hypothesis.predicted_observables),
                    json.dumps(hypothesis.required_evidence),
                    json.dumps(hypothesis.potential_falsifiers),
                    hypothesis.status.value,
                    hypothesis.confidence,
                    json.dumps(hypothesis.supporting_evidence),
                    json.dumps(hypothesis.contradicting_evidence),
                    now,
                    now,
                ),
            )

    def get_hypotheses(self, investigation_id: str) -> list[Hypothesis]:
        """Load all hypotheses for an investigation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM hypotheses WHERE investigation_id = ? ORDER BY created_at", (investigation_id,)
            ).fetchall()
            return [
                Hypothesis(
                    id=row["id"],
                    statement=row["statement"],
                    predicted_observables=json.loads(row["predicted_observables"]),
                    required_evidence=json.loads(row["required_evidence"]),
                    potential_falsifiers=json.loads(row["potential_falsifiers"]),
                    status=HypothesisStatus(row["status"]),
                    confidence=row["confidence"],
                    supporting_evidence=json.loads(row["supporting_evidence"]),
                    contradicting_evidence=json.loads(row["contradicting_evidence"]),
                )
                for row in rows
            ]

    # -- Observations ----------------------------------------------------------

    def save_observation(self, investigation_id: str, observation: Observation) -> None:
        """Save an observation."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO observations (id, investigation_id, metric, value, unit, time_window, source, method_version, tool_execution_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    observation.id,
                    investigation_id,
                    observation.metric,
                    json.dumps(observation.value),
                    observation.unit,
                    observation.time_window,
                    observation.source,
                    observation.method_version,
                    observation.tool_execution_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_observations(self, investigation_id: str) -> list[Observation]:
        """Load all observations for an investigation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM observations WHERE investigation_id = ? ORDER BY created_at", (investigation_id,)
            ).fetchall()
            return [
                Observation(
                    id=row["id"],
                    metric=row["metric"],
                    value=json.loads(row["value"]),
                    unit=row["unit"],
                    time_window=row["time_window"],
                    source=row["source"],
                    method_version=row["method_version"],
                    tool_execution_id=row["tool_execution_id"],
                )
                for row in rows
            ]

    # -- Evidence --------------------------------------------------------------

    def save_evidence(self, investigation_id: str, evidence: Evidence) -> None:
        """Insert or update evidence."""
        with self._conn() as conn:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO evidence (id, investigation_id, type, statement, observation_ids, tool_execution_id, supports, contradicts, strength, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    statement = excluded.statement,
                    observation_ids = excluded.observation_ids,
                    tool_execution_id = excluded.tool_execution_id,
                    supports = excluded.supports,
                    contradicts = excluded.contradicts,
                    strength = excluded.strength
                """,
                (
                    evidence.id,
                    investigation_id,
                    evidence.type.value,
                    evidence.statement,
                    json.dumps(evidence.observation_ids),
                    evidence.tool_execution_id,
                    json.dumps(evidence.supports),
                    json.dumps(evidence.contradicts),
                    evidence.strength,
                    now,
                ),
            )

    def get_evidence(self, investigation_id: str) -> list[Evidence]:
        """Load all evidence for an investigation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE investigation_id = ? ORDER BY created_at", (investigation_id,)
            ).fetchall()
            return [
                Evidence(
                    id=row["id"],
                    type=EvidenceType(row["type"]),
                    statement=row["statement"],
                    observation_ids=json.loads(row["observation_ids"]),
                    tool_execution_id=row["tool_execution_id"],
                    supports=json.loads(row["supports"]),
                    contradicts=json.loads(row["contradicts"]),
                    strength=row["strength"],
                )
                for row in rows
            ]

    # -- Evidence Relationships (Graph) ----------------------------------------

    def add_evidence_relationship(
        self,
        investigation_id: str,
        source_id: str,
        target_id: str,
        relationship_type: str,
        provenance: Optional[str] = None,
    ) -> str:
        """Add a directed edge between evidence nodes."""
        rel_id = uuid.uuid4().hex[:8]
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO evidence_relationships (id, investigation_id, source_id, target_id, relationship_type, provenance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rel_id, investigation_id, source_id, target_id, relationship_type, provenance, datetime.now(timezone.utc).isoformat()),
            )
        return rel_id

    def get_evidence_relationships(self, investigation_id: str) -> list[dict]:
        """Load all evidence relationships for an investigation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence_relationships WHERE investigation_id = ?", (investigation_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    # -- Tool Executions -------------------------------------------------------

    def save_tool_execution(self, investigation_id: str, execution: ToolExecution) -> None:
        """Insert or update a tool execution."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tool_executions (id, investigation_id, tool, tool_version, input, input_hash, output, output_hash, status, error, timestamp, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    tool_version = excluded.tool_version,
                    output = excluded.output,
                    output_hash = excluded.output_hash,
                    status = excluded.status,
                    error = excluded.error,
                    duration_ms = excluded.duration_ms
                """,
                (
                    execution.id,
                    investigation_id,
                    execution.tool,
                    execution.tool_version,
                    json.dumps(execution.input),
                    execution.input_hash,
                    json.dumps(execution.output) if execution.output else None,
                    execution.output_hash,
                    execution.status,
                    execution.error,
                    execution.timestamp.isoformat() if execution.timestamp else datetime.now(timezone.utc).isoformat(),
                    execution.duration_ms,
                ),
            )

    def get_tool_executions(self, investigation_id: str) -> list[ToolExecution]:
        """Load all tool executions for an investigation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_executions WHERE investigation_id = ? ORDER BY timestamp", (investigation_id,)
            ).fetchall()
            return [
                ToolExecution(
                    id=row["id"],
                    investigation_id=row["investigation_id"],
                    tool=row["tool"],
                    tool_version=row["tool_version"],
                    input=json.loads(row["input"]),
                    input_hash=row["input_hash"],
                    output=json.loads(row["output"]) if row["output"] else None,
                    output_hash=row["output_hash"],
                    status=row["status"],
                    error=row["error"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    duration_ms=row["duration_ms"],
                )
                for row in rows
            ]

    # -- Counterfactuals -------------------------------------------------------

    def save_counterfactual(self, investigation_id: str, counterfactual: Counterfactual) -> None:
        """Save a counterfactual."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO counterfactuals (id, investigation_id, baseline_id, intervention, assumptions, predicted_delta_s, uncertainty_s, simulator_version, scenario_params, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    counterfactual.id,
                    investigation_id,
                    counterfactual.baseline_id,
                    counterfactual.intervention,
                    json.dumps(counterfactual.assumptions),
                    counterfactual.predicted_delta_s,
                    counterfactual.uncertainty_s,
                    counterfactual.simulator_version,
                    json.dumps(counterfactual.scenario_params),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_counterfactuals(self, investigation_id: str) -> list[Counterfactual]:
        """Load all counterfactuals for an investigation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM counterfactuals WHERE investigation_id = ? ORDER BY created_at", (investigation_id,)
            ).fetchall()
            return [
                Counterfactual(
                    id=row["id"],
                    baseline_id=row["baseline_id"],
                    intervention=row["intervention"],
                    assumptions=json.loads(row["assumptions"]),
                    predicted_delta_s=row["predicted_delta_s"],
                    uncertainty_s=row["uncertainty_s"],
                    simulator_version=row["simulator_version"],
                    scenario_params=json.loads(row["scenario_params"]),
                )
                for row in rows
            ]

    # -- Conclusions -----------------------------------------------------------

    def save_conclusion(self, investigation_id: str, conclusion: Conclusion) -> str:
        """Save a conclusion and return its ID."""
        conclusion_id = uuid.uuid4().hex[:8]
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO conclusions (id, investigation_id, statement, confidence, evidence_ids, counterfactual_ids, limitations, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                    statement = excluded.statement,
                    confidence = excluded.confidence,
                    evidence_ids = excluded.evidence_ids,
                    counterfactual_ids = excluded.counterfactual_ids,
                    limitations = excluded.limitations
                """,
                (
                    conclusion_id,
                    investigation_id,
                    conclusion.statement,
                    conclusion.confidence,
                    json.dumps(conclusion.evidence_ids),
                    json.dumps(conclusion.counterfactual_ids),
                    json.dumps(conclusion.limitations),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return conclusion_id

    def get_conclusion(self, investigation_id: str) -> Optional[Conclusion]:
        """Load conclusion for an investigation."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM conclusions WHERE investigation_id = ?", (investigation_id,)
            ).fetchone()
            if row:
                return Conclusion(
                    statement=row["statement"],
                    confidence=row["confidence"],
                    evidence_ids=json.loads(row["evidence_ids"]),
                    counterfactual_ids=json.loads(row["counterfactual_ids"]),
                    limitations=json.loads(row["limitations"]),
                )
            return None

    # -- Event Log (Provenance) ------------------------------------------------

    def save_event(self, event: EventLogEntry) -> None:
        """Append an event to the investigation's event log."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO event_log (event_id, investigation_id, type, timestamp, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.investigation_id,
                    event.type,
                    event.timestamp.isoformat() if event.timestamp else datetime.now(timezone.utc).isoformat(),
                    json.dumps(event.payload),
                ),
            )

    def get_event_log(self, investigation_id: str) -> list[EventLogEntry]:
        """Load full event log for an investigation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM event_log WHERE investigation_id = ? ORDER BY timestamp", (investigation_id,)
            ).fetchall()
            return [
                EventLogEntry(
                    event_id=row["event_id"],
                    investigation_id=row["investigation_id"],
                    type=row["type"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    payload=json.loads(row["payload"]),
                )
                for row in rows
            ]

    # -- Replay Support --------------------------------------------------------

    def get_tool_executions_for_replay(self, investigation_id: str) -> list[dict]:
        """Get tool executions with inputs for replay."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT tool, input, output_hash FROM tool_executions WHERE investigation_id = ? AND status = 'completed' ORDER BY timestamp",
                (investigation_id,),
            ).fetchall()
            return [
                {"tool": row["tool"], "input": json.loads(row["input"]), "output_hash": row["output_hash"]}
                for row in rows
            ]

    # -- Export ----------------------------------------------------------------

    def export_investigation(self, investigation_id: str) -> Optional[dict]:
        """Export full investigation as a JSON-serializable dict."""
        inv = self.get_investigation(investigation_id)
        if not inv:
            return None

        return {
            "investigation": inv,
            "hypotheses": [h.model_dump() for h in self.get_hypotheses(investigation_id)],
            "observations": [o.model_dump() for o in self.get_observations(investigation_id)],
            "evidence": [e.model_dump() for e in self.get_evidence(investigation_id)],
            "evidence_relationships": self.get_evidence_relationships(investigation_id),
            "tool_executions": [te.model_dump() for te in self.get_tool_executions(investigation_id)],
            "counterfactuals": [cf.model_dump() for cf in self.get_counterfactuals(investigation_id)],
            "conclusion": self.get_conclusion(investigation_id).model_dump() if self.get_conclusion(investigation_id) else None,
            "event_log": [e.model_dump() for e in self.get_event_log(investigation_id)],
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    # -- Session Catalog -----------------------------------------------------

    def upsert_session(
        self,
        session_key: str,
        year: int,
        event: str,
        session_type: str,
        round_num: Optional[int] = None,
        event_name: Optional[str] = None,
        circuit: Optional[str] = None,
        date: Optional[str] = None,
        total_laps: Optional[int] = None,
        drivers: Optional[list[str]] = None,
        data_source: str = "fastf1",
        availability: str = "AVAILABLE",
        availability_reason: Optional[str] = None,
    ) -> None:
        """Insert or update a session in the catalog."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_key, year, round, event, session_type, event_name, circuit, date, total_laps, drivers, data_source, availability, availability_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    year = excluded.year,
                    round = excluded.round,
                    event = excluded.event,
                    session_type = excluded.session_type,
                    event_name = excluded.event_name,
                    circuit = excluded.circuit,
                    date = excluded.date,
                    total_laps = excluded.total_laps,
                    drivers = excluded.drivers,
                    data_source = excluded.data_source,
                    availability = excluded.availability,
                    availability_reason = excluded.availability_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    session_key,
                    year,
                    round_num,
                    event,
                    session_type,
                    event_name,
                    circuit,
                    date,
                    total_laps,
                    json.dumps(drivers or []),
                    data_source,
                    availability,
                    availability_reason,
                    now,
                    now,
                ),
            )

    def get_session(self, session_key: str) -> Optional[dict]:
        """Get session by session_key."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_key = ?", (session_key,)
            ).fetchone()
            return dict(row) if row else None

    def list_sessions(
        self, year: Optional[int] = None, event: Optional[str] = None, session_type: Optional[str] = None
    ) -> list[dict]:
        """List sessions with optional filters."""
        query = "SELECT * FROM sessions WHERE 1=1"
        params = []
        if year:
            query += " AND year = ?"
            params.append(year)
        if event:
            query += " AND event = ?"
            params.append(event)
        if session_type:
            query += " AND session_type = ?"
            params.append(session_type)
        query += " ORDER BY year DESC, round ASC, event, session_type"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_session_drivers(self, session_key: str) -> list[str]:
        """Get list of drivers for a session."""
        session = self.get_session(session_key)
        if session and session["drivers"]:
            return json.loads(session["drivers"])
        return []

    def set_session_availability(self, session_key: str, availability: str, reason: Optional[str] = None) -> bool:
        """Set session availability status."""
        with self._conn() as conn:
            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                "UPDATE sessions SET availability = ?, availability_reason = ?, updated_at = ? WHERE session_key = ?",
                (availability, reason, now, session_key),
            )
            return cursor.rowcount > 0