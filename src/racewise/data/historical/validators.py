"""Automated data-quality validators for the canonical store (Phase 6A).

Every check queries the live database - nothing is assumed. Validators are
grouped so callers (tests, CLI, investigations) can run the full suite and
get a machine-readable verdict. A failing check is a real data problem,
never silently repaired.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ValidationReport:
    passed: int = 0
    failed: int = 0
    failures: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail})
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            self.failures.append(f"{name}: {detail}")

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        return {"ok": self.ok, "passed": self.passed, "failed": self.failed,
                "failures": self.failures, "checks": self.checks}


class CanonicalDataValidator:
    """Runs data-quality checks over the canonical store."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        import os
        from pathlib import Path
        if db_path is None:
            data_dir = Path(os.environ.get("RACEWISE_DATA_DIR", Path.cwd() / "data"))
            db_path = str(data_dir / "canonical" / "canonical.db")
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def validate_all(self) -> ValidationReport:
        report = ValidationReport()
        self.check_fk_integrity(report)
        self.check_no_duplicate_stints(report)
        self.check_no_duplicate_weather(report)
        self.check_no_duplicate_race_control(report)
        self.check_lap_ordering(report)
        self.check_stint_lap_ranges(report)
        self.check_compound_values(report)
        self.check_weather_timestamps(report)
        self.check_race_control_ordering(report)
        self.check_pit_stop_ordering(report)
        self.check_driver_identity(report)
        self.check_session_identity(report)
        self.check_orphan_modern_rows(report)
        self.check_provider_provenance(report)
        return report

    # -- checks ---------------------------------------------------------------

    def check_fk_integrity(self, report: ValidationReport) -> None:
        with self._conn() as conn:
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        report.add("fk_integrity", len(violations) == 0, f"{len(violations)} violations")

    def check_no_duplicate_stints(self, report: ValidationReport) -> None:
        with self._conn() as conn:
            dupes = conn.execute("""
                SELECT session_id, driver_id, stint_number, COUNT(*) n
                FROM canonical_stints GROUP BY session_id, driver_id, stint_number
                HAVING n > 1""").fetchall()
        report.add("stints_unique", len(dupes) == 0, f"{len(dupes)} duplicate stints")

    def check_no_duplicate_weather(self, report: ValidationReport) -> None:
        with self._conn() as conn:
            dupes = conn.execute("""
                SELECT session_id, timestamp, COUNT(*) n FROM canonical_weather
                WHERE timestamp IS NOT NULL
                GROUP BY session_id, timestamp HAVING n > 1""").fetchall()
        report.add("weather_unique_timestamps", len(dupes) == 0, f"{len(dupes)} duplicate observations")

    def check_no_duplicate_race_control(self, report: ValidationReport) -> None:
        with self._conn() as conn:
            dupes = conn.execute("""
                SELECT session_id, timestamp, category, message, COUNT(*) n
                FROM canonical_race_control WHERE timestamp IS NOT NULL
                GROUP BY session_id, timestamp, category, message HAVING n > 1""").fetchall()
        report.add("race_control_unique", len(dupes) == 0, f"{len(dupes)} duplicate events")

    def check_lap_ordering(self, report: ValidationReport) -> None:
        """Every (session, driver) lap sequence must be strictly increasing per provider."""
        with self._conn() as conn:
            bad = conn.execute("""
                SELECT session_id, driver_id, source_provider, COUNT(*) n FROM (
                    SELECT lap_time_id, session_id, driver_id, source_provider, lap_number,
                           LAG(lap_number) OVER (
                               PARTITION BY session_id, driver_id, source_provider
                               ORDER BY lap_number) prev
                    FROM canonical_lap_times)
                WHERE prev IS NOT NULL AND lap_number = prev
                GROUP BY session_id, driver_id, source_provider""").fetchall()
        report.add("lap_numbers_non_decreasing", len(bad) == 0, f"{len(bad)} duplicated lap numbers")

    def check_stint_lap_ranges(self, report: ValidationReport) -> None:
        with self._conn() as conn:
            bad = conn.execute("""
                SELECT COUNT(*) FROM canonical_stints
                WHERE lap_end < lap_start OR lap_count <= 0""").fetchone()[0]
        report.add("stint_ranges_sane", bad == 0, f"{bad} stints with inverted/empty ranges")

    def check_compound_values(self, report: ValidationReport) -> None:
        """Compounds must come from the real FastF1 vocabulary (or NULL)."""
        with self._conn() as conn:
            bad = conn.execute("""
                SELECT COUNT(*) FROM canonical_stints
                WHERE compound IS NOT NULL AND TRIM(compound) != ''
                  AND compound NOT IN ('SOFT','MEDIUM','HARD','INTERMEDIATE','WET',
                                       'TEST_UNKNOWN','UNKNOWN','HYPERSOFT','ULTRASOFT',
                                       'SUPERSOFT','SUPERHARD','|')""")
        # mixed sets use '|' separator - validate each token instead
        rows = conn.execute("SELECT DISTINCT compound FROM canonical_stints WHERE compound IS NOT NULL").fetchall()
        known = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "TEST_UNKNOWN", "UNKNOWN",
                 "HYPERSOFT", "ULTRASOFT", "SUPERSOFT", "SUPERHARD"}
        unknown = [r["compound"] for r in rows
                   if not all(tok in known for tok in str(r["compound"]).split("|"))]
        report.add("compound_vocabulary", len(unknown) == 0, f"unknown compounds: {unknown[:5]}")

    def check_weather_timestamps(self, report: ValidationReport) -> None:
        """Weather observations must be non-decreasing in elapsed time.

        elapsed_s carries the session-relative offset directly from the source
        timedelta; absolute ISO datetimes (race control) sort lexicographically.
        """
        with self._conn() as conn:
            bad = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT session_id, elapsed_s,
                           LAG(elapsed_s) OVER (PARTITION BY session_id ORDER BY rowid) prev
                    FROM canonical_weather WHERE elapsed_s IS NOT NULL)
                WHERE prev IS NOT NULL AND elapsed_s < prev""").fetchone()[0]
        report.add("weather_timestamp_order", bad == 0, f"{bad} out-of-order observations")

    def check_race_control_ordering(self, report: ValidationReport) -> None:
        with self._conn() as conn:
            bad = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT session_id, timestamp,
                           LAG(timestamp) OVER (PARTITION BY session_id ORDER BY rowid) prev
                    FROM canonical_race_control WHERE timestamp IS NOT NULL)
                WHERE prev IS NOT NULL AND timestamp < prev""").fetchone()[0]
        report.add("race_control_order", bad == 0, f"{bad} out-of-order events")

    def check_pit_stop_ordering(self, report: ValidationReport) -> None:
        with self._conn() as conn:
            dupes = conn.execute("""
                SELECT session_id, driver_id, lap, stop_number, COUNT(*) n
                FROM canonical_pit_stops WHERE lap IS NOT NULL
                GROUP BY session_id, driver_id, lap, stop_number HAVING n > 1""").fetchall()
        report.add("pit_stops_unique", len(dupes) == 0, f"{len(dupes)} duplicate stops")

    def check_driver_identity(self, report: ValidationReport) -> None:
        """Modern rows must reference real canonical drivers."""
        with self._conn() as conn:
            orphans = 0
            for table in ("canonical_stints", "canonical_lap_times"):
                orphans += conn.execute(
                    f"""SELECT COUNT(*) FROM {table} t
                        LEFT JOIN canonical_drivers d ON d.driver_id = t.driver_id
                        WHERE t.driver_id IS NOT NULL AND d.driver_id IS NULL""").fetchone()[0]
        report.add("driver_fk_valid", orphans == 0, f"{orphans} orphan driver refs")

    def check_session_identity(self, report: ValidationReport) -> None:
        """Every modern row must attach to a real canonical session."""
        with self._conn() as conn:
            orphans = 0
            for table in ("canonical_stints", "canonical_weather", "canonical_race_control"):
                orphans += conn.execute(
                    f"""SELECT COUNT(*) FROM {table} t
                        LEFT JOIN canonical_sessions s ON s.session_id = t.session_id
                        WHERE t.session_id IS NOT NULL AND s.session_id IS NULL""").fetchone()[0]
        report.add("session_fk_valid", orphans == 0, f"{orphans} orphan session refs")

    def check_orphan_modern_rows(self, report: ValidationReport) -> None:
        """FastF1 rows must never exist on sessions F1DB does not represent."""
        with self._conn() as conn:
            orphans = conn.execute("""
                SELECT COUNT(*) FROM canonical_stints t
                JOIN canonical_sessions s ON s.session_id = t.session_id
                WHERE s.source_provider != 'f1db'""").fetchone()[0]
        report.add("modern_rows_on_f1db_sessions", orphans == 0, f"{orphans} rows on non-F1DB sessions")

    def check_provider_provenance(self, report: ValidationReport) -> None:
        """All modern rows must carry provider + source_version provenance."""
        with self._conn() as conn:
            missing = 0
            for table in ("canonical_stints", "canonical_weather", "canonical_race_control"):
                missing += conn.execute(
                    f"""SELECT COUNT(*) FROM {table}
                        WHERE source_provider IS NULL OR source_provider = ''
                           OR source_version IS NULL OR source_version = ''
                           OR source_id IS NULL OR source_id = ''""").fetchone()[0]
        report.add("provider_provenance_complete", missing == 0, f"{missing} rows missing provenance")


def validate_canonical_data(db_path: Optional[str] = None) -> dict:
    """Convenience entry point returning a machine-readable verdict."""
    return CanonicalDataValidator(db_path).validate_all().to_dict()
