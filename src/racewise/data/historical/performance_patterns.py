"""Phase 6L: cross-race performance pattern intelligence.

Consumes Phase 6K per-race regimes verbatim and builds deterministic,
provenance-backed cross-race comparative intelligence:

    race question -> per-race 6K regimes -> RegimeSignature (measured features)
        -> deterministic structural match (explicit thresholds)
        -> recurrence detection (MIN_RECURRING_RACES)
        -> context facets (associations, never causes)
        -> hypothesis / falsification / residual / sensitivity comparison

Epistemic boundaries (architectural, not documentation):
  - a recurring pattern is NOT a cause; similarity is NOT causality
  - no confidence scores, no rankings, no "best/worst/optimal"
  - no embeddings, no clustering, no ML: only explicit measurable distances
  - missing telemetry stays missing; insufficient evidence stays explicit
  - derived on read: zero storage growth

Driver-pair semantics: delta = driver_a - driver_b. A regime collected with
pair (b, a) is only compared to an (a, b) signature after a deterministic,
provenance-flagged inversion (delta sign flip + trajectory negation).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries

ANALYSIS = "analyze_cross_race_performance_patterns"
PATTERN_VERSION = "1.0"

# ---- deterministic bounds (mirroring repository conventions) ---------------
MAX_RACES = 20
MAX_PATTERNS = 50
MAX_DRIVER_PAIRS = 3
DEFAULT_MIN_RACES = 2
MAX_CATALOG_PAGE = 200  # catalog page_size bound for corpus enumeration

# A structural pattern is only reported as RECURRING when observed in at
# least this many independent race instances. Two occurrences are an
# observation of repetition, never a statistical significance claim.
MIN_RECURRING_RACES = 2

# slope significance: reuse Phase 6G/6K's documented threshold
SLOPE_SIGNIFICANCE_S_PER_LAP = 0.03
# two sensitivity measurements match when they differ by at most this much
SENSITIVITY_MATCH_TOLERANCE_S = 0.5

# ---- pattern-match thresholds (documented, deterministic) ------------------
#
# Tolerance rationale: 6G's 0.03 s/lap is the significance threshold for ONE
# OLS slope. Comparing two regimes means comparing two independently estimated
# slopes (each noisy over >= 3 laps), so the difference tolerance is wider and
# documented here. These thresholds define classification states; they are not
# confidence semantics.
TREND_THRESHOLD = 0.05          # s/lap slope difference treated as negligible
SLOPE_DELTA_TOLERANCE_S_PER_LAP = 0.30  # magnitude similarity of two slopes
DURATION_REL_TOL = 0.50         # |log(n_a / n_b)| <= DURATION_REL_TOL
DURATION_ABS_TOL_LAPS = 2       # or |n_a - n_b| <= DURATION_ABS_TOL_LAPS
RESIDUAL_MEAN_TOLERANCE_S = 0.25  # mean per-lap residual difference tolerance
ENVELOPE_WIDTH_REL_TOL = 0.35   # relative band-width difference threshold
MATCH_REQUIRED_COMPONENTS = 3   # components scored for a structure to count

STRUCTURE_STATES = (
    "STRONGLY_MATCHING_STRUCTURE",
    "MATCHING_STRUCTURE",
    "PARTIALLY_MATCHING_STRUCTURE",
    "NON_MATCHING_STRUCTURE",
    "INSUFFICIENT_EVIDENCE",
)

COMPARABILITY_DIMENSIONS = (
    "DRIVER_PAIR_COMPATIBILITY",
    "SESSION_TYPE_COMPATIBILITY",
    "LAP_DATA_COMPATIBILITY",
    "TELEMETRY_COMPATIBILITY",
    "CONTEXT_COMPATIBILITY",
    "EVIDENCE_COMPATIBILITY",
)

COMPARABILITY_STATES = ("COMPARABLE", "PARTIALLY_COMPARABLE",
                        "NOT_COMPARABLE", "INSUFFICIENT_EVIDENCE")

HYPOTHESIS_STATES = ("SUPPORTED", "CONTRADICTED", "NOT_SUPPORTED",
                     "NOT_TESTABLE", "INSUFFICIENT_EVIDENCE")

RESIDUAL_PATTERN_STATES = ("RESIDUAL_STABLE", "RESIDUAL_INCREASING",
                           "RESIDUAL_DECREASING", "RESIDUAL_REVERSAL",
                           "RESIDUAL_UNRESOLVED", "INSUFFICIENT_EVIDENCE")

REPEAT_TYPES = ("SAME_RACE_REPEAT", "CROSS_RACE_REPEAT",
                "CROSS_SEASON_REPEAT", "CROSS_CIRCUIT_REPEAT")

RECURRENCE_STATES = ("RECURRING", "NON_RECURRING", "INSUFFICIENT_EVIDENCE")

_TRAJECTORY_STATES = ("TRAJECTORY_COMPARABLE", "TRAJECTORY_PARTIAL",
                      "TRAJECTORY_UNAVAILABLE")

_SHAPE_POINTS = 8  # regime-relative normalized trajectory resolution

# Structural component weights: deterministic, documented, fixed.
_STRUCT_WEIGHTS = {
    "trend": 2.0,
    "slope": 1.0,
    "duration": 1.0,
    "residual": 1.0,
    "envelope": 1.0,
    "sensitivity": 1.0,
}


def _finite(x: Any) -> bool:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


def _canon_pair(a: str, b: str) -> tuple[str, str]:
    """Canonical (sorted) driver pair so signatures are order-independent."""
    return (a, b) if a <= b else (b, a)


def _hash_obj(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                         default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _pattern_provenance(
    pattern_id: str,
    key: dict[str, Any],
    occ_sigs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Per-pattern provenance: sources, method, thresholds, regime refs."""
    return {
        "pattern_id": pattern_id,
        "structural_key": key,
        "source_tables": [
            "canonical_session_catalog", "canonical_races",
            "canonical_results", "canonical_lap_times",
            "canonical_telemetry", "canonical_stints",
            "canonical_pit_stops", "canonical_weather",
            "canonical_race_control",
        ],
        "provider": "fastf1",
        "analytical_chain": ["6E", "6F", "6G", "6I", "6J", "6K", "6L"],
        "method": "deterministic structural-key grouping with explicit "
                  "component-distance matching (no clustering, no ML)",
        "thresholds": {
            "trend_threshold_s_per_lap": TREND_THRESHOLD,
            "slope_delta_tolerance_s_per_lap": SLOPE_DELTA_TOLERANCE_S_PER_LAP,
            "duration_relative_tolerance": DURATION_REL_TOL,
            "duration_absolute_tolerance_laps": DURATION_ABS_TOL_LAPS,
            "residual_mean_tolerance_s": RESIDUAL_MEAN_TOLERANCE_S,
            "envelope_width_relative_tolerance": ENVELOPE_WIDTH_REL_TOL,
            "sensitivity_match_tolerance_s": SENSITIVITY_MATCH_TOLERANCE_S,
            "match_required_components": MATCH_REQUIRED_COMPONENTS,
            "min_recurring_races": MIN_RECURRING_RACES,
        },
        "source_regime_refs": [
            {"season": s["race_identity"]["season"],
             "round": s["race_identity"]["round"],
             "regime_index": s["provenance"]["regime_index"],
             "regime_output_hash": s["provenance"]["regime_output_hash"],
             "race_id": s["provenance"]["source_race_id"]}
            for s in occ_sigs
        ],
        "generated_at": None,
        "note": "no wall-clock timestamps participate in any hash",
    }


