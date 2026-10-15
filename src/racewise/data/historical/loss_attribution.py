"""Deterministic telemetry-to-lap loss attribution (Phase 6E).

Central engineering question:
    "WHY did Driver A lose/gain time relative to Driver B on this lap?"

Causal direction is fixed and enforced: the OBSERVED lap-time delta is
measured first (canonical lap facts), and telemetry is used only to
EXPLAIN it. Telemetry never defines the delta.

Alignment decision (documented, §4 of the phase plan):
    Both drivers' telemetry is compared on a COMMON DISTANCE grid (see
    alignment.py): per-driver cumulative distance from measured speeds,
    rescaled to their mean lap distance, resampled to equal spans, with
    speeds linearly interpolated. Why distance, not lap-relative time:
    equal lap time is not equal track position, and time-window means
    overstate the deficit where speed varies (Jensen gap) — measured
    2-4x inflation on real laps. Distance-fraction alignment compares
    both drivers at the same fraction of lap distance; the signed sum
    reconciles with the measured delta up to interpolation error.
    Regions are equal-distance spans; t_start/t_end map through driver
    A's distance->time for display on time-axis views. Original
    telemetry is never modified.

Loss model (§9, conservative):
    The lap is divided into equal-DISTANCE spans on the common grid. For
    each span, the straight-line time-loss estimate
        loss_s = ds * (1/v_B - 1/v_A)
    attributes the observed pace deficit to the span. Span losses sum to
    a signed net which is RECONCILED against the independently measured
    lap-time delta; the residual is reported explicitly, never discarded.
    Regions aggregate spans for display and ranking; the positive-only
    regional figure exists for worst-region localisation only and is
    non-additive.

    Important honesty boundary: this straight-line model ignores racing
    line, tyre state, and fuel; the sum of region losses is an ESTIMATE
    of the pace deficit embedded in the speed traces, not the measured
    lap delta. The residual (measured delta - estimated) is therefore a
    first-class output, and its magnitude is interpreted (small = speed
    trace explains the delta; large = the delta lives outside the speed
    traces, e.g. pit path, standing start, or measurement differences).

Signal metrics (§8, per-signal definitions):
    speed      mean/max delta over regions; region of divergence
    throttle   mean throttle delta; lift-window count
    brake      braking-fraction delta; earliest-braking-point delta
    gear       fraction of samples in a different gear
    rpm        mean rpm delta
    drs        activation-fraction delta

Evidence typing follows the evidence taxonomy: measured deltas are FACT,
window losses and attributions are CALCULATION, interpretations are
INFERENCE, and every assumption is listed explicitly.

All outputs are deterministic: same canonical data + same methodology
version => byte-identical JSON.
"""
from __future__ import annotations

from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries

ATTRIBUTION_VERSION = "1.0"
DEFAULT_STEP_S = 0.25          # resample grid for signal comparison
DEFAULT_REGION_S = 15.0        # loss-attribution region width
MIN_SAMPLES_PER_SIGNAL = 20    # below this, evidence is too thin
RESIDUAL_TOLERANCE_S = 0.05    # reconciliation tolerance for reporting
ALPHA_RESAMPLE = 0.25          # grid step used by resample (s)

# Laps whose time_s is not representative of car performance. lap_times
# flags come from the canonical FastF1 rows (booleans 0/1 or NULL).
_NON_COMPARABLE_FLAGS = ("is_pit_in_lap", "is_pit_out_lap", "deleted")

# FastF1 track_status codes contained in the lap row's status string.
# '1' = all clear. Any of these mean the lap ran under restriction.
_TRACK_STATUS_RESTRICTED = {"2", "4", "5", "6", "7"}  # yellow, SC, SC-ending, VSC, VSC-ending

VALID = "VALID_COMPARISON"
VALID_CAVEATS = "VALID_WITH_CAVEATS"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
UNAVAILABLE = "UNAVAILABLE"


# ---------------------------------------------------------------------------
# interpolation primitives
# ---------------------------------------------------------------------------

def _interp_series(series: list[tuple[float, float]], grid: list[float]) -> list[Optional[float]]:
    """Linear interpolation onto `grid`, clamped to the observed span.

    Returns None for grid points outside the source span (no extrapolation).
    Deterministic; source series must be sorted by time.
    """
    if not series:
        return [None] * len(grid)
    ts = [t for t, _ in series]
    vs = [v for _, v in series]
    out: list[Optional[float]] = []
    lo, hi = ts[0], ts[-1]
    j = 0
    for g in grid:
        if g < lo or g > hi:
            out.append(None)
            continue
        # advance j to the last index with ts[j] <= g
        while j + 1 < len(ts) and ts[j + 1] <= g:
            j += 1
        if ts[j] == g:
            out.append(vs[j])
            continue
        if j + 1 >= len(ts):
            out.append(vs[j] if g == hi else None)
            continue
        t0, t1 = ts[j], ts[j + 1]
        v0, v1 = vs[j], vs[j + 1]
        out.append(v0 + (v1 - v0) * (g - t0) / (t1 - t0))
    return out


