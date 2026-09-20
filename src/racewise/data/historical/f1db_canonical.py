"""F1DB canonical store and canonicalizer.

Canonical database schema for historical F1 data plus a deterministic,
idempotent canonicalizer from F1DB release CSVs.

Design rules (Phase 5.5B):
- Every canonical id is DETERMINISTIC (derived from stable source keys), so
  re-running ingestion produces identical rows (idempotent upserts).
- Sessions exist ONLY where F1DB actually represents them. Availability is
  data-derived (record counts), never inferred from the year.
- Fields absent from the source stay NULL. Nothing is fabricated.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

F1DB_PROVIDER = "f1db"
F1DB_SCHEMA_VERSION = "1.0"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(*parts: Any) -> str:
    """Deterministic id from stable source parts."""
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class CanonicalStore:
    """Canonical database for normalized historical F1 data."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            data_dir = Path(os.environ.get("RACEWISE_DATA_DIR", Path.cwd() / "data"))
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "canonical" / "canonical.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
            conn.close()
        except Exception:
            conn.rollback()
            conn.close()
            raise

    @contextmanager
    def bulk_conn(self):
        """Connection tuned for bulk loading (one transaction per caller)."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = OFF")
        try:
            yield conn
            conn.commit()
            conn.close()
        except Exception:
            conn.rollback()
            conn.close()
            raise

    def counts(self) -> dict[str, int]:
        """Row counts for every canonical table."""
        tables = [
            "canonical_seasons", "canonical_circuits", "canonical_drivers",
            "canonical_constructors", "canonical_races", "canonical_sessions",
            "canonical_results", "canonical_qualifying", "canonical_pit_stops",
            "canonical_lap_times", "canonical_stints", "canonical_weather",
            "canonical_race_control", "canonical_session_catalog",
        ]
        out = {}
        with self._conn() as conn:
            for t in tables:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return out

    def execute_batch(self, query: str, params: Iterable[tuple], batch_size: int = 2000) -> int:
        """Execute one statement with executemany in a single bulk transaction."""
        rows = list(params)
        with self.bulk_conn() as conn:
            conn.executemany(query, rows)
            return len(rows)

    def _init_db(self) -> None:
        """Initialize canonical database schema."""
        with self._conn() as conn:
            # Seasons
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_seasons (
                    season_id TEXT PRIMARY KEY,
                    year INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Circuits
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_circuits (
                    circuit_id TEXT PRIMARY KEY,
                    circuit_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    country TEXT,
                    city TEXT,
                    latitude REAL,
                    longitude REAL,
                    length_km REAL,
                    corners INTEGER,
                    first_year INTEGER,
                    last_year INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Drivers
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_drivers (
                    driver_id TEXT PRIMARY KEY,
                    driver_key TEXT NOT NULL UNIQUE,
                    code TEXT,
                    driver_number INTEGER,
                    given_name TEXT NOT NULL,
                    family_name TEXT NOT NULL,
                    full_name TEXT,
                    nationality TEXT,
                    date_of_birth TEXT,
                    place_of_birth TEXT,
                    country_of_birth TEXT,
                    url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Constructors
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_constructors (
                    constructor_id TEXT PRIMARY KEY,
                    constructor_key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    nationality TEXT,
                    first_season INTEGER,
                    last_season INTEGER,
                    championships INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    pole_positions INTEGER DEFAULT 0,
                    fastests_laps INTEGER DEFAULT 0,
                    podiums INTEGER DEFAULT 0,
                    points REAL DEFAULT 0.0,
                    url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Races/Meetings
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_races (
                    race_id TEXT PRIMARY KEY,
                    race_key TEXT NOT NULL UNIQUE,
                    season INTEGER NOT NULL,
                    round INTEGER NOT NULL,
                    grand_prix TEXT NOT NULL,
                    official_name TEXT,
                    date TEXT,
                    time TEXT,
                    circuit_id TEXT,
                    circuit_name TEXT,
                    country TEXT,
                    city TEXT,
                    total_laps INTEGER,
                    distance_km REAL,
                    status TEXT,
                    official_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (circuit_id) REFERENCES canonical_circuits(circuit_id)
                )
            """)

            # Sessions
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_sessions (
                    session_id TEXT PRIMARY KEY,
                    session_key TEXT NOT NULL UNIQUE,
                    race_id TEXT NOT NULL,
                    session_type TEXT NOT NULL,
                    session_name TEXT,
                    date_start TEXT,
                    date_end TEXT,
                    laps_total INTEGER,
                    laps_completed INTEGER,
                    source_provider TEXT,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (race_id) REFERENCES canonical_races(race_id),
                    UNIQUE (race_id, session_type)
                )
            """)

            # Results
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_results (
                    result_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    constructor_id TEXT,
                    position INTEGER,
                    position_order INTEGER,
                    grid INTEGER,
                    position_text TEXT,
                    points REAL,
                    laps INTEGER,
                    time TEXT,
                    milliseconds INTEGER,
                    fastest_lap INTEGER,
                    rank INTEGER,
                    fastest_lap_time TEXT,
                    fastest_lap_speed REAL,
                    status_id TEXT,
                    status TEXT,
                    source_provider TEXT,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id),
                    FOREIGN KEY (driver_id) REFERENCES canonical_drivers(driver_id)
                )
            """)

            # Qualifying
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_qualifying (
                    qualifying_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    constructor_id TEXT,
                    position INTEGER,
                    q1 TEXT,
                    q2 TEXT,
                    q3 TEXT,
                    position_text TEXT,
                    source_provider TEXT,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id),
                    FOREIGN KEY (driver_id) REFERENCES canonical_drivers(driver_id)
                )
            """)

            # Pit stops
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_pit_stops (
                    pit_stop_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    lap INTEGER NOT NULL,
                    stop_number INTEGER,
                    time TEXT,
                    duration REAL,
                    compound_before TEXT,
                    compound_after TEXT,
                    tyre_life_before INTEGER,
                    tyre_life_after INTEGER,
                    source_provider TEXT,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id),
                    FOREIGN KEY (driver_id) REFERENCES canonical_drivers(driver_id)
                )
            """)

            # Lap times
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_lap_times (
                    lap_time_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    lap_number INTEGER NOT NULL,
                    position INTEGER,
                    time_s REAL,
                    sector1_s REAL,
                    sector2_s REAL,
                    sector3_s REAL,
                    compound TEXT,
                    tyre_life INTEGER,
                    stint INTEGER,
                    is_pit_in_lap BOOLEAN DEFAULT FALSE,
                    is_pit_out_lap BOOLEAN DEFAULT FALSE,
                    track_status TEXT,
                    is_accurate BOOLEAN,
                    deleted BOOLEAN DEFAULT FALSE,
                    source_provider TEXT,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id),
                    FOREIGN KEY (driver_id) REFERENCES canonical_drivers(driver_id)
                )
            """)

            # Stints
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_stints (
                    stint_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    stint_number INTEGER NOT NULL,
                    compound TEXT,
                    lap_start INTEGER,
                    lap_end INTEGER,
                    lap_count INTEGER,
                    source_provider TEXT,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id),
                    FOREIGN KEY (driver_id) REFERENCES canonical_drivers(driver_id)
                )
            """)

            # Weather
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_weather (
                    weather_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp TEXT,
                    elapsed_s REAL,
                    air_temp_c REAL,
                    track_temp_c REAL,
                    humidity REAL,
                    rainfall INTEGER,
                    wind_direction INTEGER,
                    wind_speed REAL,
                    pressure REAL,
                    source_provider TEXT,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id)
                )
            """)

            # Race control
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_race_control (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp TEXT,
                    category TEXT,
                    message TEXT,
                    lap INTEGER,
                    source_provider TEXT,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id)
                )
            """)

            # Canonical session catalog: the UI/API-facing index of what RACEWISE
            # can investigate. Capability flags are DATA-DERIVED (record counts).
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_session_catalog (
                    session_id TEXT PRIMARY KEY,
                    race_id TEXT NOT NULL,
                    season INTEGER NOT NULL,
                    round INTEGER NOT NULL,
                    race_name TEXT,
                    circuit_id TEXT,
                    circuit_name TEXT,
                    country TEXT,
                    date TEXT,
                    session_type TEXT NOT NULL,
                    source_provider TEXT,
                    results_count INTEGER NOT NULL DEFAULT 0,
                    qualifying_count INTEGER NOT NULL DEFAULT 0,
                    grid_count INTEGER NOT NULL DEFAULT 0,
                    pit_stops_count INTEGER NOT NULL DEFAULT 0,
                    laps_count INTEGER NOT NULL DEFAULT 0,
                    stints_count INTEGER NOT NULL DEFAULT 0,
                    weather_count INTEGER NOT NULL DEFAULT 0,
                    race_control_count INTEGER NOT NULL DEFAULT 0,
                    telemetry_available INTEGER NOT NULL DEFAULT 0,
                    results_availability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                    qualifying_availability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                    pit_stops_availability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                    laps_availability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                    stints_availability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                    weather_availability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                    race_control_availability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                    telemetry_availability TEXT NOT NULL DEFAULT 'UNAVAILABLE',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id)
                )
            """)

            # Telemetry (Phase 6C): bounded WIDE-format car-data samples.
            # One row per (driver, lap, sample); all six FastF1 car channels
            # share a single time index (verified 3.8.3), so a wide row is
            # ~6x smaller than one-row-per-signal and still fully provenanced.
            # Signals: speed_kmh, throttle_pct, brake (bool -> 1/0), gear, rpm,
            # drs (source int codes). Time is session-relative seconds (same
            # convention as weather elapsed_s) plus lap-relative seconds
            # (documented calc: SessionTime - LapStartTime). No distance
            # channel: requires positional data, deferred until a consumer
            # needs it. Adding a new channel = ALTER TABLE (documented policy;
            # the bounded consumer set is deliberately fixed in Phase 6C).
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canonical_telemetry (
                    telemetry_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    driver_id TEXT NOT NULL,
                    lap_number INTEGER NOT NULL,
                    time_elapsed_s REAL NOT NULL,
                    lap_time_s REAL NOT NULL,
                    speed_kmh REAL,
                    throttle_pct REAL,
                    brake INTEGER,
                    gear INTEGER,
                    rpm REAL,
                    drs INTEGER,
                    source_provider TEXT NOT NULL,
                    source_id TEXT,
                    source_version TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES canonical_sessions(session_id),
                    FOREIGN KEY (driver_id) REFERENCES canonical_drivers(driver_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_session ON canonical_telemetry(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_session_driver_lap ON canonical_telemetry(session_id, driver_id, lap_number)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_signal ON canonical_telemetry(session_id, lap_number)")

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_results_session ON canonical_results(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_results_driver ON canonical_results(driver_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_qualifying_session ON canonical_qualifying(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_lap_times_session ON canonical_lap_times(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_lap_times_driver ON canonical_lap_times(driver_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_pit_stops_session ON canonical_pit_stops(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_stints_session ON canonical_stints(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_weather_session ON canonical_weather(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_race_control_session ON canonical_race_control(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_sessions_race ON canonical_sessions(race_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_sessions_type ON canonical_sessions(session_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_races_season ON canonical_races(season)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_drivers_code ON canonical_drivers(code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_catalog_season ON canonical_session_catalog(season)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canonical_catalog_type ON canonical_session_catalog(session_type)")


# ---------------------------------------------------------------------------
# F1DBCanonicalizer: deterministic, idempotent F1DB -> canonical mapping
# ---------------------------------------------------------------------------

SESSION_TYPES = {
    "RACE": "RACE",
    "QUALIFYING": "QUALIFYING",
    "QUALIFYING_1": "QUALIFYING_1",
    "QUALIFYING_2": "QUALIFYING_2",
    "PRE_QUALIFYING": "PRE_QUALIFYING",
    "SPRINT_RACE": "SPRINT",
    "SPRINT_QUALIFYING": "SPRINT_QUALIFYING",
    "FREE_PRACTICE_1": "FREE_PRACTICE_1",
    "FREE_PRACTICE_2": "FREE_PRACTICE_2",
    "FREE_PRACTICE_3": "FREE_PRACTICE_3",
    "FREE_PRACTICE_4": "FREE_PRACTICE_4",
    "WARMING_UP": "WARMING_UP",
}


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _to_bool(value: Any) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "y")


class F1DBCanonicalizer:
    """Deterministic F1DB -> canonical canonicalizer.

    All canonical ids derive from stable F1DB source keys, so ingesting the
    same release twice produces identical logical rows (idempotent upserts).
    """

    def __init__(self, canonical_store: CanonicalStore, source_version: str = "2026.14.0") -> None:
        self.store = canonical_store
        self.source_version = source_version
        self._driver_ids: dict[str, str] = {}
        self._constructor_ids: dict[str, str] = {}
        self._circuit_ids: dict[str, str] = {}
        self._season_ids: dict[int, str] = {}
        self._race_ids: dict[str, str] = {}

    # -- id helpers ---------------------------------------------------------

    def season_id(self, year: int) -> str:
        return _stable_id(F1DB_PROVIDER, "season", year)

    def circuit_id(self, circuit_key: str) -> str:
        return _stable_id(F1DB_PROVIDER, "circuit", circuit_key)

    def driver_id(self, driver_key: str) -> str:
        return _stable_id(F1DB_PROVIDER, "driver", driver_key)

    def constructor_id(self, constructor_key: str) -> str:
        return _stable_id(F1DB_PROVIDER, "constructor", constructor_key)

    def race_id(self, year: int, round_num: int) -> str:
        return _stable_id(F1DB_PROVIDER, "race", year, round_num)

    def session_id(self, race_id: str, session_type: str) -> str:
        return _stable_id(F1DB_PROVIDER, "session", race_id, session_type)

    def session_key(self, year: int, round_num: int, grand_prix: str, session_type: str) -> str:
        return f"{year}-{grand_prix}-{session_type}".lower().replace(" ", "-")

    def result_id(self, session_id: str, source_row_id: Any) -> str:
        return _stable_id(F1DB_PROVIDER, "result", session_id, source_row_id)

    def qualifying_id(self, session_id: str, driver_key: str) -> str:
        return _stable_id(F1DB_PROVIDER, "qualifying", session_id, driver_key)

    def pit_stop_id(self, session_id: str, driver_key: str, stop: Any, lap: Any, time_millis: Any) -> str:
        return _stable_id(F1DB_PROVIDER, "pitstop", session_id, driver_key, stop, lap, time_millis)

    def lap_time_id(self, session_id: str, driver_key: str, lap: Any) -> str:
        return _stable_id(F1DB_PROVIDER, "fastestlap", session_id, driver_key, lap)

    def _driver_id_for(self, driver_key: Optional[str]) -> Optional[str]:
        """Resolve a driver key to canonical id, lazy-loading the cache from DB."""
        if not driver_key:
            return None
        if not self._driver_ids:
            self._load_lookups()
        return self._driver_ids.get(driver_key)

    def _constructor_id_for(self, constructor_key: Optional[str]) -> Optional[str]:
        if not constructor_key:
            return None
        if not self._constructor_ids:
            self._load_lookups()
        return self._constructor_ids.get(constructor_key)

    # -- entity upserts ------------------------------------------------------

    def ingest_seasons(self, seasons_data: list[dict]) -> int:
        rows = []
        for season in seasons_data:
            year = _to_int(season.get("year"))
            if year is None:
                continue
            now = _utcnow_iso()
            rows.append((self.season_id(year), year, now, now))
        if rows:
            self.store.execute_batch(
                "INSERT INTO canonical_seasons (season_id, year, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(season_id) DO UPDATE SET updated_at = excluded.updated_at",
                rows,
            )
        return len(rows)

    def ingest_circuits(self, circuits_data: list[dict]) -> int:
        rows = []
        for circuit in circuits_data:
            key = _to_str(circuit.get("id"))
            if not key:
                continue
            now = _utcnow_iso()
            rows.append((
                self.circuit_id(key), key, _to_str(circuit.get("name")),
                _to_str(circuit.get("countryId")),
                _to_str(circuit.get("location")) or _to_str(circuit.get("placeName")),
                _to_float(circuit.get("latitude")), _to_float(circuit.get("longitude")),
                _to_float(circuit.get("length")), _to_int(circuit.get("turns")),
                _to_int(circuit.get("firstYear")), _to_int(circuit.get("lastYear")),
                now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_circuits (circuit_id, circuit_key, name, country, city, latitude, longitude,
                   length_km, corners, first_year, last_year, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(circuit_id) DO UPDATE SET
                     name = excluded.name, country = excluded.country, city = excluded.city,
                     latitude = excluded.latitude, longitude = excluded.longitude,
                     length_km = excluded.length_km, corners = excluded.corners,
                     first_year = excluded.first_year, last_year = excluded.last_year,
                     updated_at = excluded.updated_at""",
                rows,
            )
        return len(rows)

    def ingest_drivers(self, drivers_data: list[dict]) -> int:
        rows = []
        for driver in drivers_data:
            key = _to_str(driver.get("id"))
            if not key:
                continue
            now = _utcnow_iso()
            first = _to_str(driver.get("firstName"))
            last = _to_str(driver.get("lastName"))
            full = _to_str(driver.get("fullName")) or " ".join(p for p in (first, last) if p)
            rows.append((
                self.driver_id(key), key, _to_str(driver.get("abbreviation")),
                _to_int(driver.get("permanentNumber")), first or "", last or "", full,
                _to_str(driver.get("nationalityCountryId")), _to_str(driver.get("dateOfBirth")),
                _to_str(driver.get("placeOfBirth")), _to_str(driver.get("countryOfBirthCountryId")),
                _to_str(driver.get("url")), now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_drivers (driver_id, driver_key, code, driver_number, given_name, family_name,
                   full_name, nationality, date_of_birth, place_of_birth, country_of_birth, url, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(driver_id) DO UPDATE SET
                     code = excluded.code, driver_number = excluded.driver_number,
                     given_name = excluded.given_name, family_name = excluded.family_name,
                     full_name = excluded.full_name, nationality = excluded.nationality,
                     date_of_birth = excluded.date_of_birth, place_of_birth = excluded.place_of_birth,
                     country_of_birth = excluded.country_of_birth, url = excluded.url,
                     updated_at = excluded.updated_at""",
                rows,
            )
        for row in rows:
            self._driver_ids[row[1]] = row[0]
        return len(rows)

    def ingest_constructors(self, constructors_data: list[dict]) -> int:
        rows = []
        for constructor in constructors_data:
            key = _to_str(constructor.get("id"))
            if not key:
                continue
            now = _utcnow_iso()
            rows.append((
                self.constructor_id(key), key, _to_str(constructor.get("name")),
                _to_str(constructor.get("countryId")),
                _to_int(constructor.get("firstSeasonEntry")), _to_int(constructor.get("lastSeasonEntry")),
                _to_int(constructor.get("totalChampionshipWins")) or 0,
                _to_int(constructor.get("totalRaceWins")) or 0,
                _to_int(constructor.get("totalPolePositions")) or 0,
                _to_int(constructor.get("totalFastestLaps")) or 0,
                _to_int(constructor.get("totalPodiums")) or 0,
                _to_float(constructor.get("totalPoints")) or 0.0,
                _to_str(constructor.get("url")), now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_constructors (constructor_id, constructor_key, name, nationality,
                   first_season, last_season, championships, wins, pole_positions, fastests_laps, podiums, points,
                   url, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(constructor_id) DO UPDATE SET
                     name = excluded.name, nationality = excluded.nationality,
                     first_season = excluded.first_season, last_season = excluded.last_season,
                     championships = excluded.championships, wins = excluded.wins,
                     pole_positions = excluded.pole_positions, fastests_laps = excluded.fastests_laps,
                     podiums = excluded.podiums, points = excluded.points, url = excluded.url,
                     updated_at = excluded.updated_at""",
                rows,
            )
        for row in rows:
            self._constructor_ids[row[1]] = row[0]
        return len(rows)

    def ingest_races(self, races_data: list[dict]) -> int:
        if not self._circuit_ids:
            with self.store._conn() as conn:
                for row in conn.execute("SELECT circuit_id, circuit_key FROM canonical_circuits"):
                    self._circuit_ids[row["circuit_key"]] = row["circuit_id"]
        rows = []
        for race in races_data:
            year = _to_int(race.get("year"))
            round_num = _to_int(race.get("round"))
            if year is None or round_num is None:
                continue
            circuit_key = _to_str(race.get("circuitId"))
            circuit_id = self._circuit_ids.get(circuit_key) if circuit_key else None
            now = _utcnow_iso()
            rows.append((
                self.race_id(year, round_num), f"{year}-{round_num}", year, round_num,
                _to_str(race.get("grandPrixId")), _to_str(race.get("officialName")),
                _to_str(race.get("date")), _to_str(race.get("time")),
                circuit_id, _to_str(race.get("circuitId")),
                None, None,
                _to_int(race.get("laps")), _to_float(race.get("distance")),
                None, None, now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_races (race_id, race_key, season, round, grand_prix, official_name, date,
                   time, circuit_id, circuit_name, country, city, total_laps, distance_km, status, official_url,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(race_id) DO UPDATE SET
                     grand_prix = excluded.grand_prix, official_name = excluded.official_name,
                     date = excluded.date, time = excluded.time, circuit_id = excluded.circuit_id,
                     circuit_name = excluded.circuit_name, total_laps = excluded.total_laps,
                     distance_km = excluded.distance_km, updated_at = excluded.updated_at""",
                rows,
            )
        for row in rows:
            self._race_ids[row[1]] = row[0]
        return len(rows)

    def _load_lookups(self) -> None:
        with self.store._conn() as conn:
            for row in conn.execute("SELECT driver_key, driver_id FROM canonical_drivers"):
                self._driver_ids[row["driver_key"]] = row["driver_id"]
            for row in conn.execute("SELECT constructor_key, constructor_id FROM canonical_constructors"):
                self._constructor_ids[row["constructor_key"]] = row["constructor_id"]
            for row in conn.execute("SELECT circuit_key, circuit_id FROM canonical_circuits"):
                self._circuit_ids[row["circuit_key"]] = row["circuit_id"]
            for row in conn.execute("SELECT race_key, race_id FROM canonical_races"):
                self._race_ids[row["race_key"]] = row["race_id"]

    # -- session construction -----------------------------------------------

    def construct_sessions(
        self,
        races_data: list[dict],
        detail_evidence: Optional[dict[str, set[str]]] = None,
    ) -> int:
        """Create canonical_sessions ONLY for sessions F1DB actually represents.

        A session is represented by F1DB when EITHER:
        - races.csv carries a scheduled date/time for it, OR
        - detail rows (results / qualifying / grids / practice / pit stops /
          fastest laps) actually exist for that session on that race.

        `detail_evidence` maps session type -> set of raceIds with actual
        detail rows. Sessions with no scheduling and no detail rows are NOT
        created - the capability is instead reported as UNAVAILABLE.
        """
        evidence = detail_evidence or {}
        sessions: list[tuple] = []
        seen: set[tuple[str, str]] = set()

        def add(race: dict, session_type: str, date: Any, time: Any, laps: Any = None) -> None:
            year = _to_int(race.get("year"))
            round_num = _to_int(race.get("round"))
            if year is None or round_num is None:
                return
            # Data-derived existence: scheduled date/time OR detail rows.
            has_schedule = _to_str(date) is not None
            has_rows = race.get("id") in evidence.get(session_type, set())
            if not (has_schedule or has_rows):
                return
            race_id = self.race_id(year, round_num)
            key = (race_id, session_type)
            if key in seen:
                return
            seen.add(key)
            now = _utcnow_iso()
            sessions.append((
                self.session_id(race_id, session_type),
                self.session_key(year, round_num, _to_str(race.get("grandPrixId")) or "gp", session_type),
                race_id, session_type, session_type.replace("_", " ").title(),
                _to_str(date), _to_str(time),
                _to_int(laps), None,
                F1DB_PROVIDER, _to_str(race.get("id")), self.source_version,
                now, now,
            ))

        for race in races_data:
            add(race, "RACE", race.get("date") or ("scheduled" if race.get("id") in evidence.get("RACE", set()) else None), race.get("time"), race.get("laps"))
            add(race, "QUALIFYING", race.get("qualifyingDate"), race.get("qualifyingTime"))
            add(race, "SPRINT", race.get("sprintRaceDate"), race.get("sprintRaceTime"), race.get("sprintRaceLaps"))
            add(race, "SPRINT_QUALIFYING", race.get("sprintQualifyingDate"), race.get("sprintQualifyingTime"))
            add(race, "FREE_PRACTICE_1", race.get("freePractice1Date"), race.get("freePractice1Time"))
            add(race, "FREE_PRACTICE_2", race.get("freePractice2Date"), race.get("freePractice2Time"))
            add(race, "FREE_PRACTICE_3", race.get("freePractice3Date"), race.get("freePractice3Time"))
            add(race, "FREE_PRACTICE_4", race.get("freePractice4Date"), race.get("freePractice4Time"))
            add(race, "QUALIFYING_1", race.get("qualifying1Date"), race.get("qualifying1Time"))
            add(race, "QUALIFYING_2", race.get("qualifying2Date"), race.get("qualifying2Time"))
            add(race, "PRE_QUALIFYING", race.get("preQualifyingDate"), race.get("preQualifyingTime"))
            add(race, "WARMING_UP", race.get("warmingUpDate"), race.get("warmingUpTime"))

        if sessions:
            self.store.execute_batch(
                """INSERT INTO canonical_sessions (session_id, session_key, race_id, session_type, session_name,
                   date_start, date_end, laps_total, laps_completed, source_provider, source_id, source_version,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     session_name = excluded.session_name, date_start = excluded.date_start,
                     date_end = excluded.date_end, laps_total = excluded.laps_total,
                     source_provider = excluded.source_provider, source_id = excluded.source_id,
                     source_version = excluded.source_version, updated_at = excluded.updated_at""",
                sessions,
            )
        return len(sessions)

    @staticmethod
    def collect_detail_evidence(extract_dir: Path) -> dict[str, set[str]]:
        """Scan detail CSVs for which (session_type, raceId) pairs actually have rows.

        Reads only the raceId column - cheap and memory-bounded.
        """
        evidence_files = {
            "RACE": "f1db-races-race-results.csv",
            "SPRINT": "f1db-races-sprint-race-results.csv",
            "QUALIFYING": "f1db-races-qualifying-results.csv",
            "SPRINT_QUALIFYING": "f1db-races-sprint-qualifying-results.csv",
            "QUALIFYING_1": "f1db-races-qualifying-1-results.csv",
            "QUALIFYING_2": "f1db-races-qualifying-2-results.csv",
            "PRE_QUALIFYING": "f1db-races-pre-qualifying-results.csv",
            "FREE_PRACTICE_1": "f1db-races-free-practice-1-results.csv",
            "FREE_PRACTICE_2": "f1db-races-free-practice-2-results.csv",
            "FREE_PRACTICE_3": "f1db-races-free-practice-3-results.csv",
            "FREE_PRACTICE_4": "f1db-races-free-practice-4-results.csv",
            "WARMING_UP": "f1db-races-warming-up-results.csv",
            "GRID": "f1db-races-starting-grid-positions.csv",
            "PIT_STOPS": "f1db-races-pit-stops.csv",
            "FASTEST_LAPS": "f1db-races-fastest-laps.csv",
        }
        evidence: dict[str, set[str]] = {}
        for session_type, filename in evidence_files.items():
            race_ids: set[str] = set()
            file_path = extract_dir / filename
            if not file_path.exists():
                continue
            with open(file_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    race_id = row.get("raceId")
                    if race_id:
                        race_ids.add(race_id)
            if race_ids:
                evidence[session_type] = race_ids
        return evidence

    # -- session-level data ---------------------------------------------------

    def ingest_results(self, results_data: list[dict], session_type: str = "RACE") -> int:
        """Ingest race/sprint results keyed by (raceId, positionDisplayOrder).

        Shared cars legitimately produce two rows for one driver (different
        display order); those are preserved as separate result rows.
        """
        rows = []
        for result in results_data:
            year = _to_int(result.get("year"))
            round_num = _to_int(result.get("round"))
            if year is None or round_num is None:
                continue
            race_id = self.race_id(year, round_num)
            session_id = self.session_id(race_id, session_type)
            driver_id = self._driver_id_for(_to_str(result.get("driverId")))
            if driver_id is None:
                continue
            constructor_id = self._constructor_id_for(_to_str(result.get("constructorId")))
            source_row_id = f"{result.get('raceId')}:{result.get('positionDisplayOrder')}"
            now = _utcnow_iso()
            rows.append((
                self.result_id(session_id, source_row_id), session_id, driver_id, constructor_id,
                _to_int(result.get("positionNumber")), _to_int(result.get("positionDisplayOrder")),
                _to_int(result.get("gridPositionNumber")), _to_str(result.get("positionText")),
                _to_float(result.get("points")), _to_int(result.get("laps")),
                _to_str(result.get("time")), _to_int(result.get("timeMillis")),
                _to_int(result.get("fastestLap")), None,
                None, None,
                _to_str(result.get("reasonRetired")) or _to_str(result.get("positionText")),
                _to_str(result.get("reasonRetired")),
                F1DB_PROVIDER, _to_str(result.get("raceId")), self.source_version,
                now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_results (result_id, session_id, driver_id, constructor_id, position,
                   position_order, grid, position_text, points, laps, time, milliseconds, fastest_lap, rank,
                   fastest_lap_time, fastest_lap_speed, status_id, status, source_provider, source_id,
                   source_version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(result_id) DO UPDATE SET
                     position = excluded.position, position_order = excluded.position_order,
                     grid = excluded.grid, position_text = excluded.position_text,
                     points = excluded.points, laps = excluded.laps, time = excluded.time,
                     milliseconds = excluded.milliseconds, status_id = excluded.status_id,
                     status = excluded.status, updated_at = excluded.updated_at""",
                rows,
            )
        return len(rows)

    def ingest_qualifying(self, qualifying_data: list[dict], session_type: str = "QUALIFYING") -> int:
        """Ingest qualifying results preserving the source's Q1/Q2/Q3 shape.

        Rows only carry q2/q3 where the source has them; historical eras with
        a single qualifying session keep q1 = session time, q2/q3 = NULL.
        """
        rows = []
        for qual in qualifying_data:
            year = _to_int(qual.get("year"))
            round_num = _to_int(qual.get("round"))
            if year is None or round_num is None:
                continue
            race_id = self.race_id(year, round_num)
            session_id = self.session_id(race_id, session_type)
            driver_key = _to_str(qual.get("driverId"))
            driver_id = self._driver_id_for(driver_key)
            if driver_id is None:
                continue
            constructor_id = self._constructor_id_for(_to_str(qual.get("constructorId")))
            now = _utcnow_iso()
            rows.append((
                self.qualifying_id(session_id, driver_key), session_id, driver_id, constructor_id,
                _to_int(qual.get("positionNumber")),
                _to_str(qual.get("q1")) or _to_str(qual.get("time")),
                _to_str(qual.get("q2")), _to_str(qual.get("q3")),
                _to_str(qual.get("positionText")),
                F1DB_PROVIDER, _to_str(qual.get("raceId")), self.source_version,
                now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_qualifying (qualifying_id, session_id, driver_id, constructor_id,
                   position, q1, q2, q3, position_text, source_provider, source_id, source_version,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(qualifying_id) DO UPDATE SET
                     position = excluded.position, q1 = excluded.q1, q2 = excluded.q2, q3 = excluded.q3,
                     position_text = excluded.position_text, updated_at = excluded.updated_at""",
                rows,
            )
        return len(rows)

    def ingest_pit_stops(self, pit_stops_data: list[dict], session_type: str = "RACE") -> int:
        """Ingest pit stops. Identity includes timeMillis so exact duplicate
        source rows collapse while distinct stops are preserved."""
        rows = []
        for stop in pit_stops_data:
            year = _to_int(stop.get("year"))
            round_num = _to_int(stop.get("round"))
            if year is None or round_num is None:
                continue
            race_id = self.race_id(year, round_num)
            session_id = self.session_id(race_id, session_type)
            driver_key = _to_str(stop.get("driverId"))
            driver_id = self._driver_id_for(driver_key)
            if driver_id is None:
                continue
            lap = _to_int(stop.get("lap"))
            if lap is None:
                continue
            stop_number = _to_int(stop.get("stop"))
            time_millis = _to_int(stop.get("timeMillis"))
            now = _utcnow_iso()
            rows.append((
                self.pit_stop_id(session_id, driver_key, stop_number, lap, time_millis),
                session_id, driver_id, lap, stop_number,
                _to_str(stop.get("time")),
                time_millis / 1000.0 if time_millis is not None else None,
                None, None, None, None,
                F1DB_PROVIDER, _to_str(stop.get("raceId")), self.source_version,
                now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_pit_stops (pit_stop_id, session_id, driver_id, lap, stop_number, time,
                   duration, compound_before, compound_after, tyre_life_before, tyre_life_after,
                   source_provider, source_id, source_version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(pit_stop_id) DO UPDATE SET
                     time = excluded.time, duration = excluded.duration, updated_at = excluded.updated_at""",
                rows,
            )
        return len(rows)

    def ingest_fastest_laps(self, fastest_laps_data: list[dict], session_type: str = "RACE") -> int:
        """Ingest fastest-lap records as canonical_lap_times rows.

        F1DB provides only the single fastest lap per driver - NOT full lap
        telemetry. This is stored as-is, never presented as complete laps.
        """
        rows = []
        for fl in fastest_laps_data:
            year = _to_int(fl.get("year"))
            round_num = _to_int(fl.get("round"))
            if year is None or round_num is None:
                continue
            race_id = self.race_id(year, round_num)
            session_id = self.session_id(race_id, session_type)
            driver_key = _to_str(fl.get("driverId"))
            driver_id = self._driver_id_for(driver_key)
            if driver_id is None:
                continue
            lap = _to_int(fl.get("lap"))
            millis = _to_int(fl.get("timeMillis"))
            now = _utcnow_iso()
            rows.append((
                self.lap_time_id(session_id, driver_key, fl.get("lap")),
                session_id, driver_id, lap or 0,
                _to_int(fl.get("positionNumber")),
                millis / 1000.0 if millis is not None else None,
                None, None, None, None, None, None,
                False, False, None, None, False,
                F1DB_PROVIDER, _to_str(fl.get("raceId")), self.source_version,
                now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_lap_times (lap_time_id, session_id, driver_id, lap_number, position,
                   time_s, sector1_s, sector2_s, sector3_s, compound, tyre_life, stint,
                   is_pit_in_lap, is_pit_out_lap, track_status, is_accurate, deleted,
                   source_provider, source_id, source_version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(lap_time_id) DO UPDATE SET
                     position = excluded.position, time_s = excluded.time_s, updated_at = excluded.updated_at""",
                rows,
            )
        return len(rows)

    def ingest_starting_grid(self, grid_data: list[dict], session_type: str = "RACE") -> int:
        """Ingest starting grid positions into canonical_qualifying.

        F1DB stores grids as their own dataset; grid order with a time maps to
        a qualifying row (q1 = grid time) when no qualifying file rows exist
        for the driver. position_text preserves DNS/DNQ semantics.
        """
        rows = []
        for grid in grid_data:
            year = _to_int(grid.get("year"))
            round_num = _to_int(grid.get("round"))
            if year is None or round_num is None:
                continue
            race_id = self.race_id(year, round_num)
            session_id = self.session_id(race_id, session_type)
            driver_key = _to_str(grid.get("driverId"))
            driver_id = self._driver_id_for(driver_key)
            if driver_id is None:
                continue
            constructor_id = self._constructor_id_for(_to_str(grid.get("constructorId")))
            now = _utcnow_iso()
            rows.append((
                _stable_id(F1DB_PROVIDER, "grid", session_id, driver_key),
                session_id, driver_id, constructor_id,
                _to_int(grid.get("positionNumber")),
                _to_str(grid.get("time")), None, None,
                _to_str(grid.get("positionText")),
                F1DB_PROVIDER, _to_str(grid.get("raceId")), self.source_version,
                now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_qualifying (qualifying_id, session_id, driver_id, constructor_id,
                   position, q1, q2, q3, position_text, source_provider, source_id, source_version,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(qualifying_id) DO UPDATE SET
                     position = excluded.position, q1 = excluded.q1,
                     position_text = excluded.position_text, updated_at = excluded.updated_at""",
                rows,
            )
        return len(rows)

    def ingest_practice_results(self, practice_data: list[dict], session_type: str) -> int:
        """Ingest free practice results into canonical_qualifying.

        Practice sessions have classification order and a best time (no Q1/Q2/Q3
        split), stored with q1 = best time and the source position preserved.
        """
        rows = []
        for practice in practice_data:
            year = _to_int(practice.get("year"))
            round_num = _to_int(practice.get("round"))
            if year is None or round_num is None:
                continue
            race_id = self.race_id(year, round_num)
            session_id = self.session_id(race_id, session_type)
            driver_key = _to_str(practice.get("driverId"))
            driver_id = self._driver_id_for(driver_key)
            if driver_id is None:
                continue
            constructor_id = self._constructor_id_for(_to_str(practice.get("constructorId")))
            now = _utcnow_iso()
            rows.append((
                _stable_id(F1DB_PROVIDER, "practice", session_id, driver_key),
                session_id, driver_id, constructor_id,
                _to_int(practice.get("positionNumber")),
                _to_str(practice.get("time")), None, None,
                _to_str(practice.get("positionText")),
                F1DB_PROVIDER, _to_str(practice.get("raceId")), self.source_version,
                now, now,
            ))
        if rows:
            self.store.execute_batch(
                """INSERT INTO canonical_qualifying (qualifying_id, session_id, driver_id, constructor_id,
                   position, q1, q2, q3, position_text, source_provider, source_id, source_version,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(qualifying_id) DO UPDATE SET
                     position = excluded.position, q1 = excluded.q1,
                     position_text = excluded.position_text, updated_at = excluded.updated_at""",
                rows,
            )
        return len(rows)

    # -- availability / catalog ----------------------------------------------

    def rebuild_catalog(self) -> int:
        """Rebuild the session catalog with DATA-DERIVED capability flags.

        Every count is an actual SELECT COUNT over canonical rows. A session
        with zero rows is UNAVAILABLE - availability is never inferred from
        the season year.
        """
        now = _utcnow_iso()
        with self.store.bulk_conn() as conn:
            conn.execute("DELETE FROM canonical_session_catalog")
            # Aggregate counts per session once (fast), then join.
            conn.execute("CREATE TEMP TABLE _cat_results AS SELECT session_id, COUNT(*) AS n FROM canonical_results GROUP BY session_id")
            conn.execute("CREATE TEMP TABLE _cat_qual AS SELECT session_id, COUNT(*) AS n FROM canonical_qualifying GROUP BY session_id")
            conn.execute("CREATE TEMP TABLE _cat_pits AS SELECT session_id, COUNT(*) AS n FROM canonical_pit_stops GROUP BY session_id")
            conn.execute("CREATE TEMP TABLE _cat_laps AS SELECT session_id, COUNT(*) AS n FROM canonical_lap_times GROUP BY session_id")
            conn.execute("CREATE TEMP TABLE _cat_stints AS SELECT session_id, COUNT(*) AS n FROM canonical_stints GROUP BY session_id")
            conn.execute("CREATE TEMP TABLE _cat_weather AS SELECT session_id, COUNT(*) AS n FROM canonical_weather GROUP BY session_id")
            conn.execute("CREATE TEMP TABLE _cat_rc AS SELECT session_id, COUNT(*) AS n FROM canonical_race_control GROUP BY session_id")
            conn.execute("CREATE TEMP TABLE _cat_tel AS SELECT session_id, COUNT(*) AS n FROM canonical_telemetry GROUP BY session_id")
            conn.execute(
                """
                INSERT INTO canonical_session_catalog (
                    session_id, race_id, season, round, race_name, circuit_id, circuit_name, country, date,
                    session_type, source_provider,
                    results_count, qualifying_count, grid_count, pit_stops_count, laps_count,
                    stints_count, weather_count, race_control_count, telemetry_available,
                    results_availability, qualifying_availability, pit_stops_availability,
                    laps_availability, stints_availability, weather_availability,
                    race_control_availability, telemetry_availability, updated_at
                )
                SELECT
                    s.session_id, r.race_id, r.season, r.round, r.official_name, r.circuit_id, r.circuit_name, r.country, r.date,
                    s.session_type, s.source_provider,
                    COALESCE(res.n, 0),
                    COALESCE(qual.n, 0),
                    0,
                    COALESCE(pits.n, 0),
                    COALESCE(laps.n, 0),
                    COALESCE(stints.n, 0),
                    COALESCE(weather.n, 0),
                    COALESCE(rc.n, 0),
                    CASE WHEN COALESCE(tel.n, 0) > 0 THEN 1 ELSE 0 END,
                    CASE WHEN COALESCE(res.n, 0) > 0 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END,
                    CASE WHEN COALESCE(qual.n, 0) > 0 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END,
                    CASE WHEN COALESCE(pits.n, 0) > 0 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END,
                    CASE WHEN COALESCE(laps.n, 0) > 0 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END,
                    CASE WHEN COALESCE(stints.n, 0) > 0 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END,
                    CASE WHEN COALESCE(weather.n, 0) > 0 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END,
                    CASE WHEN COALESCE(rc.n, 0) > 0 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END,
                    CASE WHEN COALESCE(tel.n, 0) > 0 THEN 'AVAILABLE' ELSE 'UNAVAILABLE' END,
                    ?
                FROM canonical_sessions s
                JOIN canonical_races r ON r.race_id = s.race_id
                LEFT JOIN _cat_results res ON res.session_id = s.session_id
                LEFT JOIN _cat_qual qual ON qual.session_id = s.session_id
                LEFT JOIN _cat_pits pits ON pits.session_id = s.session_id
                LEFT JOIN _cat_laps laps ON laps.session_id = s.session_id
                LEFT JOIN _cat_stints stints ON stints.session_id = s.session_id
                LEFT JOIN _cat_weather weather ON weather.session_id = s.session_id
                LEFT JOIN _cat_rc rc ON rc.session_id = s.session_id
                LEFT JOIN _cat_tel tel ON tel.session_id = s.session_id
                """,
                (now,),
            )
        with self.store._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM canonical_session_catalog").fetchone()[0]


def _to_bool_public(value: Any) -> bool:
    """Public alias kept for backwards compatibility with earlier imports."""
    return bool(_to_bool(value))