# ---------------------------------------------------------------------------
# Main entry point: cross-race pattern analysis
# ---------------------------------------------------------------------------

def analyze_cross_race_performance_patterns(
    queries: CanonicalQueries,
    driver_a: str,
    driver_b: str,
    seasons: Optional[list[int]] = None,
    rounds: Optional[list[int]] = None,
    circuit: Optional[str] = None,
    max_races: int = 8,
    max_patterns: int = 20,
) -> dict[str, Any]:
    """Bounded cross-race recurring performance-pattern analysis.

    Deterministic, derived-on-read, zero storage growth. Composes Phase 6K
    regime analyses over a bounded race corpus, builds RegimeSignatures,
    groups them by canonical structural key and reports recurring
    structures with full evidence, falsification, residuals, sensitivity
    and provenance. No rankings, no confidence scores, no causality.

    Corpus enumeration: when ``seasons`` is None, all seasons with race
    sessions in the canonical catalog (bounded by MAX_RACES). When
    ``rounds`` is None, all rounds within the selected seasons.
    """
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )

    base: dict[str, Any] = {
        "analysis": ANALYSIS,
        "version": PATTERN_VERSION,
        "driver_a": driver_a,
        "driver_b": driver_b,
        "bounds_requested": {
            "seasons": seasons, "rounds": rounds, "circuit": circuit,
            "max_races": max_races, "max_patterns": max_patterns,
        },
        "thresholds": {
            "slope_significance_s_per_lap": SLOPE_SIGNIFICANCE_S_PER_LAP,
            "slope_delta_tolerance_s_per_lap": SLOPE_DELTA_TOLERANCE_S_PER_LAP,
            "duration_absolute_tolerance_laps": DURATION_ABS_TOL_LAPS,
            "duration_relative_tolerance": DURATION_REL_TOL,
            "residual_mean_tolerance_s": RESIDUAL_MEAN_TOLERANCE_S,
            "envelope_width_relative_tolerance": ENVELOPE_WIDTH_REL_TOL,
            "sensitivity_match_tolerance_s": SENSITIVITY_MATCH_TOLERANCE_S,
            "match_required_components": MATCH_REQUIRED_COMPONENTS,
            "min_recurring_races": MIN_RECURRING_RACES,
        },
        "assumptions": [
            "regimes come verbatim from Phase 6K deterministic segmentation",
            "delta = driver_a - driver_b; inverted collections are negated "
            "with explicit provenance flags",
            "structural grouping is coarse by design; measured features are "
            "compared with explicit distances per occurrence",
            "recurrence is an observation of repetition across independent "
            "race instances, never a significance claim",
        ],
        "methodology": (
            "deterministic cross-race pattern matching over Phase 6K regime "
            "signatures: coarse structural keys group candidate recurrences; "
            "per-pair explicit component distances and documented thresholds "
            "classify structure states; no clustering, no embeddings, no "
            "confidence scores, no rankings, no causality"
        ),
    }
    if driver_a == driver_b:
        return {**base, "status": "INVALID",
                "reason": "driver_a and driver_b must be distinct"}
    if not _finite(max_races) or not (1 <= int(max_races) <= MAX_RACES):
        return {**base, "status": "INVALID",
                "reason": f"max_races must be an integer within [1, {MAX_RACES}]"}
    if not _finite(max_patterns) or not (1 <= int(max_patterns) <= MAX_PATTERNS):
        return {**base, "status": "INVALID",
                "reason": f"max_patterns must be an integer within "
                          f"[1, {MAX_PATTERNS}]"}

    api = get_catalog_api()
    if seasons:
        sessions: list[dict[str, Any]] = []
        for s in sorted({int(x) for x in seasons}):
            page = api.list_sessions(season=s, session_type="RACE",
                                     capability="telemetry",
                                     page_size=MAX_CATALOG_PAGE, page=1)
            sessions.extend(page["sessions"])
    else:
        page = api.list_sessions(session_type="RACE", capability="telemetry",
                                 page_size=MAX_CATALOG_PAGE, page=1)
        sessions = page["sessions"]
    if rounds:
        wanted = {int(r) for r in rounds}
        sessions = [x for x in sessions if int(x["round"]) in wanted]
    sessions = sessions[:MAX_CATALOG_PAGE]
    sessions.sort(key=lambda x: (int(x["season"]), int(x["round"])))
    if not sessions:
        # Absent data, not insufficient evidence about present data: the
        # requested scope contains no telemetry-capable race sessions.
        return {**base, "status": "UNAVAILABLE",
                "reason": "no telemetry-capable race sessions in the "
                          "requested scope of the canonical catalog"}

    # ---- deterministic bounded corpus -------------------------------------
    corpus: list[dict[str, Any]] = []
    for row in sessions:
        race = queries.resolve_race(int(row["season"]), int(row["round"]))
        if race is None:
            continue
        participants = {r["driver_key"]
                        for r in queries.get_results(int(row["season"]),
                                                     int(row["round"]), "RACE")}
        if driver_a in participants and driver_b in participants:
            corpus.append({"season": int(row["season"]),
                           "round": int(row["round"]),
                           "race_id": race["race_id"],
                           "circuit_name": race["circuit_name"]})
    if not corpus:
        return {**base, "status": "UNAVAILABLE",
                "reason": ("the requested driver pair does not appear "
                           "together in any telemetry-capable canonical "
                           "race session within the corpus bounds"),
                "corpus": {"eligible_races": 0}}
    corpus.sort(key=lambda c: (c["season"], c["round"]))
    corpus = corpus[:int(max_races)]

    # ---- per-race 6K regimes -> signatures --------------------------------
    cache = _RaceRegimeCache(queries)
    signatures: list[dict[str, Any]] = []
    race_status: list[dict[str, Any]] = []
    for c in corpus:
        res = cache.get(c["season"], c["round"], driver_a, driver_b)
        race_ref = {"season": c["season"], "round": c["round"],
                    "circuit_name": c["circuit_name"]}
        if res is None or res.get("status") != "VALID":
            race_status.append({**race_ref, "status":
                                (res or {}).get("status", "UNAVAILABLE"),
                                "reason": (res or {}).get("reason")})
            continue
        for regime in res["regimes"]:
            sig = _regime_signature(
                {"season": c["season"], "round": c["round"],
                 "race_id": c["race_id"], "circuit_name": c["circuit_name"]},
                regime, driver_a, driver_b, res["output_hash"])
            if sig is not None:
                signatures.append(sig)
        race_status.append({**race_ref, "status": "VALID",
                            "regime_count": res["regime_count"],
                            "output_hash": res["output_hash"]})

    # ---- structural grouping by canonical key -----------------------------
    groups: dict[str, list[dict[str, Any]]] = {}
    key_specs: dict[str, dict[str, Any]] = {}
    for sig in signatures:
        key = _structural_key(sig)
        gid = _hash_obj(key)
        groups.setdefault(gid, []).append(sig)
        key_specs[gid] = key

    # ---- pattern assembly (deterministic order: group id, then races) -----
    # A coarse structural key groups *candidate* recurrences. Within each
    # group, a member only joins the seed pattern when the explicit
    # component-distance matcher classifies it at least
    # PARTIALLY_MATCHING_STRUCTURE against the seed; otherwise it seeds a
    # new pattern of the same coarse key (deterministic seed-anchored
    # splitting; no clustering library, no ML, thresholds documented).
    patterns: list[dict[str, Any]] = []
    split_log: list[dict[str, Any]] = []
    non_recurring_groups = 0
    for gid in sorted(groups):
        occ_sigs = sorted(
            groups[gid],
            key=lambda s: (s["race_identity"]["season"],
                           s["race_identity"]["round"], s["start_lap"]))
        # deterministic seed-anchored split into pattern member sets
        member_sets: list[list[dict[str, Any]]] = []
        for sig in occ_sigs:
            placed = False
            for members in member_sets:
                m = _match_regimes(members[0], sig)
                if m["structure_state"] in (
                        "STRONGLY_MATCHING_STRUCTURE",
                        "MATCHING_STRUCTURE",
                        "PARTIALLY_MATCHING_STRUCTURE"):
                    members.append(sig)
                    placed = True
                    break
            if not placed:
                member_sets.append([sig])
                if len(occ_sigs) > 1:
                    split_log.append({
                        "coarse_group": gid,
                        "seed_race": {"season": sig["race_identity"]["season"],
                                      "round": sig["race_identity"]["round"]},
                        "regime_index": sig["provenance"]["regime_index"],
                        "action": "seeded new pattern within coarse group "
                                  "(explicit matcher below threshold vs "
                                  "earlier seeds)",
                    })
        for members in member_sets:
            occ_races = {(s["race_identity"]["season"],
                          s["race_identity"]["round"]) for s in members}
            if len(occ_races) < MIN_RECURRING_RACES:
                non_recurring_groups += 1
                continue  # single-race structure: not a cross-race pattern
            occs: list[dict[str, Any]] = []
            for s in sorted(members, key=lambda s: (
                    s["race_identity"]["season"],
                    s["race_identity"]["round"], s["start_lap"])):
                occs.append({
                    "season": s["race_identity"]["season"],
                    "round": s["race_identity"]["round"],
                    "circuit_name": s["race_identity"]["circuit_name"],
                    "regime_index": s["provenance"]["regime_index"],
                    "start_lap": s["start_lap"], "end_lap": s["end_lap"],
                    "lap_range": f"{s['start_lap']}-{s['end_lap']}",
                    "driver_pair": [s["driver_a"], s["driver_b"]],
                    **_measured_features(s),
                })
            hyp_summary = _hypothesis_consistency(occs)
            # deterministic internal match matrix (seed vs each member)
            match_matrix = []
            for i, s in enumerate(members[1:], start=1):
                m = _match_regimes(members[0], s)
                match_matrix.append({
                    "seed": {"season": members[0]["race_identity"]["season"],
                             "round": members[0]["race_identity"]["round"],
                             "regime_index": members[0]["provenance"]["regime_index"]},
                    "member": {"season": s["race_identity"]["season"],
                               "round": s["race_identity"]["round"],
                               "regime_index": s["provenance"]["regime_index"]},
                    "structure_state": m["structure_state"],
                    "structural_score": m.get("structural_score"),
                    "components": m.get("components", {}),
                    "trajectory": (m.get("trajectory") or {}).get("state"),
                    "comparability": m["comparability"]["overall"],
                })
            pid = _hash_obj({"coarse_group": gid,
                             "seed": _measured_features(members[0])})
            patterns.append({
            "pattern_id": pid,
            "pattern_version": PATTERN_VERSION,
            "coarse_group": gid,
            "canonical_signature": key_specs[gid],
            "occurrence_count": len(occs),
            "independent_races": len(occ_races),
            "occurrences": occs,
            "seasons": sorted({o["season"] for o in occs}),
            "circuits": sorted({o["circuit_name"] for o in occs}),
            "repeat_type": _repeat_type(occs),
            "structural_features": _measured_features(occ_sigs[0]),
            "comparison_matrix": match_matrix,
            "context_summary": {"facets": _context_facets(occs)},
            "hypothesis_summary": hyp_summary,
            "falsification_summary": _pattern_falsification_summary(
                hyp_summary),
            "residual_summary": _residual_pattern(occs),
            "sensitivity_summary": _sensitivity_comparison(occs),
            "telemetry_summary": {
                "statuses": sorted({o["telemetry_status"] for o in occs}),
                "telemetry_lap_counts": [o["telemetry_lap_count"] for o in occs],
            },
            "evidence_summary": {
                "regimes_with_valid_sensitivity": sum(
                    1 for o in occs
                    if o["sensitivity_status"] == "VALID"),
                "regimes_with_measured_shape": sum(
                    1 for o in occs if o["normalized_shape"] is not None),
            },
            "recurrence_classification": "RECURRING",
            "limitations": [
                "a recurring structure is an observation of repetition; it "
                "does not establish mechanism or causation",
                "structural grouping is coarse; measured differences between "
                "occurrences are preserved in the comparison matrix",
                "occurrence laps are comparable-lap selections, not every "
                "race lap (context exclusions apply per Phase 6E)",
            ],
            "provenance": _pattern_provenance(gid, key_specs[gid], occ_sigs),
        })

    patterns.sort(key=lambda p: (-p["independent_races"], p["pattern_id"]))
    patterns = patterns[:int(max_patterns)]
    non_recurring = non_recurring_groups

    result: dict[str, Any] = {
        **base,
        "status": "VALID" if patterns else "INSUFFICIENT_EVIDENCE",
        "reason": (None if patterns else
                   "no structural regime signature recurred across at least "
                   f"{MIN_RECURRING_RACES} independent races in the bounded "
                   "corpus"),
        "corpus": {
            "eligible_races": len(corpus),
            "analyzed_races": sum(1 for r in race_status
                                  if r["status"] == "VALID"),
            "races": race_status,
        },
        "signature_count": len(signatures),
        "structural_group_count": len(groups),
        "non_recurring_group_count": non_recurring,
        "pattern_split_log": split_log,
        "pattern_count": len(patterns),
        "patterns": patterns,
        "provenance": {
            "analytical_chain": ["6E", "6F", "6G", "6H", "6I", "6J", "6K", "6L"],
            "provider": "fastf1",
            "source_tables": [
                "canonical_session_catalog", "canonical_races",
                "canonical_results", "canonical_lap_times",
                "canonical_telemetry", "canonical_stints",
                "canonical_pit_stops", "canonical_weather",
                "canonical_race_control",
            ],
            "method": "deterministic_cross_race_pattern_matching",
            "pattern_version": PATTERN_VERSION,
            "thresholds": base["thresholds"],
            "downstream_phase": "Phase 6K regimes consumed verbatim; "
                                "Phase 6E/6F/6G/6J semantics reused without "
                                "reimplementation",
        },
        "note": ("a recurring pattern is not a cause; similarity is not "
                 "causality; this analysis organizes measured regimes and "
                 "never ranks races, drivers or circuits"),
    }
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"),
                         default=str)
    result["output_hash"] = hashlib.sha256(
        payload.encode("utf-8")).hexdigest()[:16]
    return result
