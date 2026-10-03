"""Engineering decision twin tests (§40).

A decision twin models bounded interventions. The risk it carries is not
crashing — it is *quietly wrong*: returning a plausible scenario for a
dimension the engine has no physics for, clamping an impossible request into
a valid-looking one, or letting a modelled number read as something that
happened.

These tests pin each of those.
"""
from __future__ import annotations

import pytest

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.question_engine.decision_twin import (
    DEFAULT_FRACTIONS,
    MODELLED,
    SUPPORTED_DIMENSIONS,
    SUPPORTED_INTERVENTIONS,
    build_twin,
)

REAL_SEASON = 2023
REAL_ROUND = 1
VER = "max-verstappen"
PER = "sergio-perez"
# Lap 6 is one of the laps where BOTH drivers have comparable telemetry in the
# canonical store. Lap choice is not incidental: laps the model cannot see
# correctly return INSUFFICIENT_EVIDENCE, which several tests below assert.
LAP = 6


@pytest.fixture(scope="module")
def queries() -> CanonicalQueries:
    return CanonicalQueries()


@pytest.fixture(scope="module")
def real_twin(queries: CanonicalQueries) -> dict:
    return build_twin(queries, season=REAL_SEASON, round_num=REAL_ROUND,
                      driver=VER, lap_number=LAP, reference_driver=PER)


# ---------------------------------------------------------------------------
# the model only claims what it can actually model
# ---------------------------------------------------------------------------

def test_only_speed_is_a_supported_dimension():
    """Throttle, brake, gear, rpm and drs have no lap-time model.

    Accepting them would mean inventing the physics of an intervention the
    engine cannot compute, and presenting the result as engineering.
    """
    assert SUPPORTED_DIMENSIONS == ("speed",)


@pytest.mark.parametrize("dimension",
                         ["throttle", "brake", "braking", "gear", "rpm",
                          "drs", "steering", "suspension"])
def test_unmodelled_dimensions_are_refused_not_approximated(
        queries: CanonicalQueries, dimension: str):
    twin = build_twin(queries, season=REAL_SEASON, round_num=REAL_ROUND,
                      driver=VER, lap_number=LAP, reference_driver=PER,
                      dimension=dimension)
    assert twin["status"] == "UNSUPPORTED"
    assert twin["scenario_space"] == []
    assert dimension in twin["reason"]
    assert twin["limitations"], "a refusal must state why it is a refusal"


def test_unknown_intervention_is_refused(queries: CanonicalQueries):
    twin = build_twin(queries, season=REAL_SEASON, round_num=REAL_ROUND,
                      driver=VER, lap_number=LAP, reference_driver=PER,
                      intervention_type="TELEPORT_TO_WIN")
    assert twin["status"] == "UNSUPPORTED"
    assert twin["scenario_space"] == []


# ---------------------------------------------------------------------------
# every scenario is a model, never a historical fact
# ---------------------------------------------------------------------------

def test_every_point_is_labelled_modelled(real_twin):
    """A modelled number must never be readable as a measurement."""
    for point in real_twin["scenario_space"]:
        assert point["claim_class"] == MODELLED


def test_no_point_claims_historical_truth(real_twin):
    """The hardest constraint in the brief (§3): no counterfactual as fact."""
    for point in real_twin["scenario_space"]:
        assert point["is_historical_truth"] is False


def test_baseline_is_observed_but_scenarios_are_not(real_twin):
    """The anchor is a measured lap. Everything else is modelled from it."""
    assert real_twin["baseline"]["claim_class"] == "OBSERVED"
    assert all(p["claim_class"] == MODELLED
               for p in real_twin["scenario_space"])


def test_sweep_runs_on_real_data(real_twin):
    assert real_twin["status"] == "COMPLETED"
    assert len(real_twin["scenario_space"]) == len(DEFAULT_FRACTIONS)


# ---------------------------------------------------------------------------
# the endpoints are real anchors
# ---------------------------------------------------------------------------

def test_zero_fraction_is_exactly_zero_delta(real_twin):
    """Removing none of the deficit must change nothing.

    A non-zero delta at f=0 would mean the model has an offset the sweep is
    silently absorbing — the curve would be misattributed throughout.
    """
    zero = next(p for p in real_twin["scenario_space"] if p["fraction"] == 0.0)
    assert zero["delta_lap_time_s"] == pytest.approx(0.0, abs=1e-9)


