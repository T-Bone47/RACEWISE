"""Phase 6N Q16 benchmark tests: engineering investigation semantics.

The full Q16 matrix (8 goldens x replay) is a documentation measurement;
the suite runs a bounded set (the two telemetry-rich golden investigations
plus the telemetry-poor control) so the suite stays fast. All assertions
are on deterministic semantics over real canonical data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")


@pytest.fixture(scope="module")
def q16_report():
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.q16_benchmarks import run_q16

    return run_q16(
        get_canonical_queries(),
        goldens=[g for g in __import__(
            "racewise.data.historical.q16_benchmarks",
            fromlist=["GOLDENS"]).GOLDENS
            if g["label"] in ("GOLDEN_01_lap_performance",
                              "GOLDEN_02_stint_performance",
                              "GOLDEN_08_telemetry_poor_race_gap")],
        include_mcp=True,
    )


@requires_db
class TestQ16Matrix:
    def test_goldens_valid_with_replay(self, q16_report):
        for m in q16_report["matrix"]:
            assert m["status"] == "VALID", m
            assert m["replay_identical"] is True
            assert m["output_hash"]

    def test_conclusion_states_in_closed_vocabulary(self, q16_report):
        allowed = {"SUPPORTED_BY_AVAILABLE_EVIDENCE", "MIXED_EVIDENCE",
                   "INSUFFICIENT_EVIDENCE", "NOT_TESTABLE", "UNAVAILABLE"}
        for m in q16_report["matrix"]:
            assert m["conclusion_state"] in allowed

    def test_hypothesis_states_in_closed_vocabulary(self, q16_report):
        allowed = {"SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED",
                   "CONTRADICTED", "NOT_TESTABLE", "INSUFFICIENT_EVIDENCE",
                   "MIXED_EVIDENCE", "NOT_REQUESTED"}
        for m in q16_report["matrix"]:
            assert set(m["hypothesis_states"].values()) <= allowed

    def test_stint_golden_reaches_counterfactual_execution(self, q16_report):
        m = next(m for m in q16_report["matrix"]
                 if m["label"] == "GOLDEN_02_stint_performance")
        assert m["evidence_count"] > 0
        assert m["counterfactuals"], "expected an executed 6I counterfactual"
        assert all(c["claim_class"] == "MODELLED"
                   for c in m["counterfactuals"])

    def test_telemetry_poor_golden_is_honest(self, q16_report):
        m = next(m for m in q16_report["matrix"]
                 if m["label"] == "GOLDEN_08_telemetry_poor_race_gap")
        assert m["evidence_count"] == 0
        assert m["conclusion_state"] == "INSUFFICIENT_EVIDENCE"

    def test_no_ranking_or_scoring_in_report(self, q16_report):
        blob = repr(q16_report)
        for banned in ("best_explanation", "most_likely", "winner",
                       "confidence_score"):
            assert banned not in blob


@requires_db
class TestQ16NegativeControls:
    def test_invalid_states(self, q16_report):
        nc = q16_report["negative_controls"]
        assert nc["same_driver"] == "INVALID"
        assert nc["unknown_question_type"] == "INVALID"
        assert nc["season_below_bounds"] == "INVALID"
        assert nc["round_above_bounds"] == "INVALID"
        assert nc["max_evidence_items_oob"] == "INVALID"
        assert nc["missing_pattern_id"] == "INVALID"

    def test_unavailable_states(self, q16_report):
        nc = q16_report["negative_controls"]
        assert nc["missing_race"] == "UNAVAILABLE"
        assert nc["lap_beyond_race"] == "UNAVAILABLE"
        assert nc["unknown_pattern_id_collection"] == "UNAVAILABLE"
        assert nc["unknown_pattern_id_conclusion"] == "UNAVAILABLE"
        assert nc["unknown_pattern_id_evidence"] == 0

    def test_counterfactual_negatives(self, q16_report):
        cf = q16_report["negative_controls"]["counterfactual"]
        assert cf["race_level_structurally_ineligible"] is True
        assert cf["stint_scope_kind_is_speed_profile"] is True
        assert cf["non_speed_refused_by_6i"] is True

    def test_mcp_boundary(self, q16_report):
        mcp = q16_report["mcp"]
        assert mcp["tool_registered"] is True
        assert mcp["same_driver_rejected"] is True
        assert mcp["historical_tool_count"] == 23
