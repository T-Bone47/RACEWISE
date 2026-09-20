"""Deterministic schema fixture for CI: the canonical DDL, exercised in-memory.

The CI path builds a tiny canonical store from synthetic rows (no network,
no large datasets) and runs the validator suite against it. This catches
schema regressions, FK breaks, provenance gaps and availability logic
without downloading F1DB/FastF1.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from racewise.data.historical.f1db_canonical import CanonicalStore, F1DBCanonicalizer  # noqa: E402
from racewise.data.historical.validators import CanonicalDataValidator  # noqa: E402


@pytest.fixture()
def mini_store(tmp_path):
    """A tiny canonical store: 1 race, 1 session, minimal rows from both providers."""
    store = CanonicalStore(str(tmp_path / "mini.db"))
    canon = F1DBCanonicalizer(store, source_version="test-2026.14.0")
    canon.ingest_circuits([
        {"id": "bahrain", "name": "Bahrain International Circuit", "countryId": "BHR"},
    ])
    canon.ingest_seasons([{"year": 2023}])
    canon.ingest_drivers([
        {"id": "max-verstappen", "firstName": "Max", "lastName": "Verstappen", "abbreviation": "VER"},
        {"id": "sergio-perez", "firstName": "Sergio", "lastName": "Perez", "abbreviation": "PER"},
    ])
    canon.ingest_constructors([
        {"id": "red-bull", "name": "Red Bull", "constructorId": "red-bull"},
    ])
    canon.ingest_races([{
        "id": "bahrain-2023", "year": 2023, "round": 1,
        "grandPrixId": "bahrain", "name": "Bahrain Grand Prix",
        "officialName": "Bahrain Grand Prix",
        "date": "2023-03-05", "time": "15:00:00", "circuitId": "bahrain",
    }])
    canon.construct_sessions([{
        "id": "bahrain-2023", "year": 2023, "round": 1, "grandPrixId": "bahrain",
        "date": "2023-03-05", "time": "15:00:00",
    }])
    canon.ingest_results([
        {"raceId": "bahrain-2023", "year": 2023, "round": 1, "positionDisplayOrder": 1,
         "positionNumber": 1, "positionText": "1", "driverId": "max-verstappen",
         "constructorId": "red-bull", "laps": 57, "status": "Finished"},
        {"raceId": "bahrain-2023", "year": 2023, "round": 1, "positionDisplayOrder": 2,
         "positionNumber": 2, "positionText": "2", "driverId": "sergio-perez",
         "constructorId": "red-bull", "laps": 57, "status": "Finished"},
    ], "RACE")
    # FastF1 modern rows on the same session
    session_id = canon.session_id(canon.race_id(2023, 1), "RACE")
    driver_id = canon._driver_id_for("max-verstappen")
    now = "2026-01-01T00:00:00+00:00"
    store.execute_batch(
        """INSERT INTO canonical_stints (stint_id, session_id, driver_id, stint_number, compound,
           lap_start, lap_end, lap_count, source_provider, source_id, source_version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(
            "ff1-stint-mini-1", session_id, driver_id, 1, "SOFT", 1, 12, 12,
            "fastf1", "2023-R1-RACE:VER:1", "3.8.3", now, now,
        )],
    )
    store.execute_batch(
        """INSERT INTO canonical_weather (weather_id, session_id, timestamp, elapsed_s, air_temp_c,
           track_temp_c, humidity, rainfall, wind_direction, wind_speed, pressure,
           source_provider, source_id, source_version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(
            "ff1-wx-mini-1", session_id, "PT45.438S", 45.438, 29.8, 35.1, 19.0, 0, 176, 1.2, 1016.5,
            "fastf1", "2023-R1-RACE:wx:0", "3.8.3", now, now,
        )],
    )
    store.execute_batch(
        """INSERT INTO canonical_race_control (event_id, session_id, timestamp, category, message,
           lap, source_provider, source_id, source_version, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(
            "ff1-rc-mini-1", session_id, "2023-03-05T14:20:00", "Flag",
            "GREEN LIGHT - PIT EXIT OPEN", 1, "fastf1", "2023-R1-RACE:rc:0", "3.8.3", now, now,
        )],
    )
    canon.rebuild_catalog()
    yield store


class TestSchemaGate:
    def test_mini_store_passes_all_validators(self, mini_store):
        report = CanonicalDataValidator(str(mini_store.db_path)).validate_all()
        assert report.ok, report.failures

    def test_fk_violation_is_caught(self, mini_store):
        conn = sqlite3_conn(mini_store)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """INSERT INTO canonical_stints (stint_id, session_id, driver_id, stint_number,
               compound, lap_start, lap_end, lap_count, source_provider, source_id, source_version,
               created_at, updated_at)
               VALUES ('orphan', 'no-such-session', 'no-such-driver', 9, 'SOFT', 1, 2, 2,
                       'fastf1', 'x', 'x', '2026-01-01', '2026-01-01')"""
        )
        conn.commit()
        conn.close()
        report = CanonicalDataValidator(str(mini_store.db_path)).validate_all()
        assert not report.ok  # session_fk_valid / driver_fk_valid must fail

    def test_provenance_gap_is_caught(self, mini_store):
        conn = sqlite3_conn(mini_store)
        conn.execute("UPDATE canonical_stints SET source_provider = NULL WHERE stint_id = 'ff1-stint-mini-1'")
        conn.commit()
        conn.close()
        report = CanonicalDataValidator(str(mini_store.db_path)).validate_all()
        assert not report.ok
        assert "provider_provenance_complete" in {c["name"] for c in report.checks if not c["ok"]}

    def test_availability_flags_track_counts(self, mini_store):
        import sqlite3

        conn = sqlite3.connect(str(mini_store.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT c.* FROM canonical_session_catalog c
               JOIN canonical_races r ON r.race_id = c.race_id
               WHERE r.season = 2023 AND c.session_type = 'RACE'"""
        ).fetchone()
        conn.close()
        assert row["results_availability"] == "AVAILABLE"
        assert row["stints_availability"] == "AVAILABLE"   # fastf1 row present
        assert row["weather_availability"] == "AVAILABLE"
        assert row["telemetry_availability"] == "UNAVAILABLE"  # deferred, honest

    def test_deterministic_session_identity(self, mini_store):
        expected = F1DBCanonicalizer(mini_store).session_id(
            F1DBCanonicalizer(mini_store).race_id(2023, 1), "RACE"
        )
        import sqlite3

        conn = sqlite3.connect(str(mini_store.db_path))
        row = conn.execute(
            "SELECT session_id FROM canonical_sessions WHERE session_id = ?", (expected,)
        ).fetchone()
        conn.close()
        assert row is not None


def sqlite3_conn(store) :
    import sqlite3

    conn = sqlite3.connect(str(store.db_path))
    conn.row_factory = None
    return conn
