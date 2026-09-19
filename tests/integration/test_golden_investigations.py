"""Phase 5.5B golden investigation tests: real canonical data, no fabrication.

Golden races:
- 1950 British GP: identity + classification coverage, modern data UNAVAILABLE
- 2000 Australian GP: middle era, pit stops AVAILABLE, compounds UNAVAILABLE
- 2023 Bahrain GP: deep modern coverage + deterministic counterfactual

Tests use the real canonical store (built from the local F1DB release) and the
real FastF1 cache. If the canonical DB has not been ingested yet, tests skip
with an explicit reason rather than fabricating data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "canonical" / "canonical.db"
FASTF1_CACHE = ROOT / ".fastf1-cache"

pytest.importorskip("racewise")

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.cross_provider import CrossProviderValidator
from racewise.data.historical.golden_investigations import (
    investigate_1950_british_gp,
    investigate_2000_australian_gp,
    investigate_2023_bahrain_gp,
)

requires_db = pytest.mark.skipif(
    not DB_PATH.exists(),
    reason="canonical DB not ingested yet (run: python -m racewise.data.historical.cli f1db)",
)


@pytest.fixture(scope="module")
def queries():
    return CanonicalQueries(str(DB_PATH))


@requires_db
def test_golden_1950_british_gp(queries):
    report = investigate_1950_british_gp(queries)
    assert report["status"] == "PASS"
    # Identity resolution
    assert report["winner"] is not None
    assert report["winner"]["driver"] == "Emilio Giuseppe Farina"
    assert report["winner"]["constructor"] == "Alfa Romeo"
    assert report["counts"]["results"] >= 20
    # Evidence must explicitly declare modern capabilities UNAVAILABLE
    unavailable = {e["id"] for e in report["evidence"] if e["type"] == "UNAVAILABLE"}
    assert {"E6", "E7", "E8", "E9", "E10"} <= unavailable  # pits, stints, weather, rc, telemetry
    facts = {e["id"] for e in report["evidence"] if e["type"] == "FACT"}
    assert {"E1", "E2"} <= facts


@requires_db
def test_golden_2000_australian_gp(queries):
    report = investigate_2000_australian_gp(queries)
    assert report["status"] == "PASS"
    assert report["winner"]["driver"] == "Michael Schumacher"
    assert report["counts"]["results"] >= 20
    assert report["counts"]["pit_stops"] > 0, "2000 must have pit stop data (era 1994+)"
    # Middle era: pits AVAILABLE, compounds/telemetry UNAVAILABLE
    unavailable = {e["id"] for e in report["evidence"] if e["type"] == "UNAVAILABLE"}
    assert "E6" in unavailable  # stints
    assert "E9" in unavailable  # telemetry


@requires_db
def test_golden_2023_bahrain_gp_canonical(queries):
    report = investigate_2023_bahrain_gp(queries)
    assert report["status"] == "PASS"
    assert report["winner"]["driver"] == "Max Emilian Verstappen"
    assert report["counts"]["results"] == 20
    assert report["counts"]["qualifying"] == 20
    assert report["counts"]["pit_stops"] > 40
    # Without FastF1 context, telemetry must be declared UNAVAILABLE, not faked
    telemetry = next(e for e in report["evidence"] if e["id"] == "E6")
    assert telemetry["type"] == "UNAVAILABLE"


@requires_db
@pytest.mark.skipif(
    not FASTF1_CACHE.exists(),
    reason="FastF1 cache not populated for 2023 Bahrain",
)
def test_golden_2023_bahrain_deep_data_with_counterfactual(queries):
    from racewise.data.fastf1_adapter import FastF1Adapter
    from racewise.tools.implementations import SessionContext

    ctx = SessionContext(FastF1Adapter(cache_dir=str(FASTF1_CACHE)), 2023, "Bahrain")
    report = investigate_2023_bahrain_gp(queries, fastf1_context=ctx)
    assert report["status"] == "PASS"
    # Full modern stack declared AVAILABLE
    facts = [e for e in report["evidence"] if e["type"] == "FACT"]
    assert any("1056 laps" in e["statement"] for e in facts)
    assert any("Weather" in e["statement"] for e in facts)
    assert any("Race control" in e["statement"] for e in facts)
    # Deterministic counterfactual produced by RACEWISE code (not invented)
    cf = report["counterfactual"]
    assert cf is not None
    assert cf["predicted_delta_s"] == -1.45  # deterministic: stable across runs
    assert cf["simulator_version"] == "1.0.0"
    assert len(cf["assumptions"]) >= 3
    assert "deterministic" in cf["provenance"]


@requires_db
def test_cross_provider_validation_1950(queries):
    """F1DB vs Jolpica (cached Ergast) for the 1950 British GP."""
    validator = CrossProviderValidator(queries)
    report = validator.validate_race(1950, 1)
    assert report["total_compared"] > 0
    # Finishing order mostly agrees between sources
    assert report["summary"]["MATCH"] > report["summary"]["MISMATCH"]
    # Disagreements preserved with both values, never merged
    for m in report["mismatches"]:
        assert m["value_a"] is not None or m["value_b"] is not None
        assert m["provider_a"] == "f1db" and m["provider_b"] == "jolpica"
    # The known Chiron laps discrepancy (24 in F1DB vs 26 in Ergast) must surface
    laps_mismatches = [m for m in report["mismatches"] if m["field"].startswith("laps[")]
    assert len(laps_mismatches) >= 1


@requires_db
def test_cross_provider_policy_documented(queries):
    validator = CrossProviderValidator(queries)
    report = validator.validate_race(1950, 1)
    assert "never silently merged" in report["resolution_policy"]
