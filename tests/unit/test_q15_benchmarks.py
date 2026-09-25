"""Phase 6M Q15 benchmark tests: cross-race evidence semantics.

The full Q15 matrix (4 pair/season cases x 3 pattern roles x replay) is a
documentation measurement; the suite runs a bounded single-case Q15 with
MCP verification so the whole suite stays fast. All assertions are on
deterministic semantics over real canonical data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

AGG_STATES = {"CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED", "VARIABLE",
              "CONTRADICTORY", "CONSISTENTLY_NOT_SUPPORTED",
              "INSUFFICIENT_EVIDENCE"}
RESIDUAL_STATES = {"RESIDUAL_STABLE", "RESIDUAL_INCREASING",
                   "RESIDUAL_DECREASING", "RESIDUAL_REVERSAL",
                   "RESIDUAL_UNRESOLVED", "INSUFFICIENT_EVIDENCE"}


@pytest.fixture(scope="module")
def q15_report():
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.q15_benchmarks import run_q15

    return run_q15(
        get_canonical_queries(),
        matrix=[{"label": "ver_per", "driver_a": "max-verstappen",
                 "driver_b": "sergio-perez", "seasons": [2022, 2023]}],
        include_mcp=True,
    )


@requires_db
class TestQ15Matrix:
    def test_all_roles_valid_with_replay(self, q15_report):
        for m in q15_report["matrix"]:
            for role, blk in m["investigations"].items():
                assert blk["status"] == "VALID", blk
                assert blk["replay_identical"] is True
                assert blk["output_hash"]

    def test_roles_span_distinct_real_patterns(self, q15_report):
        for m in q15_report["matrix"]:
            ids = {blk["pattern_id"]
                   for blk in m["investigations"].values()}
            assert len(ids) == 3  # each role resolves to a distinct pattern

    def test_aggregate_states_in_vocabulary(self, q15_report):
        for m in q15_report["matrix"]:
            for blk in m["investigations"].values():
                assert set(blk["aggregate_states"].values()) <= AGG_STATES
                assert set(blk["consistency_states"].values()) <= {
                    "CONSISTENT", "VARIABLE", "CONTRADICTORY", "UNRESOLVED"}
                assert blk["residual_pattern"] in RESIDUAL_STATES
                assert blk["sensitivity_status"] in (
                    "VALID", "INSUFFICIENT_EVIDENCE", "TELEMETRY_UNAVAILABLE")
                assert blk["provenance_chain"][-1] == "6M"

    def test_contradictions_preserved_when_present(self, q15_report):
        for m in q15_report["matrix"]:
            blk = m["investigations"]["most_contradictory"]
            if blk["contradiction_hypotheses"]:
                for h in blk["contradiction_hypotheses"]:
                    assert blk["falsification_statuses"][h] == \
                        "FALSIFICATION_PRESENT"

    def test_provenance_and_pool_measured(self, q15_report):
        for m in q15_report["matrix"]:
            pool = m["pattern_pool"]
            assert pool["pattern_count"] >= 1
            assert isinstance(pool["measured"]["most_informative_cells"], int)


@requires_db
class TestQ15NegativeControls:
    def test_explicit_invalid_states(self, q15_report):
        nc = q15_report["negative_controls"]
        assert nc["same_driver"] == "INVALID"
        assert nc["max_occurrences_oob"] == "INVALID"

    def test_mcp_boundary(self, q15_report):
        mcp = q15_report["mcp"]
        assert mcp["tool_registered"] is True
        assert mcp["bound_oob_rejected"] is True
        assert mcp["historical_tool_count"] == 23
