"""Deterministic strategy counterfactual simulator.

Simple, explicit, assumption-driven scenario model. NOT a physics simulator:
it replays observed lap times, applies interventions, and reports deltas
under stated assumptions with uncertainty. Always labeled COUNTERFACTUAL.
"""
from __future__ import annotations

from typing import Any, Optional

from racewise.domain.schemas import Lap

SIMULATOR_VERSION = "1.0.0"

# Compounds and typical Bahrain-wear offsets (s/lap relative to HARD at equal age);
# explicit modeling assumptions, tunable per scenario.
COMPOUND_PACE_OFFSETS = {"SOFT": 0.35, "MEDIUM": 0.15, "HARD": 0.0}


def simulate_pit_timing(
    laps: list[Lap],
    driver: str,
    original_pit_lap: int,
    counterfactual_pit_lap: int,
    *,
    pit_loss_s: float,
    degradation_s_per_lap: float,
    laps_remaining: int,
    traffic_assumption_s_per_lap: float = 0.0,
) -> dict[str, Any]:
    """Compare original vs counterfactual pit lap over remaining race distance.

    Model: stint pace = baseline pace + degradation * tyre_age; pit adds
    pit_loss_s once; clean-air delta applies traffic_assumption after the
    earlier pit (undercut effect is scenario-specific, kept explicit here).
    Returns predicted delta (negative = counterfactual gains time).
    """
    driver_laps = [lap for lap in laps if lap.driver == driver and lap.lap_time_s is not None]
    if not driver_laps:
        raise ValueError(f"No timed laps for {driver}")

    baseline_times = sorted(lap.lap_time_s for lap in driver_laps)
    baseline_pace = baseline_times[len(baseline_times) // 2]  # median clean-ish pace

    def stint_cost(pit_lap: int) -> float:
        """Total time from lap 1 to laps_remaining under a given pit lap."""
        total = 0.0
        for lap_number in range(1, laps_remaining + 1):
            age_in_stint = lap_number - pit_lap if lap_number > pit_lap else lap_number - 1
            total += baseline_pace + degradation_s_per_lap * age_in_stint
            if lap_number == pit_lap:
                total += pit_loss_s
        return total

    original_cost = stint_cost(original_pit_lap)
    counterfactual_cost = stint_cost(counterfactual_pit_lap)
    traffic_adjustment = traffic_assumption_s_per_lap * abs(original_pit_lap - counterfactual_pit_lap)
    predicted_delta = round(counterfactual_cost - original_cost + traffic_adjustment, 4)

    return {
        "intervention": f"pit lap {original_pit_lap} -> {counterfactual_pit_lap}",
        "predicted_delta_s": predicted_delta,
        "uncertainty_s": round(max(0.5, 0.1 * abs(counterfactual_pit_lap - original_pit_lap)), 4),
        "assumptions": [
            f"pit loss {pit_loss_s}s",
            f"degradation {degradation_s_per_lap}s/lap linear",
            f"median pace {baseline_pace:.3f}s as baseline",
            f"traffic effect {traffic_assumption_s_per_lap}s/lap on stints after earlier stop",
        ],
        "baseline_cost_s": round(original_cost, 4),
        "counterfactual_cost_s": round(counterfactual_cost, 4),
        "simulator_version": SIMULATOR_VERSION,
    }
