"""Phase 6H Q10 benchmark tests: race-level gap decomposition semantics.

Asserts deterministic semantics on real canonical data (skipped when the DB
is absent) across the 2022-2025 race matrix.
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
def q10():
    from racewise.data.historical.canonical_queries import CanonicalQueries
    from racewise.data.historical.q10_benchmarks import run_q10

    return run_q10(CanonicalQueries(), include_mcp=True)


@requires_db
class TestQ10Matrix:
    def test_multi_season_multi_circuit_coverage(self, q10):
        valid = [r for r in q10["matrix"] if r.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")]
        assert len(valid) >= 4, f"expected >=4 valid race rows, got {len(valid)}"
        seasons = {r["season"] for r in valid}
        assert seasons >= {2022, 2023, 2024, 2025}

    def test_q10_13_official_vs_analytical_distinct_everywhere(self, q10):
        for r in q10["matrix"]:
            if "official_vs_analytical_distinct" in r:
                assert r["official_vs_analytical_distinct"] is True, \
                    f"{r['season']} R{r['round']}: official and analytical gaps must be distinct"

    def test_q10_5_multi_stint_races(self, q10):
        valid = [r for r in q10["matrix"] if r.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")]
        assert any(r["n_stint_segments"] >= 3 for r in valid)

    def test_q10_2_3_4_patterns_and_reversal(self, q10):
        patterns = [r.get("pattern") for r in q10["matrix"] if r.get("pattern")]
        assert any(p in ("WIDENING", "NARROWING", "MIXED") for p in patterns), \
            "at least one directional race pattern must be classified"
        assert any(r.get("reversal") for r in q10["matrix"]), \
            "at least one race must show a gap reversal across stints"

    def test_q10_6_pit_windows_observed_mechanism_unproven(self, q10):
        valid = [r for r in q10["matrix"] if r.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")]
        assert any(r["pit_windows"] > 0 for r in valid)
        assert all(r["pit_mechanism_unproven"] for r in valid if r["pit_windows"] > 0), \
            "pit mechanisms must remain INSUFFICIENT_EVIDENCE"

    def test_q10_7_race_control_windows_present(self, q10):
        # 2023 R1 (VSC) and 2025 R1 (multiple restrictions) must surface windows
        r2023 = next(r for r in q10["matrix"] if r["season"] == 2023)
        r2025 = next(r for r in q10["matrix"] if r["season"] == 2025)
        assert r2023["race_control_windows"] >= 1
        assert r2025["race_control_windows"] >= 1

    def test_q10_8_telemetry_supported_segments(self, q10):
        assert any(r.get("stint_evidence_trend_valid") for r in q10["matrix"]), \
            "at least one race must chain stint evidence with a VALID trend"

    def test_q10_9_telemetry_unavailable_segments_preserved(self, q10):
        # 2025 R1: stints 1-3 have no comparable telemetry laps - preserved,
        # never extrapolated
        r2025 = next(r for r in q10["matrix"] if r["season"] == 2025)
        assert any(p == "INSUFFICIENT_EVIDENCE" for p in r2025["segments"])
        assert r2025["residual_counts"]["non_comparable"] > 0

    def test_q10_10_residual_accumulation(self, q10):
        for r in q10["matrix"]:
            if "residual_counts" not in r:
                continue
            rc = r["residual_counts"]
            assert rc["comparable"] >= 0 and rc["non_comparable"] >= 0

    def test_q10_11_hypothesis_evolution(self, q10):
        valid = [r for r in q10["matrix"] if r.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")]
        for r in valid:
            assert len(r["hypothesis_summaries"]) == 6
        # falsification-first: contradictions must surface somewhere
        assert any(
            s in ("CONTRADICTED_OVER_TIME", "NOT_SUPPORTED")
            for r in valid for s in r["hypothesis_summaries"].values())

    def test_q10_12_mcp_tool_registered(self, q10):
        assert q10.get("mcp_tool_registered") is True

    def test_q10_14_replay_determinism(self, q10):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.q10_benchmarks import run_q10

        again = run_q10(CanonicalQueries(), include_mcp=False)
        assert json.dumps(q10["matrix"], sort_keys=True) == \
            json.dumps(again["matrix"], sort_keys=True)


@requires_db
class TestQ10NegativeControls:
    def test_1950_unavailable(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(CanonicalQueries(), 1950, 5, "giuseppe-farina",
                               "luigi-fagioli")
        assert f["status"] == "UNAVAILABLE"

    def test_counterfactual_gate_in_race_output(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(CanonicalQueries(), 2023, 1, "max-verstappen",
                               "sergio-perez")
        assert "UNSUPPORTED" in f["counterfactual_gate"]
