"""Phase 6I tests: validated telemetry counterfactuals.

Pure-math tests cover profile/intervention/model mechanics with a stub query
object (no DB needed). Live-store tests run only when the canonical DB exists
and validate real data across the 2022-2025 matrix.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")


# ---------------------------------------------------------------------------
# pure-math: interventions
# ---------------------------------------------------------------------------


class TestInterventions:
    def test_remove_deficit_identity_is_exact(self):
        from racewise.data.historical.counterfactual import transform_speed_profile

        target = [100.0, 110.0, 120.0]
        ref = [130.0, 140.0, 150.0]
        out = transform_speed_profile(target, ref, "REMOVE_DEFICIT", 0.0)
        assert out == target

    def test_remove_deficit_full_adopts_reference_where_faster(self):
        from racewise.data.historical.counterfactual import transform_speed_profile

        target = [100.0, 120.0, 150.0]
        ref = [140.0, 130.0, 150.0]
        out = transform_speed_profile(target, ref, "REMOVE_DEFICIT", 1.0)
        assert out == [140.0, 130.0, 150.0]  # never slower than target

    def test_remove_deficit_half_closes_half_the_gap(self):
        from racewise.data.historical.counterfactual import transform_speed_profile

        target = [100.0]
        ref = [140.0]
        out = transform_speed_profile(target, ref, "REMOVE_DEFICIT", 0.5)
        assert out == [120.0]

    def test_blend_linear(self):
        from racewise.data.historical.counterfactual import transform_speed_profile

        out = transform_speed_profile([100.0], [200.0], "BLEND_WITH_REFERENCE", 0.25)
        assert out == [125.0]

    def test_scale_multiplicative(self):
        from racewise.data.historical.counterfactual import transform_speed_profile

        out = transform_speed_profile([100.0, -50.0], None, "SCALE_SIGNAL", -0.10)
        assert out == [90.0, -45.0]

    def test_bounds_reject_out_of_range(self):
        from racewise.data.historical.counterfactual import transform_speed_profile

        with pytest.raises(ValueError):
            transform_speed_profile([100.0], [200.0], "REMOVE_DEFICIT", 1.5)
        with pytest.raises(ValueError):
            transform_speed_profile([100.0], [200.0], "BLEND_WITH_REFERENCE", -0.1)
        with pytest.raises(ValueError):
            transform_speed_profile([100.0], None, "SCALE_SIGNAL", 0.5)  # cap is 0.10
        with pytest.raises(ValueError):
            transform_speed_profile([100.0], None, "SCALE_SIGNAL", float("nan"))
        with pytest.raises(ValueError):
            transform_speed_profile([100.0], None, "SCALE_SIGNAL", float("inf"))

    def test_unknown_type_rejected(self):
        from racewise.data.historical.counterfactual import transform_speed_profile

        with pytest.raises(ValueError, match="unknown intervention type"):
            transform_speed_profile([100.0], None, "MAKE_IT_FASTER", 0.1)

    def test_reference_required_for_reference_interventions(self):
        from racewise.data.historical.counterfactual import transform_speed_profile

        with pytest.raises(ValueError, match="reference"):
            transform_speed_profile([100.0], None, "REMOVE_DEFICIT", 0.5)
        with pytest.raises(ValueError, match="same grid"):
            transform_speed_profile([100.0, 110.0], [120.0], "REMOVE_DEFICIT", 0.5)

    def test_non_speed_signal_has_no_model(self):
        from racewise.data.historical.counterfactual import _validate_intervention

        with pytest.raises(ValueError, match="no deterministic lap-time model"):
            _validate_intervention("throttle", "REMOVE_DEFICIT", 0.5)


# ---------------------------------------------------------------------------
# pure-math: exact piecewise-linear quadrature + model
# ---------------------------------------------------------------------------


class TestQuadrature:
    def test_integral_linear_constant(self):
        from racewise.data.historical.counterfactual import _integral_plinear

        grid = [0.0, 1.0, 2.0, 3.0]
        vals = [100.0, 100.0, 100.0, 100.0]
        assert _integral_plinear(vals, grid, 0.0, 3.0) == pytest.approx(300.0)

    def test_integral_triangle_matches_hand_value(self):
        from racewise.data.historical.counterfactual import _integral_plinear

        grid = [0.0, 1.0, 2.0]
        vals = [0.0, 10.0, 0.0]  # triangle area = 10
        assert _integral_plinear(vals, grid, 0.0, 2.0) == pytest.approx(10.0)

    def test_integral_partial_window_clips_exactly(self):
        from racewise.data.historical.counterfactual import _integral_plinear

        grid = [0.0, 1.0, 2.0]
        vals = [0.0, 10.0, 20.0]
        # v is linear 0->20 over [0,2]: mean over [0.5,1.5] is (5+15)/2 = 10
        assert _integral_plinear(vals, grid, 0.5, 1.5) == pytest.approx(10.0)

    def test_segmentize_mean_v_times_duration_is_distance(self):
        from racewise.data.historical.counterfactual import _segmentize

        grid = [round(i * 0.25, 4) for i in range(40)]  # 10 s span
        vals = [100.0 + 5.0 * (i % 7) for i in range(40)]
        segs = _segmentize(vals, grid, 6.0)
        assert len(segs) == 2
        for s in segs:
            assert s["mean_v"] * s["duration"] == pytest.approx(s["distance"])

    def test_model_lap_time_excludes_stationary(self):
        from racewise.data.historical.counterfactual import _model_lap_time

        # one normal segment, one effectively stationary (< 5 km/h)
        t, excluded = _model_lap_time([100.0, 100.0], [100.0, 1.0])
        assert t == pytest.approx(1.0)
        assert excluded == 1


# ---------------------------------------------------------------------------
# stub-query end-to-end (no DB)
# ---------------------------------------------------------------------------


class _StubQueries:
    """Minimal CanonicalQueries stand-in with two deterministic driver laps."""

    MAX_TELEMETRY_SAMPLES = 2000
    TELEMETRY_SIGNALS = ("speed", "throttle", "brake", "gear", "rpm", "drs")

    def __init__(self) -> None:
        self.laps = [1, 2]

    # profile extraction path
    def get_lap_telemetry(self, season, round_num, driver_key, lap_number,
                          session_type="RACE", signals=None, max_samples=2000):
        rows = []
        n = 400  # 0.25 s grid * 400 = 100 s span
        for i in range(n):
            t = round(i * 0.25, 4)
            speed = 200.0 + 30.0 * math.sin(0.05 * i)  # deterministic wave
            if driver_key == "slow-driver":
                speed -= 12.0  # constant measured deficit
            rows.append({"lap_number": lap_number, "lap_time_s": t, "value": speed})
        return rows

    def telemetry_summary(self, season, round_num, session_type="RACE"):
        return {"available": True, "laps": list(self.laps), "sample_count": 800}


class TestStubEndToEnd:
    def _q(self) -> _StubQueries:
        return _StubQueries()

    def test_valid_counterfactual_with_exact_reproduction(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        res = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed",
            "REMOVE_DEFICIT", 0.5, reference_driver="fast-driver")
        assert res["status"] == "VALID"
        assert res["model"]["baseline_reproduction"]["error_s"] == 0.0
        assert res["model"]["baseline_reproduction"]["identity_intervention_delta_s"] == 0.0
        assert all(g["status"] == "PASS" for g in res["validation_gates"].values())
        # constant 12 km/h deficit on a ~200 km/h trace, half closed
        assert res["counterfactual_delta_s"] < 0.0

    def test_delta_is_monotone_in_fraction(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        q = self._q()
        deltas = []
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            r = simulate_telemetry_counterfactual(
                q, 2023, 1, "slow-driver", 1, "speed",
                "REMOVE_DEFICIT", f, reference_driver="fast-driver")
            deltas.append(r["counterfactual_delta_s"])
        assert all(deltas[i] >= deltas[i + 1] - 1e-9 for i in range(len(deltas) - 1))

    def test_identity_scale_is_exactly_zero(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        res = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed", "SCALE_SIGNAL", 0.0)
        assert res["status"] == "VALID"
        assert res["counterfactual_delta_s"] == 0.0

    def test_non_speed_signal_unsupported(self):
        from racewise.data.historical.counterfactual import (
            UNSUPPORTED,
            simulate_telemetry_counterfactual,
        )

        res = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "brake", "REMOVE_DEFICIT", 0.5,
            reference_driver="fast-driver")
        assert res["status"] == UNSUPPORTED

    def test_unknown_intervention_unsupported(self):
        from racewise.data.historical.counterfactual import (
            UNSUPPORTED,
            simulate_telemetry_counterfactual,
        )

        res = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed", "TELEPORT", 0.5,
            reference_driver="fast-driver")
        assert res["status"] == UNSUPPORTED

    def test_invalid_fraction_flagged_invalid(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        res = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed", "REMOVE_DEFICIT", 2.0,
            reference_driver="fast-driver")
        assert res["status"] == "INVALID"

    def test_unavailable_without_telemetry(self):
        from racewise.data.historical.counterfactual import (
            UNAVAILABLE,
            simulate_telemetry_counterfactual,
        )

        q = self._q()
        q.telemetry_summary = lambda *a, **k: {"available": False, "laps": []}  # type: ignore[method-assign]
        res = simulate_telemetry_counterfactual(
            q, 1950, 1, "slow-driver", 1, "speed", "SCALE_SIGNAL", 0.05)
        assert res["status"] == UNAVAILABLE

    def test_determinism_stub(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        a = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed",
            "REMOVE_DEFICIT", 0.5, reference_driver="fast-driver")
        b = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed",
            "REMOVE_DEFICIT", 0.5, reference_driver="fast-driver")
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        assert a["output_hash"] == b["output_hash"]

    def test_output_is_bounded_json(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        res = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed",
            "REMOVE_DEFICIT", 0.5, reference_driver="fast-driver")
        assert len(json.dumps(res)) < 100_000  # no raw telemetry dumps

    def test_epistemics_language_present(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        res = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed",
            "REMOVE_DEFICIT", 0.5, reference_driver="fast-driver")
        assert "not a historical" in res["epistemics"]
        assert "not a causal proof" in res["epistemics"]

    def test_hash_excludes_itself(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        res = simulate_telemetry_counterfactual(
            self._q(), 2023, 1, "slow-driver", 1, "speed",
            "REMOVE_DEFICIT", 0.5, reference_driver="fast-driver")
        body = {k: v for k, v in res.items() if k != "output_hash"}
        import hashlib

        expect = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        assert res["output_hash"] == expect


# ---------------------------------------------------------------------------
# live-store tests (real canonical data)
# ---------------------------------------------------------------------------


@requires_db
class TestLiveCounterfactual:
    def _q(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries

        return get_canonical_queries()

    def test_2023_r1_lap1_valid_with_exact_reproduction(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        q = self._q()
        res = simulate_telemetry_counterfactual(
            q, 2023, 1, "sergio-perez", 1, "speed", "REMOVE_DEFICIT", 0.5,
            reference_driver="max-verstappen")
        assert res["status"] == "VALID"
        assert res["model"]["baseline_reproduction"]["error_s"] == 0.0
        assert res["counterfactual_delta_s"] < 0.0

    def test_identity_intervention_exactly_zero_all_sessions(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        q = self._q()
        for season, rnd in ((2022, 4), (2023, 1), (2024, 14), (2025, 12)):
            res = simulate_telemetry_counterfactual(
                q, season, rnd, "sergio-perez" if rnd == 1 and season == 2023 else "max-verstappen",
                1, "speed", "SCALE_SIGNAL", 0.0)
            if res["status"] == "VALID":
                assert res["counterfactual_delta_s"] == 0.0

    def test_matrix_2022_2025_valid(self):
        from racewise.data.historical.counterfactual import (
            VALID,
            simulate_telemetry_counterfactual,
        )

        q = self._q()
        cases = [
            (2023, 1, "sergio-perez", "max-verstappen"),
            (2022, 4, "sergio-perez", "max-verstappen"),
            (2024, 14, "oscar-piastri", "lewis-hamilton"),
            (2025, 12, "oscar-piastri", "lando-norris"),
        ]
        for season, rnd, drv, ref in cases:
            r = simulate_telemetry_counterfactual(
                q, season, rnd, drv, 1, "speed", "REMOVE_DEFICIT", 0.5,
                reference_driver=ref)
            assert r["status"] == VALID, f"{season} R{rnd}: {r.get('reason')}"

    def test_stint_counterfactual_conservation(self):
        from racewise.data.historical.counterfactual import (
            VALID,
            simulate_stint_counterfactual,
        )

        q = self._q()
        res = simulate_stint_counterfactual(
            q, 2023, 1, "sergio-perez", "max-verstappen", 2, "speed",
            "REMOVE_DEFICIT", 0.5)
        if res["status"] == VALID:
            deltas = [p["delta_s"] for p in res["per_lap"] if p.get("delta_s") is not None]
            agg = res["aggregate"]
            assert agg["cumulative_delta_s"] == pytest.approx(sum(deltas), abs=1e-6)
            assert res["monotonicity_check"]["status"] in ("PASS", "NOT_TESTABLE")

    def test_negative_controls_live(self):
        from racewise.data.historical.counterfactual import (
            UNAVAILABLE,
            UNSUPPORTED,
            simulate_telemetry_counterfactual,
        )

        q = self._q()
        assert simulate_telemetry_counterfactual(
            q, 1950, 1, "giuseppe-farina", 1, "speed", "SCALE_SIGNAL", 0.05
        )["status"] == UNAVAILABLE
        assert simulate_telemetry_counterfactual(
            q, 2018, 1, "lewis-hamilton", 1, "speed", "SCALE_SIGNAL", 0.05
        )["status"] == UNAVAILABLE
        assert simulate_telemetry_counterfactual(
            q, 2023, 1, "max-verstappen", 999, "speed", "SCALE_SIGNAL", 0.05
        )["status"] == UNAVAILABLE
        assert simulate_telemetry_counterfactual(
            q, 2023, 1, "max-verstappen", 1, "throttle", "REMOVE_DEFICIT", 0.5,
            reference_driver="sergio-perez"
        )["status"] == UNSUPPORTED

    def test_determinism_live_repeat(self):
        from racewise.data.historical.counterfactual import (
            simulate_telemetry_counterfactual,
        )

        q = self._q()
        a = simulate_telemetry_counterfactual(
            q, 2023, 1, "sergio-perez", 1, "speed", "REMOVE_DEFICIT", 0.5,
            reference_driver="max-verstappen")
        b = simulate_telemetry_counterfactual(
            q, 2023, 1, "sergio-perez", 1, "speed", "REMOVE_DEFICIT", 0.5,
            reference_driver="max-verstappen")
        assert a["output_hash"] == b["output_hash"]


@requires_db
class TestInvestigationIntegration:
    def test_counterfactual_tool_inside_state_machine(self):
        from racewise.investigation.engine import InvestigationEngine, InvestigationState
        from racewise.tools.historical import build_historical_registry
        from racewise.data.historical.canonical_queries import get_canonical_queries

        reg = build_historical_registry(get_canonical_queries())
        eng = InvestigationEngine(
            reg, None,
            "Model sensitivity: what if PER closed half his speed deficit to VER "
            "on lap 1, 2023 R1?")

        def plan(e):
            res = e.run_tool("simulate_historical_telemetry_counterfactual", {
                "season": 2023, "round": 1, "driver": "sergio-perez",
                "reference_driver": "max-verstappen", "lap_number": 1,
                "signal": "speed", "intervention_type": "REMOVE_DEFICIT",
                "fraction": 0.5})
            assert "error" not in res, f"counterfactual tool failed: {res}"
            assert res["status"] == "VALID"

            e._set_state(InvestigationState.HYPOTHESIS_GENERATION)
            from racewise.domain.schemas import EvidenceType, Hypothesis, HypothesisStatus

            e.add_hypothesis(Hypothesis(
                id="6i-model-sensitivity",
                statement="The fixed-distance lap-time model responds materially to a "
                          "50% removal of the measured speed deficit (model sensitivity, "
                          "not a historical claim)",
                required_evidence=[],
                potential_falsifiers=[],
            ))
            obs = e.observe(
                "counterfactual_delta_s", res["counterfactual_delta_s"], "s",
                "counterfactual_model", "counterfactual_v1",
                tool_execution_id=e.tool_executions[-1].id,
            )

            e._set_state(InvestigationState.EVIDENCE_COLLECTION)
            e.add_evidence(
                statement=(
                    f"Under REMOVE_DEFICIT f=0.5 the modeled lap time changes by "
                    f"{res['counterfactual_delta_s']} s (baseline reproduction error "
                    f"{res['model']['baseline_reproduction']['error_s']} s) - model "
                    "sensitivity under a specified deterministic intervention."),
                type_=EvidenceType.COUNTERFACTUAL,
                observation_ids=[obs.id],
                tool_execution_id=e.tool_executions[-1].id,
                supports=["6i-model-sensitivity"],
                strength=0.6,
            )

            e._set_state(InvestigationState.FALSIFICATION)
            # honest contradiction: sensitivity is not causality, and the full-
            # removal model delta need not equal the measured lap delta
            e.set_status("6i-model-sensitivity", HypothesisStatus.SUPPORTED)
            e.add_evidence(
                statement=(
                    "A model-sensitivity result does not establish that the deficit "
                    "caused the historical gap; at full removal the model adopts the "
                    "reference trace over the target's distances, so the delta is a "
                    "model quantity and the Phase 6E residual applies."),
                type_=EvidenceType.CALCULATION,
                observation_ids=[obs.id],
                tool_execution_id=e.tool_executions[-1].id,
                contradicts=["6i-model-sensitivity"],
                strength=0.5,
            )
            e._set_state(InvestigationState.VERIFICATION)

        eng.run(plan)
        assert eng.state == InvestigationState.COMPLETED, f"ended {eng.state}; gate={eng.gate_failures()}"
        assert eng.gate_failures() == []
        assert eng.unsupported_claims() == []
