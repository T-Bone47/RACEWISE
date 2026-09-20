"""Phase 6H tests: race-level gap decomposition.

Pure tests cover official-gap semantics and race hypothesis rules with no
data. Live tests run against the canonical store (skipped when absent).
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
# pure rules
# ---------------------------------------------------------------------------


class TestRaceHypothesisRules:
    def test_all_evaluable_support(self):
        from racewise.data.historical.race_gap import _race_hypothesis_summary

        out = _race_hypothesis_summary(
            ["CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED"], [])
        assert out["summary"] == "CONSISTENTLY_SUPPORTED"

    def test_contradiction_without_support(self):
        from racewise.data.historical.race_gap import _race_hypothesis_summary

        out = _race_hypothesis_summary(["CONTRADICTED_OVER_TIME", "NOT_SUPPORTED"], [])
        assert out["summary"] == "CONTRADICTED_OVER_TIME"

    def test_support_plus_contradiction_is_intermittent(self):
        from racewise.data.historical.race_gap import _race_hypothesis_summary

        out = _race_hypothesis_summary(
            ["CONSISTENTLY_SUPPORTED", "CONTRADICTED_OVER_TIME"], [])
        # contradictions do NOT outweigh support at race level, but full
        # consistency is impossible -> intermittent
        assert out["summary"] == "INTERMITTENTLY_SUPPORTED"

    def test_nothing_evaluable(self):
        from racewise.data.historical.race_gap import _race_hypothesis_summary

        out = _race_hypothesis_summary(["INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE"], [])
        assert out["summary"] == "INSUFFICIENT_EVIDENCE"


class TestSegmentPattern:
    def test_insufficient_below_three(self):
        from racewise.data.historical.race_gap import _segment_pattern

        seg = {"laps": [{"comparable": True, "observed_delta_s": 0.1},
                        {"comparable": True, "observed_delta_s": 0.2}]}
        assert _segment_pattern(seg) == "INSUFFICIENT_EVIDENCE"

    def test_widening_detected(self):
        from racewise.data.historical.race_gap import _segment_pattern

        seg = {"laps": [{"comparable": True, "observed_delta_s": d}
                        for d in (0.1, 0.2, 0.3, 0.4)]}
        assert _segment_pattern(seg) == "WIDENING"

    def test_stable_within_threshold(self):
        from racewise.data.historical.race_gap import _segment_pattern

        seg = {"laps": [{"comparable": True, "observed_delta_s": d}
                        for d in (0.50, 0.51, 0.50, 0.51)]}
        assert _segment_pattern(seg) == "STABLE"


# ---------------------------------------------------------------------------
# live-store race decomposition
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries()


@requires_db
class TestRaceGapLive:
    def test_full_shape(self, queries):
        from racewise.data.historical.race_gap import RACE_GAP_VERSION, decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        assert f["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        for key in ("official_result", "timeline_summary", "segments",
                    "cumulative_comparable_gap_s", "gap_events", "pit_windows",
                    "race_control_windows", "stint_evidence", "hypothesis_evolution",
                    "residual_accounting", "conclusion", "methodology_version",
                    "provenance", "assumptions"):
            assert key in f, f"missing {key}"
        assert f["methodology_version"] == RACE_GAP_VERSION

    def test_official_gap_is_authoritative_and_distinct(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        off = f["official_result"]
        assert off["gap_s"] == 11.987  # 2023 Bahrain VER vs PER classified gap
        assert "authoritative" in off["semantics"]
        # distinct quantity, never forced to equal the analytical gap
        assert off["gap_s"] != f["cumulative_comparable_gap_s"]
        assert "no equality is implied" in f["residual_accounting"]["official_vs_analytical"]

    def test_timeline_preserves_exclusions(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        ts = f["timeline_summary"]
        assert ts["total_laps"] == ts["comparable"] + ts["non_comparable"] + ts["unavailable"]
        assert ts["non_comparable"] + ts["unavailable"] > 0, \
            "2023 R1 must have non-comparable laps (pit laps, restrictions)"
        assert ts["reasons"], "exclusion reasons must be tallied"

    def test_timeline_chronological(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap, _load_context, _rc_restricted_laps, _classify_laps
        from racewise.data.historical.stint_evidence import _telemetry_covered_laps

        q = queries
        tel_a = _telemetry_covered_laps(q, 2023, 1, "RACE", "max-verstappen")
        tel_b = _telemetry_covered_laps(q, 2023, 1, "RACE", "sergio-perez")
        ctx = _load_context(q, 2023, 1, "RACE", "max-verstappen", "sergio-perez")
        timeline = _classify_laps(ctx, _rc_restricted_laps(ctx["race_control"]), tel_a, tel_b)
        laps = [t["lap_number"] for t in timeline]
        assert laps == sorted(laps)
        assert len(laps) == len(set(laps))

    def test_pit_windows_observed_not_explained(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        assert f["pit_windows"], "2023 R1 has pit stops"
        for w in f["pit_windows"]:
            assert w["mechanism"] == "INSUFFICIENT_EVIDENCE"
            assert "NOT isolated" in w["semantics"] or "not isolated" in w["semantics"].lower()

    def test_race_control_exact_overlap(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        # 2023 R1 had a VSC; the window must be exact laps, not whole race
        for w in f["race_control_windows"]:
            assert w["end_lap"] - w["start_lap"] < 5, "windows must be exact-lap bounded"

    def test_stint_evidence_bounded_and_ranked(self, queries):
        from racewise.data.historical.race_gap import MAX_SEGMENTS_CAP, decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez",
                               max_segments=24)
        assert len(f["stint_evidence"]) <= MAX_SEGMENTS_CAP
        f2 = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez",
                                max_segments=2)
        assert len(f2["stint_evidence"]) <= 2

    def test_residual_accounting_invariants(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        ra = f["residual_accounting"]
        assert ra["comparable_count"] == f["timeline_summary"]["comparable"]
        assert "NOT" in ra["semantics"].upper(), \
            "comparable gap semantics must explicitly deny official-gap equivalence"

    def test_counterfactual_gate_preserved(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        assert "UNSUPPORTED" in f["counterfactual_gate"]

    def test_determinism(self, queries):
        import hashlib

        from racewise.data.historical.race_gap import decompose_race_gap

        f1 = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        f2 = decompose_race_gap(queries, 2023, 1, "max-verstappen", "sergio-perez")
        h1 = hashlib.sha256(json.dumps(f1, sort_keys=True, default=str).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(f2, sort_keys=True, default=str).encode()).hexdigest()
        assert h1 == h2


# ---------------------------------------------------------------------------
# negative controls
# ---------------------------------------------------------------------------


@requires_db
class TestNegativeControls:
    def test_1950_unavailable(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 1950, 5, "giuseppe-farina", "luigi-fagioli")
        assert f["status"] == "UNAVAILABLE"

    def test_missing_driver_unavailable(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "nobody-here", "max-verstappen")
        assert f["status"] == "UNAVAILABLE"

    def test_same_driver_unavailable(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        f = decompose_race_gap(queries, 2023, 1, "max-verstappen", "max-verstappen")
        assert f["status"] == "UNAVAILABLE"

    def test_missing_race_unavailable(self, queries):
        from racewise.data.historical.race_gap import decompose_race_gap

        # a round that does not exist for this season in the store
        f = decompose_race_gap(queries, 2023, 99, "max-verstappen", "sergio-perez")
        assert f["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# MCP + API surfaces
# ---------------------------------------------------------------------------


@requires_db
class TestSurfaces:
    def test_mcp_tool_bounded_and_deterministic(self, queries):
        from racewise.tools.contract import ToolError
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(queries)
        assert "decompose_historical_race_gap" in reg._tools
        r1 = reg.execute("decompose_historical_race_gap", {
            "season": 2023, "round": 1, "driver_a": "max-verstappen",
            "driver_b": "sergio-perez"})
        r2 = reg.execute("decompose_historical_race_gap", {
            "season": 2023, "round": 1, "driver_a": "max-verstappen",
            "driver_b": "sergio-perez"})
        assert r1["output_hash"] == r2["output_hash"]
        with pytest.raises(ToolError):  # unbounded max_segments rejected explicitly
            reg.execute("decompose_historical_race_gap", {
                "season": 2023, "round": 1, "driver_a": "a", "driver_b": "b",
                "max_segments": 99})
        with pytest.raises(ToolError):  # unknown parameter rejected
            reg.execute("decompose_historical_race_gap", {
                "season": 2023, "round": 1, "driver_a": "a", "driver_b": "b",
                "extra": 1})

    def test_api_endpoint(self, queries):
        from racewise.api.app import catalog_race_gap

        out = catalog_race_gap(2023, 1)
        assert out["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        assert out["official_result"]["gap_s"] == 11.987
        assert out["cumulative_comparable_gap_s"] != out["official_result"]["gap_s"]


# ---------------------------------------------------------------------------
# investigation-engine integration
# ---------------------------------------------------------------------------


@requires_db
class TestInvestigationIntegration:
    def test_race_tool_runs_in_state_machine(self, queries):
        from racewise.domain.schemas import InvestigationState
        from racewise.investigation.engine import InvestigationEngine
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(queries)
        eng = InvestigationEngine(
            reg, None, "Where during the race was the gap created or recovered?")

        def plan(e):
            out = e.run_tool("decompose_historical_race_gap", {
                "season": 2023, "round": 1, "driver_a": "max-verstappen",
                "driver_b": "sergio-perez"})
            assert "error" not in out, f"race tool failed: {out}"
            from racewise.domain.schemas import EvidenceType
            from racewise.investigation.engine import InvestigationState as IS
            e._set_state(IS.EVIDENCE_PLANNING)
            e.observe("official_gap_s", out["official_result"]["gap_s"], "s",
                      "canonical_results", "race_gap_v1",
                      tool_execution_id=e.tool_executions[-1].id)
            e._set_state(IS.EVIDENCE_COLLECTION)
            for seg in out["segments"]:
                if seg.get("pattern") in ("WIDENING", "NARROWING"):
                    e.add_evidence(
                        statement=f"Stint {seg['stint_number']} gap pattern {seg['pattern']} "
                                  f"over {seg['comparable_laps']} comparable laps",
                        type_=EvidenceType.CALCULATION,
                        observation_ids=[e.observations[-1].id],
                        tool_execution_id=e.tool_executions[-1].id,
                        strength=0.5,
                    )
            e._set_state(IS.VERIFICATION)

        eng.run(plan)
        assert eng.state in (InvestigationState.COMPLETED,
                             InvestigationState.INSUFFICIENT_EVIDENCE), eng.state
        assert any(tx.tool == "decompose_historical_race_gap" and tx.status == "completed"
                   for tx in eng.tool_executions)
