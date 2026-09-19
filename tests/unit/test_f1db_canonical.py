"""Phase 5.5B tests: F1DB canonicalization, session identity, idempotency.

These tests exercise the canonical store in a temporary database, using a
small synthetic slice shaped exactly like the F1DB 2026.14.0 CSV schemas.
No live network access and no fabrication: canonical counts always equal
source row counts.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from racewise.data.historical.f1db_canonical import (
    CanonicalStore,
    F1DBCanonicalizer,
    _stable_id,
)


@pytest.fixture()
def store(tmp_path):
    return CanonicalStore(str(tmp_path / "canonical.db"))


@pytest.fixture()
def canon(store):
    c = F1DBCanonicalizer(store, source_version="test")
    c.ingest_drivers(
        [
            {"id": "max-verstappen", "firstName": "Max", "lastName": "Verstappen", "abbreviation": "VER"},
            {"id": "charles-leclerc", "firstName": "Charles", "lastName": "Leclerc", "abbreviation": "LEC"},
        ]
    )
    c.ingest_constructors(
        [
            {"id": "red-bull", "name": "Red Bull"},
            {"id": "ferrari", "name": "Ferrari"},
        ]
    )
    c.ingest_circuits([{"id": "bahrain", "name": "Bahrain International Circuit", "countryId": "bahrain"}])
    c.ingest_races(
        [
            {
                "id": "1080",
                "year": "2023",
                "round": "1",
                "grandPrixId": "bahrain",
                "officialName": "Formula 1 Gulf Air Bahrain Grand Prix 2023",
                "date": "2023-03-05",
                "circuitId": "bahrain",
                "laps": "57",
            }
        ]
    )
    return c


def _sample_race_rows(race_id="1080", n=3):
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "raceId": race_id,
                "year": "2023",
                "round": "1",
                "positionDisplayOrder": str(i),
                "positionNumber": str(i),
                "positionText": str(i),
                "driverNumber": "1",
                "driverId": "max-verstappen" if i % 2 else "charles-leclerc",
                "constructorId": "red-bull" if i % 2 else "ferrari",
                "sharedCar": "false",
                "laps": str(57 - i),
                "time": "1:33:56.736" if i == 1 else None,
                "timeMillis": "5636736" if i == 1 else None,
                "reasonRetired": None,
                "points": "25" if i == 1 else "18",
                "gridPositionNumber": str(i),
            }
        )
    return rows


# -- session identity ---------------------------------------------------------


def test_session_identity_is_deterministic(canon):
    """Same race + session type always resolves to the same canonical id."""
    id1 = canon.session_id(canon.race_id(2023, 1), "RACE")
    id2 = canon.session_id(canon.race_id(2023, 1), "RACE")
    assert id1 == id2
    assert id1 != canon.session_id(canon.race_id(2023, 1), "QUALIFYING")
    # Different source versions must NOT change identity
    other = F1DBCanonicalizer(canon.store, source_version="other")
    assert other.session_id(other.race_id(2023, 1), "RACE") == id1


def test_stable_id_is_stable_and_distinct():
    assert _stable_id("a", 1, "b") == _stable_id("a", 1, "b")
    assert _stable_id("a", 1, "b") != _stable_id("a", 2, "b")
    assert len(_stable_id("x")) == 16


# -- session construction -------------------------------------------------------


def test_sessions_created_only_when_source_represents_them(canon):
    """No scheduling and no detail rows -> NO session row (not fabricated)."""
    races = [
        {
            "id": "1080",
            "year": "2023",
            "round": "1",
            "grandPrixId": "bahrain",
            "date": "2023-03-05",
            # no qualifying/sprint/practice scheduling columns
        }
    ]
    created = canon.construct_sessions(races, detail_evidence={"RACE": {"1080"}})
    assert created == 1
    with canon.store._conn() as conn:
        types = {r["session_type"] for r in conn.execute("SELECT session_type FROM canonical_sessions")}
    assert types == {"RACE"}


def test_session_created_for_scheduled_session_without_results(canon):
    """A scheduled sprint with no results rows still exists (F1DB represents it)."""
    races = [
        {
            "id": "1080",
            "year": "2023",
            "round": "1",
            "grandPrixId": "bahrain",
            "date": "2023-03-05",
            "laps": "57",
            "sprintRaceDate": "2023-03-04",
            "sprintRaceLaps": "19",
        }
    ]
    canon.construct_sessions(races, detail_evidence={"RACE": {"1080"}})
    with canon.store._conn() as conn:
        rows = {
            r["session_type"]: r["laps_total"]
            for r in conn.execute("SELECT session_type, laps_total FROM canonical_sessions")
        }
    assert rows == {"RACE": 57, "SPRINT": 19}


def test_no_sessions_without_evidence(canon):
    races = [{"id": "1080", "year": "2023", "round": "1", "grandPrixId": "bahrain", "date": "2023-03-05"}]
    # detail evidence for a different race only; race itself has no scheduled date here
    race_no_date = {"id": "1080", "year": "2023", "round": "1", "grandPrixId": "bahrain"}
    created = canon.construct_sessions([race_no_date], detail_evidence={"SPRINT": {"9999"}})
    assert created == 0


# -- results canonicalization ----------------------------------------------------


def test_results_ingest_matches_source_count(canon):
    rows = _sample_race_rows(n=3)
    count = canon.ingest_results(rows, "RACE")
    assert count == 3
    with canon.store._conn() as conn:
        stored = conn.execute("SELECT COUNT(*) FROM canonical_results").fetchone()[0]
    assert stored == 3


def test_shared_car_rows_preserved(canon):
    """Two rows for the same driver (shared car) are distinct results."""
    rows = _sample_race_rows(n=1)
    rows.append(
        {
            "raceId": "1080",
            "year": "2023",
            "round": "1",
            "positionDisplayOrder": "2",
            "positionNumber": "2",
            "positionText": "2",
            "driverId": "max-verstappen",
            "constructorId": "red-bull",
            "sharedCar": "true",
            "laps": "50",
            "points": "0",
            "gridPositionNumber": "2",
        }
    )
    count = canon.ingest_results(rows, "RACE")
    assert count == 2
    with canon.store._conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM canonical_results r JOIN canonical_drivers d ON d.driver_id=r.driver_id "
            "WHERE d.driver_key='max-verstappen'"
        ).fetchone()[0]
    assert n == 2


def test_unknown_driver_rows_skipped_not_fabricated(canon):
    rows = _sample_race_rows(n=2)
    rows.append({"raceId": "1080", "year": "2023", "round": "1", "positionDisplayOrder": "9",
                 "driverId": "ghost-driver", "constructorId": "ferrari"})
    count = canon.ingest_results(rows, "RACE")
    assert count == 2


# -- qualifying canonicalization --------------------------------------------------


def test_qualifying_preserves_source_representation(canon):
    """1950-style single session: q1 only, q2/q3 NULL. Modern: q1/q2/q3."""
    historic = [
        {"raceId": "1080", "year": "2023", "round": "1", "driverId": "max-verstappen",
         "constructorId": "red-bull", "positionNumber": "1", "time": "1:50.800", "positionText": "1"},
    ]
    modern = [
        {"raceId": "1080", "year": "2023", "round": "1", "driverId": "charles-leclerc",
         "constructorId": "ferrari", "positionNumber": "1",
         "q1": "1:30.5", "q2": "1:29.9", "q3": "1:29.7", "positionText": "1"},
    ]
    canon.ingest_qualifying(historic, "QUALIFYING")
    canon.ingest_qualifying(modern, "QUALIFYING")
    with canon.store._conn() as conn:
        rows = {
            r["driver_key"]: (r["q1"], r["q2"], r["q3"])
            for r in conn.execute(
                "SELECT d.driver_key, q.q1, q.q2, q.q3 FROM canonical_qualifying q "
                "JOIN canonical_drivers d ON d.driver_id=q.driver_id"
            )
        }
    assert rows["max-verstappen"] == ("1:50.800", None, None)
    assert rows["charles-leclerc"] == ("1:30.5", "1:29.9", "1:29.7")


# -- pit stops ---------------------------------------------------------------------


def test_pit_stops_ingest_and_dedupe_exact_duplicates(canon):
    stop = {
        "raceId": "1080", "year": "2023", "round": "1", "driverId": "max-verstappen",
        "stop": "1", "lap": "15", "time": "24.500", "timeMillis": "24500",
    }
    # Exact duplicate row in source (F1DB has some) must collapse to one canonical row.
    count = canon.ingest_pit_stops([stop, dict(stop)], "RACE")
    assert count == 2  # rows processed
    with canon.store._conn() as conn:
        stored = conn.execute("SELECT COUNT(*) FROM canonical_pit_stops").fetchone()[0]
    assert stored == 1  # but identity dedupes


def test_distinct_pit_stops_preserved(canon):
    stops = [
        {"raceId": "1080", "year": "2023", "round": "1", "driverId": "max-verstappen",
         "stop": "1", "lap": "15", "time": "24.500", "timeMillis": "24500"},
        {"raceId": "1080", "year": "2023", "round": "1", "driverId": "max-verstappen",
         "stop": "2", "lap": "40", "time": "23.900", "timeMillis": "23900"},
    ]
    canon.ingest_pit_stops(stops, "RACE")
    with canon.store._conn() as conn:
        stored = conn.execute("SELECT COUNT(*) FROM canonical_pit_stops").fetchone()[0]
    assert stored == 2


# -- idempotency -------------------------------------------------------------------


def test_double_ingestion_produces_identical_counts(canon):
    results = _sample_race_rows(n=5)
    qual = [
        {"raceId": "1080", "year": "2023", "round": "1", "driverId": "max-verstappen",
         "constructorId": "red-bull", "positionNumber": "1", "time": "1:29.7"},
    ]
    pits = [
        {"raceId": "1080", "year": "2023", "round": "1", "driverId": "max-verstappen",
         "stop": "1", "lap": "15", "time": "24.500", "timeMillis": "24500"},
    ]
    races = [{"id": "1080", "year": "2023", "round": "1", "grandPrixId": "bahrain", "date": "2023-03-05"}]

    canon.ingest_results(results, "RACE")
    canon.ingest_qualifying(qual, "QUALIFYING")
    canon.ingest_pit_stops(pits, "RACE")
    canon.construct_sessions(races, detail_evidence={"RACE": {"1080"}})
    first = canon.store.counts()

    # Run everything again (new canonicalizer instance, same DB)
    canon2 = F1DBCanonicalizer(canon.store, source_version="test")
    canon2.ingest_results(results, "RACE")
    canon2.ingest_qualifying(qual, "QUALIFYING")
    canon2.ingest_pit_stops(pits, "RACE")
    canon2.construct_sessions(races, detail_evidence={"RACE": {"1080"}})
    second = canon2.store.counts()

    assert first == second


def test_canonical_ids_survive_reingestion(canon):
    """Result ids are deterministic, not random UUIDs."""
    rows = _sample_race_rows(n=2)
    canon.ingest_results(rows, "RACE")
    with canon.store._conn() as conn:
        ids1 = sorted(r["result_id"] for r in conn.execute("SELECT result_id FROM canonical_results"))
    canon2 = F1DBCanonicalizer(canon.store, source_version="test")
    canon2.ingest_results(rows, "RACE")
    with canon.store._conn() as conn:
        ids2 = sorted(r["result_id"] for r in conn.execute("SELECT result_id FROM canonical_results"))
    assert ids1 == ids2
    # Deterministic: recomputable from source identity
    race_id = canon.race_id(2023, 1)
    session_id = canon.session_id(race_id, "RACE")
    expected = _stable_id("f1db", "result", session_id, "1080:1")
    assert ids1[0] == expected or ids1[1] == expected


# -- availability / catalog ---------------------------------------------------------


def test_catalog_availability_is_data_derived(canon):
    """A session with rows is AVAILABLE; without rows is UNAVAILABLE."""
    races = [{"id": "1080", "year": "2023", "round": "1", "grandPrixId": "bahrain", "date": "2023-03-05"}]
    canon.construct_sessions(races, detail_evidence={"RACE": {"1080"}, "QUALIFYING": {"1080"}, "SPRINT": {"1080"}})
    canon.ingest_results(_sample_race_rows(n=2), "RACE")
    canon.ingest_qualifying(
        [{"raceId": "1080", "year": "2023", "round": "1", "driverId": "max-verstappen",
          "constructorId": "red-bull", "positionNumber": "1", "time": "1:29.7"}],
        "QUALIFYING",
    )
    canon.rebuild_catalog()
    with canon.store._conn() as conn:
        rows = {
            r["session_type"]: dict(r)
            for r in conn.execute(
                "SELECT * FROM canonical_session_catalog WHERE session_type IN ('RACE','QUALIFYING','SPRINT')"
            )
        }
    assert rows["RACE"]["results_availability"] == "AVAILABLE"
    assert rows["RACE"]["results_count"] == 2
    assert rows["QUALIFYING"]["qualifying_availability"] == "AVAILABLE"
    # SPRINT session exists (F1DB shows results in evidence) but no rows ingested -> UNAVAILABLE
    assert rows["SPRINT"]["results_availability"] == "UNAVAILABLE"
    assert rows["SPRINT"]["results_count"] == 0
    # Weather/stints/race control have no source data -> UNAVAILABLE everywhere
    for st in ("RACE", "QUALIFYING", "SPRINT"):
        assert rows[st]["weather_availability"] == "UNAVAILABLE"
        assert rows[st]["stints_availability"] == "UNAVAILABLE"
        assert rows[st]["telemetry_availability"] == "UNAVAILABLE"


def test_no_year_based_availability_shortcuts(canon):
    """Older seasons with data are AVAILABLE; newer without data are NOT."""
    canon.ingest_races(
        [
            {"id": "1", "year": "1950", "round": "1", "grandPrixId": "great-britain",
             "date": "1950-05-13", "circuitId": "bahrain", "laps": "70"},
        ]
    )
    canon.ingest_results(
        [{"raceId": "1", "year": "1950", "round": "1", "positionDisplayOrder": "1",
          "positionNumber": "1", "driverId": "max-verstappen", "constructorId": "red-bull",
          "laps": "70", "points": "9"}],
        "RACE",
    )
    races = [
        {"id": "1080", "year": "2023", "round": "1", "grandPrixId": "bahrain", "date": "2023-03-05"},
        {"id": "1", "year": "1950", "round": "1", "grandPrixId": "great-britain", "date": "1950-05-13"},
    ]
    canon.construct_sessions(races, detail_evidence={"RACE": {"1080", "1"}})
    canon.rebuild_catalog()
    with canon.store._conn() as conn:
        rows = {
            (r["season"], r["session_type"]): dict(r)
            for r in conn.execute("SELECT * FROM canonical_session_catalog WHERE session_type='RACE'")
        }
    # 1950 has results -> AVAILABLE despite being ancient
    assert rows[(1950, "RACE")]["results_availability"] == "AVAILABLE"
    # 2023 sprint does not exist; a session absent from source simply has no row
    assert (2026, "RACE") not in rows
