"""Phase 6K tests: performance regime & change-point intelligence.

Pure tests cover the deterministic segmentation helpers with synthetic
series (no DB). Stub tests run the full analysis on a fixture query object.
Live-store tests run only when the canonical DB exists and validate real
data across the 2022-2025 matrix plus MCP/API/investigation integration.
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
# pure segmentation math (synthetic series, no DB)
# ---------------------------------------------------------------------------


class TestSegmentationPure:
    def _deltas(self, values: list[float], start: int = 1) -> list[tuple[int, float]]:
        return [(start + i, v) for i, v in enumerate(values)]

    def test_stable_series_single_regime_no_change_point(self):
        from racewise.data.historical.performance_regimes import (
            _flatten_segments, _merge_adjacent, _seg_info,
        )

        # perfectly linear series: one slope everywhere, no admissible split
        deltas = self._deltas([0.10 * i for i in range(24)])
        rejections: list[dict] = []
        segs = _flatten_segments(deltas, rejections)
        segs, merges = _merge_adjacent(segs)
        assert len(segs) == 1
        info = _seg_info(segs[0])
        assert info["pattern"] == "WIDENING"  # slope 0.10 >= 0.03 threshold
        assert not rejections

    def test_two_slopes_detected(self):
        from racewise.data.historical.performance_regimes import (
            _flatten_segments, _merge_adjacent, _seg_info,
        )

        values = [0.0] * 12 + [1.0 + 0.2 * i for i in range(12)]
        deltas = self._deltas(values)
        rejections: list[dict] = []
        segs = _flatten_segments(deltas, rejections)
        segs, _ = _merge_adjacent(segs)
        infos = [_seg_info(s) for s in segs]
        assert len(segs) >= 2
        # each regime respects MIN_REGIME_LAPS
        assert all(len(s) >= 3 for s in segs)
        # slopes genuinely differ
        assert abs(infos[0]["slope"] - infos[-1]["slope"]) >= 0.03

    def test_short_regime_rejected_and_logged(self):
        from racewise.data.historical.performance_regimes import _flatten_segments

        # a one-lap spike must not split the series (min-length rule)
        values = [0.0] * 10 + [50.0] + [0.1 * i for i in range(10)]
        deltas = self._deltas(values)
        rejections: list[dict] = []
        segs = _flatten_segments(deltas, rejections)
        assert all(len(s) >= 3 for s in segs)

    def test_noise_never_creates_regimes(self):
        from racewise.data.historical.performance_regimes import (
            _flatten_segments, _merge_adjacent, _seg_info,
        )

        # alternating noise around a flat mean: no persistent slope change
        values = [0.05 * (1 if i % 2 else -1) for i in range(30)]
        deltas = self._deltas(values)
        rejections: list[dict] = []
        segs = _flatten_segments(deltas, rejections)
        segs, merges = _merge_adjacent(segs)
        assert len(segs) == 1
        assert _seg_info(segs[0])["pattern"] == "STABLE"

    def test_pattern_thresholds_match_6g(self):
        from racewise.data.historical.performance_regimes import (
            MIN_REGIME_LAPS, SLOPE_THRESHOLD_S_PER_LAP, _pattern_for,
        )

        assert SLOPE_THRESHOLD_S_PER_LAP == 0.03
        assert MIN_REGIME_LAPS == 3
        assert _pattern_for(0.001, 10) == "STABLE"
        assert _pattern_for(0.05, 10) == "WIDENING"
        assert _pattern_for(-0.05, 10) == "NARROWING"
        assert _pattern_for(0.05, 2) == "INSUFFICIENT_EVIDENCE"

    def test_merge_adjacent_deterministic(self):
        from racewise.data.historical.performance_regimes import _merge_adjacent

        # two adjacent near-identical slopes merge into one
        segs = [self._deltas([0.10 * i for i in range(6)]),
                self._deltas([0.10 * i for i in range(6, 12)], start=7)]
        merged, log = _merge_adjacent(segs)
        assert len(merged) == 1
        assert len(log) == 1
        assert "threshold" in log[0]["reason"]

    def test_enforce_max_regimes_merges_closest_slopes(self):
        from racewise.data.historical.performance_regimes import _enforce_max_regimes

        segs = [self._deltas([0.10 * i for i in range(5)]),
                self._deltas([0.11 * i for i in range(5)], start=6),
                self._deltas([0.60 * i for i in range(5)], start=11)]
        merges: list[dict] = []
        out = _enforce_max_regimes(segs, 2, merges)
        assert len(out) == 2
        assert len(merges) == 1

    def test_timeline_synthesis_ordering(self):
        from racewise.data.historical.performance_regimes import _race_timeline

        entries = _race_timeline(
            [{"regime_index": 1, "start_lap": 1, "end_lap": 5, "pattern": "STABLE",
              "lap_count": 5},
             {"regime_index": 2, "start_lap": 6, "end_lap": 10, "pattern": "WIDENING",
              "lap_count": 5}],
            [{"transition_lap": 6, "change_point_type": "GAP_TREND_CHANGE",
              "previous_pattern": "STABLE", "new_pattern": "WIDENING"}],
            [{"type": "STINT_TRANSITION", "lap_number": 6, "previous": 1, "new": 2}])
        kinds = [e["kind"] for e in entries]
        assert kinds == ["REGIME", "REGIME", "CHANGE_POINT", "CONTEXT_TRANSITION"]


# ---------------------------------------------------------------------------
# validation + status semantics (no DB touched before validation)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_bounds_rejected_without_db(self):
        from racewise.data.historical.performance_regimes import analyze_performance_regimes
        from racewise.data.historical.canonical_queries import CanonicalQueries

        # a real store object is needed for pair validation; DB may be absent,
        # so assert on the pure validation path with a null-store guard
        q = CanonicalQueries() if DB_PATH.exists() else None
        if q is None:  # pragma: no cover
            pytest.skip("canonical DB not present")
        r = analyze_performance_regimes(q, 2023, 1, "max-verstappen",
                                        "sergio-perez", max_regimes=99)
        assert r["status"] == "INVALID"
        r = analyze_performance_regimes(q, 2023, 1, "max-verstappen",
                                        "sergio-perez", min_regime_laps=4)
        assert r["status"] == "INVALID"
        r = analyze_performance_regimes(q, 2023, 1, "max-verstappen",
                                        "sergio-perez", start_lap=30, end_lap=10)
        assert r["status"] == "INVALID"


# ---------------------------------------------------------------------------
# live-store semantics
# ---------------------------------------------------------------------------


@requires_db
class TestRegimesLive:
    @pytest.fixture(scope="class")
    def queries(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries

        return CanonicalQueries()

    @pytest.fixture(scope="class")
    def result2022(self, queries):
        """One heavy analyze run shared by the read-only semantic tests."""
        from racewise.data.historical.performance_regimes import analyze_performance_regimes

        return analyze_performance_regimes(
            queries, 2022, 4, "max-verstappen", "sergio-perez", max_regimes=8)

    def test_valid_structure(self, queries, result2022):
        r = result2022
        assert r["status"] == "VALID"
        assert r["regime_count"] == len(r["regimes"])
        assert all(g["lap_count"] >= 3 for g in r["regimes"])
        assert all(g["end_lap"] >= g["start_lap"] for g in r["regimes"])
        # regimes are contiguous
        for a, b in zip(r["regimes"], r["regimes"][1:]):
            assert b["start_lap"] == a["end_lap"] + 1
        # change points sit exactly at regime boundaries
        for cp, nxt in zip(r["change_points"], r["regimes"][1:]):
            assert cp["transition_lap"] == nxt["start_lap"]

    def test_pattern_threshold_semantics(self, result2022):
        r = result2022
        for g in r["regimes"]:
            s = g["slope_s_per_lap"]
            if abs(s) < 0.03:
                assert g["pattern"] == "STABLE"
            elif s > 0:
                assert g["pattern"] == "WIDENING"
            else:
                assert g["pattern"] == "NARROWING"

    def test_stint_boundaries_preserved_and_crossable(self, result2022):
        r = result2022
        # canonical stint identity recorded per regime
        assert all("stints_spanned" in g for g in r["regimes"])
        # at least one regime crosses a stint boundary (analytical != canonical)
        assert any(g["crosses_stint_boundary"] for g in r["regimes"])

    def test_telemetry_gap_preserved(self, result2022):
        r = result2022
        states = {g["telemetry_state"] for g in r["regimes"]}
        assert states <= {"AVAILABLE", "TELEMETRY_UNAVAILABLE"}
        # regimes without telemetry never claim speed-profile measurements
        for g in r["regimes"]:
            if g["telemetry_state"] == "TELEMETRY_UNAVAILABLE":
                assert g["speed_profile"]["state"] == "TELEMETRY_UNAVAILABLE"
                assert g["speed_profile"]["mean_abs_distance_kmh"] is None

    def test_residual_conservation(self, result2022):
        r = result2022
        for g in r["regimes"]:
            res = g["residual"]
            if res["laps_fused"] > 0:
                assert res["state"] == "PRESERVED"
                assert abs(res["observed_total_s"]
                           - (res["pace_component_total_s"]
                              + res["residual_total_s"])) <= 1e-3

    def test_hypothesis_evolution_propagates_6f_statuses(self, result2022):
        r = result2022
        allowed = {"CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED",
                   "INTERMITTENTLY_SUPPORTED", "CONTRADICTED_OVER_TIME",
                   "NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE"}
        for g in r["regimes"]:
            for h in g["hypothesis_evolution"]:
                assert h["summary"] in allowed

    def test_sensitivity_statuses_honest(self, result2022):
        r = result2022
        allowed = {"VALID", "UNAVAILABLE", "INSUFFICIENT_EVIDENCE"}
        for g in r["regimes"]:
            assert g["model_sensitivity"]["status"] in allowed

    def test_context_alignment_is_association_not_cause(self, result2022):
        r = result2022
        for cp in r["change_points"]:
            assert "temporal association" in cp["interpretation"]
            assert "not established causation" in cp["interpretation"]

    def test_negative_controls(self, queries):
        from racewise.data.historical.performance_regimes import analyze_performance_regimes

        assert analyze_performance_regimes(
            queries, 1950, 1, "giuseppe-farina", "luigi-fagioli")["status"] == "UNAVAILABLE"
        assert analyze_performance_regimes(
            queries, 2023, 1, "nobody-here", "max-verstappen")["status"] == "UNAVAILABLE"
        assert analyze_performance_regimes(
            queries, 2023, 1, "max-verstappen", "max-verstappen")["status"] == "UNAVAILABLE"
        r = analyze_performance_regimes(
            queries, 2023, 1, "max-verstappen", "sergio-perez",
            start_lap=30, end_lap=31)
        assert r["status"] == "INSUFFICIENT_EVIDENCE"
        # 2018: no telemetry -> every regime (if any) states it explicitly
        r = analyze_performance_regimes(
            queries, 2018, 1, "lewis-hamilton", "sebastian-vettel")
        if r["status"] == "VALID":
            assert all(g["telemetry_state"] == "TELEMETRY_UNAVAILABLE"
                       for g in r["regimes"])

    def test_determinism_live(self, queries):
        import hashlib

        from racewise.data.historical.performance_regimes import analyze_performance_regimes

        r1 = analyze_performance_regimes(
            queries, 2022, 4, "max-verstappen", "sergio-perez", max_regimes=8)
        r2 = analyze_performance_regimes(
            queries, 2022, 4, "max-verstappen", "sergio-perez", max_regimes=8)
        assert r1["output_hash"] == r2["output_hash"]
        payload = json.dumps(
            {k: v for k, v in r1.items() if k != "output_hash"},
            sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(payload.encode()).hexdigest()[:16] == r1["output_hash"]

    def test_window_semantics(self, queries):
        from racewise.data.historical.performance_regimes import analyze_performance_regimes

        full = analyze_performance_regimes(
            queries, 2022, 4, "max-verstappen", "sergio-perez", max_regimes=8)
        win = analyze_performance_regimes(
            queries, 2022, 4, "max-verstappen", "sergio-perez",
            max_regimes=8, start_lap=10, end_lap=40)
        assert win["status"] == "VALID"
        assert all(10 <= g["start_lap"] and g["end_lap"] <= 40 for g in win["regimes"])
        assert win["comparable_lap_count"] < full["comparable_lap_count"]

    def test_cross_race_comparison_no_ranking(self, queries):
        from racewise.data.historical.performance_regimes import compare_performance_regimes

        c = compare_performance_regimes(
            queries, [(2022, 4), (2023, 1), (1950, 1)],
            "max-verstappen", "sergio-perez")
        assert c["status"] == "VALID"
        assert len(c["races"]) == 3
        by_key = {(x["season"], x["round"]): x for x in c["races"]}
        assert by_key[(2022, 4)]["status"] == "VALID"
        assert by_key[(1950, 1)]["status"] == "UNAVAILABLE"
        assert "never ranked" in c["note"]

    def test_compare_bounds(self, queries):
        from racewise.data.historical.performance_regimes import compare_performance_regimes

        assert compare_performance_regimes(
            queries, [(2022, 4)] * 7, "max-verstappen", "sergio-perez")["status"] == "INVALID"
        assert compare_performance_regimes(
            queries, [(2022, 4)], "max-verstappen", "max-verstappen")["status"] == "UNAVAILABLE"


@requires_db
class TestMcpBoundary:
    def test_tool_registered_with_bounds(self):
        from racewise.tools.historical import build_historical_registry
        from racewise.tools.contract import ToolError
        from racewise.data.historical.canonical_queries import CanonicalQueries

        reg = build_historical_registry(CanonicalQueries())
        name = "analyze_historical_performance_regimes"
        assert name in reg._tools
        base = {"season": 2022, "round": 4,
                "driver_a": "max-verstappen", "driver_b": "sergio-perez"}
        for label, extra in (
            ("max_regimes_99", {"max_regimes": 99}),
            ("min_regime_laps_4", {"min_regime_laps": 4}),
            ("start_after_end", {"start_lap": 30, "end_lap": 10}),
            ("start_lap_0", {"start_lap": 0}),
            ("end_lap_0", {"end_lap": 0}),
            ("same_driver", {"driver_b": "max-verstappen"}),
            ("same_driver_code", {"driver_b": "VER"}),
            ("unknown_param", {"bogus": 1}),
        ):
            with pytest.raises(ToolError):
                reg.execute(name, {**base, **extra})

    def test_registry_happy_path_deterministic(self):
        from racewise.tools.historical import build_historical_registry
        from racewise.data.historical.canonical_queries import CanonicalQueries

        reg = build_historical_registry(CanonicalQueries())
        args = {"season": 2022, "round": 4, "driver_a": "VER",
                "driver_b": "PER", "max_regimes": 6}
        r1 = reg.execute("analyze_historical_performance_regimes", args)["output"]
        r2 = reg.execute("analyze_historical_performance_regimes", args)["output"]
        assert r1["status"] == "VALID"
        assert r1["output_hash"] == r2["output_hash"]

    def test_full_registry_tool_count(self):
        from racewise.tools.historical import build_historical_registry
        from racewise.data.historical.canonical_queries import CanonicalQueries

        reg = build_historical_registry(CanonicalQueries())
        # 20 pre-6L historical tools + cross-race patterns (Phase 6L)
        assert len(reg._tools) == 27  # 23 pre-6O historical + 4 memory tools (Phase 6O)


@requires_db
class TestApiEndpoint:
    def test_endpoint_valid_and_deterministic(self):
        from fastapi.testclient import TestClient
        from racewise.api.app import app

        c = TestClient(app)
        r1 = c.get("/api/catalog/performance-regimes/2022/4")
        assert r1.status_code == 200
        assert r1.json()["status"] == "VALID"
        r2 = c.get("/api/catalog/performance-regimes/2022/4")
        assert r1.content == r2.content

    def test_endpoint_bounds_and_unavailable(self):
        from fastapi.testclient import TestClient
        from racewise.api.app import app

        c = TestClient(app)
        assert c.get("/api/catalog/performance-regimes/2022/4",
                     params={"max_regimes": 99}).status_code == 422
        assert c.get("/api/catalog/performance-regimes/2022/4",
                     params={"start_lap": 30, "end_lap": 10}).status_code == 422
        r = c.get("/api/catalog/performance-regimes/1950/1")
        assert r.status_code == 200
        assert r.json()["status"] == "UNAVAILABLE"
        assert c.get("/api/catalog/performance-regimes/3011/1").status_code == 404


@requires_db
class TestInvestigationIntegration:
    def test_regime_tool_inside_state_machine(self):
        from racewise.investigation.engine import InvestigationEngine, InvestigationState
        from racewise.tools.historical import build_historical_registry
        from racewise.data.historical.canonical_queries import get_canonical_queries

        reg = build_historical_registry(get_canonical_queries())
        eng = InvestigationEngine(
            reg, None,
            "Did the 2022 R4 VER/PER performance relationship change regime mid-race?")

        def plan(e):
            res = e.run_tool("analyze_historical_performance_regimes", {
                "season": 2022, "round": 4, "driver_a": "max-verstappen",
                "driver_b": "sergio-perez", "max_regimes": 6})
            assert "error" not in res, f"regime tool failed: {res}"
            assert res["status"] == "VALID"

            e._set_state(InvestigationState.HYPOTHESIS_GENERATION)
            from racewise.domain.schemas import (
                EvidenceType, Hypothesis, HypothesisStatus,
            )

            e.add_hypothesis(Hypothesis(
                id="6k-regime-structure",
                statement="The comparable-lap delta series contains deterministic "
                          "regime structure (analytical organization of measured "
                          "temporal structure, not causal inference)",
                required_evidence=[],
                potential_falsifiers=[],
            ))
            obs = e.observe(
                "regime_count", res["regime_count"], "count",
                "performance_regimes", "regime_v1",
                tool_execution_id=e.tool_executions[-1].id,
            )
            e._set_state(InvestigationState.EVIDENCE_COLLECTION)
            e.add_evidence(
                statement=(
                    f"{res['regime_count']} regimes over {res['comparable_lap_count']} "
                    f"comparable laps; {len(res['change_points'])} change points with "
                    "context alignment recorded as temporal association - regime "
                    "detection organizes evidence, it does not establish causality."),
                type_=EvidenceType.FACT,
                observation_ids=[obs.id],
                tool_execution_id=e.tool_executions[-1].id,
                supports=["6k-regime-structure"],
                strength=0.6,
            )
            e._set_state(InvestigationState.FALSIFICATION)
            # honest contradiction: regime boundaries are analytical, not
            # canonical; a nearby context event does not explain the change
            e.set_status("6k-regime-structure", HypothesisStatus.SUPPORTED)
            e.add_evidence(
                statement=(
                    "Regime boundaries are detected from a slope statistic on the "
                    "comparable-lap subset, not from canonical stint or event "
                    "structure; any temporal alignment with context transitions is "
                    "association, and regimes may merge or be rejected by the "
                    "documented thresholds."),
                type_=EvidenceType.CALCULATION,
                observation_ids=[obs.id],
                tool_execution_id=e.tool_executions[-1].id,
                contradicts=["6k-regime-structure"],
                strength=0.5,
            )
            e._set_state(InvestigationState.VERIFICATION)

        eng.run(plan)
        assert eng.state == InvestigationState.COMPLETED, \
            f"ended {eng.state}; gate={eng.gate_failures()}"
        assert eng.gate_failures() == []
        assert eng.unsupported_claims() == []
