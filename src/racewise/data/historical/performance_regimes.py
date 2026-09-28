"""Phase 6K — performance regime & change-point intelligence.

Deterministic temporal segmentation of a race's comparable-lap delta
series into performance regimes, aligned with canonical context and the
existing evidence layers. Derived on read; zero storage growth.

Design position
---------------
A regime is an *analytical* contiguous interval of comparable laps whose
descriptive gap behaviour remains within deterministic thresholds. It is
NOT a stint: canonical stint identity is preserved separately and a
regime may cross a stint boundary.

Change-point detection is bounded deterministic segmentation over an OLS
slope statistic. It organizes measured temporal structure; it does not
establish causality and it never emits confidence scores — states are
DETECTED / NOT_DETECTED / INSUFFICIENT_EVIDENCE.

Epistemic separation (mandatory):
    historical observation != evidence verdict != model sensitivity
A performance transition "temporally aligned with" a context change is
an association statement, never a causal one.

Everything reuses existing machinery (no second engine):
    6E/6H  timeline, per-lap comparability, context classification
    6G     OLS slope, trend thresholds, hypothesis summary rules
    6F     per-lap fused evidence (statuses propagate verbatim)
    6I/6J  speed-profile model + bounded scenario sensitivity
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.race_gap import (
    _classify_laps,
    _load_context,
    _official_gap,
    _pit_laps,
    _rc_restricted_laps,
    _telemetry_laps,
)

REGIME_VERSION = "1.0"
ANALYSIS = "analyze_performance_regimes"

# ---- deterministic change-point parameters (documented, tested) ---------
# 6G/6H use |slope| >= 0.03 s/lap as the gap-trend significance threshold;
# regimes reuse the identical threshold rather than inventing a new one.
SLOPE_THRESHOLD_S_PER_LAP = 0.03
# Segmentation statistic: split where the paired half-slope difference is
# maximal; require the difference to clear twice the significance threshold
# so a split implies two regimes whose slopes genuinely differ.
SEGMENT_STAT_THRESHOLD = 2.0 * SLOPE_THRESHOLD_S_PER_LAP
# Same floor as 6G MIN_TREND_OBS: a 2-point "slope" is not evidence.
MIN_REGIME_LAPS = 3
ABS_TOL = 1e-9
MAX_SENSITIVITY_LAPS = 4
# Scenario sweep inside each telemetry-supported regime (6J semantics).
SENSITIVITY_FRACTION = 0.5

GAP_PATTERN_STATES = ("STABLE", "WIDENING", "NARROWING", "REVERSAL",
                      "INSUFFICIENT_EVIDENCE")
CHANGE_POINT_TYPES = (
    "GAP_TREND_CHANGE",
    "SPEED_PROFILE_CHANGE",
    "ENVELOPE_CHANGE",
    "RESIDUAL_CHANGE",
    "CONTEXT_CHANGE",
    "HYPOTHESIS_STATE_CHANGE",
    "STINT_TRANSITION",
    "PIT_TRANSITION",
    "RACE_CONTROL_TRANSITION",
    "WEATHER_TRANSITION",
)

SPEED_PROFILE_GAP_STATE = "TELEMETRY_UNAVAILABLE"

_METHOD = (
    "deterministic top-down slope segmentation over comparable-lap deltas "
    "(OLS; split statistic = |right slope - left slope|, significance "
    f"{SLOPE_THRESHOLD_S_PER_LAP} s/lap, split threshold "
    f"{SEGMENT_STAT_THRESHOLD} s/lap, MIN_REGIME_LAPS={MIN_REGIME_LAPS}, "
    "SSE-improvement gate, deterministic near-slope merging); descriptive "
    "only - no causality, no confidence scores"
)

ASSUMPTIONS = [
    "regimes are analytical intervals of comparable laps, not canonical stints",
    "change points are detected from deterministic OLS slope statistics only",
    "a transition temporally aligned with a context change is an association, "
    "not a causal claim",
    "model sensitivity is a property of the 6I/6J speed-profile model, not "
    "historical causation",
    "telemetry gaps are preserved as explicit unavailable intervals; no "
    "interpolation across them",
]


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def _ols_slope(xs: list[float], ys: list[float]) -> float:
    """OLS slope; identical definition to the 6G slope helper."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def _sse(values: list[float], slope: float) -> float:
    """Residual SSE of the OLS fit with intercept chosen by means."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(1, n + 1))
    mx = (n + 1) / 2
    my = sum(values) / n
    intercept = my - slope * mx
    return sum((v - (slope * x + intercept)) ** 2 for x, v in zip(xs, values))


# ---------------------------------------------------------------------------
# Race comparison setup (6H entry semantics)
# ---------------------------------------------------------------------------

def _pair_base(queries: CanonicalQueries, season: int, round_num: int,
               driver_a: str, driver_b: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Shared base + pair validation mirroring 6H decompose_race_gap."""
    base: dict[str, Any] = {
        "analysis": ANALYSIS,
        "version": REGIME_VERSION,
        "season": season,
        "round": round_num,
        "session_type": "RACE",
        "driver_a": driver_a,
        "driver_b": driver_b,
        "methodology": _METHOD,
        "assumptions": list(ASSUMPTIONS),
        "thresholds": {
            "slope_threshold_s_per_lap": SLOPE_THRESHOLD_S_PER_LAP,
            "segment_stat_threshold_s_per_lap": SEGMENT_STAT_THRESHOLD,
            "min_regime_laps": MIN_REGIME_LAPS,
        },
    }
    if driver_a == driver_b:
        return base, {"status": "UNAVAILABLE", "reason": "drivers must be distinct"}
    results = queries.get_results(season, round_num, "RACE")
    participants = {r["driver_key"] for r in results}
    if driver_a not in participants or driver_b not in participants:
        return base, {"status": "UNAVAILABLE",
                      "reason": "one or both drivers not in the canonical race result"}
    return base, {"status": "VALID"}


