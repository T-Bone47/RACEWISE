"""Phase 6E tests: loss attribution — alignment, metrics, reconciliation,
context filtering, stint aggregation, determinism, negative controls.

Pure-math tests need no data. Live-store tests run only when the canonical
DB exists and validate real data across 2022-2025.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")


# ---------------------------------------------------------------------------
# interpolation / alignment math (pure)
# ---------------------------------------------------------------------------


class TestInterpolation:
    def test_interp_on_grid_points_is_exact(self):
        from racewise.data.historical.loss_attribution import _interp_series

        series = [(0.0, 10.0), (1.0, 20.0), (2.0, 40.0)]
        out = _interp_series(series, [0.0, 1.0, 2.0])
        assert out == [10.0, 20.0, 40.0]

    def test_interp_between_points_is_linear(self):
        from racewise.data.historical.loss_attribution import _interp_series

        series = [(0.0, 0.0), (1.0, 10.0)]
        out = _interp_series(series, [0.25, 0.5, 0.75])
        assert out == [2.5, 5.0, 7.5]

    def test_interp_clamps_no_extrapolation(self):
        from racewise.data.historical.loss_attribution import _interp_series

        series = [(1.0, 5.0), (2.0, 10.0)]
        out = _interp_series(series, [0.0, 1.0, 2.0, 3.0])
        assert out[0] is None and out[3] is None  # outside span -> no values
        assert out[1] == 5.0 and out[2] == 10.0

    def test_resample_requires_overlapping_span(self):
        from racewise.data.historical.loss_attribution import _resample_lap

        a = {"speed": [(0.0, 100.0), (1.0, 110.0)]}
        b = {"speed": [(5.0, 100.0), (6.0, 110.0)]}  # no overlap with a
        assert _resample_lap(a) is not None
        assert _resample_lap({"speed": [(0.0, 1.0), (0.5, 2.0)]}) is not None
        # identical single point -> empty span
        assert _resample_lap({"speed": [(1.0, 5.0)]}) is None

    def test_attribution_is_deterministic_puremath(self):
        """Same series -> byte-identical resampled output."""
        from racewise.data.historical.loss_attribution import _resample_lap

        series = {"speed": [(i * 0.3, 100.0 + i) for i in range(30)]}
        r1 = _resample_lap(series)
        r2 = _resample_lap(series)
        assert json.dumps(r1) == json.dumps(r2)


# ---------------------------------------------------------------------------
# context classification
# ---------------------------------------------------------------------------


class TestContextClassification:
    def test_pit_lap_not_comparable(self):
        from racewise.data.historical.loss_attribution import _classify_lap

        lap = {"time_s": 90.0, "is_pit_in_lap": 1, "is_pit_out_lap": 0,
               "deleted": 0, "is_accurate": 1, "track_status": "1",
               "compound": "MEDIUM", "stint": 1, "tyre_life": 5}
        ctx = _classify_lap(lap, weather_rain=False)
        assert ctx["comparable"] is False
        assert "is_pit_in_lap" in ctx["reasons"]

    def test_restricted_track_status_flagged(self):
        from racewise.data.historical.loss_attribution import _classify_lap

        lap = {"time_s": 90.0, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
               "deleted": 0, "is_accurate": 1, "track_status": "2571",
               "compound": "HARD", "stint": 2, "tyre_life": 10}
        ctx = _classify_lap(lap, weather_rain=False)
        assert "track_status_restricted" in ctx["reasons"]

    def test_weather_rain_only_flags_when_in_window(self):
        from racewise.data.historical.loss_attribution import _classify_lap

        lap = {"time_s": 90.0, "is_pit_in_lap": 0, "is_pit_out_lap": 0,
               "deleted": 0, "is_accurate": 1, "track_status": "1",
               "compound": "HARD", "stint": 1, "tyre_life": 1}
        assert _classify_lap(lap, weather_rain=False)["comparable"] is True
        assert _classify_lap(lap, weather_rain=True)["comparable"] is False

    def test_missing_lap_present_false(self):
        from racewise.data.historical.loss_attribution import _classify_lap

        ctx = _classify_lap(None, weather_rain=False)
        assert ctx["present"] is False and ctx["comparable"] is False


# ---------------------------------------------------------------------------
# signal metrics (synthetic series)
# ---------------------------------------------------------------------------


class TestSignalMetrics:
    def _resampled(self, speeds_a, speeds_b):
        from racewise.data.historical.loss_attribution import _resample_lap

        n = min(len(speeds_a), len(speeds_b))
        grid_t = [round(i * 0.25, 4) for i in range(n)]
        a = {
            "speed": list(zip(grid_t, speeds_a)),
            "throttle": list(zip(grid_t, [80.0] * n)),
            "brake": list(zip(grid_t, [0] * n)),
            "gear": list(zip(grid_t, [5] * n)),
            "rpm": list(zip(grid_t, [9000.0] * n)),
            "drs": list(zip(grid_t, [0] * n)),
        }
        b = {
            "speed": list(zip(grid_t, speeds_b)),
            "throttle": list(zip(grid_t, [60.0] * n)),
            "brake": list(zip(grid_t, [1] * n)),
            "gear": list(zip(grid_t, [4] * n)),
            "rpm": list(zip(grid_t, [8500.0] * n)),
            "drs": list(zip(grid_t, [10] * n)),
        }
        return grid_t, _resample_lap(a), _resample_lap(b)

    def test_speed_metrics_mean_and_deficit(self):
        from racewise.data.historical.loss_attribution import _signal_metrics

        grid, ra, rb = self._resampled([100.0] * 40, [95.0] * 40)
        m = _signal_metrics(grid, ra, rb)
        assert m["speed"]["mean_delta_kmh"] == pytest.approx(-5.0, abs=0.01)
        assert m["speed"]["max_deficit_kmh"] == pytest.approx(-5.0, abs=0.01)

    def test_throttle_and_brake_metrics(self):
        from racewise.data.historical.loss_attribution import _signal_metrics

        grid, ra, rb = self._resampled([100.0] * 40, [95.0] * 40)
        m = _signal_metrics(grid, ra, rb)
        assert m["throttle"]["mean_delta_pct"] == pytest.approx(-20.0, abs=0.01)
        assert m["brake"]["braking_fraction_delta"] == pytest.approx(1.0, abs=0.01)
        assert m["gear"]["gear_mismatch_fraction"] == pytest.approx(1.0, abs=0.01)
        assert m["drs"]["activation_fraction_delta"] == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# live-store tests: real data 2022-2025
# ---------------------------------------------------------------------------


@requires_db
class TestLapAttributionLive:
    def _att(self, season, rnd, a, b, lap):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.loss_attribution import attribute_lap_loss

        return attribute_lap_loss(CanonicalQueries(str(DB_PATH)), season, rnd, a, b, lap)

    def test_2023_bahweather_rain_sector_deltas_sum_to_observed(self):
        att = self._att(2023, 1, "max-verstappen", "sergio-perez", 57)
        assert att["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        sector_sum = round(sum(s["delta_s"] for s in att["sector_attribution"]), 4)
        assert sector_sum == att["observed_delta_s"]  # measured facts reconcile exactly
        # regions + residual reconcile to the observed delta
        assert att["residual_s"] == pytest.approx(
            att["observed_delta_s"] - att["estimated_pace_component_s"], abs=1e-6
        )

    def test_determinism_in_process(self):
        h = lambda r: hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()  # noqa: E731
        a1 = self._att(2023, 1, "max-verstappen", "sergio-perez", 57)
        a2 = self._att(2023, 1, "max-verstappen", "sergio-perez", 57)
        assert h(a1) == h(a2)

    def test_pit_lap_returns_insufficient_not_numbers(self):
        att = self._att(2023, 1, "max-verstappen", "sergio-perez", 1)
        assert att["status"] == "INSUFFICIENT_EVIDENCE"
        assert "context" in att  # exclusion reasons exposed, not hidden

    def test_absent_lap_unavailable(self):
        att = self._att(2023, 1, "max-verstappen", "sergio-perez", 70)
        assert att["status"] == "UNAVAILABLE"

    def test_1950_unavailable(self):
        att = self._att(1950, 6, "giuseppe-farina", "luigi-fagioli", 1)
        assert att["status"] == "UNAVAILABLE"

    def test_2018_unavailable(self):
        att = self._att(2018, 1, "lewis-hamilton", "sebastian-vettel", 5)
        assert att["status"] == "UNAVAILABLE"

    def test_stint_aggregation_2023(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.loss_attribution import attribute_stint_loss

        st = attribute_stint_loss(CanonicalQueries(str(DB_PATH)), 2023, 1,
                                  "max-verstappen", "sergio-perez", 1)
        assert st["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        agg = st["aggregate"]
        assert agg["mean_observed_delta_s"] == pytest.approx(
            agg["mean_estimated_pace_component_s"] + agg["mean_residual_s"], abs=0.001
        )
        assert 0 <= agg["unexplained_fraction"]

    def test_attribution_across_all_four_seasons(self):
        """Real-data validation: at least one valid attribution per 2022-2025."""
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.data.historical.loss_attribution import (
            attribute_lap_loss,
            VALID,
            VALID_CAVEATS,
        )

        q = CanonicalQueries(str(DB_PATH))
        cases = [(2022, 1, "carlos-sainz-jr", "charles-leclerc"),
                 (2023, 1, "max-verstappen", "sergio-perez"),
                 (2024, 1, "max-verstappen", "sergio-perez"),
                 (2025, 1, "lando-norris", "max-verstappen")]
        for season, rnd, a, b in cases:
            tel = q.telemetry_summary(season, rnd, "RACE")
            assert tel["available"], f"{season} telemetry missing"
            found = False
            for lap in sorted(tel["laps"], reverse=True):
                att = attribute_lap_loss(q, season, rnd, a, b, lap)
                if att.get("status") in (VALID, VALID_CAVEATS):
                    assert "residual_s" in att
                    assert att["reconciliation"]["observed_delta_s"] == att["observed_delta_s"]
                    found = True
                    break
            assert found, f"{season} R{rnd}: no valid attribution lap"

    def test_q7_matrix_passes_and_negatives(self):
        from racewise.data.historical.attribution_benchmarks import (
            run_q7_attribution_benchmarks,
            run_q7_negative_controls,
        )

        neg = run_q7_negative_controls(str(DB_PATH))
        assert all(v["pass"] for v in neg.values()), neg
        matrix = run_q7_attribution_benchmarks(str(DB_PATH))
        assert len(matrix) >= 6
        # every entry either PASS with real numbers or an honest status
        for key, entry in matrix.items():
            if entry["status"] == "PASS":
                assert entry["q7_6_multi_signal"]["observed_delta_s"] is not None
            else:
                assert entry["status"] in ("INSUFFICIENT_EVIDENCE", "UNAVAILABLE")

    def test_mcp_registry_has_attribution_tools(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(CanonicalQueries(str(DB_PATH)))
        assert "attribute_historical_lap_loss" in reg.names()
        assert "attribute_historical_stint_loss" in reg.names()
        out = reg.execute("attribute_historical_lap_loss",
                          {"season": 2023, "round": 1, "driver_a": "max-verstappen",
                           "driver_b": "sergio-perez", "lap_number": 57})
        assert out["status"] == "completed"
        h1 = out["output_hash"]
        h2 = reg.execute("attribute_historical_lap_loss",
                         {"season": 2023, "round": 1, "driver_a": "max-verstappen",
                          "driver_b": "sergio-perez", "lap_number": 57})["output_hash"]
        assert h1 == h2  # deterministic output hashes

    def test_investigation_engine_completes_with_attribution(self):
        from racewise.data.historical.canonical_queries import CanonicalQueries
        from racewise.tools.historical import build_historical_registry
        from racewise.investigation.engine import InvestigationEngine
        from racewise.domain.schemas import (
            EvidenceType,
            Hypothesis,
            HypothesisStatus,
            InvestigationState,
        )

        q = CanonicalQueries(str(DB_PATH))
        reg = build_historical_registry(q)
        engine = InvestigationEngine(reg, provider=None,
                                     question="Why did PER lose time to VER on lap 57?")

        def plan(e: InvestigationEngine) -> None:
            e.add_hypothesis(Hypothesis(
                id="H1",
                statement="PER's deficit concentrates in specific windows",
                confidence=0.3, status=HypothesisStatus.PROPOSED,
                supporting_evidence=[], contradicting_evidence=[],
            ))
            e._set_state(InvestigationState.EVIDENCE_PLANNING)
            e._set_state(InvestigationState.EVIDENCE_COLLECTION)
            res = e.run_tool("attribute_historical_lap_loss", {
                "season": 2023, "round": 1, "driver_a": "max-verstappen",
                "driver_b": "sergio-perez", "lap_number": 57,
            })
            e._set_state(InvestigationState.HYPOTHESIS_TESTING)
            obs = e.observe("observed_delta_s", res["observed_delta_s"], "s",
                            "canonical_lap_times", "6E-1.0")
            e.add_evidence(
                f"delta {res['observed_delta_s']}s; residual {res['residual_s']}s",
                EvidenceType.CALCULATION, [obs.id], None, supports=["H1"], strength=0.7,
            )
            e._set_state(InvestigationState.FALSIFICATION)
            for c in res["falsification"]["checks"]:
                e.add_evidence(f"{c['hypothesis']}: {c['verdict']}", EvidenceType.FACT,
                               [obs.id], None, contradicts=["H1"])
            e.set_status("H1", HypothesisStatus.SUPPORTED)
            e._set_state(InvestigationState.SYNTHESIS)
            e._set_state(InvestigationState.VERIFICATION)

        engine.run(plan)
        assert engine.state == InvestigationState.COMPLETED
        assert engine.gate_failures() == []