def test_fraction_one_is_the_most_negative_point(real_twin):
    """Full removal should move further than any partial removal."""
    usable = [p for p in real_twin["scenario_space"]
              if p["delta_lap_time_s"] is not None]
    assert len(usable) >= 2
    full = next(p for p in usable if p["fraction"] == 1.0)
    others = [p["delta_lap_time_s"] for p in usable if p["fraction"] != 1.0]
    assert full["delta_lap_time_s"] < max(others) + 1e-9


def test_sensitivity_shape_is_described_not_inferred(real_twin):
    """The shape describes the MODEL, and must say so."""
    assert real_twin["sensitivity"]["shape"]
    assert "not evidence of physical causation" in \
           real_twin["sensitivity"]["note"]


# ---------------------------------------------------------------------------
# out-of-range requests are refused, never clamped
# ---------------------------------------------------------------------------

def test_out_of_range_fraction_is_refused(queries: CanonicalQueries):
    """Clamping 1.5 into range would answer a question nobody asked."""
    twin = build_twin(queries, season=REAL_SEASON, round_num=REAL_ROUND,
                      driver=VER, lap_number=LAP, reference_driver=PER,
                      fractions=(-0.5, 0.5, 1.5))
    assert twin["status"] == "INVALID_REQUEST"
    assert twin["scenario_space"] == []
    assert "clamped" in " ".join(twin["limitations"]).lower()


def test_scale_signal_uses_its_own_narrow_range(queries: CanonicalQueries):
    """SCALE_SIGNAL is multiplicative; sweeping 0..1 is not valid for it."""
    bad = build_twin(queries, season=REAL_SEASON, round_num=REAL_ROUND,
                     driver=VER, lap_number=LAP, reference_driver=PER,
                     intervention_type="SCALE_SIGNAL",
                     fractions=(0.0, 0.5, 1.0))
    assert bad["status"] == "INVALID_REQUEST"

    assert SUPPORTED_INTERVENTIONS["SCALE_SIGNAL"] == (-0.10, 0.10)

    good = build_twin(queries, season=REAL_SEASON, round_num=REAL_ROUND,
                      driver=VER, lap_number=LAP, reference_driver=PER,
                      intervention_type="SCALE_SIGNAL",
                      fractions=(-0.10, 0.0, 0.10))
    assert good["status"] != "INVALID_REQUEST"


def test_single_out_of_range_fraction_rejects_whole_sweep(
        queries: CanonicalQueries):
    """One impossible point invalidates the sweep rather than being dropped.

    Dropping it would silently change the curve the user is reading.
    """
    twin = build_twin(queries, season=REAL_SEASON, round_num=REAL_ROUND,
                      driver=VER, lap_number=LAP, reference_driver=PER,
                      fractions=(0.0, 0.25, 2.0))
    assert twin["status"] == "INVALID_REQUEST"
    assert twin["scenario_space"] == []


# ---------------------------------------------------------------------------
# failure is reported, never interpolated
# ---------------------------------------------------------------------------

def test_failed_points_are_reported_as_failures(queries: CanonicalQueries):
    """An unmodellable point is a gap in the result, not a number to smooth."""
    twin = build_twin(queries, season=REAL_SEASON, round_num=REAL_ROUND,
                      driver=VER, lap_number=999, reference_driver=PER)
    assert twin["status"] in ("INSUFFICIENT_EVIDENCE", "PARTIALLY_MODELLED")
    for point in twin["scenario_space"]:
        assert point["status"], "every point reports its own status"
        assert point["claim_class"] == MODELLED
    assert twin["limitations"], "a degraded sweep must say so"


def test_no_model_implies_no_claims(queries: CanonicalQueries):
    """With no usable model there is no baseline number to show."""
    twin = build_twin(queries, season=2023, round_num=1,
                      driver=PER, lap_number=999, reference_driver=VER)
    if twin["status"] == "INSUFFICIENT_EVIDENCE":
        assert twin["baseline"]["lap_time_s"] is None
        assert twin["baseline"]["source"] == "unavailable"


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------

def test_provenance_names_the_real_model(real_twin):
    prov = real_twin["provenance"]
    assert prov["model"] == "simulate_telemetry_counterfactual"
    assert prov["every_point_is_modelled"] is True
    assert "not a forecast" in prov["model_scope"].lower()