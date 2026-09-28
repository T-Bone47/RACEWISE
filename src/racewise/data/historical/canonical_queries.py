"""Canonical historical data queries for the RACEWISE tool layer.

Read-only access to the canonical SQLite store so tools, MCP, and golden
investigations can resolve historical sessions without touching raw CSVs.
All availability answers are data-derived (record counts) - never inferred
from season years.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CANONICAL_TABLE_FOR_ENTITY = {
    "results": "canonical_results",
    "qualifying": "canonical_qualifying",
    "pit_stops": "canonical_pit_stops",
    "laps": "canonical_lap_times",
    "stints": "canonical_stints",
    "weather": "canonical_weather",
    "race_control": "canonical_race_control",
}


def _default_db_path() -> str:
    data_dir = Path(os.environ.get("RACEWISE_DATA_DIR", Path.cwd() / "data"))
    return str(data_dir / "canonical" / "canonical.db")


class CanonicalQueries:
    """Read-only queries over the canonical historical store."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # -- resolution ----------------------------------------------------------

    def resolve_race(self, season: int, round_num: Optional[int] = None, grand_prix: Optional[str] = None) -> Optional[dict]:
        """Resolve a race by (season, round) or by season + grand prix key."""
        with self._conn() as conn:
            if round_num is not None:
                row = conn.execute(
                    "SELECT * FROM canonical_races WHERE season = ? AND round = ?", (season, round_num)
                ).fetchone()
            elif grand_prix:
                row = conn.execute(
                    "SELECT * FROM canonical_races WHERE season = ? AND grand_prix = ? ORDER BY round LIMIT 1",
                    (season, grand_prix.lower()),
                ).fetchone()
            else:
                return None
            return dict(row) if row else None

    def resolve_session(self, season: int, round_num: int, session_type: str) -> Optional[dict]:
        """Resolve a session deterministically by race + session type."""
        race = self.resolve_race(season, round_num=round_num)
        if race is None:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM canonical_sessions WHERE race_id = ? AND session_type = ?",
                (race["race_id"], session_type.upper()),
            ).fetchone()
            if row is None:
                return None
            session = dict(row)
            session["race"] = race
            return session

    def list_race_sessions(self, season: int, round_num: int) -> list[dict]:
        race = self.resolve_race(season, round_num=round_num)
        if race is None:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT session_id, session_type, date_start, laps_total FROM canonical_sessions "
                "WHERE race_id = ? ORDER BY date_start NULLS LAST, session_type",
                (race["race_id"],),
            ).fetchall()
            return [dict(r) for r in rows]

    # -- availability ---------------------------------------------------------

    def get_availability(self, season: int, round_num: int, session_type: str) -> Optional[dict]:
        """Data-derived availability flags for one session."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT c.* FROM canonical_session_catalog c
                JOIN canonical_races r ON r.race_id = c.race_id
                WHERE r.season = ? AND r.round = ? AND c.session_type = ?
                """,
                (season, round_num, session_type.upper()),
            ).fetchone()
            return dict(row) if row else None

    # -- session data ----------------------------------------------------------

    def get_results(self, season: int, round_num: int, session_type: str = "RACE") -> list[dict]:
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT res.*, d.full_name AS driver_name, d.code AS driver_code,
                       d.driver_key AS driver_key, c.name AS constructor_name
                FROM canonical_results res
                JOIN canonical_drivers d ON d.driver_id = res.driver_id
                LEFT JOIN canonical_constructors c ON c.constructor_id = res.constructor_id
                WHERE res.session_id = ?
                ORDER BY res.position_order NULLS LAST
                """,
                (session["session_id"],),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_qualifying(self, season: int, round_num: int, session_type: str = "QUALIFYING") -> list[dict]:
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT q.*, d.full_name AS driver_name, d.code AS driver_code, d.driver_key, c.name AS constructor_name
                FROM canonical_qualifying q
                JOIN canonical_drivers d ON d.driver_id = q.driver_id
                LEFT JOIN canonical_constructors c ON c.constructor_id = q.constructor_id
                WHERE q.session_id = ?
                ORDER BY q.position NULLS LAST
                """,
                (session["session_id"],),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_pit_stops(self, season: int, round_num: int, session_type: str = "RACE", driver_key: Optional[str] = None) -> list[dict]:
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return []
        query = """
            SELECT p.*, d.driver_key, d.full_name AS driver_name, d.code AS driver_code
            FROM canonical_pit_stops p
            JOIN canonical_drivers d ON d.driver_id = p.driver_id
            WHERE p.session_id = ?
        """
        params: list[Any] = [session["session_id"]]
        if driver_key:
            query += " AND d.driver_key = ?"
            params.append(driver_key)
        query += " ORDER BY p.lap, p.stop_number"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_lap_times(self, season: int, round_num: int, session_type: str = "RACE", driver_key: Optional[str] = None) -> list[dict]:
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return []
        query = """
            SELECT lt.*, d.driver_key, d.full_name AS driver_name, d.code AS driver_code
            FROM canonical_lap_times lt
            JOIN canonical_drivers d ON d.driver_id = lt.driver_id
            WHERE lt.session_id = ?
        """
        params: list[Any] = [session["session_id"]]
        if driver_key:
            query += " AND d.driver_key = ?"
            params.append(driver_key)
        query += " ORDER BY lt.lap_number"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_driver(self, driver_key: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM canonical_drivers WHERE driver_key = ?", (driver_key,)).fetchone()
            return dict(row) if row else None

    def get_driver_by_code(self, code: str, season: Optional[int] = None) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM canonical_drivers WHERE code = ? COLLATE NOCASE ORDER BY date_of_birth NULLS LAST",
                (code,),
            ).fetchall()
            return [dict(r) for r in rows]

    def catalog_search(
        self,
        season: Optional[int] = None,
        session_type: Optional[str] = None,
        availability: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query the canonical session catalog."""
        query = "SELECT * FROM canonical_session_catalog WHERE 1=1"
        params: list[Any] = []
        if season is not None:
            query += " AND season = ?"
            params.append(season)
        if session_type:
            query += " AND session_type = ?"
            params.append(session_type.upper())
        if availability:
            query += " AND results_availability = ?"
            params.append(availability)
        query += " ORDER BY season, round, session_type LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # -- modern provider data (FastF1) ----------------------------------------

    def get_stints(
        self,
        season: int,
        round_num: int,
        session_type: str = "RACE",
        driver_key: Optional[str] = None,
    ) -> list[dict]:
        """Canonical stints for a session (FastF1-sourced where ingested)."""
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return []
        query = """
            SELECT st.*, d.driver_key, d.full_name AS driver_name, d.code AS driver_code
            FROM canonical_stints st
            JOIN canonical_drivers d ON d.driver_id = st.driver_id
            WHERE st.session_id = ?
        """
        params: list[Any] = [session["session_id"]]
        if driver_key:
            query += " AND d.driver_key = ?"
            params.append(driver_key)
        query += " ORDER BY d.driver_key, st.stint_number"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_weather(self, season: int, round_num: int, session_type: str = "RACE") -> list[dict]:
        """Canonical weather observations for a session, time-ordered."""
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM canonical_weather WHERE session_id = ?
                   ORDER BY timestamp""",
                (session["session_id"],),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_race_control(self, season: int, round_num: int, session_type: str = "RACE") -> list[dict]:
        """Canonical race-control events for a session, time-ordered."""
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM canonical_race_control WHERE session_id = ?
                   ORDER BY timestamp, rowid""",
                (session["session_id"],),
            ).fetchall()
            return [dict(r) for r in rows]

    # -- telemetry (Phase 6C, bounded) -----------------------------------------

    TELEMETRY_SIGNALS = ("speed", "throttle", "brake", "gear", "rpm", "drs")
    MAX_TELEMETRY_SAMPLES = 2_000  # hard bound per query, protects agent context

    # Canonical signal -> wide-format column (all channels share one time index).
    TELEMETRY_COLUMNS = {
        "speed": "speed_kmh",
        "throttle": "throttle_pct",
        "brake": "brake",
        "gear": "gear",
        "rpm": "rpm",
        "drs": "drs",
    }

    def get_lap_telemetry(
        self,
        season: int,
        round_num: int,
        driver_key: str,
        lap_number: int,
        session_type: str = "RACE",
        signals: Optional[list[str]] = None,
        max_samples: int = MAX_TELEMETRY_SAMPLES,
    ) -> list[dict]:
        """Bounded telemetry samples for one driver-lap.

        Hard-bounded: signal whitelist, per-query sample cap. lap_time_s is
        lap-relative seconds (source SessionTime - LapStartTime, documented
        calculation); time_elapsed_s is session-relative. Returns [] when the
        session or driver-lap has no telemetry rows (UNAVAILABLE, never zero).
        """
        if signals:
            bad = [s for s in signals if s not in self.TELEMETRY_SIGNALS]
            if bad:
                raise ValueError(f"unknown telemetry signals: {bad}")
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return []
        limit = min(int(max_samples), self.MAX_TELEMETRY_SAMPLES)
        cols = [self.TELEMETRY_COLUMNS[s] for s in (signals or self.TELEMETRY_SIGNALS)]
        wanted = signals or list(self.TELEMETRY_SIGNALS)
        select = ", ".join(cols)
        sql = f"""
            SELECT t.lap_number, t.time_elapsed_s, t.lap_time_s, {select},
                   t.source_provider, t.source_version, d.driver_key
            FROM canonical_telemetry t
            JOIN canonical_drivers d ON d.driver_id = t.driver_id
            WHERE t.session_id = ? AND d.driver_key = ? AND t.lap_number = ?
        """
        params: list[Any] = [session["session_id"], driver_key, int(lap_number)]
        sql += " ORDER BY t.lap_time_s LIMIT ?"
        params.append(limit + 1)
        with self._conn() as conn:
            raw_rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        if len(raw_rows) > limit:
            raw_rows = raw_rows[:limit]
        rows: list[dict] = []
        for r in raw_rows:
            for signal in wanted:
                v = r.get(self.TELEMETRY_COLUMNS[signal])
                if v is None:
                    continue
                rows.append({
                    "lap_number": r["lap_number"], "time_elapsed_s": r["time_elapsed_s"],
                    "lap_time_s": r["lap_time_s"], "signal": signal, "value": v,
                    "source_provider": r["source_provider"], "source_version": r["source_version"],
                    "driver_key": r["driver_key"],
                })
        # The cap bounds OUTPUT samples (signal-expanded), not raw rows: a
        # 3-signal request over 1000 timestamps must never return 3000 rows.
        return rows[:limit]

    def get_telemetry_driver_pair(
        self, season: int, round_num: int, session_type: str = "RACE",
    ) -> Optional[tuple[str, str]]:
        """Deterministic telemetry driver pair for a session (Phase 6E).

        The pair ingested under the bounded policy (top-2 classified at
        ingestion time), ordered by driver_key for determinism. Returns None
        when the session has no telemetry.
        """
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return None
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT d.driver_key FROM canonical_telemetry t
                   JOIN canonical_drivers d ON d.driver_id = t.driver_id
                   WHERE t.session_id = ?
                   GROUP BY d.driver_key ORDER BY d.driver_key""",
                (session["session_id"],),
            ).fetchall()
        keys = [r["driver_key"] for r in rows]
        if len(keys) < 2:
            return None
        return keys[0], keys[1]

    def telemetry_summary(self, season: int, round_num: int, session_type: str = "RACE") -> dict:
        """Count-derived telemetry availability for a session (no year heuristics)."""
        session = self.resolve_session(season, round_num, session_type)
        if session is None:
            return {"available": False, "sample_count": 0, "drivers": 0, "laps": []}
        with self._conn() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM canonical_telemetry WHERE session_id = ?",
                (session["session_id"],),
            ).fetchone()[0]
            drivers = conn.execute(
                "SELECT COUNT(DISTINCT driver_id) FROM canonical_telemetry WHERE session_id = ?",
                (session["session_id"],),
            ).fetchone()[0]
            laps = [r[0] for r in conn.execute(
                "SELECT DISTINCT lap_number FROM canonical_telemetry WHERE session_id = ? ORDER BY lap_number",
                (session["session_id"],),
            ).fetchall()]
        return {
            "available": n > 0,
            "sample_count": n,
            "drivers": drivers,
            "laps": laps,
        }


@lru_cache(maxsize=4)
def get_canonical_queries(db_path: Optional[str] = None) -> CanonicalQueries:
    return CanonicalQueries(db_path)
