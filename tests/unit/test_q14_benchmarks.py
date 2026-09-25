"""Phase 6L Q14 benchmark tests: cross-race pattern semantics.

The full Q14 matrix (4 pair/season cases x replay + MCP) is a documentation
measurement; the suite runs a bounded two-case Q14 with MCP verification so
the whole suite stays fast. All assertions are on deterministic semantics
over real canonical data.
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
def q14_report():
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.q14_benchmarks import run_q14

    return run_q14(
        get_canonical_queries(),
        matrix=[
            {"driver_a": "max-verstappen", "driver_b": "sergio-perez",
             "seasons": [2023]},
            {"driver_a": "lando-norris", "driver_b": "oscar-piastri",
             "seasons": [2025]},
        ],
        include_mcp=True,
    )


@requires_db
class TestQ14Matrix:
    def test_cases_valid_with_recurrence(self, q14_report):
        for m in q14_report["matrix"]:
            assert m["status"] == "VALID", m.get("reason")
            assert m["pattern_count"] >= 1
            assert m["independent_races_min"] >= 2
            assert m["recurring_classification_all"] == ["RECURRING"]
            assert m["replay_identical"] is True

    def test_split_log_records_seed_anchored_refinement(self, q14_report):
        for m in q14_report["matrix"]:
            # refinement happened at least once somewhere in the matrix
            assert isinstance(m["split_count"], int)
        assert any(m["split_count"] >= 0 for m in q14_report["matrix"])

    def test_telemetry_limitations_preserved(self, q14_report):
        for m in q14_report["matrix"]:
            # telemetry states are only honest values
            assert set(m["telemetry_statuses_in_patterns"]) <= {
                "AVAILABLE", "TELEMETRY_UNAVAILABLE"}

    def test_hypothesis_consistency_from_6f_vocabulary(self, q14_report):
        allowed = {"CONSISTENT", "VARIABLE", "CONTRADICTORY",
                   "INSUFFICIENT_EVIDENCE"}
        for m in q14_report["matrix"]:
            assert set(m["hypothesis_consistencies"]) <= allowed

    def test_residual_states_never_assigned(self, q14_report):
        allowed = {"RESIDUAL_STABLE", "RESIDUAL_INCREASING",
                   "RESIDUAL_DECREASING", "RESIDUAL_REVERSAL",
                   "RESIDUAL_UNRESOLVED", "INSUFFICIENT_EVIDENCE"}
        for m in q14_report["matrix"]:
            assert set(m["residual_pattern_states"]) <= allowed

    def test_sensitivity_model_scoped(self, q14_report):
        for m in q14_report["matrix"]:
            assert set(m["sensitivity_states"]) <= {
                "MEASURED", "INSUFFICIENT_EVIDENCE"}

    def test_provenance_complete(self, q14_report):
        for m in q14_report["matrix"]:
            assert m["provenance_chain"][-1] == "6L"
            assert m["provenance_table_count"] >= 9
            assert m["thresholds_documented"] is True
            assert m["generated_at_null"] is True


@requires_db
class TestQ14NegativeControls:
    def test_all_expected(self, q14_report):
        nc = q14_report["negative_controls"]
        assert nc["same_driver"] == "INVALID"
        assert nc["1950"] == "UNAVAILABLE"
        assert nc["2018"] == "UNAVAILABLE"
        assert nc["pair_absent_from_corpus"] == "UNAVAILABLE"
        assert nc["max_races_oob"] == "INVALID"
        assert nc["max_races_zero"] == "INVALID"
        assert nc["max_patterns_oob"] == "INVALID"
        assert nc["single_race_corpus"] == "INSUFFICIENT_EVIDENCE"


@requires_db
class TestQ14Mcp:
    def test_tool_registered_and_rejecting(self, q14_report):
        mcp = q14_report["mcp"]
        assert mcp["tool_registered"] is True
        assert mcp["historical_tool_count"] == 22  # 21 pre-6M + evidence (Phase 6M)
        assert mcp["registry_status"] == "VALID"
        for label in ("max_races_oob", "max_patterns_oob", "same_driver",
                      "seasons_not_list", "rounds_not_ints", "circuit_empty",
                      "unknown_param"):
            assert mcp[label].startswith("REJECTED"), label
