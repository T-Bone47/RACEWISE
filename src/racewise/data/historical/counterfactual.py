"""Validated telemetry counterfactuals (Phase 6I).

Central question:
    "If a measured driver-level performance profile changed in a precisely
     defined way, what does the deterministic lap-time model predict?"

Epistemic contract (non-negotiable):
    A counterfactual result is a MODEL SENSITIVITY measurement, never a
    historical fact, a prediction, or a causal proof. The output states
    this explicitly. Historical evidence (Phase 6F) and counterfactual
    simulation are different epistemic objects and are never merged.

Why a speed-only bridge exists (the honest boundary):
    The existing deterministic simulator (simulator/strategy.py) consumes
    LAP TIMES, not telemetry: injecting telemetry there would require
    inventing a physics mapping (aero, tyres, engine) that does not exist
    in the codebase. Phase 6E, however, already established a deterministic
    lap-time model over the SPEED channel: region loss dt*(1 - v_B/v_A).
    Phase 6I generalizes that model to its exact (non-linearized) form:

        fix segment distances d_r from the ORIGINAL measured speed trace
        (d_r = integral of v dt over segment r)
        t_r = d_r / mean_v_r

    - BASELINE REPRODUCTION: with the original profile, every t_r equals
      the segment duration by construction, so the modeled lap time equals
      the measured grid duration exactly (verified numerically, gate 5).
    - INTERVENTION: transform the speed profile deterministically, keep the
      segment distances fixed, recompute t_r. The delta is pure calculation.
    - Correspondence with 6E: for d_r = v_orig*dt, the exact term
      d_r*(1/v_cf - 1/v_orig) equals dt*(1 - v_cf/v_orig), the 6E
      linearization - same first-order form, cross-checked (informational).

    Throttle, brake, gear, RPM and DRS have NO deterministic model mapping
    them to lap time in this codebase. Interventions on those signals
    return UNSUPPORTED - never a fabricated adapter.

Interventions (each a mathematical transformation, not "better driving"):
    REMOVE_DEFICIT         v_cf = v_t + f * max(v_ref - v_t, 0),  f in [0,1]
    BLEND_WITH_REFERENCE   v_cf = (1-w)*v_t + w*v_ref,           w in [0,1]
    SCALE_SIGNAL           v_cf = v_t * (1 + f),                 f in [-0.10, 0.10]

    All have identity parameters (f=0 / w=0) that must reproduce the
    baseline bit-exactly (gate: identity delta == 0.0).

Validation gates (all must pass for VALID):
    1 telemetry        target (+reference) telemetry rows exist, >= MIN_SAMPLES
    2 alignment        shared 0.25 s grid (6E semantics), >= MIN_GRID_POINTS
    3 intervention     known type, finite parameters inside explicit bounds
    4 simulator_map    signal has a documented lap-time model (speed only)
    5 baseline_repro   model baseline == measured grid duration (1e-6 s)
                       AND identity-parameter run yields delta exactly 0.0
    6 sanity_bounds    finite outputs; |delta| < lap duration; speeds >= 0

Determinism: same canonical data + same parameters => byte-identical JSON
(sha256 output_hash included). Derived on read; zero storage growth.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.loss_attribution import (
    ALPHA_RESAMPLE,
    MIN_SAMPLES_PER_SIGNAL,
    _NON_COMPARABLE_FLAGS,
)

COUNTERFACTUAL_VERSION = "1.0"

# Opt-in bounded profile serialization (frontend trace canvas). Evenly
# spaced deterministic decimation of the shared grid; display only - the
# model always integrates the FULL grid, never the samples. The default
# (opt-out) payload is byte-identical to the pre-extension output, so all
# golden hashes remain valid; the version is NOT bumped.
PROFILE_SAMPLE_CAP = 192

VALID = "VALID"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
UNAVAILABLE = "UNAVAILABLE"
UNSUPPORTED = "UNSUPPORTED"

# Signals with a documented deterministic lap-time model.
MODELED_SIGNALS = ("speed",)
# Signals that exist in canonical telemetry but have NO lap-time model.
# Interventions on them are UNSUPPORTED - the mapping must never be faked.
UNMODELED_SIGNALS = ("throttle", "brake", "gear", "rpm", "drs")

# Intervention bounds (explicit; the generic payload validator is not
# sufficient - the tool layer enforces these again).
REMOVE_DEFICIT_MIN, REMOVE_DEFICIT_MAX = 0.0, 1.0
BLEND_MIN, BLEND_MAX = 0.0, 1.0
SCALE_MIN, SCALE_MAX = -0.10, 0.10
# absolute fraction ceiling enforced at the tool/API boundary (any intervention)
MAX_FRACTION_ABS = 1.0

SEGMENT_S_DEFAULT = 6.0
SEGMENT_S_MIN, SEGMENT_S_MAX = 2.0, 30.0
MIN_GRID_POINTS = 50          # below this the profile is too thin to model
MIN_STINT_LAPS = 3            # stint aggregation needs >= 3 valid laps
MAX_STINT_LAPS_CAP = 12       # hard bound on stint sample size
MIN_SEGMENT_SPEED_KMH = 5.0   # stationary segments cannot enter t = d/v

VALIDATION_GATES = (
    "telemetry",
    "alignment",
    "intervention",
    "simulator_mapping",
    "baseline_reproduction",
    "sanity_bounds",
)


# ---------------------------------------------------------------------------
# profile extraction (reuses 6E alignment semantics exactly)
# ---------------------------------------------------------------------------

def extract_speed_profile(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    session_type: str,
    driver: str,
    lap_number: int,
    step_s: float = ALPHA_RESAMPLE,
) -> Optional[dict[str, Any]]:
    """Deterministic speed profile on the 6E lap-relative grid.

    Returns None when telemetry for this driver-lap is missing or too thin
    (UNAVAILABLE / INSUFFICIENT upstream - never a synthetic profile).
    """
    from racewise.data.historical.loss_attribution import _resample_lap

    rows = queries.get_lap_telemetry(
        season, round_num, driver, lap_number,
        session_type=session_type, signals=["speed"],
    )
    if len(rows) < MIN_SAMPLES_PER_SIGNAL:
        return None
    series = [(r["lap_time_s"], r["value"]) for r in rows]
    res = _resample_lap({"speed": series}, step_s)
    if res is None:
        return None
    finite = [v for v in res["speed"] if v is not None]
    # _resample_lap returns only signal arrays; with one signal its grid is
    # exactly the series span - rebuild it identically
    lo, hi = series[0][0], series[-1][0]
    n = int((hi - lo) / step_s) + 1
    grid = [round(lo + i * step_s, 4) for i in range(n)]
    if len(finite) < MIN_GRID_POINTS or len(finite) != len(grid):
        return None
    return {
        "signal": "speed",
        "unit": "km/h",
        "grid": grid,
        "values": [float(v) for v in finite],
        "n_points": len(finite),
        "coverage_s": round(grid[-1] - grid[0], 4),
        "step_s": step_s,
        "source": "canonical_telemetry (fastf1), lap-relative time",
    }


# ---------------------------------------------------------------------------
# interventions (pure deterministic transformations)
# ---------------------------------------------------------------------------

def _validate_intervention(signal: str, intervention_type: str, fraction: float) -> None:
    """Raise ValueError when the intervention is not mathematically valid."""
    if not math.isfinite(fraction):
        raise ValueError("intervention fraction must be finite (no NaN/inf)")
    if signal not in MODELED_SIGNALS:
        raise ValueError(
            f"signal '{signal}' has no deterministic lap-time model; "
            f"modeled signals: {list(MODELED_SIGNALS)}"
        )
    if intervention_type == "REMOVE_DEFICIT":
        if not REMOVE_DEFICIT_MIN <= fraction <= REMOVE_DEFICIT_MAX:
            raise ValueError(f"REMOVE_DEFICIT fraction must be in [0, 1], got {fraction}")
    elif intervention_type == "BLEND_WITH_REFERENCE":
        if not BLEND_MIN <= fraction <= BLEND_MAX:
            raise ValueError(f"BLEND_WITH_REFERENCE weight must be in [0, 1], got {fraction}")
    elif intervention_type == "SCALE_SIGNAL":
        if not SCALE_MIN <= fraction <= SCALE_MAX:
            raise ValueError(f"SCALE_SIGNAL fraction must be in [-0.10, 0.10], got {fraction}")
    else:
        raise ValueError(
            f"unknown intervention type '{intervention_type}'; "
            "allowed: REMOVE_DEFICIT, BLEND_WITH_REFERENCE, SCALE_SIGNAL"
        )


def transform_speed_profile(
    target_values: list[float],
    reference_values: Optional[list[float]],
    intervention_type: str,
    fraction: float,
) -> list[float]:
    """Apply the intervention to a speed profile. Pure; no side effects.

    REMOVE_DEFICIT and BLEND_WITH_REFERENCE require a reference profile of
    equal length (same shared grid). SCALE_SIGNAL is reference-free.
    """
    _validate_intervention("speed", intervention_type, fraction)
    n = len(target_values)
    if intervention_type in ("REMOVE_DEFICIT", "BLEND_WITH_REFERENCE"):
        if reference_values is None or len(reference_values) != n:
            raise ValueError(
                f"{intervention_type} requires a reference profile on the same grid"
            )
    if intervention_type == "REMOVE_DEFICIT":
        return [
            v + fraction * max(r - v, 0.0)
            for v, r in zip(target_values, reference_values)  # type: ignore[arg-type]
        ]
    if intervention_type == "BLEND_WITH_REFERENCE":
        return [
            (1.0 - fraction) * v + fraction * r
            for v, r in zip(target_values, reference_values)  # type: ignore[arg-type]
        ]
    # SCALE_SIGNAL
    return [v * (1.0 + fraction) for v in target_values]


# ---------------------------------------------------------------------------
# deterministic lap-time model (the simulator bridge)
# ---------------------------------------------------------------------------

def _integral_plinear(
    values: list[float], grid: list[float], t0: float, t1: float
) -> float:
    """Exact integral of the piecewise-linear interpolant over [t0, t1].

    The profile is linearly interpolated between grid points (6E semantics);
    its integral is therefore computable exactly via trapezoids on clipped
    sub-intervals. No rectangle-rule sampling error.
    """
    total = 0.0
    for i in range(len(grid) - 1):
        g0, g1 = grid[i], grid[i + 1]
        if g1 <= t0 or g0 >= t1:
            continue
        a = max(g0, t0)
        b = min(g1, t1)
        v0 = values[i] + (values[i + 1] - values[i]) * (a - g0) / (g1 - g0)
        v1 = values[i] + (values[i + 1] - values[i]) * (b - g0) / (g1 - g0)
        total += (v0 + v1) / 2.0 * (b - a)
    return total


def _segmentize(
    values: list[float],
    grid: list[float],
    segment_s: float,
) -> list[dict[str, float]]:
    """Tile the grid span into segments with EXACT integrated quantities.

    Each segment carries duration_s, distance (integral of v dt, exact) and
    mean_v = distance/duration (exact by construction). Unrounded values:
    the model consumes these; display rounding happens in the output layer.
    """
    segments: list[dict[str, float]] = []
    t = grid[0]
    t_end = grid[-1]
    while t < t_end - 1e-9:
        s_end = min(t + segment_s, t_end)
        dur = s_end - t
        dist = _integral_plinear(values, grid, t, s_end)
        segments.append({
            "t_start": t, "t_end": s_end, "duration": dur,
            "distance": dist, "mean_v": (dist / dur) if dur > 0 else 0.0,
        })
        t = s_end
    return segments


def lap_time_from_speed_profile(
    values: list[float],
    grid: list[float],
    segment_s: float = SEGMENT_S_DEFAULT,
) -> dict[str, Any]:
    """Fixed-distance segment integration of a speed profile (display form).

    Model: segment distances are fixed by whichever profile is passed first;
    the counterfactual reuses the ORIGINAL distances with INTERVENED mean
    speeds (see simulate_telemetry_counterfactual). With the original
    profile the modeled time equals each segment's duration exactly
    (baseline reproduction, gate 5).
    """
    if len(values) != len(grid) or len(values) < 2:
        raise ValueError("profile length mismatch or too short")
    segs = _segmentize(values, grid, segment_s)
    return {
        "n_segments": len(segs),
        "segments": [
            {
                "t_start_s": round(s["t_start"], 4),
                "t_end_s": round(s["t_end"], 4),
                "duration_s": round(s["duration"], 4),
                "mean_speed_kmh": round(s["mean_v"], 3),
                "distance_units": round(s["distance"], 4),
            }
            for s in segs
        ],
        "grid_duration_s": round(grid[-1] - grid[0], 4),
    }


def _model_lap_time(
    distances: list[float],
    mean_speeds: list[float],
) -> tuple[float, int]:
    """Sum of d_r / v_r over usable segments. Returns (time, n_excluded)."""
    total = 0.0
    excluded = 0
    for d, v in zip(distances, mean_speeds):
        if v < MIN_SEGMENT_SPEED_KMH:
            excluded += 1
            continue
        total += d / v
    return total, excluded


# ---------------------------------------------------------------------------
# single-lap counterfactual
# ---------------------------------------------------------------------------

def simulate_telemetry_counterfactual(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver: str,
    lap_number: int,
    signal: str,
    intervention_type: str,
    fraction: float,
    reference_driver: Optional[str] = None,
    session_type: str = "RACE",
    segment_s: float = SEGMENT_S_DEFAULT,
    include_profile: bool = False,
) -> dict[str, Any]:
    """Validated single-lap telemetry counterfactual.

    Returns a deterministic evidence-bounded result; every failure mode has
    an explicit status (UNAVAILABLE / INSUFFICIENT_EVIDENCE / UNSUPPORTED).
    The predicted delta measures MODEL SENSITIVITY to the intervention.

    include_profile=True additionally serializes a bounded, evenly spaced
    sample of the aligned speed profiles for display. Default False keeps
    the canonical payload (and therefore output_hash) byte-identical to
    previous versions; the model NEVER integrates the samples - only the
    full grid.
    """
    base: dict[str, Any] = {
        "analysis": "simulate_telemetry_counterfactual",
        "version": COUNTERFACTUAL_VERSION,
        "season": season,
        "round": round_num,
        "session_type": session_type,
        "driver": driver,
        "reference_driver": reference_driver,
        "lap_number": lap_number,
        "signal": signal,
        "intervention": {"type": intervention_type, "fraction": fraction},
        "epistemics": (
            "model sensitivity to a specified intervention; not a historical "
            "fact, not a prediction, not a causal proof"
        ),
    }
    gates = {g: {"status": "NOT_RUN", "detail": ""} for g in VALIDATION_GATES}

    # --- gate 3+4 first: reject invalid interventions before touching data
    try:
        _validate_intervention(signal, intervention_type, fraction)
    except ValueError as exc:
        unsupported = signal not in MODELED_SIGNALS or intervention_type not in (
            "REMOVE_DEFICIT", "BLEND_WITH_REFERENCE", "SCALE_SIGNAL"
        )
        gates["simulator_mapping"] = {"status": "FAIL", "detail": str(exc)}
        gates["intervention"] = {"status": "FAIL", "detail": str(exc)}
        return {**base, "status": UNSUPPORTED if unsupported else "INVALID",
                "reason": str(exc), "validation_gates": gates}

    if not SEGMENT_S_MIN <= segment_s <= SEGMENT_S_MAX or not math.isfinite(segment_s):
        gates["intervention"] = {
            "status": "FAIL",
            "detail": f"segment_s must be in [{SEGMENT_S_MIN}, {SEGMENT_S_MAX}]",
        }
        return {**base, "status": "INVALID",
                "reason": gates["intervention"]["detail"], "validation_gates": gates}

    needs_reference = intervention_type in ("REMOVE_DEFICIT", "BLEND_WITH_REFERENCE")
    if needs_reference and not reference_driver:
        gates["intervention"] = {
            "status": "FAIL",
            "detail": f"{intervention_type} requires reference_driver",
        }
        return {**base, "status": "INVALID",
                "reason": gates["intervention"]["detail"], "validation_gates": gates}
    if reference_driver and reference_driver == driver:
        return {**base, "status": "INVALID",
                "reason": "driver and reference_driver must be distinct",
                "validation_gates": gates}

    # --- gate 1: telemetry
    tel = queries.telemetry_summary(season, round_num, session_type)
    if not tel["available"]:
        gates["telemetry"] = {"status": "FAIL", "detail": "no canonical telemetry for this session"}
        return {**base, "status": UNAVAILABLE,
                "reason": gates["telemetry"]["detail"], "validation_gates": gates}

    profile = extract_speed_profile(queries, season, round_num, session_type, driver, lap_number)
    if profile is None:
        return {**base, "status": UNAVAILABLE,
                "reason": f"no usable speed telemetry for {driver} on lap {lap_number}",
                "validation_gates": gates}
    ref_profile: Optional[dict[str, Any]] = None
    if needs_reference:
        ref_profile = extract_speed_profile(
            queries, season, round_num, session_type, str(reference_driver), lap_number
        )
        if ref_profile is None:
            return {**base, "status": UNAVAILABLE,
                    "reason": f"no usable speed telemetry for reference {reference_driver} "
                              f"on lap {lap_number}",
                    "validation_gates": gates}
    gates["telemetry"] = {
        "status": "PASS",
        "detail": f"target n={profile['n_points']}"
                  + (f", reference n={ref_profile['n_points']}" if ref_profile else ""),
    }

    ref_vals: Optional[list[float]] = None
    # --- gate 2: shared alignment (6E grid semantics)
    if needs_reference:
        lo = max(profile["grid"][0], ref_profile["grid"][0])   # type: ignore[index]
        hi = min(profile["grid"][-1], ref_profile["grid"][-1])  # type: ignore[index]
        if hi <= lo:
            return {**base, "status": INSUFFICIENT,
                    "reason": "no overlapping lap-relative span between target and reference",
                    "validation_gates": gates}
        step = profile["step_s"]
        n = int((hi - lo) / step) + 1
        grid = [round(lo + i * step, 4) for i in range(n)]
        target_vals = _interp_to_grid(profile, grid)
        ref_vals = _interp_to_grid(ref_profile, grid)
        if target_vals is None or ref_vals is None or len(target_vals) < MIN_GRID_POINTS:
            return {**base, "status": INSUFFICIENT,
                    "reason": "shared grid too thin after alignment",
                    "validation_gates": gates}
    else:
        grid = profile["grid"]
        target_vals = profile["values"]
    gates["alignment"] = {
        "status": "PASS",
        "detail": f"lap-relative grid step {grid[1] - grid[0]:.2f} s, "
                  f"{len(grid)} points, span {grid[-1] - grid[0]:.1f} s",
    }

    # --- gate 5a: baseline reproduction (model vs measured duration)
    orig_segs = _segmentize(target_vals, grid, segment_s)
    distances = [s["distance"] for s in orig_segs]
    orig_speeds = [s["mean_v"] for s in orig_segs]
    model_baseline, excl_base = _model_lap_time(distances, orig_speeds)
    measured = round(grid[-1] - grid[0], 4)
    repro_error = abs(model_baseline - measured)
    gates["baseline_reproduction"] = {
        "status": "PASS" if repro_error <= 1e-6 and excl_base == 0 else "FAIL",
        "detail": f"model baseline {model_baseline:.6f} s vs measured grid duration "
                  f"{measured:.6f} s (error {repro_error:.2e} s, {excl_base} stationary segments)",
    }
    if gates["baseline_reproduction"]["status"] != "PASS":
        return {**base, "status": INSUFFICIENT,
                "reason": "baseline reproduction failed: " + gates["baseline_reproduction"]["detail"],
                "validation_gates": gates}

    # --- identity check: identity parameters must yield delta exactly 0.0
    gates["intervention"] = {"status": "PASS", "detail": f"{intervention_type} f={fraction}"}
    gates["simulator_mapping"] = {
        "status": "PASS",
        "detail": f"speed has a deterministic lap-time model (fixed-distance segments)",
    }
    identity_fraction = 0.0
    identity_vals = transform_speed_profile(
        target_vals, ref_vals if needs_reference else None, intervention_type, identity_fraction
    )
    identity_segs = _segmentize(identity_vals, grid, segment_s)
    identity_time, _ = _model_lap_time(distances, [s["mean_v"] for s in identity_segs])
    identity_delta = round(identity_time - model_baseline, 9)
    if identity_delta != 0.0:
        return {**base, "status": INSUFFICIENT,
                "reason": f"identity intervention did not reproduce baseline (delta {identity_delta})",
                "validation_gates": gates}

    # --- intervention + counterfactual simulation
    cf_vals = transform_speed_profile(
        target_vals, ref_vals if needs_reference else None, intervention_type, fraction
    )
    cf_segs = _segmentize(cf_vals, grid, segment_s)
    cf_time, excl_cf = _model_lap_time(
        distances, [s["mean_v"] for s in cf_segs]
    )
    delta = cf_time - model_baseline

    # --- gate 6: sanity bounds
    finite_ok = all(math.isfinite(v) for v in cf_vals) and math.isfinite(cf_time)
    speed_ok = all(v >= 0.0 for v in cf_vals)
    delta_ok = abs(delta) < measured
    gates["sanity_bounds"] = {
        "status": "PASS" if (finite_ok and speed_ok and delta_ok and excl_cf == 0) else "FAIL",
        "detail": f"finite={finite_ok}, speeds>=0={speed_ok}, |delta|<lap={delta_ok}, "
                  f"stationary_excluded={excl_cf}",
    }
    if gates["sanity_bounds"]["status"] != "PASS":
        return {**base, "status": INSUFFICIENT,
                "reason": "sanity bounds failed: " + gates["sanity_bounds"]["detail"],
                "validation_gates": gates}

    # 6E cross-check (informational): the same traces under 6E's linearized
    # region model, when available. Different quantity - never merged.
    cross_check: Optional[dict[str, Any]] = None
    if needs_reference:
        try:
            from racewise.data.historical.loss_attribution import attribute_lap_loss
            att = attribute_lap_loss(
                queries, season, round_num, str(reference_driver), driver, lap_number, session_type
            )
            if att.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS"):
                cross_check = {
                    "note": "6E estimated pace component for the reference->target deficit; "
                            "an informational correspondence, not an equality",
                    "attribution_estimated_pace_component_s": att.get("estimated_pace_component_s"),
                    "attribution_status": att.get("status"),
                }
        except Exception:  # noqa: BLE001 - cross-check is informational only
            cross_check = {"note": "6E cross-check unavailable"}

    out: dict[str, Any] = {
        **base,
        "status": VALID,
        "validation_gates": gates,
        "profile_summary": {
            "signal": "speed",
            "unit": "km/h",
            "n_points": len(grid),
            "grid_step_s": round(grid[1] - grid[0], 4),
            "coverage_s": round(grid[-1] - grid[0], 4),
            "target_mean_speed_kmh": round(sum(target_vals) / len(target_vals), 3),
            "target_max_speed_kmh": round(max(target_vals), 3),
            "transformed_mean_speed_kmh": round(sum(cf_vals) / len(cf_vals), 3),
            "reference_mean_speed_kmh": (
                round(sum(ref_vals) / len(ref_vals), 3) if ref_vals else None
            ),
        },
        "intervention_definition": _intervention_definition(intervention_type),
        "model": {
            "method": "fixed-distance segment integration of the piecewise-linear speed trace: "
                      "d_r = integral(v dt) fixed from the ORIGINAL profile (exact quadrature), "
                      "t_r = d_r / mean_v_r",
            "segment_s": segment_s,
            "n_segments": len(orig_segs),
            "units": "speed km/h, time s; distance in consistent km/h*s units",
            "baseline_reproduction": {
                "model_baseline_s": round(model_baseline, 6),
                "measured_grid_duration_s": measured,
                "error_s": round(repro_error, 9),
                "identity_intervention_delta_s": identity_delta,
            },
        },
        "baseline_result": {"modeled_lap_time_s": round(model_baseline, 6)},
        "counterfactual_result": {"modeled_lap_time_s": round(cf_time, 6)},
        "counterfactual_delta_s": round(delta, 6),
        "deficit_closed_s": round(-delta, 6),
        "delta_sign_convention": "negative delta = intervened profile gains time",
        "cross_check_6e": cross_check,
        "assumptions": [
            "speed is the only signal with a deterministic lap-time model in this codebase",
            "segment distances are fixed from the original measured trace; only the "
            "speed profile is transformed (no downstream vehicle-model coupling)",
            "the model ignores racing line, tyre state, fuel, traffic and DRS mechanics",
            "linear interpolation on the 0.25 s lap-relative grid, clamped, no extrapolation",
            "at full deficit removal the model adopts the reference trace over the target's "
            "segment distances; the resulting delta is a model quantity and need not equal "
            "the measured lap-time delta (the 6E residual applies)",
            "the result is model sensitivity to the intervention, not history or causality",
        ],
        "limitations": [
            "lap-level only unless aggregated through the stint entry point",
            "telemetry coverage follows the bounded Phase 6D policy (top-2 drivers, "
            "bounded clean laps); no race-wide extrapolation",
        ],
        "provenance": {
            "tables": ["canonical_telemetry"],
            "provider": "fastf1",
            "counterfactual_version": COUNTERFACTUAL_VERSION,
            "alignment": "loss_attribution.ALPHA_RESAMPLE grid (0.25 s)",
        },
    }
    if include_profile:
        out["profile_samples"] = _profile_samples(grid, target_vals, ref_vals, cf_vals)
    out["output_hash"] = hashlib.sha256(
        json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return out


def _profile_samples(
    grid: list[float],
    target_vals: list[float],
    ref_vals: Optional[list[float]],
    cf_vals: list[float],
) -> dict[str, Any]:
    """Bounded, deterministic, evenly spaced profile samples for display.

    Decimation is a fixed function of the grid length (same input -> same
    samples -> same output_hash). The samples carry no analytical weight:
    every model quantity is computed from the full grid.
    """
    n = len(grid)
    if n <= PROFILE_SAMPLE_CAP:
        idx = list(range(n))
    else:
        step = (n - 1) / (PROFILE_SAMPLE_CAP - 1)
        idx = sorted({int(round(i * step)) for i in range(PROFILE_SAMPLE_CAP)})
    return {
        "n_total_points": n,
        "n_samples": len(idx),
        "cap": PROFILE_SAMPLE_CAP,
        "unit": "km/h",
        "sampling": "deterministic evenly spaced decimation of the 0.25 s "
                    "lap-relative grid; display only - the model integrates "
                    "the full grid",
        "t_s": [round(grid[i], 4) for i in idx],
        "target_kmh": [round(target_vals[i], 3) for i in idx],
        "reference_kmh": [round(ref_vals[i], 3) for i in idx] if ref_vals else None,
        "counterfactual_kmh": [round(cf_vals[i], 3) for i in idx],
    }


def _intervention_definition(intervention_type: str) -> str:
    return {
        "REMOVE_DEFICIT": "v_cf(t) = v_target(t) + f * max(v_reference(t) - v_target(t), 0); "
                          "removes fraction f of the measured speed deficit where it exists",
        "BLEND_WITH_REFERENCE": "v_cf(t) = (1-w)*v_target(t) + w*v_reference(t); "
                                "linear blend toward the reference over the whole lap",
        "SCALE_SIGNAL": "v_cf(t) = v_target(t) * (1 + f); multiplicative speed change",
    }.get(intervention_type, intervention_type)


def _interp_to_grid(profile: dict[str, Any], grid: list[float]) -> Optional[list[float]]:
    """Interpolate a profile's values onto an arbitrary grid within its span."""
    from racewise.data.historical.loss_attribution import _interp_series

    series = list(zip(profile["grid"], profile["values"]))
    if grid[0] < series[0][0] - 1e-9 or grid[-1] > series[-1][0] + 1e-9:
        return None
    out = _interp_series(series, grid)
    if any(v is None for v in out):
        return None
    return [float(v) for v in out]  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# stint-level counterfactual (bounded aggregation over measured laps)
