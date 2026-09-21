"""Phase 6I Q11 benchmark tests: validated telemetry counterfactual semantics.

Asserts the deterministic semantics of the Q11 matrix on real canonical data
(skipped when the DB is absent) and the pure negative-control expectations.
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
def q11_report():
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.q11_benchmarks import run_q11

    return run_q11(get_canonical_queries(), include_mcp=True)


@requires_db
class TestQ11Matrix:
    def test_matrix_rows_valid(self, q11_report):
        for m in q11_report["matrix"]:
            assert m["status"] == "VALID", f"{m['season']} R{m['round']}: {m.get('reason')}"

    def test_sensitivity_curves_monotone(self, q11_report):
        for m in q11_report["matrix"]:
            assert m["monotone_non_increasing_delta"] is True

    def test_baseline_reproduction_exact(self, q11_report):
        for m in q11_report["matrix"]:
            br = m["baseline_reproduction"]
            assert br["error_s"] == 0.0
            assert br["identity_delta_s"] == 0.0
            assert br["all_gates_pass"] is True

    def test_replay_identical(self, q11_report):
        for m in q11_report["matrix"]:
            assert m["replay_identical"] is True

    def test_brake_interventions_unsupported(self, q11_report):
        for m in q11_report["matrix"]:
            assert m["brake_intervention_status"] == "UNSUPPORTED"

    def test_stint_level_holds(self, q11_report):
        for m in q11_report["matrix"]:
            st = m["stint"]
            if st["status"] == "VALID":
                assert st["laps_valid"] >= 3
                assert st["monotonicity_check"] == "PASS"
                assert st["mean_delta_s"] is not None
            else:
                assert st["status"] in ("INSUFFICIENT_EVIDENCE", "UNAVAILABLE")

    def test_h1_integration_keeps_objects_distinct(self, q11_report):
        for m in q11_report["matrix"]:
            h1 = m["h1_integration"]
            assert "neither establishes historical causality" in h1["epistemics"]
            assert h1["model_sensitivity_status"] == "VALID"
            # fusion on these laps may be VALID or INSUFFICIENT - either is
            # honest; the verdict must be a formal status when present
            if "evidence_verdict" in h1:
                assert h1["evidence_verdict"] in (
                    "SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED",
                    "NOT_SUPPORTED", "NOT_TESTABLE", "INSUFFICIENT_EVIDENCE",
                )


@requires_db
class TestQ11NegativeControls:
    def test_all_negative_controls_hold(self, q11_report):
        nc = q11_report["negative_controls"]
        assert nc["all_expected"] is True
        assert nc["1950"] == "UNAVAILABLE"
        assert nc["2018"] == "UNAVAILABLE"
        assert nc["missing_driver"] == "UNAVAILABLE"
        assert nc["absent_lap"] == "UNAVAILABLE"
        assert nc["fraction_out_of_bounds_status"] == "INVALID"
        assert nc["nan_fraction_status"] == "INVALID"
        assert nc["gear_intervention_status"] == "UNSUPPORTED"
        assert nc["unknown_intervention_status"] == "UNSUPPORTED"

    def test_mcp_verification(self, q11_report):
        mcp = q11_report["mcp"]
        assert mcp["tool_registered"] is True
        assert mcp["registry_status"] == "VALID"
        for key in ("fraction_99", "segment_s_99", "bad_signal", "unknown_param"):
            assert mcp[key].startswith("REJECTED"), f"{key}: {mcp[key]}"

    def test_full_replay_deterministic(self):
        """Q11.14-adjacent: a fresh module-level run reproduces hashes."""
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.data.historical.q11_benchmarks import run_q11

        rep = run_q11(get_canonical_queries(), include_mcp=False)
        for m in rep["matrix"]:
            assert m["replay_identical"] is True
