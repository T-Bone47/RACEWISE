"""Phase 6J Q12 benchmark tests: measured performance envelope semantics."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")


@pytest.fixture(scope="module")
def q12_report():
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.q12_benchmarks import run_q12

    return run_q12(get_canonical_queries(), include_mcp=True)


@requires_db
class TestQ12Matrix:
    def test_envelopes_valid(self, q12_report):
        for m in q12_report["matrix"]:
            assert m["envelope_status"] == "VALID", f"{m['season']} R{m['round']}"
            assert m["laps_in_band"] >= 3  # multi-lap measured band

    def test_baseline_identity(self, q12_report):
        for m in q12_report["matrix"]:
            assert m["reproduction"]["error_s"] == 0.0
            assert m["reproduction"]["exact"] is True
            assert m["identity_delta_s"] == 0.0

    def test_sweeps_valid_monotonic_nonlinear(self, q12_report):
        for m in q12_report["matrix"]:
            assert m["sweep_status"] == "VALID"
            assert m["response_status"] == "MONOTONIC"
            assert m["response_nonlinear"] is True  # measured, not assumed linear
            deltas = [d for _p, d in m["sweep_deltas"]]
            assert deltas[0] == 0.0
            assert all(deltas[i] >= deltas[i + 1] - 1e-9 for i in range(len(deltas) - 1))

    def test_regional_sensitivity_present(self, q12_report):
        for m in q12_report["matrix"]:
            assert m["regional_top3"] is not None
            assert 1 <= len(m["regional_top3"]) <= 3

    def test_stint_scope(self, q12_report):
        for m in q12_report["matrix"]:
            if m["stint_status"] == "VALID":
                assert m["stint_scope"] == "stint"
                assert m["stint_number"] in (1, 2, 3)

    def test_evidence_integration_keeps_objects_distinct(self, q12_report):
        for m in q12_report["matrix"]:
            h1 = m["h1_integration"]
            assert "neither establishes historical causality" in h1["epistemics"]
            assert h1["model_sensitivity_status"] == "VALID"
            if "evidence_verdict" in h1:
                assert h1["evidence_verdict"] in (
                    "SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED",
                    "NOT_SUPPORTED", "NOT_TESTABLE", "INSUFFICIENT_EVIDENCE",
                )

    def test_replay_deterministic(self, q12_report):
        for m in q12_report["matrix"]:
            assert m["replay_envelope"] is True
            assert m["replay_sweep"] is True


@requires_db
class TestQ12NegativeControls:
    def test_all_negative_controls_hold(self, q12_report):
        nc = q12_report["negative_controls"]
        assert nc["1950"] == "UNAVAILABLE"
        assert nc["2018"] == "UNAVAILABLE"
        assert nc["missing_driver"] == "UNAVAILABLE"
        assert nc["missing_reference"] == "UNAVAILABLE"
        assert nc["same_driver"] == "INVALID"
        assert nc["bad_scenario_type"] == "UNSUPPORTED"
        assert nc["param_out_of_bounds"] == "INVALID"
        assert nc["observed_with_parameter"] == "INVALID"
        assert nc["nonexistent_stint"] == "INSUFFICIENT_EVIDENCE"

    def test_mcp_verification(self, q12_report):
        mcp = q12_report["mcp"]
        assert mcp["tool_registered"] is True
        assert mcp["registry_status"] == "VALID"
        for key in ("max_scenarios_99", "max_laps_99", "segment_s_99",
                    "parameter_oob", "bad_scenario", "unknown_param"):
            assert mcp[key].startswith("REJECTED"), f"{key}: {mcp[key]}"
        assert mcp["1950"] == "UNAVAILABLE"

    def test_full_replay_deterministic(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.data.historical.q12_benchmarks import run_q12

        rep = run_q12(get_canonical_queries(), include_mcp=False)
        for m in rep["matrix"]:
            assert m["replay_envelope"] is True
            assert m["replay_sweep"] is True