# ---------------------------------------------------------------------------

class _RaceRegimeCache:
    """Invocation-scoped memo: one 6K analysis per (race, canonical pair).

    6K analyses are deterministic, so repeated fetches inside a single
    pattern analysis can safely reuse the first result.
    """

    def __init__(self, queries: CanonicalQueries) -> None:
        self._queries = queries
        self._cache: dict[tuple[str, str, str],
                          Optional[dict[str, Any]]] = {}

    def get(self, season: int, round_num: int,
            driver_a: str, driver_b: str) -> Optional[dict[str, Any]]:
        """Raw 6K result (VALID or honest status) for this race+pair.

        Pair-order invariant: the 6K call always uses the canonical pair,
        so (a, b) and (b, a) queries share one cache entry. 6K analyses
        are deterministic, so reuse within one invocation is exact.
        """
        ca, cb = _canon_pair(driver_a, driver_b)
        race = self._queries.resolve_race(season, round_num)
        if race is None:
            return None
        key = (race["race_id"], ca, cb)
        if key not in self._cache:
            from racewise.data.historical.performance_regimes import (
                analyze_performance_regimes,
            )
            self._cache[key] = analyze_performance_regimes(
                self._queries, int(season), int(round_num), ca, cb)
        return self._cache[key]


# ---------------------------------------------------------------------------
# RegimeSignature
# ---------------------------------------------------------------------------