def _resample_lap(
    series_by_signal: dict[str, list[tuple[float, float]]],
    step_s: float = ALPHA_RESAMPLE,
) -> Optional[dict[str, list[Optional[float]]]]:
    """Build a shared time grid over the overlapping span of all signals."""
    if not series_by_signal:
        return None
    lo = max(s[0][0] for s in series_by_signal.values())
    hi = min(s[-1][0] for s in series_by_signal.values())
    if hi <= lo:
        return None
    n = int((hi - lo) / step_s) + 1
    grid = [round(lo + i * step_s, 4) for i in range(n)]
    return {
        signal: _interp_series(series, grid)
        for signal, series in series_by_signal.items()
    }


def _mean(vals: list[float]) -> Optional[float]:
    return sum(vals) / len(vals) if vals else None


def _clean_floats(vals: list[Optional[float]]) -> list[float]:
    return [v for v in vals if v is not None]


# ---------------------------------------------------------------------------
# context / validity classification
# ---------------------------------------------------------------------------

def _classify_lap(lap: Optional[dict], weather_rain: bool) -> dict[str, Any]:
    """Context flags for one canonical lap row (never silently excludes)."""
    if lap is None:
        return {"present": False, "comparable": False, "reasons": ["lap_missing"]}
    reasons: list[str] = []
    for flag in _NON_COMPARABLE_FLAGS:
        if lap.get(flag):
            reasons.append(flag)
    if lap.get("time_s") is None:
        reasons.append("no_lap_time")
    status = str(lap.get("track_status") or "")
    restricted = any(code in status for code in _TRACK_STATUS_RESTRICTED)
    if restricted:
        reasons.append("track_status_restricted")
    if not lap.get("is_accurate", 1):
        reasons.append("flagged_inaccurate")
    if weather_rain:
        reasons.append("rain_observed_in_session")
    comparable = not reasons
    return {
        "present": True,
        "comparable": comparable,
        "reasons": reasons,
        "track_status": status or None,
        "compound": lap.get("compound"),
        "stint": lap.get("stint"),
        "tyre_life": lap.get("tyre_life"),
    }


def _compound_caveat(comp_a: Optional[str], comp_b: Optional[str]) -> list[str]:
    if comp_a and comp_b and comp_a != comp_b:
        return [f"compound_mismatch ({comp_a} vs {comp_b})"]
    return []


# ---------------------------------------------------------------------------
# per-signal comparison metrics (explicit definition per signal)
# ---------------------------------------------------------------------------

def _signal_metrics(
    grid: list[float],
    res_a: dict[str, list[Optional[float]]],
    res_b: dict[str, list[Optional[float]]],
) -> dict[str, Any]:
    """Signal-by-signal comparison over the shared grid.

    Each metric has an explicit definition; none are claimed causal.
    """
    metrics: dict[str, Any] = {}

    # --- speed: mean/max delta over shared samples
    pairs_speed = [
        (g, (b or 0) - (a or 0))
        for g, a, b in zip(grid, res_a.get("speed", []), res_b.get("speed", []))
        if a is not None and b is not None
    ]
    if pairs_speed:
        dvals = [d for _, d in pairs_speed]
        worst = min(pairs_speed, key=lambda p: p[1])
        metrics["speed"] = {
            "definition": "mean and max speed delta (B - A, km/h) over resampled grid; min-delta timestamp = largest deficit point",
            "mean_delta_kmh": round(_mean(dvals), 3),
            "max_deficit_kmh": round(min(dvals), 3),
            "max_gain_kmh": round(max(dvals), 3),
            "largest_deficit_at_lap_time_s": round(worst[0], 3),
            "n_samples": len(dvals),
        }

    # --- throttle: mean delta + lift-window count
    th_a = res_a.get("throttle", [])
    th_b = res_b.get("throttle", [])
    pairs_th = [
        (b or 0) - (a or 0)
        for a, b in zip(th_a, th_b)
        if a is not None and b is not None
    ]
    if pairs_th:
        # lift window: consecutive grid points where B < 50% while A >= 90%
        lift_pts = 0
        in_lift = False
        for a, b in zip(th_a, th_b):
            if a is None or b is None:
                continue
            if b < 50 and a >= 90:
                if not in_lift:
                    lift_pts += 1
                    in_lift = True
            else:
                in_lift = False
        metrics["throttle"] = {
            "definition": "mean throttle delta (B - A, % of full) + count of lift-windows (B<50% while A>=90%)",
            "mean_delta_pct": round(_mean(pairs_th), 3),
            "b_lift_windows_vs_a": lift_pts,
        }

    # --- brake: braking fraction + earliest braking point
    br_a = res_a.get("brake", [])
    br_b = res_b.get("brake", [])
    pairs_br = [(a, b) for a, b in zip(br_a, br_b) if a is not None and b is not None]
    if pairs_br:
        frac_a = _mean([float(a) for a, _ in pairs_br]) or 0
        frac_b = _mean([float(b) for _, b in pairs_br]) or 0
        t_brake_a = next((g for g, v in zip(grid, br_a) if v), None)
        t_brake_b = next((g for g, v in zip(grid, br_b) if v), None)
        metrics["brake"] = {
            "definition": "braking-fraction delta (B - A share of grid samples braking) + earliest braking point delta (B - A, s)",
            "braking_fraction_delta": round(frac_b - frac_a, 4),
            "first_brake_a_s": round(t_brake_a, 3) if t_brake_a is not None else None,
            "first_brake_b_s": round(t_brake_b, 3) if t_brake_b is not None else None,
            "first_brake_delta_s": (
                round(t_brake_b - t_brake_a, 3)
                if (t_brake_a is not None and t_brake_b is not None) else None
            ),
        }

    # --- gear: fraction of samples in a different gear
    g_a = res_a.get("gear", [])
    g_b = res_b.get("gear", [])
    pairs_g = [(a, b) for a, b in zip(g_a, g_b) if a is not None and b is not None]
    if pairs_g:
        diff_frac = _mean([1.0 if int(a) != int(b) else 0.0 for a, b in pairs_g]) or 0
        metrics["gear"] = {
            "definition": "fraction of grid samples where selected gear differs",
            "gear_mismatch_fraction": round(diff_frac, 4),
        }

    # --- rpm: mean delta
    r_a = res_a.get("rpm", [])
    r_b = res_b.get("rpm", [])
    pairs_r = [(b or 0) - (a or 0) for a, b in zip(r_a, r_b) if a is not None and b is not None]
    if pairs_r:
        metrics["rpm"] = {
            "definition": "mean rpm delta (B - A) over resampled grid",
            "mean_delta_rpm": round(_mean(pairs_r), 1),
        }

    # --- drs: activation fraction delta
    d_a = res_a.get("drs", [])
    d_b = res_b.get("drs", [])
    pairs_d = [(a, b) for a, b in zip(d_a, d_b) if a is not None and b is not None]
    if pairs_d:
        # DRS enabled states are codes 8/10/12/14 per FastF1 docs
        act_a = _mean([1.0 if int(a) >= 8 else 0.0 for a, _ in pairs_d]) or 0
        act_b = _mean([1.0 if int(b) >= 8 else 0.0 for _, b in pairs_d]) or 0
        metrics["drs"] = {
            "definition": "DRS activation-fraction delta (B - A share of grid samples with DRS enabled codes>=8)",
            "activation_fraction_delta": round(act_b - act_a, 4),
        }
    return metrics


