"""Phase 6G Q9 benchmark tests: stint evidence semantics across seasons.

Asserts deterministic semantics on real canonical data (skipped when the DB
is absent): pattern classification, hypothesis-evolution validity, residual
conservation, tyre-consistency honesty, MCP presence and replay determinism.
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
def q9():
    from racewise.data.historical.canonical_queries import CanonicalQueries
    from racewise.data.historical.q9_benchmarks import run_q9

    return run_q9(CanonicalQueries(), include_mcp=True)


@requires_db
class TestQ9Matrix:
    def test_multi_season_coverage(self, q9):
        seasons = {r["season"] for r in q9["matrix"]}
        assert seasons >= {2021, 2022, 2023}
        assert len(q9["matrix"]) >= 7

    def test_valid_rows_with_real_trends(self, q9):
        valid = [r for r in q9["matrix"] if r.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")]
        assert len(valid) >= 4, f"expected >=4 valid rows, got {len(valid)}"
        with_trend = [r for r in valid if r["pattern"] in ("WIDENING", "NARROWING", "STABLE")]
        assert with_trend, "at least one stint must yield a classifiable trend"

    def test_pattern_classification_matches_slope(self, q9):
        for r in q9["matrix"]:
            if r.get("pattern") in ("WIDENING", "NARROWING", "STABLE"):
                assert r["slope_s_per_stint_lap"] is not None
                s = r["slope_s_per_stint_lap"]
                expected = "STABLE" if abs(s) <= 0.02 else ("WIDENING" if s > 0 else "NARROWING")
                assert r["pattern"] == expected

    def test_q9_4_telemetry_trend_persistence(self, q9):
        valid = [r for r in q9["matrix"]
                 if r.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
                 and r.get("valid_laps", 0) >= 3]
        assert valid, "need at least one stint with >=3 valid laps"
        assert any(r["metric_trends_valid"] for r in valid), \
            "metric trend blocks must be VALID for sufficiently covered stints"

    def test_q9_5_tyre_consistency_honest(self, q9):
        for r in q9["matrix"]:
            if "tyre_consistency" not in r:
                continue
            tc = r["tyre_consistency"]
            assert tc["assessment"]
            if tc["pattern"] == "WIDENING" and \
                    tc["tyre_summary"] in ("CONTRADICTED_OVER_TIME", "NOT_SUPPORTED"):
                assert tc["assessment"].startswith("NOT_CONSISTENT"), \
                    "widening gap with contradicted tyre evidence must not be attributed to tyres"

    def test_q9_6_context_transitions_structured(self, q9):
        for r in q9["matrix"]:
            if "context_transitions" in r:
                assert isinstance(r["context_transitions"], int) and r["context_transitions"] >= 0

    def test_q9_7_contradictory_hypothesis_present(self, q9):
        assert any(r.get("contradictory_present") for r in q9["matrix"]), \
            "falsification-first: at least one stint must surface a contradicted hypothesis"

    def test_q9_8_insufficient_common_laps_reported(self, q9):
        """Thin stints are reported honestly when they exist.

        Phase 6S widened the 6D telemetry coverage (12 -> 24 laps/driver),
        so the fixed sampling matrix can legitimately contain no thin
        stint anymore; the invariant under test is the reporting rule:
        every matrix entry with <2 comparable laps must be flagged
        trend-insufficient or honestly INSUFFICIENT_EVIDENCE.
        """
        for r in q9["matrix"]:
            if (r.get("valid_laps") or 0) < 2 and \
                    r.get("status") in ("VALID_COMPARISON",
                                        "VALID_WITH_CAVEATS"):
                assert r.get("trend_insufficient") or \
                    r.get("pattern") == "INSUFFICIENT_EVIDENCE", \
                    f"thin stint reported as trended: {r}"
        thin = [r for r in q9["matrix"] if r.get("trend_insufficient")
                or r.get("pattern") == "INSUFFICIENT_EVIDENCE"
                or r.get("status") == "INSUFFICIENT_EVIDENCE"]
        # honesty invariant: thin entries never carry a trend pattern
        for r in thin:
            assert r.get("pattern") not in ("WIDENING", "NARROWING", "STABLE")

    def test_q9_9_residual_conservation_everywhere(self, q9):
        for r in q9["matrix"]:
            if "residual_conservation_ok" in r:
                assert r["residual_conservation_ok"], \
                    f"{r['season']} R{r['round']} s{r['stint']}: conservation identity violated"

    def test_q9_10_mcp_tool_registered(self, q9):
        assert q9.get("mcp_tool_registered") is True

    def test_q9_11_replay_determinism(self, q9):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.q9_benchmarks import run_q9

        again = run_q9(CanonicalQueries(), include_mcp=False)
        assert json.dumps(q9["matrix"], sort_keys=True) == \
            json.dumps(again["matrix"], sort_keys=True)


@requires_db
class TestQ9NegativeControls:
    def test_1950_not_in_matrix_and_unavailable(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(CanonicalQueries(), 1950, 5, "giuseppe-farina",
                                "luigi-fagioli", 1)
        assert f["status"] == "UNAVAILABLE"

    def test_absent_stint(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(CanonicalQueries(), 2023, 1, "max-verstappen",
                                "sergio-perez", 99)
        assert f["status"] == "UNAVAILABLE"

    def test_counterfactual_gate_in_stint_output(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(CanonicalQueries(), 2022, 4, "max-verstappen",
                                "sergio-perez", 2)
        assert "UNSUPPORTED" in f["counterfactual_gate"]