# ---------------------------------------------------------------------------

def simulate_stint_counterfactual(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver: str,
    reference_driver: str,
    stint_number: int,
    signal: str,
    intervention_type: str,
    fraction: float,
    session_type: str = "RACE",
    max_laps: int = 6,
    segment_s: float = SEGMENT_S_DEFAULT,
) -> dict[str, Any]:
    """Aggregate validated single-lap counterfactuals across one stint.

    Common laps come from the Phase 6G selector (canonical stint identity,
    telemetry coverage for BOTH drivers, every exclusion reported). The
    aggregate covers ONLY the measured sampled laps - never a race claim.
    """
    base: dict[str, Any] = {
        "analysis": "simulate_stint_counterfactual",
        "version": COUNTERFACTUAL_VERSION,
        "season": season, "round": round_num, "session_type": session_type,
        "driver": driver, "reference_driver": reference_driver,
        "stint_number": stint_number,
        "signal": signal,
        "intervention": {"type": intervention_type, "fraction": fraction},
        "epistemics": (
            "aggregate model sensitivity over the sampled comparable laps; "
            "not history, not prediction, not causation"
        ),
    }
    if driver == reference_driver:
        return {**base, "status": "INVALID", "reason": "drivers must be distinct"}
    max_laps = max(2, min(int(max_laps), MAX_STINT_LAPS_CAP))

    from racewise.data.historical.stint_evidence import _select_common_laps

    selected, excluded, _, _ = _select_common_laps(
        queries, season, round_num, session_type, driver, reference_driver,
        stint_number, max_laps,
    )
    if len(selected) < 2:
        return {**base, "status": INSUFFICIENT,
                "reason": f"fewer than 2 common telemetry-covered laps ({len(selected)})",
                "excluded_laps": excluded}

    per_lap: list[dict[str, Any]] = []
    for ln in selected:
        res = simulate_telemetry_counterfactual(
            queries, season, round_num, driver, ln, signal, intervention_type,
            fraction, reference_driver=reference_driver,
            session_type=session_type, segment_s=segment_s,
        )
        if res.get("status") == VALID:
            per_lap.append({
                "lap_number": ln,
                "baseline_lap_time_s": res["baseline_result"]["modeled_lap_time_s"],
                "counterfactual_lap_time_s": res["counterfactual_result"]["modeled_lap_time_s"],
                "delta_s": res["counterfactual_delta_s"],
                "output_hash": res["output_hash"],
            })
        else:
            per_lap.append({"lap_number": ln, "status": res.get("status"),
                            "reason": res.get("reason")})

    valid = [p for p in per_lap if p.get("delta_s") is not None]
    if len(valid) < MIN_STINT_LAPS:
        return {**base, "status": INSUFFICIENT,
                "reason": f"fewer than {MIN_STINT_LAPS} valid laps "
                          f"({len(valid)}/{len(selected)} sampled)",
                "per_lap": per_lap, "excluded_laps": excluded}

    deltas = [p["delta_s"] for p in valid]
    mean_delta = sum(deltas) / len(deltas)
    srt = sorted(deltas)
    median_delta = (
        srt[len(srt) // 2] if len(srt) % 2
        else round((srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2, 6)
    )
    cumulative = round(sum(deltas), 6)

    # monotonicity sanity: closing MORE deficit must not gain LESS time
    monotone: Optional[bool] = None
    if intervention_type in ("REMOVE_DEFICIT", "BLEND_WITH_REFERENCE") and fraction > 0:
        probe = simulate_telemetry_counterfactual(
            queries, season, round_num, driver, valid[0]["lap_number"], signal,
            intervention_type, min(1.0, fraction + 0.25), reference_driver=reference_driver,
            session_type=session_type, segment_s=segment_s,
        )
        if probe.get("status") == VALID:
            monotone = probe["counterfactual_delta_s"] <= valid[0]["delta_s"] + 1e-9

    return {
        **base,
        "status": VALID,
        "laps_sampled": len(selected),
        "laps_valid": len(valid),
        "per_lap": per_lap,
        "excluded_laps": excluded,
        "aggregate": {
            "mean_delta_s": round(mean_delta, 6),
            "median_delta_s": median_delta,
            "min_delta_s": round(min(deltas), 6),
            "max_delta_s": round(max(deltas), 6),
            "cumulative_delta_s": cumulative,
            "cumulative_semantics": "sum over the SAMPLED comparable laps only; "
                                    "not race time, not a season or race claim",
        },
        "monotonicity_check": (
            {"status": "PASS" if monotone else "FAIL",
             "detail": "larger intervention fraction must not reduce time gained"}
            if monotone is not None else {"status": "NOT_TESTABLE",
                                          "detail": "single-fraction request"}
        ),
        "assumptions": [
            "per-lap results use the same fixed-distance segment model",
            "the stint aggregate covers only the sampled measured laps",
            f"stint aggregation requires >= {MIN_STINT_LAPS} valid laps",
        ],
        "provenance": {
            "tables": ["canonical_telemetry", "canonical_lap_times", "canonical_stints"],
            "provider": "fastf1",
            "counterfactual_version": COUNTERFACTUAL_VERSION,
            "lap_selection": "Phase 6G _select_common_laps",
        },
    }