def _normalized_shape(delta_series: list[list[float]]) -> Optional[list[float]]:
    """Regime-relative normalized delta trajectory (deterministic resample).

    Position x = (lap - first_lap) / (last_lap - first_lap); value = observed
    comparable-lap delta (s). Resampled onto a fixed grid by linear
    interpolation (the same no-extrapolation semantics as 6I/6J grids are
    not required here because resampling stays strictly INSIDE the measured
    lap span). Needs >= 2 measured points; otherwise None.
    """
    pts = [(float(ln), float(v)) for ln, v in delta_series
           if _finite(ln) and _finite(v)]
    if len(pts) < 2:
        return None
    l0, l1 = pts[0][0], pts[-1][0]
    if l1 <= l0:
        return None
    norm = [((ln - l0) / (l1 - l0), v) for ln, v in pts]
    out: list[float] = []
    for k in range(_SHAPE_POINTS):
        x = k / (_SHAPE_POINTS - 1)
        if x <= norm[0][0]:
            out.append(norm[0][1])
            continue
        if x >= norm[-1][0]:
            out.append(norm[-1][1])
            continue
        for j in range(1, len(norm)):
            if norm[j][0] >= x:
                x0, y0 = norm[j - 1]
                x1, y1 = norm[j]
                t = (x - x0) / (x1 - x0)
                out.append(y0 + t * (y1 - y0))
                break
    return [round(v, 4) for v in out]


