"""Measured driver performance envelope & bounded scenario analysis (Phase 6J).

Central question:
    "Across the measured telemetry-supported laps, what performance envelope
     did the driver actually operate within, and how does the validated
     speed-profile model respond to bounded changes inside that envelope?"

What the envelope IS:
    a MEASURED band - per grid point, the min/max (and median centre) of the
    driver's own clean comparable laps in the session. Nothing theoretical.

What the envelope is NOT (enforced in language and code):
    not an ideal lap, not a theoretical maximum, not a prediction, not a
    driver model. OBSERVED != ENVELOPE != OPTIMAL != PREDICTION.

Reuse discipline (no second implementation of anything):
    - profile extraction: Phase 6I extract_speed_profile (0.25 s lap-relative
      grid, linear interpolation, clamped, no extrapolation)
    - lap-time model: Phase 6I _segmentize / _model_lap_time (exact
      piecewise-linear quadrature, fixed distances from the baseline profile)
    - clean-lap context: Phase 6E _classify_lap (pit/flags/rain/inaccurate)
    - stint common-lap selection: Phase 6G _select_common_laps
    - validation gates: Phase 6I semantics (baseline reproduction error 0,
      identity-parameter delta exactly 0.0)

Scenarios (typed enums only; no caller-supplied expressions):
    OBSERVED               identity; parameter must be 0.0
    DEFICIT_REDUCTION      v' = v + f*max(v_ref - v, 0),  f in [0, 1]
    REFERENCE_BLEND        v' = (1-w)*v + w*v_ref,         w in [0, 1]
    ENVELOPE_LOWER_BOUND   profile = band lower edge (driver's own slowest
                           measured form per grid point)
    ENVELOPE_UPPER_BOUND   profile = band upper edge (driver's own fastest
                           measured form per grid point)

    The reference profile is the reference driver's telemetry on the SAME
    anchor lap (Phase 6I semantics, validated there). Reference drivers are
    explicit - never assumed winner/teammate.

Sensitivity sweep:
    bounded parameter grid (max 11 points), each point run through the 6I
    model. Response classification is descriptive finite differences:
    MONOTONIC / NON_MONOTONIC / FLAT / INSUFFICIENT_DATA. No ML, no fits.

Race-level boundary preserved: scenario results cover only the sampled
measured laps; race-wide extrapolation is NOT offered (6I limitation).

Determinism: same canonical data + parameters => byte-identical JSON with
embedded output_hash. Derived on read; zero storage growth.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.counterfactual import (
    BLEND_MAX,
    BLEND_MIN,
    COUNTERFACTUAL_VERSION,
    MAX_FRACTION_ABS,
    MIN_GRID_POINTS,
    MIN_SEGMENT_SPEED_KMH,
    MODELED_SIGNALS,
    REMOVE_DEFICIT_MAX,
    REMOVE_DEFICIT_MIN,
    SEGMENT_S_MAX,
    SEGMENT_S_MIN,
    VALID,
    _model_lap_time,
    _segmentize,
    _validate_intervention,
    extract_speed_profile,
)
from racewise.data.historical.loss_attribution import (
    ALPHA_RESAMPLE,
    _classify_lap,
    _interp_series,
    _rain_in_window,
)

ENVELOPE_VERSION = "1.0"

INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
UNAVAILABLE = "UNAVAILABLE"
UNSUPPORTED = "UNSUPPORTED"
VALID_CAVEATS = "VALID_WITH_CAVEATS"

SCENARIO_TYPES = (
    "OBSERVED",
    "DEFICIT_REDUCTION",
    "REFERENCE_BLEND",
    "ENVELOPE_LOWER_BOUND",
    "ENVELOPE_UPPER_BOUND",
)
REFERENCE_SCENARIOS = ("DEFICIT_REDUCTION", "REFERENCE_BLEND")

# sweep bounds (explicit; re-enforced in the tool layer)
MAX_SCENARIOS_CAP = 11
MAX_LAPS_CAP = 12
DEFAULT_MAX_SCENARIOS = 5
DEFAULT_MAX_LAPS = 6

FLAT_TOLERANCE_S = 1e-6   # sweep deltas all within this -> FLAT
MIN_SWEEP_POINTS = 3      # fewer -> INSUFFICIENT_DATA classification

# Laps whose time_s is not representative (same flags as 6E).
_NON_COMPARABLE_FLAGS = ("is_pit_in_lap", "is_pit_out_lap", "deleted")


# ---------------------------------------------------------------------------
# clean comparable laps for ONE driver across the session (6E context rules)
# ---------------------------------------------------------------------------

def _clean_covered_laps(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    session_type: str,
    driver: str,
) -> tuple[list[int], list[dict[str, Any]]]:
    """Deterministic clean telemetry-covered laps for one driver.

    Uses the canonical lap facts + 6E context classification (pit in/out,
    deleted, restricted track status, flagged inaccurate, per-lap-window
    rain) restricted to laps that actually have telemetry coverage.
    Exclusions are returned with reasons - never silently dropped. The third
    element is the count of the driver's lap facts that have telemetry
    coverage (0 => the driver is effectively absent => UNAVAILABLE).
    """
    covered = set()
    summary = queries.telemetry_summary(season, round_num, session_type)
    if summary.get("available"):
        covered = set(summary.get("laps") or [])
    laps = {r["lap_number"]: r for r in queries.get_lap_times(season, round_num, session_type, driver)}
    selected: list[int] = []
    excluded: list[dict[str, Any]] = []
    for ln in sorted(laps):
        lap = laps[ln]
        if ln not in covered:
            excluded.append({"lap_number": ln, "reason": "telemetry not covered"})
            continue
        rain = _rain_in_window(queries, season, round_num, session_type, lap)
        ctx = _classify_lap(lap, rain)
        if not ctx["comparable"]:
            excluded.append({
                "lap_number": ln,
                "reason": "; ".join(ctx["reasons"]) or "context",
            })
            continue
        selected.append(ln)
    for ln in covered - set(laps):
        excluded.append({"lap_number": ln, "reason": "telemetry without canonical lap fact"})
    n_covered = len(set(laps) & covered)
    return selected, excluded, n_covered


def _bounded_sample(laps: list[int], max_laps: int) -> list[int]:
    """Evenly spaced deterministic sample (6G style), order preserved."""
    if len(laps) <= max_laps:
        return list(laps)
    step = (len(laps) - 1) / (max_laps - 1)
    picked = sorted({int(round(i * step)) for i in range(max_laps)})
    return [laps[i] for i in picked]


# ---------------------------------------------------------------------------
# envelope construction
# ---------------------------------------------------------------------------

def _profiles_on_common_grid(
    profiles: list[dict[str, Any]],
) -> Optional[tuple[list[float], list[list[float]]]]:
    """Interpolate measured profiles onto their common span (6E semantics).

    Returns (grid, rows) where rows[i] is profile i interpolated onto the
    grid, or None when the common span is too thin. No extrapolation.
    """
    lo = max(p["grid"][0] for p in profiles)
    hi = min(p["grid"][-1] for p in profiles)
    step = profiles[0]["step_s"]
    if hi <= lo:
        return None
    n = int((hi - lo) / step) + 1
    grid = [round(lo + i * step, 4) for i in range(n)]
    rows: list[list[float]] = []
    for p in profiles:
        out = _interp_series(list(zip(p["grid"], p["values"])), grid)
        if any(v is None for v in out):
            return None
        rows.append([float(v) for v in out])  # type: ignore[arg-type]
    if len(grid) < MIN_GRID_POINTS:
        return None
    return grid, rows


def build_performance_envelope(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver: str,
    lap_number: Optional[int] = None,
    session_type: str = "RACE",
    max_laps: int = DEFAULT_MAX_LAPS,
    segment_s: float = 6.0,
) -> dict[str, Any]:
    """Measured multi-lap speed envelope for one driver (bounded, deterministic).

    The anchor lap defaults to the first clean telemetry-covered lap
    (data-derived, never fabricated). The band is built from the driver's
    own clean laps interpolated onto the common grid: per grid point,
    lower = slowest measured, upper = fastest measured, centre = median.
    """
    base: dict[str, Any] = {
        "analysis": "performance_envelope",
        "version": ENVELOPE_VERSION,
        "counterfactual_version": COUNTERFACTUAL_VERSION,
        "season": season, "round": round_num, "session_type": session_type,
        "driver": driver,
        "epistemics": (
            "the envelope is measured driver variability over clean comparable "
            "laps - not an ideal lap, not a theoretical maximum, not a prediction"
        ),
    }
    max_laps = max(2, min(int(max_laps), MAX_LAPS_CAP))
    if not SEGMENT_S_MIN <= segment_s <= SEGMENT_S_MAX or not math.isfinite(segment_s):
        return {**base, "status": "INVALID",
                "reason": f"segment_s must be in [{SEGMENT_S_MIN}, {SEGMENT_S_MAX}]"}

    tel = queries.telemetry_summary(season, round_num, session_type)
    if not tel["available"]:
        return {**base, "status": UNAVAILABLE,
                "reason": "no canonical telemetry for this session"}

    clean, excluded, n_covered = _clean_covered_laps(queries, season, round_num, session_type, driver)
    anchor = int(lap_number) if lap_number is not None else (clean[0] if clean else None)
    if anchor is None:
        if n_covered == 0:
            return {**base, "status": UNAVAILABLE,
                    "reason": "no telemetry coverage for this driver (absent or not ingested)",
                    "excluded_laps": excluded}
        return {**base, "status": INSUFFICIENT,
                "reason": "no clean telemetry-covered laps for this driver",
                "excluded_laps": excluded}
    if anchor not in clean:
        return {**base, "status": INSUFFICIENT,
                "reason": f"anchor lap {anchor} is not a clean comparable lap",
                "excluded_laps": excluded}

    sample = _bounded_sample(clean, max_laps)
    for ln in clean:
        if ln not in sample:
            excluded.append({"lap_number": ln, "reason": "outside bounded sample (envelope window)"})

    profiles: list[dict[str, Any]] = []
    per_lap: list[dict[str, Any]] = []
    for ln in sample:
        p = extract_speed_profile(queries, season, round_num, session_type, driver, ln)
        if p is None:
            excluded.append({"lap_number": ln, "reason": "profile extraction failed (thin samples)"})
            per_lap.append({"lap_number": ln, "status": UNAVAILABLE})
            continue
        profiles.append(p)
        per_lap.append({"lap_number": ln, "status": VALID})
    if not profiles:
        return {**base, "status": INSUFFICIENT,
                "reason": "no usable profiles in the envelope sample",
                "excluded_laps": excluded}

    common = _profiles_on_common_grid(profiles)
    if common is None:
        return {**base, "status": INSUFFICIENT,
                "reason": "no common grid span across the sampled laps",
                "excluded_laps": excluded}
    grid, rows = common

    n_pts = len(grid)
    lower = [min(col) for col in zip(*rows)]
    upper = [max(col) for col in zip(*rows)]
    srt_cols = [sorted(col) for col in zip(*rows)]
    centre: list[float] = []
    for col in srt_cols:
        m = len(col) // 2
        centre.append(col[m] if len(col) % 2 else (col[m - 1] + col[m]) / 2.0)

    # model baseline from the median profile (6I fixed-distance model)
    segs = _segmentize(centre, grid, segment_s)
    distances = [s["distance"] for s in segs]
    speeds = [s["mean_v"] for s in segs]
    baseline_time, excl_base = _model_lap_time(distances, speeds)
    measured = round(grid[-1] - grid[0], 4)
    repro_ok = abs(baseline_time - measured) <= 1e-6 and excl_base == 0

    # segment-level band summary (bounded output; full arrays stay internal)
    band_segments: list[dict[str, Any]] = []
    for s in segs:
        idx = [i for i, g in enumerate(grid) if s["t_start"] - 1e-9 <= g < s["t_end"] - 1e-9]
        if not idx:
            continue
        lo_vals = [lower[i] for i in idx]
        up_vals = [upper[i] for i in idx]
        ct_vals = [centre[i] for i in idx]
        band_segments.append({
            "t_start_s": round(s["t_start"], 3),
            "t_end_s": round(s["t_end"], 3),
            "band_lower_mean_kmh": round(sum(lo_vals) / len(lo_vals), 2),
            "band_centre_mean_kmh": round(sum(ct_vals) / len(ct_vals), 2),
            "band_upper_mean_kmh": round(sum(up_vals) / len(up_vals), 2),
            "band_width_mean_kmh": round(
                (sum(up_vals) / len(up_vals)) - (sum(lo_vals) / len(lo_vals)), 2),
        })

    profile_id = hashlib.sha256(
        json.dumps({
            "season": season, "round": round_num, "session_type": session_type,
            "driver": driver, "laps": sample,
            "grid": [grid[0], grid[-1], grid[1] - grid[0]],
        }, sort_keys=True).encode()
    ).hexdigest()[:16]

    out: dict[str, Any] = {
        **base,
        "status": VALID,
        "profile_id": profile_id,
        "anchor_lap": anchor,
        "laps_used": sample,
        "laps_in_band": len(rows),
        "excluded_laps": excluded,
        "grid": {
            "step_s": round(grid[1] - grid[0], 4),
            "t_start_s": grid[0],
            "t_end_s": grid[-1],
            "n_points": n_pts,
            "coverage_s": round(grid[-1] - grid[0], 4),
            "alignment": "lap-relative time resampling (linear, clamped, no extrapolation)",
        },
        "envelope_summary": {
            "definition": "per grid point: min/max/median of the driver's own "
                          "clean comparable laps (MEASURED band)",
            "overall_min_speed_kmh": round(min(lower), 2),
            "overall_max_speed_kmh": round(max(upper), 2),
            "mean_band_width_kmh": round(
                sum(u - l for l, u in zip(lower, upper)) / n_pts, 2),
            "max_band_width_kmh": round(max(u - l for l, u in zip(lower, upper)), 2),
        },
        "band_segments": band_segments,
        "model_baseline": {
            "method": "Phase 6I fixed-distance segment model on the median profile",
            "segment_s": segment_s,
            "n_segments": len(segs),
            "baseline_time_s": round(baseline_time, 6),
            "measured_grid_duration_s": measured,
            "reproduction_error_s": round(abs(baseline_time - measured), 9),
            "reproduction_exact": repro_ok,
        },
        "assumptions": [
            "the band is the driver's own measured variability; it is not an "
            "optimal or theoretical envelope",
            "laps are pooled across the session: stint age and tyre state vary "
            "inside the band and are not separated here (see stint scenario entry)",
            "the median profile defines the model baseline; distances are fixed "
            "from it (Phase 6I semantics)",
        ],
        "provenance": {
            "tables": ["canonical_telemetry", "canonical_lap_times"],
            "provider": "fastf1",
            "envelope_version": ENVELOPE_VERSION,
            "profile_extraction": "Phase 6I extract_speed_profile",
        },
    }
    out["output_hash"] = hashlib.sha256(
        json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return out


# ---------------------------------------------------------------------------
# scenario sweep + sensitivity (through the Phase 6I model only)
# ---------------------------------------------------------------------------

def _linspace(lo: float, hi: float, n: int) -> list[float]:
    if n == 1:
        return [lo]
    step = (hi - lo) / (n - 1)
    return [round(lo + i * step, 4) for i in range(n)]


def _classify_response(deltas: list[float]) -> dict[str, Any]:
    """Descriptive finite-difference classification of a sweep response."""
    if len(deltas) < MIN_SWEEP_POINTS:
        return {"status": "INSUFFICIENT_DATA", "n_points": len(deltas)}
    changes = [deltas[i + 1] - deltas[i] for i in range(len(deltas) - 1)]
    flat = all(abs(d) <= FLAT_TOLERANCE_S for d in deltas)
    monotone_down = all(c <= 1e-9 for c in changes)
    monotone_up = all(c >= -1e-9 for c in changes)
    second = [abs(changes[i + 1] - changes[i]) for i in range(len(changes) - 1)]
    status = (
        "FLAT" if flat
        else "MONOTONIC" if (monotone_down or monotone_up)
        else "NON_MONOTONIC"
    )
    return {
        "status": status,
        "n_points": len(deltas),
        "max_abs_first_difference_s": round(max(abs(c) for c in changes), 6),
        "max_abs_second_difference_s": round(max(second), 6) if second else 0.0,
        "total_range_s": round(max(deltas) - min(deltas), 6),
        "note": "descriptive finite differences of the measured response; "
                "no fits, no extrapolation",
    }


def analyze_performance_envelope(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver: str,
    scenario_type: str = "DEFICIT_REDUCTION",
    parameter: Optional[float] = None,
    reference_driver: Optional[str] = None,
    lap_number: Optional[int] = None,
    session_type: str = "RACE",
    max_scenarios: int = DEFAULT_MAX_SCENARIOS,
    max_laps: int = DEFAULT_MAX_LAPS,
    segment_s: float = 6.0,
    stint_number: Optional[int] = None,
    laps: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Bounded scenario sweep over the measured envelope (Phase 6I model).

    One entry point for lap-level and stint-level analysis. The sweep runs
    typed scenarios through the exact 6I model; every scenario point is a
    deterministic model-sensitivity measurement.

    ``laps`` (Phase 6K integration): an explicit bounded lap set to build
    the envelope from instead of the default even-space sample. Every lap
    must belong to the driver's clean comparable telemetry-covered set;
    invalid requests are rejected, never silently re-sampled.
    """
    base: dict[str, Any] = {
        "analysis": "performance_envelope_scenario",
        "version": ENVELOPE_VERSION,
        "counterfactual_version": COUNTERFACTUAL_VERSION,
        "season": season, "round": round_num, "session_type": session_type,
        "driver": driver, "reference_driver": reference_driver,
        "stint_number": stint_number,
        "scenario": {"type": scenario_type, "parameter": parameter},
        "epistemics": (
            "model sensitivity to a specified bounded intervention over the "
            "measured envelope; not history, not prediction, not causality"
        ),
    }

    # typed-scenario gate (never accept executable logic from callers)
    if scenario_type not in SCENARIO_TYPES:
        return {**base, "status": UNSUPPORTED,
                "reason": f"unknown scenario type; allowed: {list(SCENARIO_TYPES)}"}
    if not SEGMENT_S_MIN <= segment_s <= SEGMENT_S_MAX or not math.isfinite(segment_s):
        return {**base, "status": "INVALID",
                "reason": f"segment_s must be in [{SEGMENT_S_MIN}, {SEGMENT_S_MAX}]"}
    max_scenarios = max(2, min(int(max_scenarios), MAX_SCENARIOS_CAP))
    max_laps = max(2, min(int(max_laps), MAX_LAPS_CAP))

    needs_reference = scenario_type in REFERENCE_SCENARIOS
    if needs_reference and not reference_driver:
        return {**base, "status": "INVALID",
                "reason": f"{scenario_type} requires reference_driver"}
    if reference_driver and reference_driver == driver:
        return {**base, "status": "INVALID",
                "reason": "driver and reference_driver must be distinct"}
    if scenario_type == "OBSERVED":
        if parameter is not None and float(parameter) != 0.0:
            return {**base, "status": "INVALID",
                    "reason": "OBSERVED is the identity scenario; parameter must be 0.0 or omitted"}
        parameter = 0.0
        params: list[float] = [0.0]
    elif scenario_type in REFERENCE_SCENARIOS:
        p = float(parameter) if parameter is not None else 0.5
        lo, hi = (REMOVE_DEFICIT_MIN, REMOVE_DEFICIT_MAX) if scenario_type == "DEFICIT_REDUCTION" \
            else (BLEND_MIN, BLEND_MAX)
        if not math.isfinite(p) or not lo <= p <= hi:
            return {**base, "status": "INVALID",
                    "reason": f"{scenario_type} parameter must be in [{lo}, {hi}]"}
        _validate_intervention("speed", "REMOVE_DEFICIT" if scenario_type == "DEFICIT_REDUCTION"
                               else "BLEND_WITH_REFERENCE", p)
        params = _linspace(lo, hi, max_scenarios)
    else:  # ENVELOPE_*_BOUND - single scenario, no parameter
        if parameter is not None and float(parameter) != 0.0:
            return {**base, "status": "INVALID",
                    "reason": f"{scenario_type} takes no parameter"}
        params = [0.0]

    # ---- envelope profiles (session scope, or stint scope via 6G selection)
    profile_pairs: list[tuple[int, dict[str, Any]]] = []
    anchor: Optional[int] = None
    excluded: list[dict[str, Any]] = []
    if stint_number is not None:
        from racewise.data.historical.stint_evidence import _select_common_laps
        if not reference_driver:
            return {**base, "status": "INVALID",
                    "reason": "stint envelopes compare a driver pair; reference_driver required"}
        selected, excluded, _sa, _sb = _select_common_laps(
            queries, season, round_num, session_type, driver, reference_driver,
            int(stint_number), max_laps)
        if len(selected) < 2:
            return {**base, "status": INSUFFICIENT,
                    "reason": f"fewer than 2 common clean laps in stint ({len(selected)})",
                    "excluded_laps": excluded}
        anchor = selected[len(selected) // 2]  # middle selected lap (deterministic)
        for ln in selected:
            p = extract_speed_profile(queries, season, round_num, session_type, driver, ln)
            if p is None:
                excluded.append({"lap_number": ln, "reason": "profile extraction failed"})
                continue
            profile_pairs.append((ln, p))
        if len(profile_pairs) < 2:
            return {**base, "status": INSUFFICIENT,
                    "reason": "fewer than 2 usable stint profiles",
                    "excluded_laps": excluded}
        scope = "stint"
    else:
        clean, excluded, n_covered = _clean_covered_laps(queries, season, round_num, session_type, driver)
        if laps is not None:
            # Phase 6K integration: exact caller-specified lap set (validated).
            req = [int(l) for l in laps]
            if not req or len(req) > MAX_LAPS_CAP:
                return {**base, "status": "INVALID",
                        "reason": f"laps must contain 1..{MAX_LAPS_CAP} entries"}
            if len(set(req)) != len(req):
                return {**base, "status": "INVALID",
                        "reason": "laps must not contain duplicates"}
            outside = [l for l in req if l not in set(clean)]
            if outside:
                return {**base, "status": "INVALID",
                        "reason": "laps outside the driver's clean comparable "
                                  f"telemetry-covered set: {sorted(outside)}"}
            sample = list(req)
            anchor = req[len(req) // 2]
        else:
            anchor = int(lap_number) if lap_number is not None else (clean[0] if clean else None)
            sample = _bounded_sample(clean, max_laps)
        if anchor is None:
            if n_covered == 0:
                return {**base, "status": UNAVAILABLE,
                        "reason": "no telemetry coverage for this driver (absent or not ingested)",
                        "excluded_laps": excluded}
            return {**base, "status": INSUFFICIENT,
                    "reason": "no clean telemetry-covered laps for this driver",
                    "excluded_laps": excluded}
        sample = _bounded_sample(clean, max_laps)
        for ln in clean:
            if ln not in sample:
                excluded.append({"lap_number": ln,
                                 "reason": "outside bounded sample (envelope window)"})
        for ln in sample:
            p = extract_speed_profile(queries, season, round_num, session_type, driver, ln)
            if p is None:
                excluded.append({"lap_number": ln, "reason": "profile extraction failed (thin samples)"})
                continue
            profile_pairs.append((ln, p))
        if not profile_pairs:
            return {**base, "status": INSUFFICIENT,
                    "reason": "no usable profiles in the envelope sample",
                    "excluded_laps": excluded}
        scope = "session"

    profiles = [p for _ln, p in profile_pairs]
    envelope_laps = [ln for ln, _p in profile_pairs]

    common = _profiles_on_common_grid(profiles)
    if common is None:
        return {**base, "status": INSUFFICIENT,
                "reason": "no common grid span across the sampled laps"}
    grid, rows = common
    n_pts = len(grid)

    # baseline = median profile on the common grid
    srt_cols = [sorted(col) for col in zip(*rows)]
    centre: list[float] = []
    for col in srt_cols:
        m = len(col) // 2
        centre.append(col[m] if len(col) % 2 else (col[m - 1] + col[m]) / 2.0)
    lower = [min(col) for col in zip(*rows)]
    upper = [max(col) for col in zip(*rows)]

    # 6I model: distances fixed from the baseline profile
    segs = _segmentize(centre, grid, segment_s)
    distances = [s["distance"] for s in segs]
    base_speeds = [s["mean_v"] for s in segs]
    baseline_time, excl_base = _model_lap_time(distances, base_speeds)
    measured = round(grid[-1] - grid[0], 4)
    if abs(baseline_time - measured) > 1e-6 or excl_base != 0:
        return {**base, "status": INSUFFICIENT,
                "reason": "baseline reproduction failed ("
                          f"{baseline_time:.6f} vs {measured:.6f}, {excl_base} stationary)"}

    # identity invariant
    identity_time, _ = _model_lap_time(distances, base_speeds)
    if round(identity_time - baseline_time, 9) != 0.0:
        return {**base, "status": INSUFFICIENT,
                "reason": "identity scenario did not reproduce the baseline exactly"}

    # reference profile on the common grid (6I semantics: same anchor lap)
    ref_profile: Optional[dict[str, Any]] = None
    ref_vals: Optional[list[float]] = None
    if needs_reference:
        ref_profile = extract_speed_profile(
            queries, season, round_num, session_type, str(reference_driver), anchor)
        if ref_profile is None:
            return {**base, "status": UNAVAILABLE,
                    "reason": f"no usable speed telemetry for reference {reference_driver} "
                              f"on anchor lap {anchor}"}
        out = _interp_series(list(zip(ref_profile["grid"], ref_profile["values"])), grid)
        if any(v is None for v in out):
            return {**base, "status": INSUFFICIENT,
                    "reason": "reference profile does not cover the common grid span"}
        ref_vals = [float(v) for v in out]  # type: ignore[arg-type]

    def _apply(profile_vals: list[float], p: float) -> list[float]:
        if scenario_type == "OBSERVED":
            return list(profile_vals)
        if scenario_type == "DEFICIT_REDUCTION":
            return [v + p * max(r - v, 0.0) for v, r in zip(profile_vals, ref_vals)]  # type: ignore[arg-type]
        if scenario_type == "REFERENCE_BLEND":
            return [(1.0 - p) * v + p * r for v, r in zip(profile_vals, ref_vals)]  # type: ignore[arg-type]
        return profile_vals  # envelope bounds applied below

    # ---- scenario points
    scenario_results: list[dict[str, Any]] = []
    seg_deltas_anchor: Optional[list[float]] = None
    for p in params:
        if scenario_type == "ENVELOPE_LOWER_BOUND":
            vals = lower
            label = "band lower edge (slowest measured form)"
        elif scenario_type == "ENVELOPE_UPPER_BOUND":
            vals = upper
            label = "band upper edge (fastest measured form)"
        else:
            vals = _apply(centre, p)
            label = f"{scenario_type} parameter={p}"
        cf_segs = _segmentize(vals, grid, segment_s)
        cf_speeds = [s["mean_v"] for s in cf_segs]
        cf_time, excl_cf = _model_lap_time(distances, cf_speeds)
        delta = cf_time - baseline_time
        if not math.isfinite(cf_time) or excl_cf != 0 or abs(delta) >= measured:
            scenario_results.append({"parameter": p, "label": label,
                                     "status": INSUFFICIENT, "reason": "sanity bounds failed"})
            continue
        entry: dict[str, Any] = {
            "parameter": p,
            "label": label,
            "status": VALID,
            "modeled_lap_time_s": round(cf_time, 6),
            "delta_s": round(delta, 6),
        }
        seg_deltas = [
            d * (1.0 / v2 - 1.0 / v1)
            for d, v1, v2 in zip(distances, base_speeds, cf_speeds)
            if v1 >= MIN_SEGMENT_SPEED_KMH and v2 >= MIN_SEGMENT_SPEED_KMH
        ]
        if seg_deltas_anchor is None and (p == params[len(params) // 2] or len(params) == 1):
            seg_deltas_anchor = seg_deltas
        scenario_results.append(entry)

    valid_pts = [s for s in scenario_results if s.get("status") == VALID]
    if not valid_pts:
        return {**base, "status": INSUFFICIENT,
                "reason": "no valid scenario points", "scenarios": scenario_results}

    deltas = [s["delta_s"] for s in valid_pts]
    response = _classify_response(deltas) if len(valid_pts) > 1 else {
        "status": "INSUFFICIENT_DATA", "n_points": len(valid_pts)}

    # regional response at the anchor parameter (model sensitivity by region)
    regional: list[dict[str, Any]] = []
    if seg_deltas_anchor is not None:
        ranked = sorted(
            enumerate(seg_deltas_anchor), key=lambda t: t[1])[:3]
        for idx, d in seg_deltas_anchor and ranked or []:
            s = segs[idx]
            regional.append({
                "t_start_s": round(s["t_start"], 3),
                "t_end_s": round(s["t_end"], 3),
                "scenario_delta_s": round(d, 6),
            })
        regional.sort(key=lambda r: r["t_start_s"])

    # stint-level per-lap response trend (early/middle/late measured laps)
    stint_response: Optional[dict[str, Any]] = None
    if stint_number is not None and needs_reference and valid_pts:
        mid_param = valid_pts[len(valid_pts) // 2]["parameter"]
        assert ref_profile is not None  # needs_reference guaranteed by stint+deficit path
        per_lap_resp: list[dict[str, Any]] = []
        n_ref_skipped = 0
        for ln, p_item in profile_pairs:
            # per-lap sensitivity: intervention applied to THAT lap's measured
            # profile, with the reference interpolated onto the lap/reference
            # common span (6E semantics; laps without sufficient overlap are
            # skipped and counted - never extrapolated)
            common_lap = _profiles_on_common_grid([p_item, ref_profile])
            if common_lap is None:
                n_ref_skipped += 1
                continue
            lap_grid, lap_rows = common_lap
            lap_vals, ref_lap_vals = lap_rows[0], lap_rows[1]

            def _apply_lap(vals: list[float]) -> list[float]:
                if scenario_type == "DEFICIT_REDUCTION":
                    return [v + mid_param * max(r - v, 0.0)
                            for v, r in zip(vals, ref_lap_vals)]
                return [(1.0 - mid_param) * v + mid_param * r
                        for v, r in zip(vals, ref_lap_vals)]

            lap_base_segs = _segmentize(lap_vals, lap_grid, segment_s)
            lap_dist = [s["distance"] for s in lap_base_segs]
            lap_base, eb = _model_lap_time(
                lap_dist, [s["mean_v"] for s in lap_base_segs])
            lap_cf_segs = _segmentize(_apply_lap(lap_vals), lap_grid, segment_s)
            lap_cf, ecf = _model_lap_time(
                lap_dist, [s["mean_v"] for s in lap_cf_segs])
            if (eb == 0 and ecf == 0 and math.isfinite(lap_cf - lap_base)
                    and lap_base > 0):
                per_lap_resp.append({
                    "lap_number": ln,
                    "grid_span_s": round(lap_grid[-1] - lap_grid[0], 4),
                    "delta_s": round(lap_cf - lap_base, 6),
                })
        if n_ref_skipped:
            excluded.append({"reason": f"per-lap sensitivity skipped for {n_ref_skipped} laps "
                                       "(insufficient reference overlap)"})
        if len(per_lap_resp) >= 3:
            xs = list(range(len(per_lap_resp)))
            ys = [r["delta_s"] for r in per_lap_resp]
            n = len(xs)
            mx = sum(xs) / n
            my = sum(ys) / n
            denom = sum((x - mx) ** 2 for x in xs)
            slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom) if denom else 0.0
            stint_response = {
                "method": "mid-parameter scenario applied to each measured stint lap "
                          "on its own grid; OLS trend over lap order",
                "parameter": mid_param,
                "per_lap": per_lap_resp,
                "sensitivity_trend_s_per_lap": round(slope, 6),
                "interpretation": (
                    "descriptive trend of model sensitivity across the stint; "
                    "interpret alongside canonical degradation evidence - no new "
                    "tyre model is built here"),
            }

    out: dict[str, Any] = {
        **base,
        "status": VALID,
        "anchor_lap": anchor,
        "excluded_laps": excluded,
        "envelope": {
            "scope": scope,
            "laps_used": envelope_laps,
            "n_profiles": len(rows),
            "grid": {
                "step_s": round(grid[1] - grid[0], 4),
                "t_start_s": grid[0], "t_end_s": grid[-1],
                "n_points": n_pts, "coverage_s": round(grid[-1] - grid[0], 4),
            },
            "band_summary": {
                "mean_band_width_kmh": round(
                    sum(u - l for l, u in zip(lower, upper)) / n_pts, 2),
                "overall_min_speed_kmh": round(min(lower), 2),
                "overall_max_speed_kmh": round(max(upper), 2),
            },
        },
        "model_baseline": {
            "method": "Phase 6I fixed-distance segment model on the median profile",
            "segment_s": segment_s, "n_segments": len(segs),
            "baseline_time_s": round(baseline_time, 6),
            "measured_grid_duration_s": measured,
            "reproduction_error_s": round(abs(baseline_time - measured), 9),
            "identity_delta_s": 0.0,
        },
        "scenario_definition": {
            "type": scenario_type,
            "parameters": params,
            "max_scenarios_cap": MAX_SCENARIOS_CAP,
            "reference": reference_driver if needs_reference else None,
            "definitions": {
                "OBSERVED": "identity: the measured median profile unchanged",
                "DEFICIT_REDUCTION": "v' = v + f*max(v_ref - v, 0) on the median profile",
                "REFERENCE_BLEND": "v' = (1-w)*v + w*v_ref on the median profile",
                "ENVELOPE_LOWER_BOUND": "the slowest measured form per grid point",
                "ENVELOPE_UPPER_BOUND": "the fastest measured form per grid point",
            },
        },
        "scenarios": scenario_results,
        "sensitivity": {
            "response": response,
            "note": "each delta is a model sensitivity under the specified "
                    "deterministic intervention; non-linear response is measured, "
                    "never fitted",
        },
        "regional_response": regional or None,
        "stint_response": stint_response,
        "assumptions": [
            "the envelope is measured variability over the driver's own clean laps",
            "scenarios transform only the speed profile; the 6I model scope applies "
            "(no racing line, tyre, fuel, traffic or DRS mechanics)",
            "reference scenarios use the reference driver's telemetry on the anchor lap",
            "results cover the sampled measured laps only; no race-wide extrapolation",
        ],
        "limitations": [
            "non-speed signals remain UNSUPPORTED (no deterministic lap-time model)",
            "race-level telemetry counterfactuals remain UNSUPPORTED (Phase 6I)",
        ],
        "provenance": {
            "tables": ["canonical_telemetry", "canonical_lap_times"]
                      + (["canonical_stints"] if stint_number is not None else []),
            "provider": "fastf1",
            "envelope_version": ENVELOPE_VERSION,
            "lap_time_model": "Phase 6I fixed-distance exact quadrature",
        },
    }
    out["output_hash"] = hashlib.sha256(
        json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return out