# ---------------------------------------------------------------------------
# loss attribution with regions + reconciliation
# ---------------------------------------------------------------------------

def attribute_lap_loss(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_a: str,
    driver_b: str,
    lap_number: int,
    session_type: str = "RACE",
    region_s: float = DEFAULT_REGION_S,
    step_s: float = ALPHA_RESAMPLE,
) -> dict[str, Any]:
    """Attribute the measured lap-time delta to lap-time regions.

    Order of operations (enforced):
      1. measure the lap-time delta from canonical lap facts (FACT)
      2. classify context/validity for both laps
      3. resample telemetry onto the shared lap-relative grid
      4. compute per-region speed-based loss estimates (CALCULATION)
      5. reconcile: measured delta ≈ signed-net region sum + residual
         (the gross positive-only exposure is non-additive localisation)
      6. attach per-signal metrics for the divergent regions

    Returns INSUFFICIENT_EVIDENCE / UNAVAILABLE rather than guessing.
    """
    base: dict[str, Any] = {
        "analysis": "attribute_lap_loss",
        "version": ATTRIBUTION_VERSION,
        "season": season,
        "round": round_num,
        "session_type": session_type,
        "lap_number": lap_number,
        "driver_a": driver_a,
        "driver_b": driver_b,
        "alignment": {
            "method": "lap-relative time resampling (linear, clamped, no extrapolation)",
            "grid_step_s": step_s,
            "why": "car-local timestamps share no time base; lap_time_s is canonical",
        },
        "loss_model": {
            "method": "straight-line region loss dt*(1 - v_B/v_A) per region",
            "region_s": region_s,
            "note": "estimate of pace deficit in the speed traces; residual vs measured delta is first-class",
        },
    }

    tel_summary = queries.telemetry_summary(season, round_num, session_type)
    if not tel_summary["available"]:
        return {**base, "status": UNAVAILABLE, "reason": "no canonical telemetry for this session"}

    laps_a = {r["lap_number"]: r for r in queries.get_lap_times(season, round_num, session_type, driver_a)}
    laps_b = {r["lap_number"]: r for r in queries.get_lap_times(season, round_num, session_type, driver_b)}
    lap_a, lap_b = laps_a.get(lap_number), laps_b.get(lap_number)

    # Rain context is per-lap: only observations within the lap's own time
    # window matter. Session-level "any rainfall" would disqualify every lap
    # of every wet-weather race (e.g. 2022 R10) - the correct granularity is
    # the lap window [lap_start, lap_end) mapped to session-relative time.
    rain_a = _rain_in_window(queries, season, round_num, session_type, lap_a)
    rain_b = _rain_in_window(queries, season, round_num, session_type, lap_b)
    ctx_a = _classify_lap(lap_a, rain_a)
    ctx_b = _classify_lap(lap_b, rain_b)
    caveats: list[str] = _compound_caveat(
        ctx_a.get("compound"), ctx_b.get("compound")
    )
    caveats.extend(f"driver_a:{r}" for r in ctx_a["reasons"])
    caveats.extend(f"driver_b:{r}" for r in ctx_b["reasons"])

    if lap_a is None or lap_b is None:
        return {
            **base,
            "status": UNAVAILABLE,
            "reason": "lap missing from canonical lap facts for "
                      f"{driver_a if lap_a is None else driver_b}",
            "context": {"driver_a": ctx_a, "driver_b": ctx_b},
        }

    # (1) measured delta - FACT, from canonical lap rows
    t_a, t_b = lap_a.get("time_s"), lap_b.get("time_s")
    if t_a is None or t_b is None:
        return {
            **base,
            "status": INSUFFICIENT,
            "reason": "one or both laps lack a measured lap time",
            "context": {"driver_a": ctx_a, "driver_b": ctx_b, "caveats": caveats},
        }
    observed_delta_s = round(t_b - t_a, 4)

    if not ctx_a["comparable"] or not ctx_b["comparable"]:
        return {
            **base,
            "status": INSUFFICIENT,
            "reason": "lap context prevents a clean comparison (pit laps, flags, deleted, inaccurate)",
            "observed_delta_s": observed_delta_s,
            "context": {"driver_a": ctx_a, "driver_b": ctx_b, "caveats": caveats},
        }

    # (3) telemetry on the shared grid
    sig_a = _load_signals(queries, season, round_num, driver_a, lap_number, session_type)
    sig_b = _load_signals(queries, season, round_num, driver_b, lap_number, session_type)
    if sig_a is None or sig_b is None:
        return {
            **base,
            "status": UNAVAILABLE,
            "reason": f"telemetry missing for {driver_a if sig_a is None else driver_b} on this lap",
            "observed_delta_s": observed_delta_s,
            "context": {"driver_a": ctx_a, "driver_b": ctx_b, "caveats": caveats},
        }
    res_a = _resample_lap(sig_a, step_s)
    res_b = _resample_lap(sig_b, step_s)
    if res_a is None or res_b is None:
        return {**base, "status": INSUFFICIENT, "reason": "no overlapping lap-relative span"}
    grid = _shared_grid(sig_a, sig_b, step_s)

    # (4) per-region losses from the speed traces (grid is uniform, so the
    # resampled arrays carry every grid point - no cleaning needed here)
    speed_a = list(zip(grid, res_a["speed"]))
    speed_b = list(zip(grid, res_b["speed"]))
    t0 = max(speed_a[0][0], speed_b[0][0])
    t1 = min(speed_a[-1][0], speed_b[-1][0])
    if t1 <= t0:
        return {**base, "status": INSUFFICIENT, "reason": "no overlapping speed-trace span"}

    # (4) per-region losses from the speed traces, computed on the COMMON
    # DISTANCE grid (see alignment.py): equal lap time is not equal track
    # position, so time-window means overstate the deficit where speed
    # varies (Jensen gap). Distance-fraction alignment compares both
    # drivers at the same fraction of lap distance using their NATIVE
    # samples (resampling would smooth corner entries/exits and reintroduce
    # bias); the signed sum reconciles with the measured delta up to
    # interpolation error.
    from racewise.data.historical.alignment import (
        cumulative_distance,
        distance_aligned_losses,
    )
    nat_a = [(t, v) for t, v in sig_a["speed"]
             if v is not None]
    nat_b = [(t, v) for t, v in sig_b["speed"]
             if v is not None]
    if len(nat_a) < 2 or len(nat_b) < 2:
        return {**base, "status": INSUFFICIENT, "reason": "no overlapping speed-trace span"}
    # Full laps, fraction-aligned: both series span their driver's lap, and
    # the common-distance rescale maps them onto the same [0, D]. Clipping
    # to the time overlap would discard real lap content (up to ~1% of the
    # lap); edge offsets (~0.1 s) are second-order and documented.
    t0 = max(nat_a[0][0], nat_b[0][0])
    t1 = min(nat_a[-1][0], nat_b[-1][0])
    aligned = distance_aligned_losses(
        [t for t, _ in nat_a], [v for _, v in nat_a],
        [t for t, _ in nat_b], [v for _, v in nat_b],
        n_spans=400)
    if aligned is None:
        return {**base, "status": INSUFFICIENT,
                "reason": "derived lap distances disagree beyond tolerance"}
    spans = aligned["span_losses"]
    dist_total = aligned["distance_m"]
    n_regions = max(1, round((t1 - t0) / region_s)) if region_s > 0 else 1
    # driver A distance->time inverse for display mapping (native samples)
    cum_a = cumulative_distance([t for t, _ in nat_a],
                                [v for _, v in nat_a])
    D_a = cum_a[-1] if cum_a[-1] > 0 else dist_total

    def _time_at_distance(s: float) -> float:
        import bisect as _bisect
        i = _bisect.bisect_left(cum_a, s)
        if i <= 0:
            return nat_a[0][0]
        if i >= len(cum_a):
            return nat_a[-1][0]
        c0, c1 = cum_a[i - 1], cum_a[i]
        if c1 == c0:
            return nat_a[i][0]
        f = (s - c0) / (c1 - c0)
        t0_, t1_ = nat_a[i - 1][0], nat_a[i][0]
        return t0_ + f * (t1_ - t0_)

    regions: list[dict[str, Any]] = []
    for r in range(n_regions):
        lo, hi = dist_total * r / n_regions, dist_total * (r + 1) / n_regions
        in_region = [sp for sp in spans if lo <= (sp["s_start_m"] + sp["s_end_m"]) / 2 < hi]
        if r == n_regions - 1:
            in_region = [sp for sp in spans if (sp["s_start_m"] + sp["s_end_m"]) / 2 >= lo]
        if not in_region:
            continue
        signed = round(sum(sp["signed_loss_s"] for sp in in_region), 4)
        va = sum(sp["v_a_kmh"] for sp in in_region) / len(in_region)
        vb = sum(sp["v_b_kmh"] for sp in in_region) / len(in_region)
        # map region distance bounds to A-lap time via A's own cumulative
        # distance rescaled to the common total (same rescaling as alignment)
        t_start = _time_at_distance(lo / dist_total * D_a)
        t_end = _time_at_distance(min(hi, dist_total) / dist_total * D_a)
        regions.append({
            "region": len(regions) + 1,
            "t_start_s": round(t_start, 3),
            "t_end_s": round(t_end, 3),
            "mean_speed_a_kmh": round(va, 2),
            "mean_speed_b_kmh": round(vb, 2),
            "speed_delta_kmh": round(vb - va, 2),
            "signed_loss_s": signed,
            "attributed_loss_s": round(max(signed, 0.0), 4),
        })
    if not regions:
        return {**base, "status": INSUFFICIENT, "reason": "no overlapping speed-trace span"}
    estimated_total = round(sum(r["attributed_loss_s"] for r in regions), 4)
    net_total = round(sum(r["signed_loss_s"] for r in regions), 4)
    # Gross positive-only exposure minus the signed net: the amount of
    # loss created by zeroing faster regions instead of offsetting them.
    # Large values mean the time-aligned windows are mixing track phases
    # (equal lap time is not equal track position; no distance channel
    # is ingested), not that the lap delta is larger than measured.
    rectification_gap = round(estimated_total - net_total, 4)
    residual = round(observed_delta_s - net_total, 4)

    # signal metrics attached for cross-checking regions
    metrics = _signal_metrics(grid, res_a, res_b)

    # (4b) authoritative sector attribution when canonical sector splits
    # exist for BOTH laps: sector deltas are measured FACTS and sum exactly
    # to the lap delta (no model, no residual). Sector telemetry nets are
    # assigned in DISTANCE space: each sector's time share of A's lap maps
    # to a distance share via A's cumulative distance, and distance-span
    # losses sum within it. No padding, no time-window overlap heuristics.
    sectors_out: Optional[list[dict[str, Any]]] = None
    s_a = [lap_a.get("sector1_s"), lap_a.get("sector2_s"), lap_a.get("sector3_s")]
    s_b = [lap_b.get("sector1_s"), lap_b.get("sector2_s"), lap_b.get("sector3_s")]
    if all(v is not None for v in (*s_a, *s_b)):
        import bisect as _bisect2

        nat_times = [t for t, _ in nat_a]

        def _dist_at_time(t: float) -> float:
            i = _bisect2.bisect_left(nat_times, t)
            if i <= 0:
                return cum_a[0]
            if i >= len(nat_times):
                return cum_a[-1]
            c0, c1 = cum_a[i - 1], cum_a[i]
            t0_, t1_ = nat_times[i - 1], nat_times[i]
            if t1_ == t0_:
                return c1
            return c0 + (c1 - c0) * (t - t0_) / (t1_ - t0_)

        scale = dist_total / D_a if D_a > 0 else 1.0
        cum_a_time = [0.0, s_a[0], s_a[0] + s_a[1], s_a[0] + s_a[1] + s_a[2]]
        sec_bounds = [_dist_at_time(t) * scale for t in cum_a_time]
        sectors_out = []
        for i in range(3):
            w_start, w_end = sec_bounds[i], sec_bounds[i + 1]
            in_span = [sp for sp in spans
                       if w_start <= (sp["s_start_m"] + sp["s_end_m"]) / 2
                       < w_end or (i == 2 and (sp["s_start_m"] + sp["s_end_m"]) / 2 >= w_start)]
            sectors_out.append({
                "sector": i + 1,
                "delta_s": round(s_b[i] - s_a[i], 4),          # FACT
                "telemetry_estimated_loss_s": round(sum(
                    max(sp["signed_loss_s"], 0.0) for sp in in_span), 4),
                "telemetry_net_estimate_s": round(sum(
                    sp["signed_loss_s"] for sp in in_span), 4),
                "note": "delta is measured; telemetry estimate covers A's sector distance share",
            })

    # (5) reconciliation verdict — the residual is measured minus the SIGNED
    # net estimate (the reconcilable figure). A large gap between the gross
    # positive-only exposure and the net means the time-aligned windows are
    # mixing track phases; that gap is reported, never assigned. A sector
    # whose measured fact and telemetry net disagree by far more than
    # tolerance is the same failure localised: methodological, not physical.
    sector_mismatch = any(
        abs(s["delta_s"] - s["telemetry_net_estimate_s"])
        > 5 * RESIDUAL_TOLERANCE_S
        for s in (sectors_out or [])
        if isinstance(s, dict)
        and isinstance(s.get("delta_s"), (int, float))
        and isinstance(s.get("telemetry_net_estimate_s"), (int, float))
    )
    phase_mixing = (
        (rectification_gap > RESIDUAL_TOLERANCE_S
         and rectification_gap > 0.5 * abs(observed_delta_s))
        or (abs(residual) > RESIDUAL_TOLERANCE_S and sector_mismatch)
    )
    if phase_mixing:
        interpretation = (
            "window estimates mix track phases (time-aligned, not "
            "distance-aligned): the gross positive-only exposure "
            f"({estimated_total} s) exceeds the signed net "
            f"({net_total} s) because faster windows were zeroed instead "
            "of offsetting. The net estimate is the reconcilable figure; "
            "the gross exposure localises slower windows but is non-additive"
        )
    else:
        interpretation = (
            "speed-trace deficit accounts for the measured delta within tolerance"
            if abs(residual) <= RESIDUAL_TOLERANCE_S
            else (
                "large positive residual: the measured delta exceeds what the speed traces "
                "explain - look for pit-path/track-position effects or lap-time measurement "
                "differences outside the speed traces"
                if residual > 0
                else (
                    "negative residual with B slower than A: the speed-trace model "
                    "OVERESTIMATES the pace component here (time-aligned windows mix "
                    "track phases and window-mean ratios overstate the deficit); the "
                    "net is an upper bound, not a measurement - the measured delta stands"
                    if observed_delta_s > 0
                    else "negative residual: driver B's speed trace does not explain their "
                         "faster lap - window means smooth corner-exit differences the "
                         "straight-line model cannot see"
                )
            )
        )
    reconciliation = {
        "observed_delta_s": observed_delta_s,
        "estimated_pace_component_s": net_total,
        "gross_positive_exposure_s": estimated_total,
        "rectification_gap_s": rectification_gap,
        "phase_mixing_flag": phase_mixing,
        "residual_s": residual,
        "tolerance_s": RESIDUAL_TOLERANCE_S,
        "within_tolerance": abs(residual) <= RESIDUAL_TOLERANCE_S,
        "interpretation": interpretation,
    }

    ranked = sorted(regions, key=lambda r: r["attributed_loss_s"], reverse=True)

    out: dict[str, Any] = {
        **base,
        "status": VALID_CAVEATS if caveats else VALID,
        "observed_delta_s": observed_delta_s,
        "lap_times": {"driver_a": t_a, "driver_b": t_b},
        "context": {"driver_a": ctx_a, "driver_b": ctx_b, "caveats": caveats},
        "grid_span_s": {"t_start": round(t0, 3), "t_end": round(t1, 3)},
        "n_regions": len(regions),
        "regions": regions,
        "top_loss_regions": ranked[:3],
        "sector_attribution": sectors_out,
        "estimated_pace_component_s": net_total,
        "gross_positive_exposure_s": estimated_total,
        "gross_scope_note": (
            "gross positive-only region exposure (faster regions zeroed, "
            "not offset); NON-ADDITIVE — for worst-region localisation "
            "only; use estimated_pace_component_s (signed net) for "
            "reconciliation"
        ),
        "residual_s": residual,
        "reconciliation": reconciliation,
        "signal_metrics": metrics,
        "evidence_typing": {
            "FACT": ["observed_delta_s", "lap_times"],
            "CALCULATION": ["regions[].attributed_loss_s", "regions[].signed_loss_s",
                            "estimated_pace_component_s", "gross_positive_exposure_s",
                            "residual_s", "signal_metrics"],
            "INFERENCE": ["reconciliation.interpretation"],
        },
        "assumptions": [
            "linear interpolation of car-local telemetry onto a 0.25 s shared grid",
            "straight-line region loss dt*(1 - v_B/v_A); ignores racing line, tyre state, fuel",
            "region losses estimate the pace deficit embedded in the speed traces only",
            "regions align by lap-relative TIME (SessionTime - LapStartTime per driver); "
            "equal lap time is not equal track position and no distance channel is "
            "ingested, so neighbouring regions can mix track phases",
            "both laps ran in comparable context (see context flags for caveats)",
        ],
        "provenance": {
            "tables": ["canonical_lap_times", "canonical_telemetry"],
            "provider": "fastf1",
            "attribution_version": ATTRIBUTION_VERSION,
        },
    }
    return out


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_signals(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_key: str,
    lap_number: int,
    session_type: str,
) -> Optional[dict[str, list[tuple[float, float]]]]:
    out: dict[str, list[tuple[float, float]]] = {}
    for signal in ("speed", "throttle", "brake", "gear", "rpm", "drs"):
        rows = queries.get_lap_telemetry(
            season, round_num, driver_key, lap_number,
            session_type=session_type, signals=[signal],
        )
        if len(rows) < MIN_SAMPLES_PER_SIGNAL:
            return None
        out[signal] = [(r["lap_time_s"], r["value"]) for r in rows]
    return out


