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
                SELECT res.*, d.full_name AS driver_name, d.code AS driver_code, c.name AS constructor_name
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
                SELECT q.*, d.full_name AS driver_name, d.code AS driver_code, c.name AS constructor_name
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


@lru_cache(maxsize=4)
def get_canonical_queries(db_path: Optional[str] = None) -> CanonicalQueries:
    return CanonicalQueries(db_path)
