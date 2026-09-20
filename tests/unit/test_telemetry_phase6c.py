"""Phase 6C telemetry tests: fixtures, identity, idempotency, bounded queries,
availability, deterministic analysis, Q6 benchmark and negative controls.

No network access: telemetry fixture rows are built with the real schema and
ingestion helper, exercising the same code paths as live ingestion. Live-store
tests run only when the canonical DB exists.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"

requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

SIGNALS = ("speed", "throttle", "brake", "gear", "rpm", "drs")

INSERT_SQL = """INSERT INTO canonical_telemetry (telemetry_id, session_id, driver_id,
    lap_number, time_elapsed_s, lap_time_s, speed_kmh, throttle_pct,
    brake, gear, rpm, drs, source_provider, source_id, source_version, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(telemetry_id) DO NOTHING"""


def _fixture_row(session_id, driver_id, lap_number, t_elapsed, t_lap, speed, throttle,
                 brake, gear, rpm, drs, source_version="test-1"):
    """Build one canonical telemetry row with the real content-derived id."""
    from racewise.data.historical.f1db_canonical import _stable_id

    return (
        _stable_id("fastf1", "tel", session_id, driver_id, lap_number, round(t_elapsed, 3)),
        session_id, driver_id, lap_number, t_elapsed, t_lap,
        speed, throttle, brake, gear, rpm, drs,
        "fastf1", f"test:{driver_id}:L{lap_number}", source_version,
        "2023-01-01T00:00:00", "2023-01-01T00:00:00",
    )


def _synthetic_canonical_rows(n_samples: int = 60) -> list[tuple]:
    """Deterministic speed/throttle/brake series (documented fixture, not data)."""
    rows = []
    for i in range(n_samples):
        t = round(i / 10.0, 4)
        speed = 100 + (i % 20) * 5  # deterministic triangle wave 100..195
        throttle = 60 + (i % 10) * 4
        brake = 1 if (i % 10) == 9 else 0
        rows.append(_fixture_row("sess-1", "drv-1", 1, t, t, speed, throttle, brake, 4, 9000 + i, 0))
    return rows


def _insert_rows(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(INSERT_SQL, rows)
    conn.commit()


def _make_store(tmp_path: Path) -> sqlite3.Connection:
    """Minimal canonical store with the real telemetry schema + fixture identity."""
    from racewise.data.historical.f1db_canonical import CanonicalStore

    store = CanonicalStore(str(tmp_path / "t.db"))
    conn = sqlite3.connect(str(tmp_path / "t.db"))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO canonical_races (race_id, race_key, season, round, grand_prix, circuit_name, country, date, created_at, updated_at) "
        "VALUES ('race-1', 'rk', 2023, 1, 'Test GP', 'Test Circuit', 'Bahrain', '2023-03-05', '2023-01-01T00:00:00', '2023-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO canonical_sessions (session_id, session_key, race_id, session_type, source_provider, source_id, source_version, created_at, updated_at) "
        "VALUES ('sess-1', '2023-1-RACE', 'race-1', 'RACE', 'f1db', 'test', 'test', '2023-01-01T00:00:00', '2023-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO canonical_drivers (driver_id, driver_key, code, given_name, family_name, full_name, created_at, updated_at) "
        "VALUES ('drv-1', 'max-verstappen', 'VER', 'Max', 'Verstappen', 'Max Verstappen', '2023-01-01T00:00:00', '2023-01-01T00:00:00')"
    )
    conn.commit()
    return conn


# -- identity, insertion, idempotency -------------------------------------------


class TestTelemetryIdentityAndIdempotency:
    def test_ingest_twice_yields_identical_counts(self, tmp_path):
        conn = _make_store(tmp_path)
        rows = _synthetic_canonical_rows()
        _insert_rows(conn, rows)
        n1 = conn.execute("SELECT COUNT(*) FROM canonical_telemetry").fetchone()[0]
        # second run: identical content -> zero new rows (ON CONFLICT DO NOTHING
        # on the deterministic content key)
        _insert_rows(conn, rows)
        n2 = conn.execute("SELECT COUNT(*) FROM canonical_telemetry").fetchone()[0]
        assert n1 == n2 == len(rows)
        conn.close()

    def test_telemetry_ids_are_content_derived(self):
        from racewise.data.historical.f1db_canonical import _stable_id

        a = _stable_id("fastf1", "tel", "sess-1", "drv-1", 1, 1.0)
        b = _stable_id("fastf1", "tel", "sess-1", "drv-1", 1, 1.0)
        assert a == b  # deterministic, not random
        c = _stable_id("fastf1", "tel", "sess-1", "drv-1", 1, 2.0)
        assert c != a  # different timestamp -> different id (collision behaviour)


# -- bounded query layer (fixture store) ----------------------------------------


class TestBoundedTelemetryQueries:
    def _seed_and_query(self, tmp_path, n_samples: int = 60):
        from racewise.data.historical.canonical_queries import CanonicalQueries

        conn = _make_store(tmp_path)
        _insert_rows(conn, _synthetic_canonical_rows(n_samples))
        conn.close()
        return CanonicalQueries(str(tmp_path / "t.db"))

    def test_query_respects_signal_whitelist(self, tmp_path):
        q = self._seed_and_query(tmp_path)
        with pytest.raises(ValueError):
            q.get_lap_telemetry(2023, 1, "max-verstappen", 1, signals=["velocity"])

    def test_query_output_cap_bounds_signal_expansion(self, tmp_path):
        q = self._seed_and_query(tmp_path, n_samples=100)
        rows = q.get_lap_telemetry(
            2023, 1, "max-verstappen", 1, signals=["speed", "throttle", "brake"], max_samples=120,
        )
        assert len(rows) <= 120  # cap bounds OUTPUT rows, not raw rows

    def test_missing_telemetry_returns_empty_not_zero(self, tmp_path):
        q = self._seed_and_query(tmp_path)
        rows = q.get_lap_telemetry(1950, 6, "max-verstappen", 1)
        assert rows == []  # UNAVAILABLE, never fabricated

    def test_telemetry_summary_is_count_derived(self, tmp_path):
        q = self._seed_and_query(tmp_path)
        s = q.telemetry_summary(2023, 1, "RACE")
        assert s["available"] is True
        assert s["sample_count"] == 60
        assert s["drivers"] == 1
        s2 = q.telemetry_summary(1950, 6, "RACE")
        assert s2["available"] is False and s2["sample_count"] == 0


# -- deterministic analysis + Q6 + negative controls (fixture store) -------------


class TestTelemetryAnalysis:
    def _seeded(self, tmp_path):
        from racewise.data.historical.canonical_queries import CanonicalQueries

        conn = _make_store(tmp_path)
        conn.execute(
            "INSERT INTO canonical_drivers (driver_id, driver_key, code, given_name, family_name, full_name, created_at, updated_at) "
            "VALUES ('drv-2', 'sergio-perez', 'PER', 'Sergio', 'Perez', 'Sergio Perez', '2023-01-01T00:00:00', '2023-01-01T00:00:00')"
        )
        conn.commit()
        # driver A: faster series; driver B: 10 km/h slower everywhere
        rows_a = _synthetic_canonical_rows(60)
        rows_b = [
            _fixture_row("sess-1", "drv-2", 1, r[4], r[5], r[6] - 10, r[7] - 5, r[8], r[9], r[10] - 500, r[11])
            for r in rows_a
        ]
        _insert_rows(conn, rows_a + rows_b)
        conn.close()
        return CanonicalQueries(str(tmp_path / "t.db"))

    def test_comparison_is_deterministic(self, tmp_path):
        import hashlib
        import json

        from racewise.data.historical.telemetry_analysis import compare_telemetry_lap

        q = self._seeded(tmp_path)
        r1 = compare_telemetry_lap(q, 2023, 1, "max-verstappen", "sergio-perez", 1)
        r2 = compare_telemetry_lap(q, 2023, 1, "max-verstappen", "sergio-perez", 1)
        h = lambda r: hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()  # noqa: E731
        assert h(r1) == h(r2)
        assert r1["verdict"] == "PASS"
        assert r1["total_est_time_loss_s"] > 0  # B is slower by construction

    def test_comparison_insufficient_when_lap_missing(self, tmp_path):
        from racewise.data.historical.telemetry_analysis import compare_telemetry_lap

        q = self._seeded(tmp_path)
        r = compare_telemetry_lap(q, 2023, 1, "max-verstappen", "sergio-perez", 99)
        assert r["verdict"] == "INSUFFICIENT_EVIDENCE"

    def test_q6_negative_control_no_telemetry(self, tmp_path):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.engineering_benchmarks import EngineeringBenchmarks

        _make_store(tmp_path)  # schema exists, but no telemetry rows anywhere
        q = CanonicalQueries(str(tmp_path / "t.db"))
        r = EngineeringBenchmarks(q, season=2023, round_num=1).q6_telemetry_pace_explanation(
            "max-verstappen", "sergio-perez",
        )
        assert r["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert "no canonical telemetry" in r["reason"]


# -- live-store checks (bounded set actually ingested) ---------------------------


@requires_db
class TestLiveTelemetryStore:
    def test_bounded_session_set_and_availability(self):
        conn = sqlite3.connect(str(DB_PATH))
        sessions = conn.execute(
            """SELECT r.season, r.round FROM canonical_telemetry t
               JOIN canonical_sessions s ON s.session_id = t.session_id
               JOIN canonical_races r ON r.race_id = s.race_id
               GROUP BY t.session_id"""
        ).fetchall()
        conn.close()
        assert len(sessions) == 5, "bounded Phase 6C scope must stay 5 sessions"
        assert all(2021 <= s[0] <= 2025 for s in sessions)

    def test_catalog_telemetry_capability_is_count_derived(self):
        from racewise.data.historical.catalog_api import CatalogAPI

        api = CatalogAPI(str(DB_PATH))
        d = api.session_detail(2023, 1, "RACE")
        assert d["capabilities"]["telemetry"]["available"] is True
        d2 = api.session_detail(2018, 1, "RACE")
        assert d2["capabilities"]["telemetry"]["available"] is False

    def test_q6_passes_on_live_telemetry_sessions(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.engineering_benchmarks import EngineeringBenchmarks

        q = CanonicalQueries(str(DB_PATH))
        cases = [
            (2021, 10, "charles-leclerc", "lewis-hamilton"),
            (2022, 1, "charles-leclerc", "carlos-sainz-jr"),
            (2023, 1, "max-verstappen", "sergio-perez"),
            (2024, 1, "max-verstappen", "sergio-perez"),
            (2025, 1, "max-verstappen", "lando-norris"),
        ]
        for season, rnd, a, b in cases:
            r = EngineeringBenchmarks(q, season=season, round_num=rnd).q6_telemetry_pace_explanation(a, b)
            assert r["verdict"] == "PASS", f"Q6 {season} R{rnd}: {r.get('reason')}"

    def test_q6_negative_controls(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.engineering_benchmarks import EngineeringBenchmarks

        q = CanonicalQueries(str(DB_PATH))
        # 1950: no telemetry era
        r1 = EngineeringBenchmarks(q, season=1950, round_num=6).q6_telemetry_pace_explanation(
            "giuseppe-farina", "luigi-fagioli",
        )
        assert r1["verdict"] == "INSUFFICIENT_EVIDENCE"
        # 2018: modern era but telemetry not ingested for it
        r2 = EngineeringBenchmarks(q, season=2018, round_num=1).q6_telemetry_pace_explanation(
            "lewis-hamilton", "sebastian-vettel",
        )
        assert r2["verdict"] == "INSUFFICIENT_EVIDENCE"

    def test_telemetry_investigation_deterministic(self):
        import hashlib
        import json

        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.engineering_benchmarks import EngineeringBenchmarks

        q = CanonicalQueries(str(DB_PATH))
        bench = EngineeringBenchmarks(q)
        h = lambda: hashlib.sha256(json.dumps(
            bench.telemetry_investigation_2023_bahrain(), sort_keys=True, default=str,
        ).encode()).hexdigest()[:16]
        assert h() == h()
