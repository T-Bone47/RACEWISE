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


def simulate_compound_change(
    laps: list[Lap],
    driver: str,
    original_compound: str,
    counterfactual_compound: str,
    stint_start_lap: int,
    stint_end_lap: int,
    *,
    degradation_s_per_lap: float,
    laps_remaining: int,
) -> dict[str, Any]:
    """Compare original vs counterfactual tyre compound for a given stint window.

    Model: compound pace offset applies for each lap in the stint window;
    degradation accumulates from stint start. Returns predicted delta.
    """
    driver_laps = [lap for lap in laps if lap.driver == driver and lap.lap_time_s is not None]
    if not driver_laps:
        raise ValueError(f"No timed laps for {driver}")

    baseline_times = sorted(lap.lap_time_s for lap in driver_laps)
    baseline_pace = baseline_times[len(baseline_times) // 2]

    original_offset = COMPOUND_PACE_OFFSETS.get(original_compound.upper(), 0.0)
    counterfactual_offset = COMPOUND_PACE_OFFSETS.get(counterfactual_compound.upper(), 0.0)
    compound_delta_per_lap = counterfactual_offset - original_offset

    stint_laps_count = max(0, stint_end_lap - stint_start_lap + 1)
    compound_effect = compound_delta_per_lap * stint_laps_count

    # Degradation effect: counterfactual compound may degrade differently
    # For simplicity, assume same degradation rate; only compound offset differs
    predicted_delta = round(compound_effect, 4)

    return {
        "intervention": f"compound {original_compound} -> {counterfactual_compound} on laps {stint_start_lap}-{stint_end_lap}",
        "predicted_delta_s": predicted_delta,
        "uncertainty_s": round(max(0.5, 0.05 * stint_laps_count), 4),
        "assumptions": [
            f"compound pace offsets: {COMPOUND_PACE_OFFSETS}",
            f"degradation {degradation_s_per_lap}s/lap linear (same for both compounds)",
            f"median pace {baseline_pace:.3f}s as baseline",
            f"stint window: {stint_laps_count} laps",
        ],
        "compound_delta_per_lap_s": round(compound_delta_per_lap, 4),
        "stint_laps_count": stint_laps_count,
        "simulator_version": SIMULATOR_VERSION,
    }


def compare_strategy_scenarios(
    laps: list[Lap],
    driver: str,
    scenarios: list[dict[str, Any]],
    *,
    pit_loss_s: float,
    degradation_s_per_lap: float,
    laps_remaining: int,
    traffic_assumption_s_per_lap: float = 0.0,
) -> dict[str, Any]:
    """Compare multiple strategy scenarios against observed baseline.

    Each scenario dict may contain:
    - pit_laps: list[int] (pit stops)
    - compounds: list[str] (compound per stint)
    Returns ranked scenarios with deltas.
    """
    driver_laps = [lap for lap in laps if lap.driver == driver and lap.lap_time_s is not None]
    if not driver_laps:
        raise ValueError(f"No timed laps for {driver}")

    baseline_times = sorted(lap.lap_time_s for lap in driver_laps)
    baseline_pace = baseline_times[len(baseline_times) // 2]

    def scenario_cost(scenario: dict[str, Any]) -> float:
        pit_laps = sorted(scenario.get("pit_laps", []))
        compounds = scenario.get("compounds", ["HARD"])
        total = 0.0
        stint_num = 0
        for lap_number in range(1, laps_remaining + 1):
            # Determine current stint
            while stint_num < len(pit_laps) and lap_number > pit_laps[stint_num]:
                stint_num += 1
            compound = compounds[min(stint_num, len(compounds) - 1)]
            compound_offset = COMPOUND_PACE_OFFSETS.get(compound.upper(), 0.0)
            age_in_stint = lap_number - (pit_laps[stint_num - 1] if stint_num > 0 else 1)
            if stint_num == 0:
                age_in_stint = lap_number - 1
            total += baseline_pace + compound_offset + degradation_s_per_lap * age_in_stint
            if lap_number in pit_laps:
                total += pit_loss_s
        return total

    baseline_cost = scenario_cost({"pit_laps": [], "compounds": ["HARD"]})  # Simple baseline
    results = []
    for i, scenario in enumerate(scenarios):
        cost = scenario_cost(scenario)
        delta = round(cost - baseline_cost, 4)
        results.append({
            "scenario_id": f"S{i+1}",
            "intervention": f"pits={scenario.get('pit_laps', [])}, compounds={scenario.get('compounds', ['HARD'])}",
            "predicted_delta_s": delta,
            "uncertainty_s": round(max(0.5, 0.1 * len(scenario.get('pit_laps', []))), 4),
        })

    results.sort(key=lambda x: x["predicted_delta_s"])
    return {
        "baseline_cost_s": round(baseline_cost, 4),
        "scenarios": results,
        "assumptions": [
            f"pit loss {pit_loss_s}s",
            f"degradation {degradation_s_per_lap}s/lap linear",
            f"compound offsets: {COMPOUND_PACE_OFFSETS}",
            f"median pace {baseline_pace:.3f}s as baseline",
            f"traffic effect {traffic_assumption_s_per_lap}s/lap",
        ],
        "simulator_version": SIMULATOR_VERSION,
    }
