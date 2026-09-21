"""Phase 6J tests: measured performance envelope & bounded scenario sweeps.

Pure-math tests use a stub query object (no DB). Live-store tests run only
when the canonical DB exists and validate real data across the 2022-2025
matrix plus investigation-engine integration.
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
# pure-math: bounded sample + response classification
# ---------------------------------------------------------------------------


class TestPureMath:
    def test_bounded_sample_preserves_order_and_bounds(self):
        from racewise.data.historical.performance_envelope import _bounded_sample

        laps = list(range(10, 30))
        out = _bounded_sample(laps, 6)
        assert len(out) == 6
        assert out == sorted(out)
        assert all(l in laps for l in out)
        # small input passes through
        assert _bounded_sample([1, 2, 3], 6) == [1, 2, 3]

    def test_response_monotonic(self):
        from racewise.data.historical.performance_envelope import _classify_response

        r = _classify_response([0.0, -1.0, -2.0, -3.0])
        assert r["status"] == "MONOTONIC"

    def test_response_non_monotonic(self):
        from racewise.data.historical.performance_envelope import _classify_response

        r = _classify_response([0.0, -1.0, -0.5, -2.0])
        assert r["status"] == "NON_MONOTONIC"

    def test_response_flat(self):
        from racewise.data.historical.performance_envelope import _classify_response

        r = _classify_response([0.0, 0.0, 0.0])
        assert r["status"] == "FLAT"

    def test_response_insufficient(self):
        from racewise.data.historical.performance_envelope import _classify_response

        assert _classify_response([0.0, -1.0])["status"] == "INSUFFICIENT_DATA"

    def test_linspace_bounded(self):
        from racewise.data.historical.performance_envelope import _linspace

        out = _linspace(0.0, 1.0, 11)
        assert len(out) == 11
        assert out[0] == 0.0 and out[-1] == 1.0


# ---------------------------------------------------------------------------
# stub end-to-end
# ---------------------------------------------------------------------------


class _StubQueries:
    """Two drivers with deterministic multi-lap speed profiles."""

    def __init__(self) -> None:
        self.clean_laps = [2, 4, 6, 8]

    def get_lap_times(self, season, round_num, session_type, driver):
        return [
            {"lap_number": ln, "time_s": 90.0 + 0.1 * ln, "is_pit_in_lap": 0,
             "is_pit_out_lap": 0, "deleted": 0, "track_status": "1",
             "is_accurate": 1, "compound": "MEDIUM", "stint": 1, "tyre_life": ln}
            for ln in (1, 2, 4, 6, 8, 10)
        ]

    def get_weather(self, season, round_num, session_type="RACE"):
        return []  # no rainfall observations in the fixture

    def telemetry_summary(self, season, round_num, session_type="RACE"):
        return {"available": True, "laps": [1, 2, 4, 6, 8, 10], "sample_count": 600}

    def get_lap_telemetry(self, season, round_num, driver_key, lap_number,
                          session_type="RACE", signals=None, max_samples=2000):
        n = 400  # 100 s span at 0.25 s
        rows = []
        for i in range(n):
            t = round(i * 0.25, 4)
            speed = 200.0 + 30.0 * math.sin(0.05 * i)
            if driver_key == "slow-driver":
                speed -= 10.0 + 0.05 * lap_number  # lap-dependent measured deficit
            rows.append({"lap_number": lap_number, "lap_time_s": t, "value": speed})
        return rows


class TestStubEndToEnd:
    def _q(self) -> _StubQueries:
        return _StubQueries()

    def test_envelope_fast_driver_valid_too(self):
        from racewise.data.historical.performance_envelope import build_performance_envelope

        env = build_performance_envelope(self._q(), 2023, 1, "fast-driver")
        assert env["status"] == "VALID"

    def test_envelope_valid_with_exact_reproduction(self):
        from racewise.data.historical.performance_envelope import build_performance_envelope

        env = build_performance_envelope(self._q(), 2023, 1, "slow-driver")
        assert env["status"] == "VALID"
        assert env["laps_in_band"] == 6  # all stub laps clean + covered, max_laps=6
        assert env["model_baseline"]["reproduction_error_s"] == 0.0
        assert env["envelope_summary"]["mean_band_width_kmh"] > 0.0

    def test_scenario_sweep_monotone(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope,
        )

        res = analyze_performance_envelope(
            self._q(), 2023, 1, "slow-driver", "DEFICIT_REDUCTION",
            reference_driver="fast-driver", max_scenarios=5)
        assert res["status"] == "VALID"
        deltas = [s["delta_s"] for s in res["scenarios"]]
        assert all(deltas[i] >= deltas[i + 1] - 1e-9 for i in range(len(deltas) - 1))
        assert res["sensitivity"]["response"]["status"] in ("MONOTONIC", "FLAT")
        assert res["regional_response"] is not None

    def test_observed_identity_is_exactly_zero(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope,
        )

        res = analyze_performance_envelope(self._q(), 2023, 1, "slow-driver", "OBSERVED")
        assert res["status"] == "VALID"
        assert res["scenarios"][0]["delta_s"] == 0.0

    def test_envelope_bounds_scenarios(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope,
        )

        lo = analyze_performance_envelope(self._q(), 2023, 1, "slow-driver", "ENVELOPE_LOWER_BOUND")
        hi = analyze_performance_envelope(self._q(), 2023, 1, "slow-driver", "ENVELOPE_UPPER_BOUND")
        assert lo["scenarios"][0]["delta_s"] > 0.0   # slowest form -> slower model
        assert hi["scenarios"][0]["delta_s"] < 0.0   # fastest form -> faster model

    def test_unknown_scenario_unsupported(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope,
        )

        res = analyze_performance_envelope(self._q(), 2023, 1, "slow-driver", "TELEPORT")
        assert res["status"] == "UNSUPPORTED"

    def test_out_of_bounds_parameter_invalid(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope,
        )

        res = analyze_performance_envelope(
            self._q(), 2023, 1, "slow-driver", "DEFICIT_REDUCTION", 1.5,
            reference_driver="fast-driver")
        assert res["status"] == "INVALID"

    def test_reference_required(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope,
        )

        res = analyze_performance_envelope(self._q(), 2023, 1, "slow-driver", "DEFICIT_REDUCTION")
        assert res["status"] == "INVALID"
        same = analyze_performance_envelope(
            self._q(), 2023, 1, "slow-driver", "DEFICIT_REDUCTION", 0.5,
            reference_driver="slow-driver")
        assert same["status"] == "INVALID"

    def test_determinism_stub(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope, build_performance_envelope,
        )

        a = build_performance_envelope(self._q(), 2023, 1, "slow-driver")
        b = build_performance_envelope(self._q(), 2023, 1, "slow-driver")
        assert a["output_hash"] == b["output_hash"]
        ra = analyze_performance_envelope(
            self._q(), 2023, 1, "slow-driver", "DEFICIT_REDUCTION",
            reference_driver="fast-driver")
        rb = analyze_performance_envelope(
            self._q(), 2023, 1, "slow-driver", "DEFICIT_REDUCTION",
            reference_driver="fast-driver")
        assert ra["output_hash"] == rb["output_hash"]

    def test_epistemics_language(self):
        from racewise.data.historical.performance_envelope import build_performance_envelope

        env = build_performance_envelope(self._q(), 2023, 1, "slow-driver")
        assert "not an ideal lap" in env["epistemics"]
        assert "not a prediction" in env["epistemics"]


# ---------------------------------------------------------------------------
# live-store tests
# ---------------------------------------------------------------------------


@requires_db
class TestLiveEnvelope:
    def _q(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries

        return get_canonical_queries()

    def test_envelope_valid_exact_reproduction(self):
        from racewise.data.historical.performance_envelope import build_performance_envelope

        env = build_performance_envelope(self._q(), 2023, 1, "sergio-perez")
        assert env["status"] == "VALID"
        assert env["model_baseline"]["reproduction_error_s"] == 0.0
        assert env["laps_in_band"] >= 3

    def test_sweep_monotone_nonlinear(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope,
        )

        res = analyze_performance_envelope(
            self._q(), 2023, 1, "sergio-perez", "DEFICIT_REDUCTION",
            reference_driver="max-verstappen", max_scenarios=5)
        assert res["status"] == "VALID"
        assert res["sensitivity"]["response"]["status"] == "MONOTONIC"
        assert res["sensitivity"]["response"]["max_abs_second_difference_s"] > 0.0

    def test_negative_controls_live(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope, build_performance_envelope,
        )

        q = self._q()
        assert build_performance_envelope(q, 1950, 1, "giuseppe-farina")["status"] == "UNAVAILABLE"
        assert build_performance_envelope(q, 2018, 1, "lewis-hamilton")["status"] == "UNAVAILABLE"
        assert analyze_performance_envelope(
            q, 2023, 1, "sergio-perez", "DEFICIT_REDUCTION", 0.5,
            reference_driver="sergio-perez")["status"] == "INVALID"
        assert analyze_performance_envelope(
            q, 2023, 1, "sergio-perez", "TELEPORT")["status"] == "UNSUPPORTED"

    def test_stint_scope_live(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope,
        )

        res = analyze_performance_envelope(
            self._q(), 2023, 1, "sergio-perez", "DEFICIT_REDUCTION", 0.5,
            reference_driver="max-verstappen", stint_number=2, max_laps=6)
        assert res["status"] == "VALID"
        assert res["envelope"]["scope"] == "stint"
        assert "excluded_laps" in res
        if res.get("stint_response"):
            assert len(res["stint_response"]["per_lap"]) >= 3

    def test_determinism_live(self):
        from racewise.data.historical.performance_envelope import (
            analyze_performance_envelope, build_performance_envelope,
        )

        q = self._q()
        a = build_performance_envelope(q, 2023, 1, "sergio-perez")
        b = build_performance_envelope(q, 2023, 1, "sergio-perez")
        assert a["output_hash"] == b["output_hash"]
        ra = analyze_performance_envelope(
            q, 2023, 1, "sergio-perez", "DEFICIT_REDUCTION",
            reference_driver="max-verstappen")
        rb = analyze_performance_envelope(
            q, 2023, 1, "sergio-perez", "DEFICIT_REDUCTION",
            reference_driver="max-verstappen")
        assert ra["output_hash"] == rb["output_hash"]


@requires_db
class TestInvestigationIntegration:
    def test_envelope_tool_inside_state_machine(self):
        from racewise.investigation.engine import InvestigationEngine, InvestigationState
        from racewise.tools.historical import build_historical_registry
        from racewise.data.historical.canonical_queries import get_canonical_queries

        reg = build_historical_registry(get_canonical_queries())
        eng = InvestigationEngine(
            reg, None,
            "How sensitive is PER's measured envelope to closing the speed "
            "deficit to VER across 2023 R1?")

        def plan(e):
            res = e.run_tool("analyze_historical_performance_envelope", {
                "season": 2023, "round": 1, "driver": "sergio-perez",
                "reference_driver": "max-verstappen",
                "scenario_type": "DEFICIT_REDUCTION", "parameter": 0.5})
            assert "error" not in res, f"envelope tool failed: {res}"
            assert res["status"] == "VALID"

            e._set_state(InvestigationState.HYPOTHESIS_GENERATION)
            from racewise.domain.schemas import EvidenceType, Hypothesis, HypothesisStatus

            e.add_hypothesis(Hypothesis(
                id="6j-envelope-sensitivity",
                statement="The validated lap-time model responds materially across "
                          "the measured envelope to the specified bounded scenarios "
                          "(model sensitivity, not a historical claim)",
                required_evidence=[],
                potential_falsifiers=[],
            ))
            obs = e.observe(
                "sweep_range_s", res["sensitivity"]["response"]["total_range_s"], "s",
                "performance_envelope_model", "envelope_v1",
                tool_execution_id=e.tool_executions[-1].id,
            )
            e._set_state(InvestigationState.EVIDENCE_COLLECTION)
            e.add_evidence(
                statement=(
                    f"Sweep over the measured envelope changes the modeled lap time by "
                    f"{res['sensitivity']['response']['total_range_s']} s across the "
                    f"parameter grid ({res['sensitivity']['response']['status']} response) "
                    "- model sensitivity under specified interventions."),
                type_=EvidenceType.COUNTERFACTUAL,
                observation_ids=[obs.id],
                tool_execution_id=e.tool_executions[-1].id,
                supports=["6j-envelope-sensitivity"],
                strength=0.6,
            )
            e._set_state(InvestigationState.FALSIFICATION)
            e.set_status("6j-envelope-sensitivity", HypothesisStatus.SUPPORTED)
            e.add_evidence(
                statement=(
                    "Envelope sensitivity measures the model's response to a bounded "
                    "intervention; it does not establish that the deficit caused any "
                    "historical outcome, and the envelope is measured variability, "
                    "not an ideal lap."),
                type_=EvidenceType.CALCULATION,
                observation_ids=[obs.id],
                tool_execution_id=e.tool_executions[-1].id,
                contradicts=["6j-envelope-sensitivity"],
                strength=0.5,
            )
            e._set_state(InvestigationState.VERIFICATION)

        eng.run(plan)
        assert eng.state == InvestigationState.COMPLETED, f"ended {eng.state}; gate={eng.gate_failures()}"
        assert eng.gate_failures() == []
        assert eng.unsupported_claims() == []
