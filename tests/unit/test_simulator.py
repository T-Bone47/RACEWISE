"""Simulator tests: pit-timing counterfactual against known structure."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from racewise.simulator.strategy import simulate_pit_timing
from racewise.domain.schemas import Lap


def _laps(driver: str = "VER") -> list[Lap]:
    return [Lap(session_key="s", driver=driver, lap_number=i, lap_time_s=97.5) for i in range(1, 58)]


def test_earlier_pit_costs_time_without_undercut():
    result = simulate_pit_timing(
        _laps(), "VER", original_pit_lap=14, counterfactual_pit_lap=10,
        pit_loss_s=24.0, degradation_s_per_lap=0.05, laps_remaining=57,
    )
    assert result["simulator_version"] == "1.0.0"
    # Deterministic: earlier pit => every post-pit lap runs 4 tyre-laps older.
    # Age-lap diff = [sum(0..9)+sum(1..47)] - [sum(0..13)+sum(1..43)] = 136
    # delta = 0.05 * 136 = 6.8s against the counterfactual.
    assert result["predicted_delta_s"] == 6.8


def test_pit_loss_dominates():
    result = simulate_pit_timing(
        _laps(), "VER", original_pit_lap=14, counterfactual_pit_lap=13,
        pit_loss_s=24.0, degradation_s_per_lap=0.5, laps_remaining=57,
    )
    # One lap earlier on a deg-running tyre: counterfactual should lose (more wear laps)
    assert result["counterfactual_cost_s"] >= result["baseline_cost_s"]


def test_assumptions_and_uncertainty_present():
    result = simulate_pit_timing(
        _laps(), "VER", original_pit_lap=36, counterfactual_pit_lap=31,
        pit_loss_s=24.2, degradation_s_per_lap=0.08, laps_remaining=57,
        traffic_assumption_s_per_lap=0.3,
    )
    assert len(result["assumptions"]) == 4
    assert result["uncertainty_s"] >= 0.5
    assert "COUNTERFACTUAL" not in result  # labeling is the caller's job; model reports numbers only


def test_no_laps_raises():
    try:
        simulate_pit_timing([], "VER", 14, 10, pit_loss_s=24, degradation_s_per_lap=0.1, laps_remaining=57)
        raised = False
    except ValueError:
        raised = True
    assert raised
