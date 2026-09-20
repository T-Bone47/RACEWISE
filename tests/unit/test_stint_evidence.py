"""Phase 6G tests: stint-level evidence fusion.

Pure tests cover trend math, hypothesis-evolution rules and change-point
thresholds with no data. Live tests run against the canonical store (skipped
when absent) across 2021-2025.
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


# ---------------------------------------------------------------------------
# pure math and rules
# ---------------------------------------------------------------------------


class TestTrendMath:
    def test_ols_slope_positive(self):
        from racewise.data.historical.stint_evidence import _ols_slope

        assert _ols_slope([0.0, 1.0, 2.0], [0.1, 0.2, 0.3]) == pytest.approx(0.1)

    def test_ols_slope_zero_for_constant(self):
        from racewise.data.historical.stint_evidence import _ols_slope

        assert _ols_slope([0.0, 1.0, 2.0], [0.5, 0.5, 0.5]) == 0.0

    def test_ols_slope_degenerate_returns_zero(self):
        from racewise.data.historical.stint_evidence import _ols_slope

        assert _ols_slope([1.0, 1.0, 1.0], [0.1, 0.2, 0.3]) == 0.0

    def test_trend_block_minimum_observations(self):
        from racewise.data.historical.stint_evidence import MIN_TREND_OBS, _trend_block

        blk = _trend_block([0.1, 0.2], [0, 1])
        assert blk["status"] == "INSUFFICIENT_EVIDENCE"
        assert f">= {MIN_TREND_OBS}" in blk["reason"]

    def test_trend_block_insufficient_below_three_valid(self):
        from racewise.data.historical.stint_evidence import _trend_block

        blk = _trend_block([0.1, None, 0.3], [0, 1, 2])
        assert blk["status"] == "INSUFFICIENT_EVIDENCE"

    def test_trend_block_valid_with_outliers_retained(self):
        from racewise.data.historical.stint_evidence import _trend_block

        blk = _trend_block([0.10, 0.11, 5.0, 0.13], [0, 1, 2, 3])
        assert blk["status"] == "VALID"
        assert blk["max"] == 5.0  # outlier retained, never silently discarded

    def test_trend_block_insufficient_when_all_missing(self):
        from racewise.data.historical.stint_evidence import _trend_block

        assert _trend_block([None, None], [0, 1])["status"] == "INSUFFICIENT_EVIDENCE"


class TestHypothesisSummaryRules:
    def test_insufficient_below_two_evaluable(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        assert _hypothesis_summary(["SUPPORTED"])["summary"] == "INSUFFICIENT_EVIDENCE"

    def test_two_supports_are_insufficient_for_positive_claim(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        out = _hypothesis_summary(["SUPPORTED", "SUPPORTED"])
        assert out["summary"] == "INSUFFICIENT_EVIDENCE"

    def test_consistently_supported(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        out = _hypothesis_summary(["SUPPORTED"] * 4)
        assert out["summary"] == "CONSISTENTLY_SUPPORTED"
        assert out["status_transitions"] == 0
        assert out["support_fraction"] == 1.0

    def test_partially_supported_counts_as_support(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        out = _hypothesis_summary(["PARTIALLY_SUPPORTED"] * 3)
        assert out["summary"] == "CONSISTENTLY_SUPPORTED"

    def test_mostly_supported(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        out = _hypothesis_summary(
            ["SUPPORTED", "SUPPORTED", "SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED"])
        assert out["summary"] == "MOSTLY_SUPPORTED"

    def test_intermittent_with_contradiction(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        out = _hypothesis_summary(["SUPPORTED", "CONTRADICTED", "SUPPORTED"])
        assert out["summary"] == "INTERMITTENTLY_SUPPORTED"
        assert out["contradicted_count"] == 1

    def test_contradicted_over_time(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        out = _hypothesis_summary(["CONTRADICTED", "NOT_SUPPORTED", "CONTRADICTED"])
        assert out["summary"] == "CONTRADICTED_OVER_TIME"

    def test_not_testable_excluded_from_evaluable(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        out = _hypothesis_summary(["SUPPORTED", "NOT_TESTABLE", "SUPPORTED", "NOT_TESTABLE"])
        assert out["summary"] == "INSUFFICIENT_EVIDENCE"  # only 2 evaluable
        assert out["not_testable_count"] == 2

    def test_transitions_counted(self):
        from racewise.data.historical.stint_evidence import _hypothesis_summary

        out = _hypothesis_summary(["SUPPORTED", "SUPPORTED", "NOT_SUPPORTED",
                                   "SUPPORTED", "SUPPORTED"])
        assert out["status_transitions"] == 2


class TestChangePoint:
    def test_not_testable_below_six(self):
        from racewise.data.historical.stint_evidence import _change_point

        traj = [{"observed_delta_s": float(i)} for i in range(5)]
        assert _change_point(traj)["status"] == "NOT_TESTABLE"

    def test_stable_within_threshold(self):
        from racewise.data.historical.stint_evidence import _change_point

        traj = [{"observed_delta_s": 0.5 + 0.01 * i} for i in range(6)]
        out = _change_point(traj)
        assert out["status"] in ("STABLE", "NOT_TESTABLE")
        if out["status"] == "STABLE":
            assert abs(out["slope_delta"]) < out["threshold"]


# ---------------------------------------------------------------------------
# live-store stint fusion
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries()


@requires_db
class TestStintFusionLive:
    def test_full_shape_and_provenance(self, queries):
        from racewise.data.historical.stint_evidence import STINT_EVIDENCE_VERSION, fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2022, 4, "max-verstappen", "sergio-perez", 2)
        assert f["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        for key in ("selection", "trajectory", "performance", "residuals",
                    "hypothesis_evolution", "change_point", "conclusion",
                    "methodology_version", "provenance", "assumptions"):
            assert key in f, f"missing {key}"
        assert f["methodology_version"] == STINT_EVIDENCE_VERSION
        assert f["provenance"]["selected_laps"] == [t["lap_number"] for t in f["trajectory"]]

    def test_trajectory_preserves_order_and_exclusions(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2022, 4, "max-verstappen", "sergio-perez", 2)
        laps = [t["lap_number"] for t in f["trajectory"]]
        assert laps == sorted(laps), "trajectory must be in stint-lap order"
        assert f["selection"]["candidate_laps"] == \
            f["selection"]["valid_laps"] + len(f["selection"]["excluded"])
        for e in f["selection"]["excluded"]:
            assert e["reason"], "every exclusion must carry a reason"

    def test_no_duplicate_laps(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2022, 2, "charles-leclerc", "max-verstappen", 2)
        laps = [t["lap_number"] for t in f["trajectory"]]
        assert len(laps) == len(set(laps))

    def test_hypothesis_evolution_properties(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2022, 4, "max-verstappen", "sergio-perez", 2)
        for h, v in f["hypothesis_evolution"].items():
            assert v["summary"] in (
                "CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED", "INTERMITTENTLY_SUPPORTED",
                "CONTRADICTED_OVER_TIME", "NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE")
            assert v["valid_observations"] == (
                v["supported_count"] + v["partially_supported_count"]
                + v["not_supported_count"])
            if v["summary"] == "CONSISTENTLY_SUPPORTED":
                assert v["supported_count"] + v["partially_supported_count"] \
                    == v["valid_observations"]
                assert v["contradicted_count"] == 0

    def test_premise_gate_propagates(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        # 2022 R2 stint 2: VER faster on both valid laps -> NOT_TESTABLE expected
        f = fuse_stint_evidence(queries, 2022, 2, "charles-leclerc", "max-verstappen", 2)
        usable = [t for t in f["trajectory"] if t.get("observed_delta_s") is not None]
        if any(t["observed_delta_s"] <= 0 for t in usable) and \
                all(t["observed_delta_s"] <= 0 for t in usable):
            for v in f["hypothesis_evolution"].values():
                assert v["summary"] == "INSUFFICIENT_EVIDENCE"

    def test_residual_conservation_identity(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2022, 4, "max-verstappen", "sergio-perez", 2)
        r = f["residuals"]
        assert abs(r["cumulative_observed_s"]
                   - (r["cumulative_pace_component_s"] + r["cumulative_residual_s"])) < 1e-6
        assert "never assigned" in r["unresolved_note"]

    def test_cumulative_gap_semantics_stated(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2022, 4, "max-verstappen", "sergio-perez", 2)
        cg = f["performance"]["cumulative_gap_s"]
        assert "SELECTED comparable laps" in cg["semantics"]

    def test_trend_minimum_rule_on_thin_stint(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 1)
        trend = f["performance"]["trend"]
        if f["selection"]["valid_laps"] < 3:
            assert trend["status"] == "INSUFFICIENT_EVIDENCE"

    def test_counterfactual_gate_preserved(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2022, 4, "max-verstappen", "sergio-perez", 2)
        assert "UNSUPPORTED" in f["counterfactual_gate"]

    def test_determinism(self, queries):
        import hashlib

        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f1 = fuse_stint_evidence(queries, 2022, 4, "max-verstappen", "sergio-perez", 2)
        f2 = fuse_stint_evidence(queries, 2022, 4, "max-verstappen", "sergio-perez", 2)
        h1 = hashlib.sha256(json.dumps(f1, sort_keys=True, default=str).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(f2, sort_keys=True, default=str).encode()).hexdigest()
        assert h1 == h2


# ---------------------------------------------------------------------------
# negative controls
# ---------------------------------------------------------------------------


@requires_db
class TestNegativeControls:
    def test_1950_unavailable(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 1950, 5, "giuseppe-farina", "luigi-fagioli", 1)
        assert f["status"] == "UNAVAILABLE"

    def test_absent_stint_unavailable(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 99)
        assert f["status"] == "UNAVAILABLE"

    def test_same_driver_unavailable(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2023, 1, "max-verstappen", "max-verstappen", 1)
        assert f["status"] == "UNAVAILABLE"

    def test_no_common_laps_insufficient(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        # 2023 R9 stint 2: telemetry coverage/context filters leave 0
        # comparable laps - honest INSUFFICIENT_EVIDENCE, never fabricated
        f = fuse_stint_evidence(queries, 2023, 9, "max-verstappen", "sergio-perez", 2)
        assert f["status"] == "INSUFFICIENT_EVIDENCE"

    def test_only_one_valid_lap_trend_insufficient(self, queries):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence

        f = fuse_stint_evidence(queries, 2022, 5, "charles-leclerc", "max-verstappen", 1)
        if f["status"] == "INSUFFICIENT_EVIDENCE":
            pytest.skip("stint yields no trajectory")
        assert f["performance"]["trend"]["status"] == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# MCP + API surfaces
# ---------------------------------------------------------------------------


@requires_db
class TestSurfaces:
    def test_mcp_tool_bounded_and_deterministic(self, queries):
        from racewise.tools.contract import ToolError
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(queries)
        assert "fuse_historical_stint_evidence" in reg._tools
        r1 = reg.execute("fuse_historical_stint_evidence", {
            "season": 2022, "round": 4, "driver_a": "max-verstappen",
            "driver_b": "sergio-perez", "stint_number": 2})
        r2 = reg.execute("fuse_historical_stint_evidence", {
            "season": 2022, "round": 4, "driver_a": "max-verstappen",
            "driver_b": "sergio-perez", "stint_number": 2})
        assert r1["output_hash"] == r2["output_hash"]
        with pytest.raises(ToolError):  # unbounded max_laps rejected
            reg.execute("fuse_historical_stint_evidence", {
                "season": 2022, "round": 4, "driver_a": "a", "driver_b": "b",
                "stint_number": 1, "max_laps": 99})
        with pytest.raises(ToolError):  # unknown parameter rejected
            reg.execute("fuse_historical_stint_evidence", {
                "season": 2022, "round": 4, "driver_a": "a", "driver_b": "b",
                "stint_number": 1, "extra": 1})

    def test_api_endpoint(self, queries):
        from racewise.api.app import catalog_stint_evidence

        out = catalog_stint_evidence(2022, 4, stint=2)
        assert out["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        auto = catalog_stint_evidence(2022, 4)
        assert auto["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        assert auto["stint_number"] == 2


# ---------------------------------------------------------------------------
# investigation-engine integration (deterministic plan, no LLM)
# ---------------------------------------------------------------------------


@requires_db
class TestInvestigationIntegration:
    def test_stint_tool_runs_in_state_machine(self, queries):
        from racewise.domain.schemas import EvidenceType, Hypothesis, InvestigationState
        from racewise.investigation.engine import InvestigationEngine, InvestigationState
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(queries)
        eng = InvestigationEngine(
            reg, None, "How did the gap between driver A and B evolve across the stint?")

        def plan(e):
            out = e.run_tool("fuse_historical_stint_evidence", {
                "season": 2022, "round": 4, "driver_a": "max-verstappen",
                "driver_b": "sergio-perez", "stint_number": 2})
            assert "error" not in out, f"stint tool failed: {out}"
            e._set_state(InvestigationState.HYPOTHESIS_GENERATION)
            hyp_ids = {}
            for hid, v in out["hypothesis_evolution"].items():
                hyp_ids[hid] = f"6g-{hid}"
                e.add_hypothesis(Hypothesis(
                    id=f"6g-{hid}", statement=v.get("label", hid)))
            perf = out["performance"]
            obs = e.observe("stint_trend_s_per_lap",
                            perf.get("trend", {}).get("slope_per_stint_lap"),
                            "s/lap", "canonical_lap_facts", "stint_evidence_v1",
                            tool_execution_id=e.tool_executions[-1].id)
            e._set_state(InvestigationState.EVIDENCE_COLLECTION)
            for tid, v in out["hypothesis_evolution"].items():
                if v["supported_count"] + v["partially_supported_count"] > 0 \
                        and v["contradicted_count"] > 0:
                    # mixed evidence over time: record both sides with provenance
                    e.add_evidence(
                        statement=f"{tid}: {v['summary']} over the stint "
                                  f"(support {v['supported_count'] + v['partially_supported_count']}, "
                                  f"contradicted {v['contradicted_count']}, "
                                  f"transitions {v['status_transitions']})",
                        type_=EvidenceType.CALCULATION,
                        observation_ids=[obs.id],
                        tool_execution_id=e.tool_executions[-1].id,
                        supports=[hyp_ids[tid]],
                        contradicts=[hyp_ids[tid]],
                        strength=0.5,
                    )
            e._set_state(InvestigationState.VERIFICATION)

        eng.run(plan)
        # the stint fusion provides observations + evidence; the engine's
        # falsification gate requires a leading hypothesis, so a minimal plan
        # ends INSUFFICIENT_EVIDENCE - assert it never crashes on the tool
        assert eng.state in (InvestigationState.COMPLETED,
                             InvestigationState.INSUFFICIENT_EVIDENCE), eng.state
        assert any(tx.tool == "fuse_historical_stint_evidence" and tx.status == "completed"
                   for tx in eng.tool_executions)
