"""Engineering Decision Twin: bounded scenario space over measured telemetry.

This is **not** a physical digital twin of the car. It is a deterministic,
evidence-grounded representation of one observed lap under bounded, explicitly
stated interventions, using the existing validated counterfactual model.

What it adds over calling the counterfactual directly:

* **Scenario sweeps** (§30). One invocation per requested fraction, so the user
  can see how the modelled outcome responds across 0/25/50/75/100% rather than
  one number at a time.
* **Multi-dimensional scenarios** (§31), restricted to the intervention types
  the existing model actually validates. No unsupported physical interactions
  are introduced and no claim is made that the model represents the vehicle.
* **Sensitivity classification** (§32) over the sweep — but only as a statement
  about *model response*, never about physical causality.

The honesty rules are absolute here:

* Every outcome is ``MODELLED``. None is historical fact.
* Every scenario records its own assumptions and validity from the model.
* A sweep that fails reports per-point failure. It is never interpolated,
  smoothed, or filled in.
* Sensitivity shape is classified only over points that actually succeeded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries

TWIN_VERSION = "question_engine_decision_twin_v1"

MODELLED = "MODELLED"

# The intervention dimensions the deterministic counterfactual actually models.
# This mirrors ``counterfactual.MODELED_SIGNALS``, which is currently speed
# only: throttle, brake, gear, rpm and drs have NO lap-time model in this
# codebase. Claiming a throttle scenario would mean inventing the physics of an
# intervention the engine cannot compute, so those dimensions are refused.
SUPPORTED_DIMENSIONS = ("speed",)

# Intervention types the model validates, with their fraction ranges.
# SCALE_SIGNAL is multiplicative and lives in [-0.10, 0.10]; sweeping it 0..1
# would silently produce out-of-range requests rather than scenarios.
SUPPORTED_INTERVENTIONS = {
    "REMOVE_DEFICIT": (0.0, 1.0),
    "BLEND_WITH_REFERENCE": (0.0, 1.0),
    "SCALE_SIGNAL": (-0.10, 0.10),
}

# Default bounded sweep. The endpoints are always included so the curve is
# anchored at "no change" and "complete removal".
DEFAULT_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)

# Outcomes the model may return that mean "this point did not produce a result".
_FAILED_STATUSES = frozenset({
    "UNAVAILABLE", "INSUFFICIENT_EVIDENCE", "UNSUPPORTED",
    "INVALID_COMPARISON", "NO_TELEMETRY",
})


@dataclass
class ScenarioPoint:
    """One modelled scenario. Always MODELLED, never an observation."""

    fraction: float
    status: str
    delta_lap_time_s: Optional[float] = None
    assumptions: tuple[str, ...] = ()
    validity: Optional[str] = None
    limitations: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def modelled(self) -> bool:
        return self.status not in _FAILED_STATUSES

    def as_dict(self) -> dict[str, Any]:
        return {
            "fraction": self.fraction,
            "status": self.status,
            "delta_lap_time_s": self.delta_lap_time_s,
            "claim_class": MODELLED,
            "is_historical_truth": False,
            "assumptions": list(self.assumptions),
            "validity": self.validity,
            "limitations": list(self.limitations),
        }


def _classify_sensitivity(values: list[tuple[float, float]]) -> str:
    """Describe how the MODEL responds across a sweep.

    Deliberately descriptive. A monotone model response is a fact about the
    model; calling it evidence of physical causation would not be, and the
    classification is named to make that distinction visible.
    """
    if len(values) < 2:
        return "INSUFFICIENT_POINTS"
    deltas = [v for _, v in values]
    steps = [b - a for a, b in zip(deltas, deltas[1:])]
    tolerance = 1e-9
    if all(abs(s) <= tolerance for s in steps):
        return "FLAT"
    if all(s > -tolerance for s in steps) or all(s < tolerance for s in steps):
        return "MONOTONIC"
    if len(values) >= 4:
        turns = sum(1 for a, b in zip(steps, steps[1:])
                    if a * b < -tolerance)
        if turns >= 2:
            return "NONLINEAR"
        if turns == 1:
            return "THRESHOLD_LIKE"
    return "NON_MONOTONIC"


def build_twin(
    queries: CanonicalQueries,
    *,
    season: int,
    round_num: int,
    driver: str,
    lap_number: int,
    reference_driver: Optional[str] = None,
    dimension: str = "speed",
    fractions: tuple[float, ...] = DEFAULT_FRACTIONS,
    intervention_type: str = "REMOVE_DEFICIT",
    session_type: str = "RACE",
) -> dict[str, Any]:
    """Run a bounded scenario sweep and return the decision twin."""
    limitations: list[str] = []

    if dimension not in SUPPORTED_DIMENSIONS:
        return {
            "analysis": "engineering_decision_twin",
            "version": TWIN_VERSION,
            "status": "UNSUPPORTED",
            "reason": (
                f"'{dimension}' has no deterministic lap-time model; "
                f"modelled signals: {list(SUPPORTED_DIMENSIONS)}"
            ),
            "scenario_space": [],
            "sensitivity": {"shape": "UNSUPPORTED"},
            "limitations": [
                "No physical model exists for this dimension; approximating "
                "one would invent an engineering result.",
            ],
        }

    if intervention_type not in SUPPORTED_INTERVENTIONS:
        return {
            "analysis": "engineering_decision_twin",
            "version": TWIN_VERSION,
            "status": "UNSUPPORTED",
            "reason": (
                f"unknown intervention '{intervention_type}'; allowed: "
                f"{sorted(SUPPORTED_INTERVENTIONS)}"
            ),
            "scenario_space": [],
            "sensitivity": {"shape": "UNSUPPORTED"},
            "limitations": [],
        }

    low, high = SUPPORTED_INTERVENTIONS[intervention_type]

    # The fraction is validated against the model's own range. We never clamp or
    # round a requested value into range silently.
    wanted = tuple(fractions)
    if not wanted:
        wanted = DEFAULT_FRACTIONS
    if any(f < low or f > high for f in wanted):
        return {
            "analysis": "engineering_decision_twin",
            "version": TWIN_VERSION,
            "status": "INVALID_REQUEST",
            "reason": (
                f"{intervention_type} fractions must lie in [{low}, {high}]"
            ),
            "scenario_space": [],
            "sensitivity": {"shape": "INVALID"},
            "limitations": [
                f"A value outside [{low}, {high}] is not a valid "
                f"{intervention_type} for this model; it is refused rather "
                f"than clamped."
            ],
        }

    from racewise.data.historical.counterfactual import simulate_telemetry_counterfactual

    points: list[ScenarioPoint] = []
    for fraction in wanted:
        try:
            raw = simulate_telemetry_counterfactual(
                queries, int(season), int(round_num), driver, int(lap_number),
                dimension, intervention_type, float(fraction),
                reference_driver=reference_driver,
                session_type=session_type,
            )
        except Exception as exc:  # noqa: BLE001 — one bad point must not sink the sweep
            points.append(ScenarioPoint(
                fraction=float(fraction), status="TOOL_FAILURE",
                limitations=(f"{type(exc).__name__}: {exc}",),
            ))
            continue

        status = str(raw.get("status") or "UNKNOWN")
        # The engine's own key is counterfactual_delta_s; fall back to the
        # older name rather than inventing a third.
        delta = raw.get("counterfactual_delta_s")
        if not isinstance(delta, (int, float)) or isinstance(delta, bool):
            delta = raw.get("delta_lap_time_s", raw.get("predicted_delta_s"))
        gates = raw.get("validation_gates")
        validity = None
        if isinstance(gates, dict):
            failed = [name for name, gate in gates.items()
                      if isinstance(gate, dict) and gate.get("status") not in
                      (None, "PASS")]
            validity = "ALL_GATES_PASS" if not failed else f"GATES_FAILED:{failed}"
        points.append(ScenarioPoint(
            fraction=float(fraction),
            status=status,
            delta_lap_time_s=(float(delta)
                              if isinstance(delta, (int, float)) and
                              not isinstance(delta, bool) else None),
            assumptions=tuple(str(a) for a in (raw.get("assumptions") or [])),
            validity=validity,
            limitations=tuple(str(x) for x in (raw.get("limitations") or [])),
            raw=raw,
        ))

    usable = [(p.fraction, p.delta_lap_time_s) for p in points
              if p.modelled and p.delta_lap_time_s is not None]
    failed = [p for p in points if not p.modelled]

    if not usable:
        limitations.append(
            "no scenario in the sweep produced a modelled result; the model "
            "does not support an intervention here"
        )
        status = "INSUFFICIENT_EVIDENCE"
    elif failed:
        status = "PARTIALLY_MODELLED"
        limitations.append(
            f"{len(failed)} of {len(points)} scenario points failed and are "
            f"reported as failures, never interpolated"
        )
    else:
        status = "COMPLETED"

    baseline = points[0].raw if points and points[0].modelled else {}
    baseline_lap_time = None
    if isinstance(baseline.get("baseline_result"), dict):
        baseline_lap_time = baseline["baseline_result"].get("lap_time_s")
    if not isinstance(baseline_lap_time, (int, float)) or \
            isinstance(baseline_lap_time, bool):
        baseline_lap_time = None
    return {
        "analysis": "engineering_decision_twin",
        "version": TWIN_VERSION,
        "status": status,
        "scope": {
            "season": int(season),
            "round": int(round_num),
            "driver": driver,
            "reference_driver": reference_driver,
            "lap_number": int(lap_number),
            "session_type": session_type,
        },
        "dimension": dimension,
        "intervention_type": intervention_type,
        "baseline": {
            "claim_class": "OBSERVED",
            "lap_time_s": baseline_lap_time,
            "source": "measured canonical lap",
        } if baseline_lap_time is not None else {
            "claim_class": "OBSERVED",
            "lap_time_s": None,
            "source": "unavailable",
        },
        "scenario_space": [p.as_dict() for p in points],
        "sensitivity": {
            "shape": _classify_sensitivity(usable),
            "points": [{"fraction": f, "delta_lap_time_s": d} for f, d in usable],
            "note": (
                "Shape describes how the MODEL responds across the sweep. It "
                "is not evidence of physical causation."
            ),
        },
        "limitations": limitations,
        "provenance": {
            "model": "simulate_telemetry_counterfactual",
            "model_scope": (
                "Single-lap telemetry intervention sensitivity. Not a vehicle "
                "model; it does not represent the complete car, and it is not "
                "a forecast."
            ),
            "twin_version": TWIN_VERSION,
            "every_point_is_modelled": True,
        },
    }