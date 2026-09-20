"""Phase 6F Q8 benchmark tests: evidence-fusion semantics across seasons.

Asserts deterministic semantics (source coverage, formal verdicts, premise
gate, determinism) on real canonical data. Skips when the DB is absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")


@pytest.fixture(scope="module")
def q8():
    from racewise.data.historical.canonical_queries import CanonicalQueries
    from racewise.data.historical.q8_benchmarks import run_q8

    return run_q8(CanonicalQueries())


@requires_db
class TestQ8Matrix:
    def test_multi_season_multi_circuit_coverage(self, q8):
        valid = [r for r in q8["matrix"] if r["status"] != "UNAVAILABLE"]
        assert len(valid) >= 6, f"expected >=6 valid matrix rows, got {len(valid)}"
        seasons = {r["season"] for r in valid}
        assert seasons >= {2022, 2023, 2024, 2025}

    def test_q8_1_sector_evidence_fused(self, q8):
        for r in q8["matrix"]:
            if r["status"] == "UNAVAILABLE":
                continue
            assert "canonical_sector_split" in r["sources"], r

    def test_q8_2_tyre_stint_evidence_fused(self, q8):
        for r in q8["matrix"]:
            if r["status"] == "UNAVAILABLE":
                continue
            assert "canonical_stint_state" in r["sources"], r

    def test_q8_3_race_control_evidence_fused(self, q8):
        for r in q8["matrix"]:
            if r["status"] == "UNAVAILABLE":
                continue
            assert "canonical_race_control_lap_overlap" in r["sources"], r

    def test_q8_4_weather_evidence_fused(self, q8):
        for r in q8["matrix"]:
            if r["status"] == "UNAVAILABLE":
                continue
            assert "canonical_weather_lap_window" in r["sources"], r

    def test_q8_5_drs_evidence_fused(self, q8):
        for r in q8["matrix"]:
            if r["status"] == "UNAVAILABLE":
                continue
            assert "telemetry_drs_metric" in r["sources"], r

    def test_q8_6_contradictions_recorded_when_present(self, q8):
        valid = [r for r in q8["matrix"] if r["status"] != "UNAVAILABLE"]
        deficit = [r for r in valid if r["observed_delta_s"] > 0]
        assert deficit, "matrix must contain at least one deficit comparison"
        assert any(r["n_contradicting"] > 0 for r in deficit), \
            "falsification-first: contradicting evidence must surface somewhere"
        # and at least one deficit row must carry a non-supported verdict
        statuses = [s for r in deficit for s in r["hypotheses"].values()]
        assert any(s in ("CONTRADICTED", "NOT_SUPPORTED") for s in statuses)

    def test_q8_7_deficit_premise_gate(self, q8):
        for r in q8["matrix"]:
            if r["status"] == "UNAVAILABLE" or r["observed_delta_s"] is None:
                continue
            if r["observed_delta_s"] <= 0:
                assert all(s == "NOT_TESTABLE" for s in r["hypotheses"].values()), \
                    f"{r['season']} R{r['round']}: deficit hypotheses must be " \
                    "NOT_TESTABLE when B was not slower"

    def test_q8_8_multi_source_investigation(self, q8):
        for r in q8["matrix"]:
            if r["status"] == "UNAVAILABLE":
                continue
            assert len(r["sources"]) >= 4, f"too few sources fused: {r}"
            assert len(r["hypotheses"]) == 6
            assert r["residual_class"] in (
                "EXPLAINED_BY_SPEED_TRACES", "PARTIALLY_EXPLAINED", "UNRESOLVED")

    def test_q8_9_replay_determinism(self, q8):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.q8_benchmarks import run_q8

        again = run_q8(CanonicalQueries())
        assert json.dumps(q8, sort_keys=True) == json.dumps(again, sort_keys=True)


@requires_db
class TestQ8NegativeControls:
    def test_1950_no_matrix_row(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.q8_benchmarks import _lap_evidence

        assert _lap_evidence(CanonicalQueries(), 1950, 5) is None

    def test_2018_no_telemetry(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.q8_benchmarks import _lap_evidence

        assert _lap_evidence(CanonicalQueries(), 2018, 1) is None

    def test_absent_lap(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(CanonicalQueries(), 2023, 1, "max-verstappen",
                              "sergio-perez", 999)
        assert f["status"] == "UNAVAILABLE"

    def test_missing_driver(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(CanonicalQueries(), 2023, 1, "nobody-here",
                              "max-verstappen", 57)
        assert f["status"] == "UNAVAILABLE"