def _regime_signature(
    race: dict[str, Any],
    regime: dict[str, Any],
    driver_a: str, driver_b: str,
    regime_output_hash: str,
) -> Optional[dict[str, Any]]:
    """Deterministic RegimeSignature from one 6K regime (measured features only).

    driver_a/driver_b are the QUERY's ordered pair: signature fields are
    reported in query order (with an explicit inversion flag when the
    underlying 6K collection used the canonical opposite order, in which
    case signed quantities were deterministically negated).
    """
    season = int(race["season"])
    round_num = int(race["round"])
    ca, cb = _canon_pair(driver_a, driver_b)
    inverted = (ca, cb) != (driver_a, driver_b)

    slope = regime.get("slope_s_per_lap")
    sens = regime.get("model_sensitivity") or {}
    res = regime.get("residual") or {}
    spd = regime.get("speed_profile") or {}
    ctx = regime.get("context") or {}

    residual_state = res.get("state", "INSUFFICIENT_EVIDENCE")
    if residual_state == "PRESERVED":
        residual_state = "RESIDUAL_UNRESOLVED"
    elif residual_state == "CONSERVATION_VIOLATED":
        residual_state = "INSUFFICIENT_EVIDENCE"

    stints_spanned = regime.get("stints_spanned") or []
    pit_laps = ctx.get("pit_laps") or []
    restricted = ctx.get("restricted_laps") or []
    comp = ctx.get("compounds") or []

    delta_series = regime.get("delta_series") or []
    sig_delta_series = [[int(ln), float(v)] for ln, v in delta_series]
    if inverted:
        sig_delta_series = [[ln, -v] for ln, v in sig_delta_series]

    sig: dict[str, Any] = {
        "race_identity": {
            "season": int(race["season"]), "round": int(race["round"]),
            "race_id": race["race_id"],
            "circuit_id": race.get("circuit_id"),
            "circuit_name": race.get("circuit_name"),
        },
        "driver_a": driver_a,
        "driver_b": driver_b,
        "pair_inverted_vs_canonical": inverted,
        "canonical_pair": [ca, cb],
        "start_lap": regime["start_lap"],
        "end_lap": regime["end_lap"],
        "lap_count": regime["lap_count"],
        "trend_classification": regime.get("pattern"),
        "slope_s_per_lap": (-float(slope) if (inverted and _finite(slope))
                            else (float(slope) if _finite(slope) else None)),
        "residual_state": residual_state,
        "residual_mean_s": (round(-res["residual_total_s"] / res["laps_fused"], 4)
                            if (inverted and _finite(res.get("residual_total_s"))
                                and res.get("laps_fused")) else
                            (round(res["residual_total_s"] / res["laps_fused"], 4)
                             if (_finite(res.get("residual_total_s"))
                                 and res.get("laps_fused")) else None)),
        "envelope_width_mean_kmh": sens.get("band_width_mean_kmh"),
        "model_sensitivity": {
            "status": sens.get("status"),
            "delta_s": (-float(sens["delta_s"])
                        if (inverted and _finite(sens.get("delta_s")))
                        else (float(sens["delta_s"])
                              if _finite(sens.get("delta_s")) else None)),
            "fraction": sens.get("fraction"),
        },
        "sensitivity_parameter": sens.get("fraction"),
        "telemetry_status": regime.get("telemetry_state"),
        "telemetry_lap_count": regime.get("telemetry_lap_count"),
        "compound_summary": sorted({str(c) for c in comp}) if comp else [],
        "stint_overlap": [int(s) for s in stints_spanned],
        "pit_overlap_laps": [int(x) for x in pit_laps],
        "race_control_overlap_laps": [int(x) for x in restricted],
        "delta_series": sig_delta_series,
        "normalized_shape": _normalized_shape(sig_delta_series),
        "hypothesis_state_summary": {
            h["hypothesis_id"]: h.get("summary")
            for h in (regime.get("hypothesis_evolution") or [])
        },
    }
    sig["evidence_coverage"] = {
        "comparable_laps": regime["lap_count"],
        "telemetry_laps": regime.get("telemetry_lap_count", 0),
        "hypotheses_summarized": len(sig["hypothesis_state_summary"]),
        "residual_laps": res.get("laps_fused", 0),
    }
    sig["provenance"] = {
        "source_phase": "6K",
        "regime_index": regime.get("regime_index"),
        "regime_output_hash": regime_output_hash,
        "source_race_id": race["race_id"],
    }
    return sig


def _structural_key(sig: dict[str, Any]) -> dict[str, Any]:
    """Coarse structural key: the canonical serialization hashed into
    pattern_signature_id.

    Deliberately coarse: continuous measurements (exact slope, band width,
    sensitivity, shapes) are NOT in the key - they are preserved per
    occurrence in ``structural_features`` and compared with explicit
    distances. Grouping on them would fragment patterns so that no
    cross-race recurrence could ever be observed. Race identity, absolute
    lap numbers and provenance are excluded: two regimes share a signature
    when their *structure* matches, not when they share a race.
    """
    slope = sig["slope_s_per_lap"]
    if not _finite(slope):
        slope_state = None
    elif abs(float(slope)) <= SLOPE_SIGNIFICANCE_S_PER_LAP:
        slope_state = "NEAR_ZERO"
    else:
        slope_state = "POSITIVE" if float(slope) > 0 else "NEGATIVE"
    return {
        "trend_classification": sig["trend_classification"],
        "slope_state": slope_state,
        "duration_bucket": _duration_bucket(sig["lap_count"]),
        "residual_state": sig["residual_state"],
        "telemetry_status": sig["telemetry_status"],
    }


def _measured_features(sig: dict[str, Any]) -> dict[str, Any]:
    """Full measured structural vector of one occurrence (never hashed).

    Exact floats are rounded explicitly so serialization is stable across
    processes; kept alongside every occurrence for pairwise comparison.
    """
    return {
        "trend_classification": sig["trend_classification"],
        "slope_s_per_lap": (round(sig["slope_s_per_lap"], 4)
                            if _finite(sig["slope_s_per_lap"]) else None),
        "lap_count": sig["lap_count"],
        "duration_bucket": _duration_bucket(sig["lap_count"]),
        "residual_state": sig["residual_state"],
        "residual_mean_s": (round(sig["residual_mean_s"], 4)
                            if _finite(sig["residual_mean_s"]) else None),
        "envelope_width_mean_kmh": (round(sig["envelope_width_mean_kmh"], 2)
                                    if _finite(sig["envelope_width_mean_kmh"])
                                    else None),
        "sensitivity_status": sig["model_sensitivity"]["status"],
        "sensitivity_delta_s": (round(sig["model_sensitivity"]["delta_s"], 4)
                                if _finite(sig["model_sensitivity"]["delta_s"])
                                else None),
        "sensitivity_parameter": sig["sensitivity_parameter"],
        "telemetry_status": sig["telemetry_status"],
        "telemetry_lap_count": sig["telemetry_lap_count"],
        "compound_summary": sig["compound_summary"],
        "stint_overlap": sig["stint_overlap"],
        "pit_overlap": bool(sig["pit_overlap_laps"]),
        "race_control_overlap": bool(sig["race_control_overlap_laps"]),
        "hypothesis_state_summary": sig["hypothesis_state_summary"],
        "normalized_shape": sig["normalized_shape"],
        "pair_inverted_vs_canonical": sig["pair_inverted_vs_canonical"],
    }


def _duration_bucket(n: int) -> str:
    """Coarse duration bucket so 12-lap and 13-lap regimes can match."""
    if n <= 3:
        return "2-3"
    if n <= 6:
        return "4-6"
    if n <= 10:
        return "7-10"
    return "11+"