def _shared_grid(
    sig_a: dict[str, list[tuple[float, float]]],
    sig_b: dict[str, list[tuple[float, float]]],
    step_s: float,
) -> list[float]:
    lo = max(sig_a["speed"][0][0], sig_b["speed"][0][0])
    hi = min(sig_a["speed"][-1][0], sig_b["speed"][-1][0])
    n = int((hi - lo) / step_s) + 1
    return [round(lo + i * step_s, 4) for i in range(n)]


def _rain_in_window(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    session_type: str,
    lap: Optional[dict],
) -> bool:
    """True when rainfall was observed during THIS lap's time window.

    Lap window = [cumulative mean lap * (n-1), cumulative mean lap * n), the
    same documented approximation used by Q4 weather correlation. Laps with
    no measured time return False (the lap itself is already disqualified).
    """
    if not lap or lap.get("time_s") is None:
        return False
    obs = [w for w in queries.get_weather(season, round_num, session_type)
           if w.get("elapsed_s") is not None and w.get("rainfall") is not None]
    if not obs:
        return False
    mean_lap = lap["time_s"]
    n = lap["lap_number"] or 1
    lo, hi = (n - 1) * mean_lap, n * mean_lap
    return any(lo <= o["elapsed_s"] < hi and o["rainfall"] for o in obs)


