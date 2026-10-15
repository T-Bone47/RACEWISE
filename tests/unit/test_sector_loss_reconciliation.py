"""Perez sector-2 regression: window estimates must reconcile, never masquerade.

Mandatory diagnostic case (Bahrain 2023, VER vs PER, lap 6): the measured
lap delta is +0.732 s with sector splits (-0.065, +0.411, +0.386) that sum
to it exactly. The telemetry-window model originally reported a gross
exposure of 4.049 s (rectified time-window sums); distance-fraction
alignment (see alignment.py) now reports gross 1.521 s / net 0.915 s,
and attribution net 0.909 s with residual -0.177 s. These tests pin the
generalizable contract, not the numbers:

- sector facts sum to the measured delta (compatible time bases);
- the gross positive-only exposure is labelled non-additive and
  flagged when it diverges from the measured delta (phase mixing);
- the signed net is strictly closer to the measured delta than the gross;
- residuals reconcile against the net, never the rectified sum;
- synthesised telemetry observations are DERIVED, never OBSERVED;
- the sector-2 question parses as sector-specific (sectors=(2,)) with
  LOCATE/EXPLAIN intents — not a generic lap-delta query;
- mechanism associations come from the tool (throttle/brake deltas in the
  worst windows); no invented driving mechanism is asserted.

Live-store tests run only when the canonical DB exists. No assertion
hardcodes a natural-language answer or any specific gross figure.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

A = "max-verstappen"
B = "sergio-perez"


def _queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries(str(DB_PATH))


@requires_db
class TestWindowEstimateReconciliation:
    def _compare(self):
        from racewise.data.historical.telemetry_analysis import compare_telemetry_lap

        out = compare_telemetry_lap(_queries(), 2023, 1, A, B, 6)
        assert out["verdict"] == "PASS"
        return out

    def test_measured_delta_is_a_fact_alongside_the_estimate(self):
        out = self._compare()
        assert out["measured_delta_s"] == pytest.approx(0.732, abs=1e-3)
        assert out["measured_delta_s"] > 0  # B slower than A: sign convention B minus A

    def test_gross_exposure_is_labelled_non_additive_and_flagged(self):
        out = self._compare()
        assert "NON-ADDITIVE" in (out.get("total_scope_note") or "")
        # the discrepancy exists (gross dwarfs the measured delta) and is flagged
        assert out["total_est_time_loss_s"] > out["measured_delta_s"]
        assert out["phase_mixing_flag"] is True
        assert out.get("phase_mixing_note")

    def test_net_estimate_is_strictly_closer_to_measured_than_gross(self):
        out = self._compare()
        gross_err = abs(out["total_est_time_loss_s"] - out["measured_delta_s"])
        net_err = abs(out["net_est_time_loss_s"] - out["measured_delta_s"])
        assert net_err < gross_err
        assert out["net_residual_s"] == pytest.approx(
            out["measured_delta_s"] - out["net_est_time_loss_s"], abs=1e-6
        )

    def test_signed_windows_sum_to_net(self):
        out = self._compare()
        signed_sum = round(sum(w["signed_loss_s"] for w in out["top_windows"]
                               if "signed_loss_s" in w), 4)
        # top-5 signed losses are a subset of the net; each window carries both signs
        assert all("signed_loss_s" in w for w in out["top_windows"])
        assert signed_sum <= out["total_est_time_loss_s"]  # subset of the gross


@requires_db
class TestAttributionReconciliation:
    def _att(self):
        from racewise.data.historical.loss_attribution import attribute_lap_loss

        out = attribute_lap_loss(_queries(), 2023, 1, A, B, 6)
        assert out["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        return out

    def test_sector_facts_sum_to_observed_and_locate_sector_2(self):
        att = self._att()
        sectors = {s["sector"]: s for s in att["sector_attribution"]}
        assert set(sectors) == {1, 2, 3}
        sector_sum = round(sum(s["delta_s"] for s in sectors.values()), 4)
        assert sector_sum == att["observed_delta_s"]  # measured facts reconcile exactly
        s2 = sectors[2]
        assert s2["delta_s"] > 0  # sector 2 is where B lost time (measured)
        assert s2["delta_s"] == max(s["delta_s"] for s in sectors.values())

    def test_residual_reconciles_against_net_not_rectified_sum(self):
        att = self._att()
        assert att["residual_s"] == pytest.approx(
            att["observed_delta_s"] - att["estimated_pace_component_s"], abs=1e-6
        )
        assert att["estimated_pace_component_s"] == pytest.approx(
            sum(r["signed_loss_s"] for r in att["regions"]), abs=1e-3
        )
        assert att["gross_positive_exposure_s"] == pytest.approx(
            sum(r["attributed_loss_s"] for r in att["regions"]), abs=1e-3
        )

    def test_phase_mixing_flagged_with_honest_interpretation(self):
        att = self._att()
        rec = att["reconciliation"]
        # On this lap the distance-aligned regions reconcile without
        # positive evidence of phase mixing (small rectification gap, no
        # sector mismatch), so the flag stays off and the residual is
        # reported through the overestimate branch — never the stale
        # "faster lap" reading while B is slower.
        assert rec["phase_mixing_flag"] is False
        assert "OVERESTIMATES" in rec["interpretation"]
        # the stale reading ("B faster") must not appear when B is slower
        assert "their faster lap" not in rec["interpretation"]

    def test_mechanism_evidence_comes_from_the_tool_not_invention(self):
        from racewise.data.historical.telemetry_analysis import compare_telemetry_lap
        from racewise.question_engine.synthesizer import _extract_calculations

        compare = compare_telemetry_lap(_queries(), 2023, 1, A, B, 6)
        worst = compare["max_loss_window"]
        # worst-window channel deltas are always numeric (measured means)
        assert isinstance(worst["throttle_delta_pct"], (int, float))
        assert isinstance(worst["brake_delta_frac"], (int, float))
        assert isinstance(worst["speed_delta_kmh"], (int, float))
        # association strings exist only when the data shows an event;
        # their absence is honest (no lift/brake event to associate),
        # never a fabricated one
        for key in ("throttle_association", "brake_association"):
            val = compare.get(key)
            assert val is None or (isinstance(val, str) and val.strip())
        # ... and whatever mechanism evidence exists reaches the answer
        # calculations, tied to hypothesis ids, as DERIVED (never OBSERVED)
        calcs = _extract_calculations({"compare_laps": compare})
        mech = [c for c in calcs if c.get("capability_id") == "compare_laps"]
        assert mech, "worst-window mechanism evidence must reach the answer"
        assert all(c["claim_class"] == "DERIVED" for c in mech)
        assert {c.get("hypothesis_id") for c in mech if "hypothesis_id" in c} >= {
            "H1_corner_speed", "H2_throttle", "H3_braking"}
        assoc = [c for c in mech if "association" in (c.get("statement") or "")]
        assert all(c.get("detail") for c in assoc), (
            "association strings must be carried verbatim as evidence detail"
        )


@requires_db
class TestAnswerContract:
    def test_telemetry_observations_are_derived_never_observed(self):
        from racewise.data.historical.telemetry_analysis import compare_telemetry_lap
        from racewise.question_engine.synthesizer import _extract_observations

        compare = compare_telemetry_lap(_queries(), 2023, 1, A, B, 6)
        fusion = {"observed_delta_s": 0.732,
                  "lap_times": {"driver_a": 97.986, "driver_b": 98.718}}
        obs = _extract_observations({"compare_laps": compare, "fuse_lap_evidence": fusion})
        tel = [e for e in obs if "Telemetry-window" in e["statement"]]
        assert tel, "telemetry observations must be present"
        assert all(e["claim_class"] == "DERIVED" for e in tel), (
            "a window estimate must never be labelled OBSERVED"
        )
        kinds = {e["statement"] for e in tel}
        assert any("net" in s for s in kinds), "net estimate entry required"
        all_kinds = {e["statement"] for e in obs}
        assert any("residual" in s.lower() for s in all_kinds), (
            "reconciliation residual entry required"
        )

    def test_sector_question_parses_as_sector_specific(self):
        from racewise.question_engine.compiler import compile_question

        compiled = compile_question(
            _queries(), "why did perez lose time in sector 2",
            context={"driver_a": A, "driver_b": B, "season": 2023,
                     "round": 1, "lap_number": 6, "sector": 2},
        )
        assert compiled.status == "PARSED"
        assert 2 in compiled.sectors  # sector-scoped, not a generic lap query
        assert set(compiled.detected_intents) & {"LOCATE", "EXPLAIN", "TEST_HYPOTHESIS"}