def _structure_state_from_score(score: float, n_components: int) -> str:
    """Deterministic structure classification from the weighted score."""
    if n_components < MATCH_REQUIRED_COMPONENTS:
        return "INSUFFICIENT_EVIDENCE"
    if score >= 1.0:
        return "STRONGLY_MATCHING_STRUCTURE"
    if score >= 0.75:
        return "MATCHING_STRUCTURE"
    if score >= 0.5:
        return "PARTIALLY_MATCHING_STRUCTURE"
    return "NON_MATCHING_STRUCTURE"


def _component_scores(sa: dict[str, Any], sb: dict[str, Any]) -> dict[str, Any]:
    """Per-component measurable distances between two signatures."""
    out: dict[str, Any] = {}

    ta, tb = sa["slope_s_per_lap"], sb["slope_s_per_lap"]
    out["slope_delta_s_per_lap"] = (round(abs(ta - tb), 4)
                                    if (_finite(ta) and _finite(tb)) else None)
    out["trend_match"] = (ta is not None and tb is not None
                          and ta * tb >= 0)
    out["slope_magnitude_match"] = (
        out["slope_delta_s_per_lap"] is not None
        and out["slope_delta_s_per_lap"] <= SLOPE_DELTA_TOLERANCE_S_PER_LAP)

    na, nb = sa["lap_count"], sb["lap_count"]
    out["duration_delta_laps"] = abs(na - nb)
    out["duration_ratio"] = round(min(na, nb) / max(na, nb), 4)

    ra, rb = sa["residual_mean_s"], sb["residual_mean_s"]
    out["residual_distance_s"] = (round(abs(ra - rb), 4)
                                  if (_finite(ra) and _finite(rb)) else None)

    wa, wb = sa["envelope_width_mean_kmh"], sb["envelope_width_mean_kmh"]
    if _finite(wa) and _finite(wb) and max(wa, wb) > 0:
        out["envelope_distance_rel"] = round(abs(wa - wb) / max(wa, wb), 4)
    else:
        out["envelope_distance_rel"] = None

    da, db = (sa["model_sensitivity"]["delta_s"],
              sb["model_sensitivity"]["delta_s"])
    out["sensitivity_delta_s"] = (round(abs(da - db), 4)
                                  if (_finite(da) and _finite(db)) else None)

    out["context_match"] = _context_similarity(sa, sb)
    out["hypothesis_overlap"] = _hypothesis_agreement(sa, sb)
    return out


def _score_components(c: dict[str, Any]) -> tuple[float, int]:
    """Weighted structural score in [0, 1] + count of scored components.

    Each scored component contributes weight * (1 if within threshold else 0);
    the score is the weighted fraction of achievable weight. Missing
    measurements score 0 but still count as achieved-against (documented:
    a missing measurement is not a match).
    """
    total = 0.0
    achieved = 0.0
    n = 0
    if c.get("slope_delta_s_per_lap") is not None:
        total += _STRUCT_WEIGHTS["slope"] + _STRUCT_WEIGHTS["trend"]
        if c["slope_magnitude_match"]:
            achieved += _STRUCT_WEIGHTS["slope"]
        if c["trend_match"]:
            achieved += _STRUCT_WEIGHTS["trend"]
        n += 2
    if c.get("duration_ratio") is not None:
        total += _STRUCT_WEIGHTS["duration"]
        if (abs(c["duration_delta_laps"]) <= DURATION_ABS_TOL_LAPS
                or c["duration_ratio"] >= 1 - DURATION_REL_TOL):
            achieved += _STRUCT_WEIGHTS["duration"]
        n += 1
    if c.get("residual_distance_s") is not None:
        total += _STRUCT_WEIGHTS["residual"]
        if c["residual_distance_s"] <= RESIDUAL_MEAN_TOLERANCE_S:
            achieved += _STRUCT_WEIGHTS["residual"]
        n += 1
    if c.get("envelope_distance_rel") is not None:
        total += _STRUCT_WEIGHTS["envelope"]
        if c["envelope_distance_rel"] <= ENVELOPE_WIDTH_REL_TOL:
            achieved += _STRUCT_WEIGHTS["envelope"]
        n += 1
    if c.get("sensitivity_delta_s") is not None:
        total += _STRUCT_WEIGHTS["sensitivity"]
        if c["sensitivity_delta_s"] <= SENSITIVITY_MATCH_TOLERANCE_S:
            achieved += _STRUCT_WEIGHTS["sensitivity"]
        n += 1
    return (round(achieved / total, 4) if total > 0 else 0.0), n


def _context_similarity(sa: dict[str, Any], sb: dict[str, Any]) -> dict[str, Any]:
    """Descriptive context overlap between two signatures."""
    ca, cb = set(sa["compound_summary"]), set(sb["compound_summary"])
    same_compounds = bool(ca) and ca == cb
    both_single_compound = (len(ca) == 1 and len(cb) == 1)
    return {
        "same_compound_set": same_compounds,
        "both_single_compound": both_single_compound,
        "pit_overlap_both": bool(sa["pit_overlap_laps"]) and bool(sb["pit_overlap_laps"]),
        "race_control_overlap_both": (bool(sa["race_control_overlap_laps"])
                                      and bool(sb["race_control_overlap_laps"])),
        "same_circuit": (sa["race_identity"]["circuit_id"]
                         == sb["race_identity"]["circuit_id"]),
        "same_season": (sa["race_identity"]["season"]
                        == sb["race_identity"]["season"]),
    }


def _hypothesis_agreement(sa: dict[str, Any], sb: dict[str, Any]) -> dict[str, Any]:
    """Deterministic hypothesis-state agreement between two signatures."""
    ha: dict[str, Any] = sa["hypothesis_state_summary"]
    hb: dict[str, Any] = sb["hypothesis_state_summary"]
    shared = sorted(set(ha) & set(hb))
    informative = ["SUPPORTED", "CONTRADICTED", "NOT_SUPPORTED"]
    agree = disagree = 0
    per_hypothesis: dict[str, str] = {}
    for h in shared:
        va, vb = ha[h], hb[h]
        if va == vb:
            agree += 1
            per_hypothesis[h] = "CONSISTENT" if va in informative else "INSUFFICIENT_EVIDENCE"
        elif va in informative and vb in informative:
            disagree += 1
            per_hypothesis[h] = "CONTRADICTORY"
        else:
            per_hypothesis[h] = "INSUFFICIENT_EVIDENCE"
    if agree + disagree == 0:
        overall = "INSUFFICIENT_EVIDENCE"
    elif disagree == 0 and agree > 0:
        overall = "CONSISTENT"
    elif agree > 0 and disagree > 0:
        overall = "VARIABLE"
    else:
        overall = "CONTRADICTORY"
    return {
        "agreement": overall,
        "agree_count": agree,
        "disagree_count": disagree,
        "per_hypothesis": per_hypothesis,
    }


