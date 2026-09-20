"""Phase 6B CI gate tests.

Deterministic gates that run on fixtures and (when present) the local
canonical store. These are the CI layer: no network downloads, no large
datasets. Large-data validation remains a separate manually-triggered run.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO / "tests" / "fixtures" / "canonical"
DB_PATH = REPO / "data" / "canonical" / "canonical.db"

requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

# Regression hash registry (Phase 5.5B/6A verified values).
# A hash change is NOT automatically a failure, but it MUST be a conscious,
# documented update to this registry.
EXPECTED_GOLDEN_HASHES = {
    "golden_1950_british_gp": "1487764bf78a3c38",
    "golden_2000_australian_gp": "43434c839bd05315",
    "golden_2023_bahrain_gp": "749879bc5f037359",
    "cross_provider_1950_british_gp": "276591d5d8c104bd",
}


# -- fixtures ------------------------------------------------------------------


class TestGoldenFixtures:
    def test_fixtures_exist_and_are_small(self):
        paths = sorted(FIXTURE_DIR.glob("golden_*.json"))
        assert len(paths) >= 3
        for p in paths:
            assert p.stat().st_size < 200_000, f"{p.name} too large for CI fixture"

    @pytest.mark.parametrize(
        "name,era",
        [
            ("golden_1950_british", "1950s"),
            ("golden_2000_australian", "2000s"),
            ("golden_2023_bahrain", "2020s"),
        ],
    )
    def test_fixture_capability_profile(self, name, era):
        """Each era's fixture must show its REAL capability profile."""
        payload = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert payload["session"]["session_type"] == "RACE"
        if name == "golden_1950_british":
            assert len(payload["results"]) > 0
            assert len(payload["pit_stops"]) == 0   # pre-1994: UNAVAILABLE, not zero
            assert len(payload["stints"]) == 0      # FastF1 cannot cover 1950
            assert len(payload["weather"]) == 0
        if name == "golden_2000_australian":
            assert len(payload["pit_stops"]) > 0
            assert len(payload["stints"]) == 0
        if name == "golden_2023_bahrain":
            assert len(payload["stints"]) > 0
            assert len(payload["weather"]) > 0
            assert len(payload["race_control"]) > 0
            assert all(r["source_provider"] == "fastf1" for r in payload["stints"])

    def test_fixture_ids_deterministic(self):
        """Re-deriving the id from source keys must reproduce the stored id."""
        payload = json.loads((FIXTURE_DIR / "golden_2023_bahrain.json").read_text(encoding="utf-8"))
        session_id = payload["session"]["session_id"]
        race_id = payload["session"]["race_id"]
        expected = hashlib.sha1(f"f1db:session:{race_id}:RACE".encode()).hexdigest()[:16]
        assert session_id == expected


# -- canonical determinism / provenance gates (fixture-level) -------------------


class TestCanonicalizerDeterminism:
    def test_ids_derive_from_source_keys_not_randomness(self):
        """Two canonicalizer instantiations must produce identical ids."""
        from racewise.data.historical.f1db_canonical import CanonicalStore, F1DBCanonicalizer

        store_a = CanonicalStore(str(DB_PATH)) if DB_PATH.exists() else None
        if store_a is None:
            pytest.skip("canonical DB not present")
        canon = F1DBCanonicalizer(store_a)
        race_id = canon.race_id(2023, 1)
        assert race_id == canon.race_id(2023, 1)
        assert canon.session_id(race_id, "RACE") == canon.session_id(race_id, "RACE")
        # and they match the live store
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT session_id FROM canonical_sessions WHERE session_id = ?",
            (canon.session_id(race_id, "RACE"),),
        ).fetchone()
        conn.close()
        assert row is not None


# -- no-fabrication gate ---------------------------------------------------------


NO_FABRICATION_PATTERNS = [
    (r"year\s*>=\s*20\d{2}", "year-based availability threshold"),
    (r"year\s*>\s*20\d{2}", "year-based availability threshold"),
    (r"default_weather|synthetic_stint|estimated_lap|fake_telemetry", "fabrication helper"),
]