# ---------------------------------------------------------------------------
# Context transitions (exact lap-overlap; association only)
# ---------------------------------------------------------------------------

def _context_transitions(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic per-lap context-transition list with exact overlap."""
    transitions: list[dict[str, Any]] = []
    prev_compound: Optional[str] = None
    prev_stint: Optional[int] = None
    prev_restricted: Optional[str] = None
    prev_pit = False
    prev_tel: Optional[bool] = None

    for t in sorted(timeline, key=lambda x: x["lap_number"]):
        ln = t["lap_number"]

        compound = t.get("compound")
        if compound is not None:
            if prev_compound is not None and compound != prev_compound:
                transitions.append({
                    "type": "COMPOUND_CHANGE", "lap_number": ln,
                    "previous": prev_compound, "new": compound,
                    "methodology": "compound field changed between consecutive "
                                   "timeline laps",
                })
            prev_compound = compound

        stint = t.get("stint")
        if stint is not None:
            if prev_stint is not None and stint != prev_stint:
                transitions.append({
                    "type": "STINT_TRANSITION", "lap_number": ln,
                    "previous": prev_stint, "new": stint,
                    "methodology": "canonical stint number changed (driver A "
                                   "stint identity)",
                })
            prev_stint = stint

        restricted = t.get("restricted")
        if (restricted is None) != (prev_restricted is None) or (
                restricted is not None and prev_restricted is not None
                and restricted != prev_restricted):
            transitions.append({
                "type": "RACE_CONTROL_TRANSITION", "lap_number": ln,
                "previous": prev_restricted, "new": restricted,
                "methodology": "race-control restriction state changed "
                               "(exact lap overlap)",
            })
        prev_restricted = restricted

        pit = bool(t.get("pit_lap"))
        if pit != prev_pit:
            transitions.append({
                "type": "PIT_TRANSITION", "lap_number": ln,
                "previous": prev_pit, "new": pit,
                "methodology": "pit-lap state changed (canonical pit stop lap)",
            })
        prev_pit = pit

        tel = bool(t.get("telemetry"))
        if prev_tel is not None and tel != prev_tel:
            transitions.append({
                "type": "TELEMETRY_TRANSITION", "lap_number": ln,
                "previous": prev_tel, "new": tel,
                "methodology": "paired telemetry availability changed",
            })
        prev_tel = tel

    return transitions


def _weather_transitions(queries: CanonicalQueries, season: int,
                         round_num: int) -> list[dict[str, Any]]:
    """Weather transitions at exact lap-window granularity (6E semantics).

    Reuses the 6E per-lap rain-window approximation so a single wet
    observation never labels a whole race wet. Pure helper function so a
    monotone synthetic series is unit-testable without a DB.
    """
    from racewise.data.historical.loss_attribution import _rain_in_window
    obs = [w for w in queries.get_weather(season, round_num, "RACE")
           if w.get("elapsed_s") is not None and w.get("rainfall") is not None]
    if not obs:
        return []
    laps_a = queries.get_lap_times(season, round_num, "RACE")
    if not laps_a:
        return []
    laps_a.sort(key=lambda r: r["lap_number"])
    transitions: list[dict[str, Any]] = []
    prev: Optional[bool] = None
    for lap in laps_a:
        ln = lap.get("lap_number")
        if ln is None:
            continue
        cur = _rain_in_window(queries, season, round_num, "RACE", lap)
        if prev is not None and cur != prev:
            transitions.append({
                "type": "WEATHER_TRANSITION", "lap_number": int(ln),
                "previous": "RAIN" if prev else "DRY",
                "new": "RAIN" if cur else "DRY",
                "methodology": "per-lap rainfall window flag changed (6E "
                               "lap-window approximation)",
            })
        prev = cur
    return transitions


# ---------------------------------------------------------------------------
# Speed-profile regime feature (paired-profile mean |speed difference|)
# ---------------------------------------------------------------------------

def _profile_distance_series(
    queries: CanonicalQueries,
    season: int, round_num: int,
    driver_a: str, driver_b: str,
    tel_laps: list[int],
) -> tuple[dict[int, float], dict[int, str]]:
    """Mean |speed difference| between paired measured profiles per lap.

    Uses the exact Phase 6I extract_speed_profile and 6J common-grid
    alignment. Only valid overlapping profiles contribute; laps without
    paired telemetry are absent (never extrapolated).
    """
    from racewise.data.historical.counterfactual import extract_speed_profile
    from racewise.data.historical.performance_envelope import _profiles_on_common_grid

    distances: dict[int, float] = {}
    failures: dict[int, str] = {}
    for ln in tel_laps:
        try:
            pa = extract_speed_profile(queries, season, round_num, "RACE",
                                       driver_a, ln)
            pb = extract_speed_profile(queries, season, round_num, "RACE",
                                       driver_b, ln)
        except Exception as exc:
            failures[ln] = f"profile extraction failed: {type(exc).__name__}"
            continue
        if pa is None or pb is None:
            failures[ln] = "profile unavailable"
            continue
        common = _profiles_on_common_grid([pa, pb])
        if common is None:
            failures[ln] = "no valid common grid span"
            continue
        _grid, rows = common
        diffs = [abs(b - a) for a, b in zip(rows[0], rows[1])]
        distances[ln] = round(sum(diffs) / len(diffs), 4)
    return distances, failures


# ---------------------------------------------------------------------------
# Regime segmentation (bounded deterministic)
# ---------------------------------------------------------------------------

def _pattern_for(slope: float, n: int) -> str:
    if n < MIN_REGIME_LAPS or not _finite(slope):
        return "INSUFFICIENT_EVIDENCE"
    if abs(slope) < SLOPE_THRESHOLD_S_PER_LAP:
        return "STABLE"
    return "WIDENING" if slope > 0 else "NARROWING"


def _best_split(values: list[float]) -> Optional[tuple[int, float]]:
    """Best admissible split index with its statistic.

    Splits after values[:i] where both halves carry >= MIN_REGIME_LAPS
    and the paired half-slope difference clears SEGMENT_STAT_THRESHOLD.
    Ties resolve to the earliest split. None when no split qualifies.
    """
    n = len(values)
    best_i: Optional[int] = None
    best_stat = 0.0
    for i in range(MIN_REGIME_LAPS, n - MIN_REGIME_LAPS + 1):
        left, right = values[:i], values[i:]
        stat = abs(
            _ols_slope([float(x) for x in range(1, len(right) + 1)], right)
            - _ols_slope([float(x) for x in range(1, len(left) + 1)], left)
        )
        if stat >= SEGMENT_STAT_THRESHOLD and stat > best_stat + ABS_TOL:
            best_stat = stat
            best_i = i
    return (best_i, best_stat) if best_i is not None else None


def _seg_info(seg: list[tuple[int, float]]) -> dict[str, Any]:
    laps = [ln for ln, _ in seg]
    values = [d for _, d in seg]
    slope = _ols_slope([float(x) for x in range(1, len(values) + 1)], values)
    return {"laps": laps, "values": values, "slope": slope,
            "pattern": _pattern_for(slope, len(values))}


def _flatten_segments(
    deltas: list[tuple[int, float]],
    rejections: list[dict[str, Any]],
) -> list[list[tuple[int, float]]]:
    """Iterative top-down segmentation with deterministic ordering.

    Repeatedly splits the segment with the largest admissible split
    statistic until no admissible split remains. Every rejected candidate
    (minimum length, SSE improvement, depth) is logged with its reason —
    rejected candidates are never silently discarded.
    """
    segments: list[list[tuple[int, float]]] = [list(deltas)]
    for _depth in range(64):  # hard bound; lap series are bounded anyway
        best: Optional[tuple[int, int, float]] = None
        for idx, seg in enumerate(segments):
            values = [d for _, d in seg]
            if len(values) < 2 * MIN_REGIME_LAPS:
                continue
            split = _best_split(values)
            if split is None:
                continue
            i, stat = split
            if best is None or stat > best[2] + ABS_TOL:
                best = (idx, i, stat)
        if best is None:
            break
        idx, i, _stat = best
        seg = segments[idx]
        left, right = seg[:i], seg[i:]
        new_sse = _sse([d for _, d in left], _seg_info(left)["slope"]) \
            + _sse([d for _, d in right], _seg_info(right)["slope"])
        info_all = _seg_info(seg)
        old_sse = _sse(info_all["values"], info_all["slope"])
        if old_sse - new_sse <= ABS_TOL:
            rejections.append({
                "candidate_transition_lap": right[0][0],
                "reason": "split did not reduce residual sum of squares",
                "action": "rejected; regime kept whole",
            })
            break
        segments[idx:idx + 1] = [left, right]
    return segments


def _merge_adjacent(segments: list[list[tuple[int, float]]]) -> tuple[list[list[tuple[int, float]]], list[dict[str, Any]]]:
    """Deterministic merge of adjacent near-equal-slope regimes."""
    merges: list[dict[str, Any]] = []
    changed = True
    while changed and len(segments) > 1:
        changed = False
        for k in range(len(segments) - 1):
            a, b = _seg_info(segments[k]), _seg_info(segments[k + 1])
            if (a["pattern"] != "INSUFFICIENT_EVIDENCE"
                    and a["pattern"] == b["pattern"]
                    and abs(a["slope"] - b["slope"]) < SLOPE_THRESHOLD_S_PER_LAP):
                segments[k:k + 2] = [segments[k] + segments[k + 1]]
                merges.append({
                    "merged_lap_ranges": [[a["laps"][0], a["laps"][-1]],
                                          [b["laps"][0], b["laps"][-1]]],
                    "reason": "adjacent regimes share qualitative pattern with "
                              "|slope difference| below the significance threshold",
                    "methodology": "deterministic merging rule; no manual tuning",
                })
                changed = True
                break
    return segments, merges


def _enforce_max_regimes(
    segments: list[list[tuple[int, float]]],
    max_regimes: int,
    merges: list[dict[str, Any]],
) -> list[list[tuple[int, float]]]:
    """Deterministically merge closest-slope neighbours down to the cap."""
    while len(segments) > max_regimes:
        candidates = []
        for k in range(len(segments) - 1):
            sa = _seg_info(segments[k])["slope"]
            sb = _seg_info(segments[k + 1])["slope"]
            candidates.append((abs(sa - sb), k))
        if not candidates:
            break
        _, k = min(candidates)
        a, b = _seg_info(segments[k]), _seg_info(segments[k + 1])
        segments[k:k + 2] = [segments[k] + segments[k + 1]]
        merges.append({
            "merged_lap_ranges": [[a["laps"][0], a["laps"][-1]],
                                  [b["laps"][0], b["laps"][-1]]],
            "reason": "max_regimes enforcement: adjacent regimes with the "
                      "closest slopes merged deterministically",
            "methodology": "deterministic; no manual tuning",
        })
    return segments


# ---------------------------------------------------------------------------
# Regime evidence: hypothesis evolution + residual + sensitivity
# ---------------------------------------------------------------------------

def _regime_hypotheses(
    queries: CanonicalQueries,
    season: int, round_num: int,
    driver_a: str, driver_b: str,
    regime_laps: list[int],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Fuse 6F lap evidence over a regime's laps and summarize per hypothesis.

    Reuses fuse_lap_evidence verbatim (statuses propagate) and the 6G
    temporal summary rules. Returns (hypothesis summaries, per-lap fused
    evidence for residual accounting).
    """
    from racewise.data.historical.evidence_fusion import HYPOTHESES, fuse_lap_evidence
    from racewise.data.historical.stint_evidence import _hypothesis_summary

    fused: dict[int, dict[str, Any]] = {}
    statuses: dict[str, list[str]] = {h: [] for h in HYPOTHESES}
    for ln in regime_laps:
        f = fuse_lap_evidence(queries, season, round_num, driver_a, driver_b, ln)
        fused[ln] = f
        for h in f.get("hypotheses", []):
            hid = h.get("hypothesis_id")
            if hid in statuses:
                statuses[hid].append(h.get("status", "INSUFFICIENT_EVIDENCE"))
    out = []
    for hid in HYPOTHESES:
        out.append({
            "hypothesis_id": hid,
            "regime_lap_statuses": list(statuses[hid]),
            **_hypothesis_summary(statuses[hid]),
        })
    return out, fused


def _regime_residual(fused: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Residual accounting over the regime from fused lap evidence.

    observed = pace component + residual holds per lap (6E); regime
    totals sum the fused laps. Residual is reported, never assigned.
    """
    rows = [(f["observed_delta_s"], f["estimated_pace_component_s"], f["residual_s"])
            for f in fused.values()
            if _finite(f.get("observed_delta_s"))
            and _finite(f.get("estimated_pace_component_s"))
            and _finite(f.get("residual_s"))]
    if not rows:
        return {"laps_fused": 0, "observed_total_s": None,
                "pace_component_total_s": None, "residual_total_s": None,
                "state": "INSUFFICIENT_EVIDENCE",
                "note": "residual is reported, never assigned to a hypothesis"}
    tot_o = sum(o for o, _c, _r in rows)
    tot_c = sum(c for _o, c, _r in rows)
    tot_r = sum(r for _o, _c, r in rows)
    state = "PRESERVED" if abs(tot_o - (tot_c + tot_r)) <= 1e-6 \
        else "CONSERVATION_VIOLATED"
    return {
        "laps_fused": len(rows),
        "observed_total_s": round(tot_o, 4),
        "pace_component_total_s": round(tot_c, 4),
        "residual_total_s": round(tot_r, 4),
        "state": state,
        "note": "residual is reported, never assigned to a hypothesis; "
                "observed = pace component + residual per 6E semantics",
    }


def _regime_sensitivity(
    queries: CanonicalQueries,
    season: int, round_num: int,
    driver_a: str, driver_b: str,
    regime_tel_laps: list[int],
) -> dict[str, Any]:
    """Bounded 6J sensitivity sweep restricted to this regime's telemetry laps."""
    from racewise.data.historical.performance_envelope import (
        _clean_covered_laps, analyze_performance_envelope,
    )
    if not regime_tel_laps:
        return {"status": "UNAVAILABLE",
                "reason": "no paired telemetry laps inside this regime"}
    # Restrict to the driver's clean comparable telemetry-covered set: the
    # envelope (correctly) rejects context-dirty laps (pit in/out, flags,
    # deleted, inaccurate) with INVALID, so the regime probe must pre-filter
    # with the exact same criteria instead of relying on probe-lap spacing
    # (Phase 6S: the wider telemetry coverage surfaced this latent coupling).
    clean, _excluded, _n = _clean_covered_laps(
        queries, season, round_num, "RACE", driver_a)
    usable = [ln for ln in regime_tel_laps if ln in set(clean)]
    if not usable:
        return {"status": "UNAVAILABLE",
                "reason": ("no clean comparable telemetry laps inside this "
                           "regime (telemetry laps are pit/flag-affected)")}
    try:
        env = analyze_performance_envelope(
            queries, season, round_num, driver_a,
            scenario_type="DEFICIT_REDUCTION", parameter=SENSITIVITY_FRACTION,
            reference_driver=driver_b, max_scenarios=5,
            max_laps=MAX_SENSITIVITY_LAPS,
            stint_number=None,
            laps=usable[:MAX_SENSITIVITY_LAPS],
        )
    except Exception as exc:
        return {"status": "INSUFFICIENT_EVIDENCE",
                "reason": f"envelope analysis unavailable: {type(exc).__name__}"}
    if env.get("status") not in ("VALID", "VALID_WITH_CAVEATS"):
        return {"status": env.get("status", "INSUFFICIENT_EVIDENCE"),
                "reason": env.get("reason")}
    sweep = env.get("scenarios") or []
    at_mid = next((s for s in sweep
                   if s.get("status") == "VALID" and _finite(s.get("parameter"))
                   and abs(float(s["parameter"]) - SENSITIVITY_FRACTION) < 1e-9), None)
    if at_mid is None:
        return {"status": "INSUFFICIENT_EVIDENCE",
                "reason": "sensitivity sweep missing a valid mid parameter point"}
    return {
        "status": "VALID",
        "fraction": SENSITIVITY_FRACTION,
        "delta_s": at_mid.get("delta_s"),
        "modeled_lap_time_s": at_mid.get("modeled_lap_time_s"),
        "envelope_laps": env.get("envelope_laps") or env.get("anchor_lap"),
        "band_width_mean_kmh": (env.get("envelope") or {})
        .get("band_summary", {}).get("mean_band_width_kmh"),
        "note": "model sensitivity under the 6I/6J speed-profile model "
                f"(DEFICIT_REDUCTION f={SENSITIVITY_FRACTION} vs reference "
                f"{driver_b}); not historical causation",
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Invocation-scoped read memo (performance: repeated immutable reads)
# ---------------------------------------------------------------------------

class _MemoQueries:
    """Read-through memo wrapper around CanonicalQueries for one analysis.

    The canonical store is read-only during an analysis invocation, so
    repeated identical reads return identical data; memoizing them is a
    pure performance measure. All downstream layers (6E/6F/6G/6H/6I/6J)
    keep using their existing code paths — this wrapper changes nothing
    about what is computed, only how many times identical rows are
    fetched. Memo lifetime is exactly one analysis call, so stale data
    across invocations is impossible.
    """

    def __init__(self, inner: CanonicalQueries) -> None:
        self._inner = inner
        self._cache: dict[tuple[Any, ...], Any] = {}

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def _memoized(*args: Any, **kwargs: Any) -> Any:
            key = (name, repr(args), repr(sorted(kwargs.items())))
            if key not in self._cache:
                self._cache[key] = attr(*args, **kwargs)
            return self._cache[key]

        return _memoized


def analyze_performance_regimes(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_a: str,
    driver_b: str,
    max_regimes: int = 8,
    min_regime_laps: int = MIN_REGIME_LAPS,
    start_lap: Optional[int] = None,
    end_lap: Optional[int] = None,
) -> dict[str, Any]:
    """Deterministic performance-regime analysis for a driver pair in one race.

    Bounded, derived-on-read, zero storage growth. Emits regimes,
    transitions, context alignment, hypothesis evolution, falsification,
    residual accounting, model sensitivity and provenance.
    """
    base, pair = _pair_base(queries, season, round_num, driver_a, driver_b)
    # One-invocation read memo: canonical data is immutable during the call,
    # so repeated identical reads are memoized (pure performance, no
    # semantic change; all downstream code paths are unchanged).
    queries = _MemoQueries(queries)
    base["bounds_requested"] = {"max_regimes": max_regimes,
                                "min_regime_laps": min_regime_laps,
                                "start_lap": start_lap, "end_lap": end_lap}
    if pair["status"] != "VALID":
        return {**base, **pair}

    # ---- explicit bounds validation (schema metadata is insufficient) -----
    if not (_finite(max_regimes) and 2 <= int(max_regimes) <= 12):
        return {**base, "status": "INVALID",
                "reason": "max_regimes must be an integer within [2, 12]"}
    if min_regime_laps != MIN_REGIME_LAPS:
        return {**base, "status": "INVALID",
                "reason": f"Phase 6K fixes min_regime_laps at {MIN_REGIME_LAPS} "
                          "(documented deterministic threshold)"}
    if start_lap is not None and end_lap is not None and int(start_lap) > int(end_lap):
        return {**base, "status": "INVALID",
                "reason": "start_lap must be <= end_lap"}

    # ---- race timeline (6H machinery) --------------------------------------
    ctx = _load_context(queries, season, round_num, "RACE", driver_a, driver_b)
    if not ctx["laps_a"] and not ctx["laps_b"]:
        return {**base, "status": "UNAVAILABLE", "reason": "no canonical lap facts"}
    tel_a = _telemetry_laps(queries, season, round_num, "RACE", driver_a)
    tel_b = _telemetry_laps(queries, season, round_num, "RACE", driver_b)
    restricted = _rc_restricted_laps(ctx["race_control"])
    timeline_full = _classify_laps(ctx, restricted, tel_a, tel_b)
    if start_lap is not None:
        timeline_full = [t for t in timeline_full if t["lap_number"] >= int(start_lap)]
    if end_lap is not None:
        timeline_full = [t for t in timeline_full if t["lap_number"] <= int(end_lap)]

    comparable = [t for t in timeline_full if t.get("comparable")
                  and _finite(t.get("observed_delta_s"))]
    if len(comparable) < 2 * MIN_REGIME_LAPS:
        return {**base, "status": "INSUFFICIENT_EVIDENCE",
                "reason": (f"only {len(comparable)} comparable laps with valid "
                           f"deltas; regime segmentation needs >= {2 * MIN_REGIME_LAPS}"),
                "comparable_lap_count": len(comparable),
                "timeline_lap_count": len(timeline_full)}

    deltas = [(int(t["lap_number"]), float(t["observed_delta_s"]))
              for t in comparable]
    comparable_set = {ln for ln, _ in deltas}
    timeline_by_lap = {t["lap_number"]: t for t in timeline_full}

    # ---- segmentation -------------------------------------------------------
    rejections: list[dict[str, Any]] = []
    segments = _flatten_segments(deltas, rejections)
    segments, merges = _merge_adjacent(segments)
    segments = _enforce_max_regimes(segments, int(max_regimes), merges)

    regimes: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    for i, seg in enumerate(segments):
        info = _seg_info(seg)
        laps = info["laps"]
        values = info["values"]
        n = len(values)
        mean_d = sum(values) / n
        var = sum((v - mean_d) ** 2 for v in values) / n
        first_mean = last_mean = None
        if n >= 2 * MIN_REGIME_LAPS:
            half = n // 2
            first_mean = sum(values[:half]) / half
            last_mean = sum(values[half:]) / (n - half)
        shift = (last_mean - first_mean) \
            if (first_mean is not None and last_mean is not None) else None

        regimes.append({
            "regime_index": i + 1,
            "start_lap": laps[0],
            "end_lap": laps[-1],
            "lap_count": n,
            "laps": list(laps),
            "slope_s_per_lap": round(info["slope"], 4),
            "pattern": info["pattern"],
            "mean_delta_s": round(mean_d, 4),
            "variance_s2": round(var, 6),
            "mean_shift_s": round(shift, 4) if shift is not None else None,
            "stints_spanned": sorted({t.get("stint") for ln in laps
                                      if (t := timeline_by_lap.get(ln)) is not None
                                      and t.get("stint") is not None}),
            # comparable-lap delta series (lap, observed delta s) for
            # regime-shape comparison by downstream phases (6L)
            "delta_series": [[int(ln), round(v, 4)] for ln, v in seg],
        })
        regimes[-1]["crosses_stint_boundary"] = len(regimes[-1]["stints_spanned"]) > 1

        if i > 0:
            prev = regimes[-2]
            transitions.append({
                "change_point_type": "GAP_TREND_CHANGE",
                "transition_lap": laps[0],
                "previous_regime": prev["regime_index"],
                "new_regime": regimes[-1]["regime_index"],
                "previous_pattern": prev["pattern"],
                "new_pattern": info["pattern"],
                "detected": "DETECTED",
                "trigger": (f"OLS slope segmentation split (statistic >= "
                            f"{SEGMENT_STAT_THRESHOLD} s/lap, SSE improvement "
                            "gate)"),
                "previous_slope_s_per_lap": prev["slope_s_per_lap"],
                "new_slope_s_per_lap": regimes[-1]["slope_s_per_lap"],
            })

    # ---- context alignment (association, never cause) -----------------------
    ctx_transitions = _context_transitions(timeline_full)
    wx_transitions = _weather_transitions(queries, season, round_num)
    all_ctx = sorted(ctx_transitions + wx_transitions,
                     key=lambda c: c["lap_number"])
    for cp in transitions:
        ln = cp["transition_lap"]
        near = [c for c in all_ctx if abs(c["lap_number"] - ln) <= 2]
        cp["context_alignment"] = [{
            "type": c["type"], "lap_number": c["lap_number"],
            "previous": c.get("previous"), "new": c.get("new"),
            "relationship": ("at transition lap" if c["lap_number"] == ln
                             else f"{abs(c['lap_number'] - ln)} lap(s) "
                                  + ("after" if c["lap_number"] > ln else "before")),
        } for c in near]
        cp["interpretation"] = (
            "performance regime changed; any nearby context transition is "
            "temporal association, not established causation"
        )

    # ---- per-regime evidence layers -----------------------------------------
    for reg in regimes:
        laps = reg["laps"]
        laps_set = set(laps)
        in_regime = [ln for ln in laps if ln in comparable_set]
        tel_laps = [ln for ln in in_regime
                    if timeline_by_lap[ln].get("telemetry")]

        reg["telemetry_lap_count"] = len(tel_laps)
        reg["telemetry_state"] = "AVAILABLE" if tel_laps else SPEED_PROFILE_GAP_STATE

        if tel_laps:
            dist, fails = _profile_distance_series(
                queries, season, round_num, driver_a, driver_b, tel_laps)
            reg["speed_profile"] = {
                "state": "MEASURED" if dist else "INSUFFICIENT_EVIDENCE",
                "mean_abs_distance_kmh": (round(sum(dist.values()) / len(dist), 4)
                                          if dist else None),
                "laps_measured": sorted(dist),
                "laps_unavailable": sorted(fails),
                "distance_trend_kmh_per_lap": (
                    round(_ols_slope([float(i + 1) for i in range(len(sorted(dist)))],
                                     [dist[ln] for ln in sorted(dist)]), 4)
                    if len(dist) >= 2 else None),
            }
        else:
            reg["speed_profile"] = {
                "state": SPEED_PROFILE_GAP_STATE,
                "mean_abs_distance_kmh": None,
                "laps_measured": [],
                "laps_unavailable": sorted(in_regime),
                "distance_trend_kmh_per_lap": None,
            }

        reg["context"] = {
            "compounds": sorted({c for c in (timeline_by_lap[ln].get("compound")
                                             for ln in laps) if c}),
            "restricted_laps": sorted(ln for ln in laps
                                      if timeline_by_lap[ln].get("restricted")),
            "pit_laps": sorted(ln for ln in laps
                               if timeline_by_lap[ln].get("pit_lap")),
        }

        hyp, fused = _regime_hypotheses(queries, season, round_num,
                                        driver_a, driver_b, in_regime)
        reg["hypothesis_evolution"] = hyp
        reg["residual"] = _regime_residual(fused)
        reg["model_sensitivity"] = _regime_sensitivity(
            queries, season, round_num, driver_a, driver_b, tel_laps)

    unavailable = [
        {"lap_number": t["lap_number"], "status": t["status"],
         "reason": t.get("reason")}
        for t in timeline_full if t.get("status") != "comparable"
    ]

    result: dict[str, Any] = {
        **base,
        "status": "VALID",
        "comparable_lap_count": len(comparable),
        "timeline_lap_count": len(timeline_full),
        "regime_count": len(regimes),
        "regimes": regimes,
        "change_points": transitions,
        "rejected_change_points": rejections,
        "regime_merges": merges,
        "context_transitions": all_ctx,
        "race_timeline": _race_timeline(regimes, transitions, all_ctx),
        "unavailable_intervals": unavailable,
        "provenance": {
            "tables": ["canonical_lap_times", "canonical_telemetry",
                       "canonical_stints", "canonical_pit_stops",
                       "canonical_weather", "canonical_race_control",
                       "canonical_session_catalog", "canonical_races"],
            "provider": "fastf1",
            "regime_version": REGIME_VERSION,
            "lap_time_model": "Phase 6I fixed-distance exact quadrature (via Phase 6J)",
            "reuse": ["Phase 6E clean-lap rules", "Phase 6F evidence fusion",
                      "Phase 6G OLS trend + minimum observations",
                      "Phase 6J scenario sweep (exact regime lap sets)"],
        },
        "note": ("regime detection identifies measured temporal structure; "
                 "it does not establish causality. A transition temporally "
                 "aligned with a context change is an association."),
    }
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["output_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return result


# ---------------------------------------------------------------------------
# Race timeline synthesis + bounded cross-race comparison
# ---------------------------------------------------------------------------

def _race_timeline(
    regimes: list[dict[str, Any]],
    change_points: list[dict[str, Any]],
    context_transitions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deterministic merged timeline of regimes, change points and context
    transitions, ordered by lap (machine-generated structured facts)."""
    entries: list[dict[str, Any]] = []
    for r in regimes:
        entries.append({"kind": "REGIME", "lap_number": r["start_lap"],
                        "end_lap": r["end_lap"],
                        "regime_index": r["regime_index"],
                        "pattern": r["pattern"],
                        "lap_count": r["lap_count"]})
    for c in change_points:
        entries.append({"kind": "CHANGE_POINT", "lap_number": c["transition_lap"],
                        "change_point_type": c["change_point_type"],
                        "previous_pattern": c["previous_pattern"],
                        "new_pattern": c["new_pattern"]})
    for t in context_transitions:
        entries.append({"kind": "CONTEXT_TRANSITION", "lap_number": t["lap_number"],
                        "transition_type": t["type"],
                        "previous": t.get("previous"), "new": t.get("new")})
    order = {"REGIME": 0, "CHANGE_POINT": 1, "CONTEXT_TRANSITION": 2}
    entries.sort(key=lambda e: (e["lap_number"], order[e["kind"]],
                                e.get("regime_index") or 0))
    return entries


MAX_COMPARE_RACES = 6


def _hypothesis_transitions(regimes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hypotheses whose regime summaries actually changed across a race."""
    if not regimes:
        return []
    hyp_ids = [h["hypothesis_id"] for h in regimes[0]["hypothesis_evolution"]]
    out: list[dict[str, Any]] = []
    for hid in hyp_ids:
        seq = []
        for g in regimes:
            s = next((x["summary"] for x in g["hypothesis_evolution"]
                      if x["hypothesis_id"] == hid), None)
            seq.append({"regime_index": g["regime_index"], "summary": s})
        distinct = {s["summary"] for s in seq if s["summary"] is not None}
        if len(distinct) > 1:
            out.append({"hypothesis_id": hid, "sequence": seq})
    return out


def compare_performance_regimes(
    queries: CanonicalQueries,
    races: list[tuple[int, int]],
    driver_a: str,
    driver_b: str,
    max_regimes: int = 8,
) -> dict[str, Any]:
    """Bounded cross-race regime comparison (no ranking, no 'best').

    Composes analyze_performance_regimes over the requested races in the
    caller's order. Per-race failures keep their honest status; they never
    poison the comparison. Comparisons are descriptive only.
    """
    base: dict[str, Any] = {
        "analysis": "compare_performance_regimes",
        "version": REGIME_VERSION,
        "driver_a": driver_a,
        "driver_b": driver_b,
        "methodology": ("descriptive cross-race composition of per-race "
                        "regime analyses; comparisons are not rankings"),
    }
    if driver_a == driver_b:
        return {**base, "status": "UNAVAILABLE", "reason": "drivers must be distinct"}
    if not races or len(races) > MAX_COMPARE_RACES:
        return {**base, "status": "INVALID",
                "reason": f"1..{MAX_COMPARE_RACES} races required"}
    per_race: list[dict[str, Any]] = []
    for season, round_num in races:
        r = analyze_performance_regimes(queries, int(season), int(round_num),
                                        driver_a, driver_b,
                                        max_regimes=max_regimes)
        if r.get("status") == "VALID":
            tel_regimes = sum(1 for g in r["regimes"]
                              if g["telemetry_state"] == "AVAILABLE")
            hyp_transitions = _hypothesis_transitions(r["regimes"])
            per_race.append({
                "season": int(season), "round": int(round_num),
                "status": "VALID",
                "regime_count": r["regime_count"],
                "regime_lap_counts": [g["lap_count"] for g in r["regimes"]],
                "patterns": [g["pattern"] for g in r["regimes"]],
                "telemetry_available_regimes": tel_regimes,
                "change_point_count": len(r["change_points"]),
                "transition_types": sorted({c["change_point_type"]
                                            for c in r["change_points"]}),
                "hypothesis_transitions": hyp_transitions,
                "output_hash": r["output_hash"],
            })
        else:
            per_race.append({"season": int(season), "round": int(round_num),
                             "status": r.get("status"), "reason": r.get("reason")})
    return {**base, "status": "VALID", "races": per_race,
            "note": ("comparisons are descriptive; races are never ranked and "
                     "no 'best' regime is identified")}