# ---------------------------------------------------------------------------
# Regime-shape trajectory comparison
# ---------------------------------------------------------------------------

def _trajectory_comparison(sa: dict[str, Any],
                           sb: dict[str, Any]) -> dict[str, Any]:
    """Compare normalized regime-relative delta trajectories.

    Only measured comparable-lap deltas enter the shapes; resampling is a
    deterministic linear interpolation strictly inside each regime's own
    measured lap span (no fabricated endpoints beyond clamping to the first
    and last *measured* values). Inverted signatures already carry
    negated series, so shapes are directly comparable.
    """
    fa, fb = sa["normalized_shape"], sb["normalized_shape"]
    if fa is None or fb is None:
        return {
            "state": "TRAJECTORY_UNAVAILABLE",
            "mean_abs_deviation_s": None,
            "max_abs_deviation_s": None,
            "note": "fewer than two measured comparable laps in at least "
                    "one regime; no trajectory is fabricated",
        }
    devs = [abs(a - b) for a, b in zip(fa, fb)]
    return {
        "state": "TRAJECTORY_COMPARABLE",
        "mean_abs_deviation_s": round(sum(devs) / len(devs), 4),
        "max_abs_deviation_s": round(max(devs), 4),
        "shape_a": fa,
        "shape_b": fb,
    }


# ---------------------------------------------------------------------------
# Comparability contract
# ---------------------------------------------------------------------------

def _comparability(sa: dict[str, Any], sb: dict[str, Any]) -> dict[str, Any]:
    """Explicit six-dimension comparability contract between two regimes.

    Every dimension returns an explicit state; failed dimensions are never
    silently dropped. Overall = weakest dimension (PARTIALLY_COMPARABLE
    beats COMPARABLE only when no dimension is worse).
    """
    dims: list[dict[str, Any]] = []

    def _dim(name: str, state: str, reasons: list[str]) -> None:
        dims.append({"dimension": name, "state": state,
                     "reasons": reasons})

    # 1. driver pair: identical canonical pair required (order may differ)
    ca = tuple(sa["canonical_pair"])
    cb = tuple(sb["canonical_pair"])
    if ca == cb:
        _dim("DRIVER_PAIR_COMPATIBILITY", "COMPARABLE", [])
    else:
        _dim("DRIVER_PAIR_COMPATIBILITY", "NOT_COMPARABLE",
             ["incompatible_driver_pair"])

    # 2. session type: 6K regimes are race sessions by construction
    if sa["race_identity"] and sb["race_identity"]:
        _dim("SESSION_TYPE_COMPATIBILITY", "COMPARABLE", [])

    # 3. lap data: both regimes carry measured comparable laps
    lap_reasons: list[str] = []
    lap_state = "COMPARABLE"
    if not sa["delta_series"] or not sb["delta_series"]:
        lap_state = "INSUFFICIENT_EVIDENCE"
        lap_reasons.append("insufficient_common_laps")
    _dim("LAP_DATA_COMPATIBILITY", lap_state, lap_reasons)

    # 4. telemetry: both measured, one measured, or neither
    ta, tb = sa["telemetry_status"], sb["telemetry_status"]
    if ta == "AVAILABLE" and tb == "AVAILABLE":
        _dim("TELEMETRY_COMPATIBILITY", "COMPARABLE", [])
    elif ta != "AVAILABLE" and tb != "AVAILABLE":
        _dim("TELEMETRY_COMPATIBILITY", "COMPARABLE",
             ["telemetry_missing_in_both; descriptive-only comparison"])
    else:
        _dim("TELEMETRY_COMPATIBILITY", "PARTIALLY_COMPARABLE",
             ["telemetry_missing_in_one_regime"])

    # 5. context: compounds / overlaps described, never used to exclude
    ctx = _context_similarity(sa, sb)
    ctx_reasons: list[str] = []
    ctx_state = "COMPARABLE"
    if not ctx["same_compound_set"]:
        ctx_state = "PARTIALLY_COMPARABLE"
        ctx_reasons.append("incompatible_context: different compound sets")
    _dim("CONTEXT_COMPATIBILITY", ctx_state, ctx_reasons)

    # 6. evidence: both regimes carry 6F hypothesis summaries
    ha = sa["hypothesis_state_summary"]
    hb = sb["hypothesis_state_summary"]
    if ha and hb:
        _dim("EVIDENCE_COMPATIBILITY", "COMPARABLE", [])
    else:
        _dim("EVIDENCE_COMPATIBILITY", "INSUFFICIENT_EVIDENCE",
             ["insufficient_evidence"])

    order = {"COMPARABLE": 0, "PARTIALLY_COMPARABLE": 1,
             "INSUFFICIENT_EVIDENCE": 2, "NOT_COMPARABLE": 3}
    worst = max(dims, key=lambda d: order[d["state"]])
    return {
        "dimensions": dims,
        "overall": worst["state"],
        "reasons": sorted({r for d in dims for r in d["reasons"]}) or
        ([worst["state"].lower()] if worst["state"] != "COMPARABLE" else []),
    }


def _match_regimes(sa: dict[str, Any], sb: dict[str, Any]) -> dict[str, Any]:
    """Deterministic structural match between two signatures.

    Emits every component's measured distance, the weighted score and the
    threshold-based structure state. No confidence semantics anywhere.
    """
    comp = _comparability(sa, sb)
    traj = _trajectory_comparison(sa, sb)
    if comp["overall"] == "NOT_COMPARABLE":
        return {
            "comparability": comp,
            "structure_state": "NOT_COMPARABLE",
            "components": {},
            "trajectory": traj,
        }
    comps = _component_scores(sa, sb)
    score, n_scored = _score_components(comps)
    return {
        "comparability": comp,
        "components": comps,
        "structural_score": score,
        "scored_component_count": n_scored,
        "structure_state": _structure_state_from_score(score, n_scored),
        "trajectory": traj,
    }


# ---------------------------------------------------------------------------
# Recurrence detection
# ---------------------------------------------------------------------------

def _repeat_type(occurrences: list[dict[str, Any]]) -> str:
    seasons = {o["season"] for o in occurrences}
    circuits = {o["circuit_name"] for o in occurrences}
    races = {(o["season"], o["round"]) for o in occurrences}
    if len(races) == 1:
        return "SAME_RACE_REPEAT"
    if len(circuits) == 1 and len(seasons) > 1:
        return "CROSS_SEASON_REPEAT"
    if len(circuits) > 1:
        return "CROSS_CIRCUIT_REPEAT"
    return "CROSS_RACE_REPEAT"


