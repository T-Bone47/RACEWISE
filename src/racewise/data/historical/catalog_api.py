"""Catalog Explorer backend: filtered, paginated session catalog over the
canonical store (Phase 6B).

Read-only. All capability flags are data-derived from canonical_session_catalog
(actual record counts). Never returns the full 5,000+ session dataset without
pagination. This is the single source of truth for the frontend Catalog
Explorer and mirrors what MCP historical tools expose.
"""
from __future__ import annotations

import os
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from racewise.data.historical.telemetry_policy import TelemetrySessionStatus

CATALOG_API_VERSION = "1.0.0"

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

FILTERABLE_SESSION_TYPES = (
    "RACE", "QUALIFYING", "SPRINT", "SPRINT_QUALIFYING", "FREE_PRACTICE_1",
    "FREE_PRACTICE_2", "FREE_PRACTICE_3", "FREE_PRACTICE_4", "QUALIFYING_1",
    "QUALIFYING_2", "PRE_QUALIFYING", "WARMING_UP",
)

_CAPABILITY_COLUMNS = {
    "results": ("results_count", "results_availability"),
    "qualifying": ("qualifying_count", "qualifying_availability"),
    "pit_stops": ("pit_stops_count", "pit_stops_availability"),
    "laps": ("laps_count", "laps_availability"),
    "stints": ("stints_count", "stints_availability"),
    "weather": ("weather_count", "weather_availability"),
    "race_control": ("race_control_count", "race_control_availability"),
    "telemetry": ("telemetry_count", "telemetry_availability"),
}


def _default_db_path() -> str:
    data_dir = Path(os.environ.get("RACEWISE_DATA_DIR", Path.cwd() / "data"))
    return str(data_dir / "canonical" / "canonical.db")


class CatalogAPI:
    """Filtered/paginated catalog queries with honest capability states."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or _default_db_path()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -- session listing ------------------------------------------------------

    def list_sessions(
        self,
        season: Optional[int] = None,
        season_from: Optional[int] = None,
        season_to: Optional[int] = None,
        country: Optional[str] = None,
        circuit: Optional[str] = None,
        session_type: Optional[str] = None,
        provider: Optional[str] = None,
        availability: Optional[str] = None,
        capability: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        """Filtered, paginated catalog listing.

        capability: one of the capability names (results, stints, weather, ...)
                    filtered on that capability being AVAILABLE.
        """
        page = max(1, page)
        page_size = min(max(1, page_size), MAX_PAGE_SIZE)
        where: list[str] = []
        params: list[Any] = []
        if season is not None:
            where.append("c.season = ?")
            params.append(season)
        if season_from is not None:
            where.append("c.season >= ?")
            params.append(season_from)
        if season_to is not None:
            where.append("c.season <= ?")
            params.append(season_to)
        if country:
            where.append("c.country LIKE ?")
            params.append(f"%{country}%")
        if circuit:
            where.append("c.circuit_name LIKE ?")
            params.append(f"%{circuit}%")
        if session_type:
            where.append("c.session_type = ?")
            params.append(session_type.upper())
        if provider:
            where.append("c.source_provider = ?")
            params.append(provider)
        if availability:
            where.append("c.results_availability = ?")
            params.append(availability.upper())
        if capability:
            if capability not in _CAPABILITY_COLUMNS:
                raise ValueError(f"unknown capability {capability!r}")
            count_col, avail_col = _CAPABILITY_COLUMNS[capability]
            where.append(f"c.{avail_col} = 'AVAILABLE'")
        if search:
            like = f"%{search}%"
            where.append(
                "(c.race_name LIKE ? OR c.circuit_name LIKE ? OR c.country LIKE ? "
                "OR CAST(c.season AS TEXT) LIKE ?)"
            )
            params.extend([like, like, like, like])

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM canonical_session_catalog c {where_sql}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""SELECT c.* FROM canonical_session_catalog c {where_sql}
                    ORDER BY c.season DESC, c.round ASC, c.session_type ASC
                    LIMIT ? OFFSET ?""",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return {
            "api_version": CATALOG_API_VERSION,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
            "sessions": [self._session_entry(r) for r in rows],
        }

    # -- session detail ---------------------------------------------------------

    def session_detail(self, season: int, round_num: int, session_type: str) -> Optional[dict]:
        """Full detail for one session: identity, providers, capabilities, provenance."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT c.* FROM canonical_session_catalog c
                   JOIN canonical_races r ON r.race_id = c.race_id
                   WHERE c.season = ? AND c.round = ? AND c.session_type = ?""",
                (season, round_num, session_type.upper()),
            ).fetchone()
            if row is None:
                return None
            providers = [
                r["source_provider"]
                for r in conn.execute(
                    """SELECT DISTINCT source_provider FROM canonical_stints WHERE session_id = ?
                       UNION SELECT DISTINCT source_provider FROM canonical_weather WHERE session_id = ?
                       UNION SELECT DISTINCT source_provider FROM canonical_race_control WHERE session_id = ?
                       UNION SELECT DISTINCT source_provider FROM canonical_results WHERE session_id = ?""",
                    (row["session_id"],) * 4,
                )
                if r["source_provider"]
            ]
        entry = self._session_entry(row)
        entry["capabilities"]["telemetry"] = self._telemetry_capability(row)
        entry["providers"] = sorted(set(providers) | {row["source_provider"]})
        entry["provenance"] = {
            "source_provider": row["source_provider"],
            "source_version": self._session_source_versions(conn_unused := None, row),
            "catalog_updated_at": row["updated_at"],
        }
        return entry

    # -- helpers --------------------------------------------------------------

    def _telemetry_capability(self, row: sqlite3.Row) -> dict:
        """Count-derived telemetry capability (Phase 6C): never year-based.

        The availability rebuild writes telemetry_count/telemetry_availability
        from actual canonical_telemetry rows; this maps them to the policy
        vocabulary without ever assuming availability.
        """
        count = row["telemetry_available"] if "telemetry_available" in row.keys() else 0
        if count and count > 0:
            return {
                "status": TelemetrySessionStatus.INGESTED.value,
                "available": True,
                "count": count,
            }
        return {
            "status": TelemetrySessionStatus.NOT_INGESTED.value,
            "available": False,
            "note": "No telemetry rows ingested (bounded Phase 6C policy; opt-in only).",
        }

    def _session_source_versions(self, _unused: Any, row: sqlite3.Row) -> Optional[str]:
        return None  # per-row versions live on detail tables; catalog carries counts

    def _session_entry(self, row: sqlite3.Row) -> dict[str, Any]:
        capabilities: dict[str, Any] = {}
        for name, (count_col, avail_col) in _CAPABILITY_COLUMNS.items():
            if name == "telemetry":
                continue  # handled separately
            capabilities[name] = {
                "count": row[count_col],
                "availability": row[avail_col],
            }
        return {
            "session_id": row["session_id"],
            "season": row["season"],
            "round": row["round"],
            "race_name": row["race_name"],
            "circuit": row["circuit_name"],
            "country": row["country"],
            "date": row["date"],
            "session_type": row["session_type"],
            "capabilities": capabilities,
        }


@lru_cache(maxsize=4)
def get_catalog_api(db_path: Optional[str] = None) -> CatalogAPI:
    return CatalogAPI(db_path)