def _mean_in(series: list[tuple[float, float]], t_start: float, t_end: float) -> Optional[float]:
    vals = [v for (tt, v) in series if t_start <= tt < t_end]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# falsification + stint aggregation
# ---------------------------------------------------------------------------

def falsify_attribution(
    queries: CanonicalQueries,
    attribution: dict[str, Any],
) -> dict[str, Any]:
    """Actively test alternative explanations for the attributed loss.

    Tests the data, not the narrative:
      - braking hypothesis: does B brake more/earlier in the top loss region?
      - DRS hypothesis: was B's DRS availability materially lower?
      - traffic/flags: was either lap under restricted track status?
      - tyre state: large compound/tyre-life mismatch?
    Each check reports SUPPORTED / NOT_SUPPORTED / NOT_TESTABLE with the
    numbers used. Nothing is claimed causal.
    """
    season, rnd = attribution["season"], attribution["round"]
    lap = attribution["lap_number"]
    a, b = attribution["driver_a"], attribution["driver_b"]
    metrics = attribution.get("signal_metrics", {})
    ctx = attribution.get("context", {})
    checks: list[dict[str, Any]] = []

    top = (attribution.get("top_loss_regions") or [{}])[0]
    t_start = top.get("t_start_s")

    # braking hypothesis
    brake = metrics.get("brake")
    if brake:
        delta = brake.get("braking_fraction_delta")
        onset = brake.get("first_brake_delta_s")
        if delta is not None and delta > 0.02:
            checks.append({"hypothesis": "B braked more than A (extra braking explains the deficit)",
                           "verdict": "SUPPORTED", "evidence": f"braking_fraction_delta={delta}"})
        elif onset is not None and onset < -0.2:
            checks.append({"hypothesis": "B braked later than A (late braking into the region)",
                           "verdict": "NOT_SUPPORTED",
                           "evidence": f"first_brake_delta_s={onset} (B braked earlier or same)"})
        else:
            checks.append({"hypothesis": "braking differences explain the deficit",
                           "verdict": "NOT_SUPPORTED",
                           "evidence": f"braking_fraction_delta={delta}, first_brake_delta_s={onset}"})

    # DRS hypothesis
    drs = metrics.get("drs")
    if drs:
        d = drs.get("activation_fraction_delta")
        if d is not None and abs(d) > 0.1:
            checks.append({"hypothesis": "DRS availability difference explains the deficit",
                           "verdict": "SUPPORTED" if d < 0 else "NOT_SUPPORTED",
                           "evidence": f"activation_fraction_delta={d} (B relative to A)"})
        else:
            checks.append({"hypothesis": "DRS availability difference explains the deficit",
                           "verdict": "NOT_SUPPORTED", "evidence": f"activation_fraction_delta={d}"})

    # flags / traffic context
    restricted = [k for k in (*ctx.get("driver_a", {}).get("reasons", []),
                              *ctx.get("driver_b", {}).get("reasons", []),)
                  if k == "track_status_restricted"]
    checks.append({
        "hypothesis": "race-control restriction (SC/VSC/yellow) affected the comparison",
        "verdict": "NOT_TESTABLE" if not restricted else "SUPPORTED",
        "evidence": f"restricted laps: {len(restricted)}",
    })

    # tyre state
    comp_a = ctx.get("driver_a", {}).get("compound")
    comp_b = ctx.get("driver_b", {}).get("compound")
    checks.append({
        "hypothesis": "compound mismatch confounds the comparison",
        "verdict": "SUPPORTED" if (comp_a and comp_b and comp_a != comp_b) else "NOT_SUPPORTED",
        "evidence": f"compound A={comp_a}, B={comp_b}",
    })

    return {
        "method": "alternative explanations tested against the measured signal metrics and lap context",
        "checks": checks,
        "n_supported": sum(1 for c in checks if c["verdict"] == "SUPPORTED"),
        "note": "SUPPORTED means the evidence is consistent with the hypothesis; causation is not claimed",
    }