def _context_facets(occurrences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Descriptive context facets across occurrences (associations only)."""
    facets: list[dict[str, Any]] = []
    dry = [o for o in occurrences
           if o["compound_summary"] and all("WET" not in str(c).upper()
                                            and "INTER" not in str(c).upper()
                                            for c in o["compound_summary"])]
    if dry:
        facets.append({
            "facet": "dry_compound_laps",
            "occurrence_count": len(dry),
            "races": [f"{o['season']} R{o['round']}" for o in dry],
            "note": "the structure was measured on dry-compound laps in "
                    "these races; no causal role is assigned",
        })
    wet = [o for o in occurrences if o not in dry]
    if wet:
        facets.append({
            "facet": "wet_or_intermediate_compound_laps",
            "occurrence_count": len(wet),
            "races": [f"{o['season']} R{o['round']}" for o in wet],
        })
    diff_comp = [o for o in occurrences if len(o["compound_summary"]) > 1]
    if diff_comp:
        facets.append({
            "facet": "regime_spans_multiple_compounds",
            "occurrence_count": len(diff_comp),
            "races": [f"{o['season']} R{o['round']}" for o in diff_comp],
        })
    pit = [o for o in occurrences if o["pit_overlap"]]
    if pit:
        facets.append({
            "facet": "regime_overlaps_pit_lap",
            "occurrence_count": len(pit),
            "races": [f"{o['season']} R{o['round']}" for o in pit],
        })
    rc = [o for o in occurrences if o["race_control_overlap"]]
    if rc:
        facets.append({
            "facet": "regime_overlaps_restricted_laps",
            "occurrence_count": len(rc),
            "races": [f"{o['season']} R{o['round']}" for o in rc],
        })
    return facets


def _hypothesis_consistency(occurrences: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic per-hypothesis consistency across a pattern's regimes."""
    informative = ["SUPPORTED", "CONTRADICTED", "NOT_SUPPORTED"]
    out: dict[str, Any] = {}
    hyp_ids: list[str] = []
    for o in occurrences:
        for h in o["hypothesis_state_summary"]:
            if h not in hyp_ids:
                hyp_ids.append(h)
    for h in sorted(hyp_ids):
        statuses: list[str] = []
        race_refs: list[str] = []
        for o in occurrences:
            v = o["hypothesis_state_summary"].get(h)
            if v is not None:
                statuses.append(v)
                race_refs.append(f"{o['season']} R{o['round']} regime {o['regime_index']}")
        distinct_informative = {s for s in statuses if s in informative}
        if not statuses:
            state = "INSUFFICIENT_EVIDENCE"
        elif len(distinct_informative) > 1:
            state = "CONTRADICTORY" if \
                ("SUPPORTED" in distinct_informative
                 and "CONTRADICTED" in distinct_informative) else "VARIABLE"
        elif distinct_informative:
            state = "CONSISTENT"
        else:
            state = "INSUFFICIENT_EVIDENCE"
        out[h] = {
            "consistency": state,
            "statuses": statuses,
            "race_regime_refs": race_refs,
        }
    return out


def _pattern_falsification_summary(
    hypothesis_summary: dict[str, Any],
) -> dict[str, Any]:
    """Counts of supporting/contradicting/not-testable hypothesis states
    across all regimes of a pattern, with explicit refs (never erased)."""
    supporting: list[str] = []
    contradicting: list[str] = []
    not_testable: list[str] = []
    for h, agg in sorted(hypothesis_summary.items()):
        for status, ref in zip(agg["statuses"], agg["race_regime_refs"]):
            if status == "SUPPORTED":
                supporting.append(f"{ref}: {h}")
            elif status == "CONTRADICTED":
                contradicting.append(f"{ref}: {h}")
            elif status == "NOT_TESTABLE":
                not_testable.append(f"{ref}: {h}")
    return {
        "supporting_refs": sorted(supporting),
        "contradicting_refs": sorted(contradicting),
        "not_testable_refs": sorted(not_testable),
        "note": ("contradictions are preserved, never averaged away; a "
                 "recurring structure does not rehabilitate a contradicted "
                 "hypothesis"),
    }


def _residual_pattern(occurrences: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic recurring residual structure across occurrences."""
    states = [o["residual_state"] for o in occurrences]
    informative = {"RESIDUAL_STABLE", "RESIDUAL_INCREASING",
                   "RESIDUAL_DECREASING"}
    distinct = set(states) & informative
    if len(states) < MIN_RECURRING_RACES:
        overall = "INSUFFICIENT_EVIDENCE"
    elif len(distinct) == 1:
        overall = next(iter(distinct))
    elif len(distinct) > 1 and \
            {"RESIDUAL_INCREASING", "RESIDUAL_DECREASING"} <= set(states):
        overall = "RESIDUAL_REVERSAL"
    elif len(distinct) > 1:
        overall = "RESIDUAL_UNRESOLVED"
    else:
        overall = "RESIDUAL_UNRESOLVED"
    return {
        "state": overall,
        "per_occurrence": states,
        "note": "residual recurrence is an analytical observation, not a "
                "mechanism; residual is never assigned to a hypothesis",
    }


def _sensitivity_comparison(occurrences: list[dict[str, Any]]) -> dict[str, Any]:
    """Same-intervention model-sensitivity comparison across occurrences."""
    vals: list[dict[str, Any]] = []
    for o in occurrences:
        if o["sensitivity_status"] == "VALID" and _finite(o["sensitivity_delta_s"]):
            vals.append({
                "race": f"{o['season']} R{o['round']}",
                "regime_index": o["regime_index"],
                "delta_s": round(o["sensitivity_delta_s"], 4),
            })
    if len(vals) < 2:
        return {
            "state": "INSUFFICIENT_EVIDENCE",
            "values": vals,
            "note": "sensitivity comparison needs at least two regimes with "
                    "valid telemetry-supported sweeps",
        }
    deltas = [v["delta_s"] for v in vals]
    spread = round(max(deltas) - min(deltas), 4)
    return {
        "state": "MEASURED",
        "intervention": "DEFICIT_REDUCTION f=0.5 vs reference (6I/6J model)",
        "values": vals,
        "sensitivity_spread_s": spread,
        "note": "the speed-profile model produces different sensitivity "
                "under the specified intervention; this is a model property, "
                "not historical causation or recoverable performance",
    }
