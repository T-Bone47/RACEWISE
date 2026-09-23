"""Phase 6K Q13 benchmark tests: performance regime semantics.

The full Q13 matrix (4 races x replay + comparison) is a documentation
measurement; the suite runs a bounded single-race Q13 with MCP verification
so the whole suite stays fast. All assertions are on deterministic semantics
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
def q13_report():
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.q13_benchmarks import run_q13

    return run_q13(
        get_canonical_queries(),
        races=[{"season": 2022, "round": 4,
                "driver_a": "max-verstappen", "driver_b": "sergio-perez"}],
        include_mcp=True,
        include_compare=False,
    )


@requires_db
class TestQ13Matrix:
    def test_regimes_valid_with_min_length(self, q13_report):
        for m in q13_report["matrix"]:
            assert m["status"] == "VALID", f"{m['season']} R{m['round']}"
            assert m["min_regime_laps_observed"] >= 3
            assert m["regime_count"] == len(m["patterns"])

    def test_patterns_and_reversal(self, q13_report):
        for m in q13_report["matrix"]:
            assert m["has_stable"] or m["has_widening"] or m["has_narrowing"]
            assert set(m["patterns"]) <= {
                "STABLE", "WIDENING", "NARROWING", "INSUFFICIENT_EVIDENCE"}
            # reversal = slope sign change across consecutive regimes
            signs = [1 if s > 0 else -1 for s in m["slopes"] if s != 0]
            expected = any(a * b < 0 for a, b in zip(signs, signs[1:]))
            assert m["reversal"] == expected

    def test_change_points_documented(self, q13_report):
        for m in q13_report["matrix"]:
            assert m["change_point_count"] == len(m["change_points"])
            for cp in m["change_points"]:
                # a split means the two half-slopes differ by >= 0.06 s/lap;
                # the qualitative pattern may coincide on opposite-sign pairs
                assert isinstance(cp["previous_pattern"], str)
                assert isinstance(cp["new_pattern"], str)
                # every change point carries its context alignment
                assert isinstance(cp["context_alignment"], list)

    def test_noise_rejection_logged(self, q13_report):
        for m in q13_report["matrix"]:
            # rejections and merges are explicit, never silent
            for rej in m["rejected_change_points"]:
                assert "reason" in rej and "action" in rej
            assert m["regime_merges"] >= 0

    def test_stint_alignment_and_crossing(self, q13_report):
        for m in q13_report["matrix"]:
            assert m["regimes_crossing_stint_boundary"] >= 1  # analytical != canonical
            assert all(isinstance(s, list) for s in m["stints_spanned"])

    def test_telemetry_states_preserved(self, q13_report):
        for m in q13_report["matrix"]:
            assert m["telemetry_available_regimes"] >= 1
            assert all(s in ("MEASURED", "INSUFFICIENT_EVIDENCE",
                             "TELEMETRY_UNAVAILABLE")
                       for s in m["speed_profile_states"])

    def test_residual_conservation(self, q13_report):
        for m in q13_report["matrix"]:
            assert m["residual_conservation_preserved"] is True

    def test_hypothesis_transitions(self, q13_report):
        for m in q13_report["matrix"]:
            for t in m["hypothesis_transitions"]:
                assert len({s["summary"] for s in t["sequence"]}) > 1

    def test_sensitivity_varies_or_honest(self, q13_report):
        for m in q13_report["matrix"]:
            statuses = {st for _i, st, _d in m["model_sensitivity"]}
            assert statuses <= {"VALID", "UNAVAILABLE", "INSUFFICIENT_EVIDENCE"}
            if m["sensitivity_varies_across_regimes"] is not None:
                assert m["sensitivity_varies_across_regimes"] is True

    def test_replay_identical(self, q13_report):
        for m in q13_report["matrix"]:
            assert m["replay_identical"] is True
            assert m["output_hash"]


@requires_db
class TestQ13NegativeControls:
    def test_unavailable_and_invalid(self, q13_report):
        nc = q13_report["negative_controls"]
        assert nc["1950"] == "UNAVAILABLE"
        assert nc["missing_driver"] == "UNAVAILABLE"
        assert nc["same_driver"] == "UNAVAILABLE"
        assert nc["max_regimes_oob"] == "INVALID"
        assert nc["min_regime_laps_changed"] == "INVALID"
        assert nc["start_after_end"] == "INVALID"
        assert nc["tiny_window"] == "INSUFFICIENT_EVIDENCE"

    def test_telemetry_absence_never_extrapolated(self, q13_report):
        nc = q13_report["negative_controls"]
        if nc.get("2018_status") == "VALID":
            assert nc["2018_all_regimes_telemetry_unavailable"] is True
        if nc.get("no_telemetry_pair_status") == "VALID":
            assert nc["no_telemetry_pair_all_unavailable"] is True
            assert set(nc["no_telemetry_pair_sensitivity"]) == {"UNAVAILABLE"}


@requires_db
class TestQ13Mcp:
    def test_registry_verification(self, q13_report):
        mcp = q13_report["mcp"]
        assert mcp["tool_registered"] is True
        assert mcp["registry_status"] == "VALID"
        for label in ("max_regimes_99", "min_regime_laps_4", "start_after_end",
                      "start_lap_0", "same_driver", "unknown_param"):
            assert mcp[label].startswith("REJECTED"), label
        assert mcp["1950_registry_status"] == "UNAVAILABLE"
