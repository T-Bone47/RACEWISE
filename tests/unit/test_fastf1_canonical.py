"""Phase 6A tests: FastF1 canonicalization, validators, benchmarks, tools.

FastF1 data-path tests use the local cache when present and are skipped
(honestly, with reason) when the cached session does not exist on this
machine - no network downloads in unit tests, no fabricated fixtures for
provider behavior.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from racewise.data.historical.canonical_queries import get_canonical_queries  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
CACHE_DIR = REPO / ".fastf1-cache"

_canonical_db_present = DB_PATH.exists()
_bahrain_cached = (CACHE_DIR / "2023" / "2023-03-05_Bahrain_Grand_Prix").exists()

requires_db = pytest.mark.skipif(
    not _canonical_db_present, reason="canonical DB not ingested on this machine"
)
requires_bahrain_cache = pytest.mark.skipif(
    not _bahrain_cached, reason="2023 Bahrain FastF1 cache not present locally"
)


def _count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# -- FastF1 canonicalizer on the real store ----------------------------------


@requires_db
@requires_bahrain_cache
class TestFastF1Canonicalizer:
    def test_ingest_session_is_idempotent(self, tmp_path):
        from racewise.data.fastf1_adapter import FastF1Adapter
        from racewise.data.historical.fastf1_canonical import FastF1Canonicalizer
        from racewise.data.historical.f1db_canonical import CanonicalStore

        store = CanonicalStore(str(DB_PATH))
        canon = FastF1Canonicalizer(store)
        adapter = FastF1Adapter(cache_dir=str(CACHE_DIR))
        session = adapter.load_session(2023, 1, "R")

        first = canon.ingest_session(2023, 1, "R", session)
        assert first["attached"] is True
        counts_1 = {
            "stints": _count(DB_PATH, "canonical_stints"),
            "weather": _count(DB_PATH, "canonical_weather"),
            "race_control": _count(DB_PATH, "canonical_race_control"),
        }
        canon.ingest_session(2023, 1, "R", session)
        counts_2 = {
            "stints": _count(DB_PATH, "canonical_stints"),
            "weather": _count(DB_PATH, "canonical_weather"),
            "race_control": _count(DB_PATH, "canonical_race_control"),
        }
        assert counts_1 == counts_2  # idempotent

    def test_stints_have_provenance_and_compounds(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries

        rows = get_canonical_queries(str(DB_PATH)).get_stints(2023, 1, "RACE")
        assert len(rows) > 0
        for r in rows:
            assert r["source_provider"] == "fastf1"
            assert r["source_version"]
            assert r["source_id"]
            assert r["lap_end"] >= r["lap_start"]
            assert r["compound"] is None or isinstance(r["compound"], str)

    def test_weather_native_precision_and_order(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries

        rows = get_canonical_queries(str(DB_PATH)).get_weather(2023, 1, "RACE")
        assert len(rows) > 50
        # get_weather orders by the ISO timestamp string; rowid carries the
        # source observation order, which is non-decreasing in elapsed time.
        by_rowid = sorted(rows, key=lambda r: r["rowid"] if "rowid" in r else 0)
        if "rowid" not in by_rowid[0]:
            from racewise.data.historical.canonical_queries import CanonicalQueries

            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT rowid, * FROM canonical_weather WHERE session_id = ? ORDER BY rowid",
                    (CanonicalQueries(str(DB_PATH)).resolve_session(2023, 1, "RACE")["session_id"],),
                )
            ]
            conn.close()
        elapsed = [r["elapsed_s"] for r in rows if r.get("elapsed_s") is not None]
        assert elapsed == sorted(elapsed)  # non-decreasing session time
        assert all(r["source_provider"] == "fastf1" for r in rows)

    def test_race_control_events(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries

        rows = get_canonical_queries(str(DB_PATH)).get_race_control(2023, 1, "RACE")
        assert len(rows) > 20
        assert all(r["message"] for r in rows)
        assert any(r["category"] == "Flag" for r in rows)

    def test_no_fastf1_rows_on_1950_session(self):
        """FastF1 never attaches data to sessions it did not cover."""
        from racewise.data.historical.canonical_queries import get_canonical_queries

        q = get_canonical_queries(str(DB_PATH))
        assert q.get_stints(1950, 2, "RACE") == []
        assert q.get_weather(1950, 2, "RACE") == []
        assert q.get_race_control(1950, 2, "RACE") == []


@requires_db
class TestFastF1SessionResolution:
    def test_unknown_session_code_rejected(self):
        from racewise.data.historical.fastf1_canonical import FastF1Canonicalizer
        from racewise.data.historical.f1db_canonical import CanonicalStore

        canon = FastF1Canonicalizer(CanonicalStore(str(DB_PATH)))
        assert canon.resolve_session(2023, 1, "XX") is None

    def test_unrepresented_session_rejected(self):
        """A session F1DB does not represent must not receive FastF1 rows."""
        from racewise.data.historical.fastf1_canonical import FastF1Canonicalizer
        from racewise.data.historical.f1db_canonical import CanonicalStore

        canon = FastF1Canonicalizer(CanonicalStore(str(DB_PATH)))
        # Season 1950 round 2 qualifying exists canonically; pick a type/round
        # that does not exist: 1950 has no FREE_PRACTICE_1 schedule or rows.
        assert canon.resolve_session(1950, 2, "FP1") is None


# -- validators ---------------------------------------------------------------


@requires_db
class TestValidators:
    def test_all_validators_pass(self):
        from racewise.data.historical.validators import validate_canonical_data

        report = validate_canonical_data(str(DB_PATH))
        assert report["ok"] is True, report["failures"]
        assert report["failed"] == 0
        assert report["passed"] >= 14

    def test_validator_detects_bad_stint_range(self, tmp_path):
        """A corrupt stint row must be caught (no silent acceptance)."""
        from racewise.data.historical.validators import CanonicalDataValidator

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """INSERT INTO canonical_stints (stint_id, session_id, driver_id, stint_number,
               compound, lap_start, lap_end, lap_count, source_provider, source_id, source_version,
               created_at, updated_at)
               SELECT 'test-bad-stint', session_id, driver_id, 99, 'SOFT', 10, 5, -1,
                      'fastf1', 'test', 'test', '2026-01-01', '2026-01-01'
               FROM canonical_stints LIMIT 1"""
        )
        conn.commit()
        conn.close()
        try:
            report = CanonicalDataValidator(str(DB_PATH)).validate_all()
            names = {c["name"] for c in report.checks if not c["ok"]}
            assert "stint_ranges_sane" in names
        finally:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("DELETE FROM canonical_stints WHERE stint_id = 'test-bad-stint'")
            conn.commit()
            conn.close()


# -- availability / catalog reflects modern data ------------------------------


@requires_db
class TestModernAvailability:
    def test_2023_bahrain_flags_are_data_derived(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT c.* FROM canonical_session_catalog c
               JOIN canonical_races r ON r.race_id = c.race_id
               WHERE r.season = 2023 AND r.round = 1 AND c.session_type = 'RACE'"""
        ).fetchone()
        conn.close()
        assert row["stints_availability"] == "AVAILABLE"
        assert row["weather_availability"] == "AVAILABLE"
        assert row["race_control_availability"] == "AVAILABLE"
        assert row["stints_count"] > 0
        assert row["weather_count"] > 0

    def test_1950_monaco_still_unavailable(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT c.* FROM canonical_session_catalog c
               JOIN canonical_races r ON r.race_id = c.race_id
               WHERE r.season = 1950 AND r.round = 2 AND c.session_type = 'RACE'"""
        ).fetchone()
        conn.close()
        assert row["stints_availability"] == "UNAVAILABLE"
        assert row["weather_availability"] == "UNAVAILABLE"
        assert row["race_control_availability"] == "UNAVAILABLE"


# -- engineering benchmarks ----------------------------------------------------


@requires_db
@requires_bahrain_cache
class TestEngineeringBenchmarks:
    def test_all_benchmarks_verdict_or_pass(self):
        from racewise.data.historical.engineering_benchmarks import run_engineering_benchmarks

        res = run_engineering_benchmarks()
        for name in ("q1_degradation", "q2_strategy_vs_pace", "q3_pit_windows",
                     "q4_weather_pace", "q5_traffic_vs_degradation"):
            assert res[name].get("verdict") in ("PASS", "INSUFFICIENT_EVIDENCE"), name
        assert res["q1_degradation"]["verdict"] == "PASS"
        assert res["deep_2023_bahrain"]["status"] == "PASS"

    def test_counterfactual_is_deterministic(self):
        from racewise.data.historical.engineering_benchmarks import run_engineering_benchmarks

        res = run_engineering_benchmarks()
        cf = res["deep_2023_bahrain"]["counterfactual"]
        assert cf["tool"].startswith("simulate_pit_timing")
        assert isinstance(cf["predicted_delta_s"], (int, float))
        assert cf["assumptions"]

    def test_insufficient_evidence_when_no_stints(self):
        """1950 has no FastF1 stints: benchmark must answer INSUFFICIENT_EVIDENCE."""
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.data.historical.engineering_benchmarks import EngineeringBenchmarks

        bench = EngineeringBenchmarks(get_canonical_queries(str(DB_PATH)), season=1950, round_num=2)
        out = bench.q1_degradation_comparison("giuseppe-farina", "luigi-fagioli")
        assert out["verdict"] == "INSUFFICIENT_EVIDENCE"


# -- cross-provider FastF1 vs F1DB --------------------------------------------


@requires_db
class TestFastF1CrossValidator:
    def test_2023_bahrain_validation_structure(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.data.historical.cross_provider import FastF1CrossValidator

        report = FastF1CrossValidator(get_canonical_queries(str(DB_PATH))).validate_race(2023, 1)
        assert report["providers"] == ["f1db", "fastf1"]
        assert set(report["summary"]) == {"MATCH", "MISMATCH", "NOT_AVAILABLE"}
        assert report["total_compared"] >= 4
        # Driver sets must MATCH after season-scoped code resolution
        driver_cmp = next(c for c in report["comparisons"] if c["field"] == "driver_set")
        assert driver_cmp["classification"] == "MATCH"
        # Every mismatch preserves a note explaining both values
        for m in report["mismatches"]:
            assert m.get("note")

    def test_position_semantics_documented(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.data.historical.cross_provider import FastF1CrossValidator

        report = FastF1CrossValidator(get_canonical_queries(str(DB_PATH))).validate_race(2023, 1)
        pos = next(c for c in report["comparisons"] if c["field"].startswith("finishing_positions"))
        assert pos["classification"] in ("MATCH", "MISMATCH")


# -- MCP tools (in-process registry check) -------------------------------------


@requires_db
class TestModernTools:
    def test_new_tools_registered_and_contracted(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.tools.historical import build_historical_registry

        registry = build_historical_registry(get_canonical_queries(str(DB_PATH)))
        for name in ("get_historical_stints", "get_historical_weather", "get_historical_race_control"):
            assert name in registry._tools
            tool = registry._tools[name]
            assert tool.spec.name == name
            assert tool.spec.input_schema["type"] == "object"
            assert tool.spec.output_schema["type"] == "object"

    def test_weather_tool_boolean_rainfall(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.tools.historical import build_historical_registry

        registry = build_historical_registry(get_canonical_queries(str(DB_PATH)))
        out = registry._tools["get_historical_weather"].execute(season=2023, round=1)
        assert out["available"] is True
        assert all(o["rainfall"] is None or isinstance(o["rainfall"], bool) for o in out["observations"])

    def test_stints_tool_1950_unavailable(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.tools.historical import build_historical_registry

        registry = build_historical_registry(get_canonical_queries(str(DB_PATH)))
        out = registry._tools["get_historical_stints"].execute(season=1950, round=2)
        assert out["available"] is False
        assert out["n_stints"] == 0