def attribute_stint_loss(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_a: str,
    driver_b: str,
    stint_number: int,
    session_type: str = "RACE",
    max_laps: int = 6,
) -> dict[str, Any]:
    """Stint-level attribution: per-lap attribution across a stint, aggregated.

    Comparable laps = clean laps of the stint present for BOTH drivers.
    Aggregates observed deltas, attributed pace components, residuals and
    the dominant loss region per lap. Deterministic and bounded (max_laps).
    """
    base: dict[str, Any] = {
        "analysis": "attribute_stint_loss",
        "version": ATTRIBUTION_VERSION,
        "season": season, "round": round_num, "session_type": session_type,
        "driver_a": driver_a, "driver_b": driver_b, "stint_number": stint_number,
    }
    laps_a = queries.get_lap_times(season, round_num, session_type, driver_a)
    laps_b = queries.get_lap_times(season, round_num, session_type, driver_b)
    stints_a = {s.get("lap_start"): s for s in queries.get_stints(season, round_num, session_type, driver_a)}
    stint_laps_a = sorted(
        r["lap_number"] for r in laps_a
        if r.get("stint") == stint_number and r.get("time_s")
        and not any(r.get(f) for f in _NON_COMPARABLE_FLAGS)
    )
    if not stint_laps_a:
        return {**base, "status": INSUFFICIENT, "reason": "no clean laps in this stint for driver_a"}
    stint_laps_b = {
        r["lap_number"] for r in laps_b
        if r.get("stint") == stint_number and r.get("time_s")
        and not any(r.get(f) for f in _NON_COMPARABLE_FLAGS)
    }
    comparable = [ln for ln in stint_laps_a if ln in stint_laps_b]
    if len(comparable) < 2:
        return {**base, "status": INSUFFICIENT,
                "reason": f"fewer than 2 common clean laps ({len(comparable)})"}

    # bounded deterministic selection: evenly spaced sample of the stint
    if len(comparable) > max_laps:
        step = (len(comparable) - 1) / (max_laps - 1)
        picked = sorted({int(round(i * step)) for i in range(max_laps)})
        comparable = [comparable[i] for i in picked]

    per_lap: list[dict[str, Any]] = []
    for ln in comparable:
        att = attribute_lap_loss(queries, season, round_num, driver_a, driver_b, ln, session_type)
        if att.get("status") in (VALID, VALID_CAVEATS):
            per_lap.append({
                "lap_number": ln,
                "observed_delta_s": att["observed_delta_s"],
                "estimated_pace_component_s": att["estimated_pace_component_s"],
                "residual_s": att["residual_s"],
                "dominant_region_t_start_s": (att.get("top_loss_regions") or [{}])[0].get("t_start_s"),
                "status": att["status"],
            })
        else:
            per_lap.append({"lap_number": ln, "status": att.get("status"),
                            "reason": att.get("reason")})

    usable = [p for p in per_lap if p.get("observed_delta_s") is not None]
    if not usable:
        return {**base, "status": INSUFFICIENT, "reason": "no attributable laps in the stint sample"}

    deltas = [p["observed_delta_s"] for p in usable]
    components = [p["estimated_pace_component_s"] for p in usable]
    residuals = [p["residual_s"] for p in usable]
    s_deltas = sorted(deltas)
    median_delta = (
        s_deltas[len(s_deltas) // 2] if len(s_deltas) % 2
        else round((s_deltas[len(s_deltas) // 2 - 1] + s_deltas[len(s_deltas) // 2]) / 2, 4)
    )
    # degradation trend of the DELTA across the sampled laps (least squares)
    xs = list(range(len(usable)))
    n = len(xs)
    mx, my = _mean([float(x) for x in xs]) or 0, _mean(deltas) or 0
    denom = sum((x - mx) ** 2 for x in xs)
    trend = (sum((x - mx) * (d - my) for x, d in zip(xs, deltas)) / denom) if denom else 0.0

    return {
        **base,
        "status": VALID_CAVEATS if any(p.get("status") == VALID_CAVEATS for p in usable) else VALID,
        "stint_info": {"driver_a": stints_a.get(min(stint_laps_a))},
        "laps_sampled": len(usable),
        "sampled_lap_numbers": [p["lap_number"] for p in usable],
        "per_lap": per_lap,
        "aggregate": {
            "mean_observed_delta_s": round(_mean(deltas), 4),
            "median_observed_delta_s": median_delta,
            "mean_estimated_pace_component_s": round(_mean(components), 4),
            "mean_residual_s": round(_mean(residuals), 4),
            "delta_trend_s_per_sample_index": round(trend, 4),
            "unexplained_fraction": round(
                abs(_mean(residuals) or 0) / max(abs(_mean(deltas) or 1e-9), 1e-9), 4
            ),
            "n_unexplained_note": "unexplained_fraction = |mean residual| / |mean observed delta|",
        },
        "assumptions": [
            "per-lap attributions use the same straight-line region model",
            "sampled laps are evenly spaced across the stint (bounded)",
        ],
        "provenance": {"tables": ["canonical_lap_times", "canonical_telemetry", "canonical_stints"],
                       "attribution_version": ATTRIBUTION_VERSION},
    }
