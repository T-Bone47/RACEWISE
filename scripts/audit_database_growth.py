"""Database growth and query-performance audit (Phase 6B).

Read-only audit of the canonical store:
- per-table row counts and storage pages
- representative tool-layer queries timed p50/p95
Run manually or from CI (no writes, no downloads):

    python scripts/audit_database_growth.py [path-to-db]
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

DEFAULT_DB = Path("data/canonical/canonical.db")

TABLES = [
    "canonical_seasons", "canonical_circuits", "canonical_drivers",
    "canonical_constructors", "canonical_races", "canonical_sessions",
    "canonical_results", "canonical_qualifying", "canonical_pit_stops",
    "canonical_lap_times", "canonical_stints", "canonical_weather",
    "canonical_race_control", "canonical_session_catalog",
]

QUERIES = {
    "catalog_page": """SELECT season, round, race_name, session_type, stints_availability,
        weather_availability FROM canonical_session_catalog WHERE season = ?
        ORDER BY round LIMIT 50""",
    "session_detail_counts": """SELECT
        (SELECT COUNT(*) FROM canonical_results r JOIN canonical_sessions s ON r.session_id=s.session_id
         JOIN canonical_races ra ON s.race_id=ra.race_id WHERE ra.season=2023 AND s.session_type='RACE') AS results,
        (SELECT COUNT(*) FROM canonical_lap_times WHERE session_id IN
         (SELECT s.session_id FROM canonical_sessions s JOIN canonical_races ra ON s.race_id=ra.race_id
          WHERE ra.season=2023 AND s.session_type='RACE')) AS laps""",
    "stints_by_session": """SELECT st.* FROM canonical_stints st
        JOIN canonical_sessions s ON st.session_id = s.session_id
        JOIN canonical_races r ON s.race_id = r.race_id
        WHERE r.season = 2023 AND s.session_type = 'RACE' LIMIT 100""",
    "weather_by_session": """SELECT w.* FROM canonical_weather w
        JOIN canonical_sessions s ON w.session_id = s.session_id
        JOIN canonical_races r ON s.race_id = r.race_id
        WHERE r.season = 2023 AND s.session_type = 'RACE' LIMIT 100""",
    "race_control_by_session": """SELECT rc.* FROM canonical_race_control rc
        JOIN canonical_sessions s ON rc.session_id = s.session_id
        JOIN canonical_races r ON s.race_id = r.race_id
        WHERE r.season = 2023 AND s.session_type = 'RACE' LIMIT 100""",
    "driver_lap_history": """SELECT l.lap_number, l.time_s, l.compound FROM canonical_lap_times l
        WHERE l.session_id = (SELECT s.session_id FROM canonical_sessions s
            JOIN canonical_races r ON s.race_id = r.race_id
            WHERE r.season = 2023 AND r.round = 1 AND s.session_type = 'RACE')
        LIMIT 500""",
    "availability_lookup": """SELECT stints_availability, weather_availability, race_control_availability
        FROM canonical_session_catalog WHERE season = 2023 AND session_type = 'RACE'""",
}


def audit(db_path: Path) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    report: dict = {"db_path": str(db_path), "db_bytes": db_path.stat().st_size, "tables": {}, "queries": {}}

    for table in TABLES:
        try:
            rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            pages = conn.execute(
                "SELECT SUM(pgsize) FROM dbstat WHERE name = ?", (table,)
            ).fetchone()[0] if conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='dbstat'"
            ).fetchone()[0] else None
            report["tables"][table] = {"rows": rows, "bytes": pages}
        except sqlite3.OperationalError as exc:
            report["tables"][table] = {"error": str(exc)}

    for name, sql in QUERIES.items():
        params: tuple = ()
        if "?" in sql:
            params = (2023,) if "catalog_page" in name else ()
        samples: list[float] = []
        for _ in range(15):
            t0 = time.perf_counter()
            conn.execute(sql, params).fetchall()
            samples.append((time.perf_counter() - t0) * 1000)
        report["queries"][name] = {
            "p50_ms": round(statistics.median(samples), 2),
            "p95_ms": round(sorted(samples)[int(0.95 * (len(samples) - 1))], 2),
        }
    conn.close()
    return report


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    print(json.dumps(audit(db), indent=1))