class TestNoFabricationGate:
    @pytest.mark.parametrize("path", [
        "src/racewise/data/historical/f1db_canonical.py",
        "src/racewise/data/historical/fastf1_canonical.py",
        "src/racewise/data/historical/scaling.py",
        "src/racewise/data/historical/catalog_api.py",
        "src/racewise/data/historical/validators.py",
        "src/racewise/data/historical/engineering_benchmarks.py",
    ])
    def test_no_year_heuristics_or_fabrication_in_data_paths(self, path):
        src = (REPO / path).read_text(encoding="utf-8")
        for pattern, label in NO_FABRICATION_PATTERNS:
            matches = re.findall(pattern, src)
            assert not matches, f"{path}: {label} found: {matches[:3]}"

    def test_telemetry_default_off(self):
        from racewise.data.historical.telemetry_policy import TelemetryPolicy, TelemetrySessionStatus

        policy = TelemetryPolicy()
        assert policy.enabled is False  # default OFF
        assert policy.validate() == []

    def test_telemetry_capability_never_claims_available(self):
        from racewise.data.historical.telemetry_policy import (
            TelemetryCapability,
            TelemetrySessionStatus,
        )

        cap = TelemetryCapability(session_id="test")
        assert cap.available is False
        assert cap.describe()["status"] == TelemetrySessionStatus.NOT_INGESTED.value


# -- availability contradiction gate (live store) ---------------------------------


@requires_db
class TestAvailabilityConsistency:
    def test_flags_match_counts(self):
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        contradictions = 0
        for table, count_col, avail_col in (
            ("canonical_results", "results_count", "results_availability"),
            ("canonical_stints", "stints_count", "stints_availability"),
            ("canonical_weather", "weather_count", "weather_availability"),
            ("canonical_race_control", "race_control_count", "race_control_availability"),
        ):
            bad = conn.execute(
                f"""SELECT COUNT(*) FROM canonical_session_catalog
                    WHERE ({count_col} > 0 AND {avail_col} != 'AVAILABLE')
                       OR ({count_col} = 0 AND {avail_col} = 'AVAILABLE')"""
            ).fetchone()[0]
            contradictions += bad
        conn.close()
        assert contradictions == 0, f"{contradictions} availability contradictions"


# -- regression hashes ------------------------------------------------------------


@requires_db
class TestRegressionHashes:
    def test_golden_hashes_match_registry(self):
        """Golden hashes must equal the deliberate registry values."""
        import logging

        logging.disable(logging.WARNING)
        from racewise.data.historical.golden_investigations import run_all_golden_investigations

        results = run_all_golden_investigations()
        for name, expected in EXPECTED_GOLDEN_HASHES.items():
            inv = results[name]
            payload = {
                k: v
                for k, v in inv.items()
                if "timestamp" not in k.lower() and "generated" not in k.lower() and "created" not in k.lower()
            }
            actual = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            assert actual == expected, (
                f"{name} hash changed: {expected} -> {actual}. "
                "If intentional, document why and update EXPECTED_GOLDEN_HASHES deliberately."
            )


# -- catalog API gates -------------------------------------------------------------


@requires_db
class TestCatalogAPIGates:
    def test_pagination_caps_and_counts(self):
        from racewise.data.historical.catalog_api import get_catalog_api

        api = get_catalog_api(str(DB_PATH))
        r = api.list_sessions(page_size=500)  # above MAX_PAGE_SIZE
        assert r["page_size"] <= 100
        assert r["total"] > 5000  # full catalog present
        page1 = api.list_sessions(page=1, page_size=50)
        page2 = api.list_sessions(page=2, page_size=50)
        ids1 = {s["session_id"] for s in page1["sessions"]}
        ids2 = {s["session_id"] for s in page2["sessions"]}
        assert not (ids1 & ids2), "pagination must not overlap"

    def test_capability_filter_returns_only_available(self):
        from racewise.data.historical.catalog_api import get_catalog_api

        api = get_catalog_api(str(DB_PATH))
        r = api.list_sessions(capability="stints", page_size=100)
        assert r["total"] >= 1
        for s in r["sessions"]:
            assert s["capabilities"]["stints"]["availability"] == "AVAILABLE"

    def test_unknown_capability_rejected(self):
        from racewise.data.historical.catalog_api import get_catalog_api

        api = get_catalog_api(str(DB_PATH))
        with pytest.raises(ValueError):
            api.list_sessions(capability="hoverboards")
