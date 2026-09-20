"""Stint-level evidence fusion and performance-divergence analysis (Phase 6G).

Answers: "How did the performance relationship between Driver A and Driver B
evolve across an entire stint - which explanations remained consistent over
time, which changed or were contradicted, and what remains unexplained?"

Design (extends, never replaces 6E/6F):
  - canonical stint identity (canonical_stints) - never inferred from laps
  - deterministic common-lap selection reusing the 6E clean-lap rules, with
    every exclusion reason exposed
  - per-lap Phase 6F fusions (temporal sequence preserved - never a bare mean)
  - deterministic OLS trend over stint-lap index with a minimum-observation
    rule (INSUFFICIENT_EVIDENCE below MIN_TREND_OBS)
  - hypothesis-evolution semantics (CONSISTENTLY_SUPPORTED /
    MOSTLY_SUPPORTED / INTERMITTENTLY_SUPPORTED / CONTRADICTED_OVER_TIME /
    NOT_TESTABLE / INSUFFICIENT_EVIDENCE) with per-hypothesis persistence
    properties (counts, first/last supported, transitions) - descriptive
    facts, never scores
  - residual trajectory + cumulative gap (documented semantics: cumulative
    across the SELECTED comparable laps, not race time)
  - context transitions (rain / race control) recorded, never merged silently
  - change-point detection: thresholded segmented-slope comparison, bounded,
    deterministic, NOT_TESTABLE when unsupported
  - conservation: cumulative residual reconciliation vs cumulative observed
    delta, with explicit residual - never discarded

Derived on read: zero storage growth. SUPPORTED means evidence-consistent,
never causation.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries

STINT_EVIDENCE_VERSION = "stint_evidence_v1"

MIN_TREND_OBS = 3          # fewer valid laps -> trend INSUFFICIENT_EVIDENCE
DEFAULT_MAX_LAPS = 10      # bounded evenly spaced sample across the stint
MAX_LAPS_CAP = 16          # hard input bound
# change-point thresholds (documented, deterministic): a slope change between
# the first and second half of the lap sequence must exceed this absolute
# value (s/lap) to be reported.
CHANGE_POINT_MIN_SLOPE_S = 0.02
CHANGE_POINT_DELTA_S = 0.03

# hypothesis-id -> short label used in temporal summaries
_HYPOthesis_LABELS: dict[str, str] = {
    "H1_corner_speed": "corner speed",
    "H2_throttle": "throttle",
    "H3_braking": "braking",
    "H4_tyre_state": "tyre state",
    "H5_race_control": "race control",
    "H6_drs": "DRS",
}


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _ols_slope(xs: list[float], ys: list[float]) -> float:
    """Ordinary least-squares slope (documented deterministic method)."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


# ---------------------------------------------------------------------------
# stint resolution and common-lap selection
# ---------------------------------------------------------------------------

def _resolve_stint(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    session_type: str,
    driver_key: str,
    stint_number: int,
) -> dict[str, Any] | None:
    """Canonical stint row for (session, driver, stint_number) - never inferred."""
    stints = queries.get_stints(season, round_num, session_type, driver_key)
    for s in stints:
        if s.get("stint_number") == stint_number:
            return s
    for s in stints:  # tolerant key fallback
        if s.get("stint") == stint_number:
            return s
    return None


def _telemetry_covered_laps(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    session_type: str,
    driver_key: str,
) -> set[int]:
    """Canonical lap numbers with telemetry rows for one driver."""
    session = queries.resolve_session(season, round_num, session_type)
    if session is None:
        return set()
    with queries._conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT t.lap_number FROM canonical_telemetry t
               JOIN canonical_drivers d ON d.driver_id = t.driver_id
               WHERE t.session_id = ? AND d.driver_key = ?""",
            (session["session_id"], driver_key),
        ).fetchall()
    return {r["lap_number"] for r in rows}


def _select_common_laps(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    session_type: str,
    driver_a: str,
    driver_b: str,
    stint_number: int,
    max_laps: int,
) -> tuple[list[int], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None]:
    """Deterministic common clean laps of one stint for both drivers.

    A lap is comparable when BOTH drivers have a canonical lap fact in the
    stint with a valid time, none of the 6E non-comparable flags
    (pit-in / pit-out / deleted), and telemetry coverage for both drivers
    (telemetry evidence is required for stint fusion; spec candidate rule).
    Rejected laps are never silently dropped: their lap numbers and exclusion
    reasons are returned.
    """
    from racewise.data.historical.loss_attribution import _NON_COMPARABLE_FLAGS

    laps_a = queries.get_lap_times(season, round_num, session_type, driver_a)
    laps_b = queries.get_lap_times(season, round_num, session_type, driver_b)
    by_lap_a = {r["lap_number"]: r for r in laps_a if r.get("stint") == stint_number}
    by_lap_b = {r["lap_number"]: r for r in laps_b if r.get("stint") == stint_number}
    candidates = sorted(set(by_lap_a) | set(by_lap_b))
    tel_a = _telemetry_covered_laps(queries, season, round_num, session_type, driver_a)
    tel_b = _telemetry_covered_laps(queries, season, round_num, session_type, driver_b)

    selected: list[int] = []
    excluded: list[dict[str, Any]] = []
    for ln in candidates:
        ra, rb = by_lap_a.get(ln), by_lap_b.get(ln)
        if ra is None or rb is None:
            excluded.append({"lap_number": ln, "reason": "lap fact missing for one driver"})
            continue
        reasons = []
        if not (ra.get("time_s") and rb.get("time_s")):
            reasons.append("missing lap time")
        for flag in _NON_COMPARABLE_FLAGS:
            if ra.get(flag) or rb.get(flag):
                reasons.append(f"{flag}")
        if ln not in tel_a or ln not in tel_b:
            reasons.append("telemetry not covered for one driver")
        if reasons:
            excluded.append({"lap_number": ln, "reason": "; ".join(reasons)})
            continue
        selected.append(ln)

    stint_a = _resolve_stint(queries, season, round_num, session_type, driver_a, stint_number)
    stint_b = _resolve_stint(queries, season, round_num, session_type, driver_b, stint_number)

    # bounded evenly spaced sample across the stint (deterministic)
    if len(selected) > max_laps:
        step = (len(selected) - 1) / (max_laps - 1)
        picked = sorted({int(round(i * step)) for i in range(max_laps)})
        sampled = [selected[i] for i in picked]
        for ln in selected:
            if ln not in sampled:
                excluded.append({"lap_number": ln, "reason": "outside bounded sample (stint window)"})
        selected = sampled
    return selected, excluded, stint_a, stint_b


# ---------------------------------------------------------------------------
# temporal evidence from per-lap fusions
# ---------------------------------------------------------------------------

_METRIC_FIELDS: dict[str, tuple[str, ...]] = {
    "speed_metric": ("mean_delta_kmh",),
    "throttle": ("mean_delta_pct", "b_lift_windows_vs_a"),
    "brake": ("braking_fraction_delta", "first_brake_delta_s"),
    "drs": ("activation_fraction_delta",),
}


def _temporal_facts(fused_lap: dict[str, Any]) -> dict[str, Any]:
    """Extract per-lap temporal facts from a 6F fusion output."""
    facts: dict[str, Any] = {
        "observed_delta_s": fused_lap.get("observed_delta_s"),
        "pace_component_s": fused_lap.get("estimated_pace_component_s"),
        "residual_s": fused_lap.get("residual_s"),
        "metrics": {},
        "compound": None,
        "tyre_age_gap": None,
        "restricted": False,
        "rain_in_window": False,
    }
    for e in fused_lap.get("evidence_items", []):
        st = e["source_id"].split(":", 1)[0]
        vals = e.get("values") or {}
        if st in _METRIC_FIELDS and st not in facts["metrics"]:
            facts["metrics"][st] = {k: vals.get(k) for k in _METRIC_FIELDS[st]}
        if st == "tyre_state" and facts["compound"] is None:
            facts["compound"] = vals.get("compound_a") or vals.get("compound")
            facts["tyre_age_gap"] = vals.get("age_gap_laps", vals.get("tyre_age_gap_laps"))
        if st == "race_control" and e.get("relationship") == "SUPPORTS":
            facts["restricted"] = True
        if st == "weather" and e.get("relationship") == "SUPPORTS":
            facts["rain_in_window"] = True
    return facts


def _hypothesis_summary(statuses: list[str]) -> dict[str, Any]:
    """Deterministic temporal summary for one hypothesis across laps.

    Rules (documented; over laps where the premise held and required evidence
    existed - i.e. status != NOT_TESTABLE):
      CONSISTENTLY_SUPPORTED   >= 3 evaluable laps and all SUPPORTED/PARTIALLY_SUPPORTED
      MOSTLY_SUPPORTED         >= 3 evaluable laps, support fraction >= 0.7, zero contradictions
      INTERMITTENTLY_SUPPORTED >= 3 evaluable laps, some support, and either a
                                  contradiction or support fraction < 0.7
      CONTRADICTED_OVER_TIME   >= 2 CONTRADICTED/NOT_SUPPORTED and zero support
      NOT_SUPPORTED            evaluable laps exist, zero support, not enough contradictions
      INSUFFICIENT_EVIDENCE    fewer than 2 evaluable laps
    """
    evaluable = [s for s in statuses if s not in ("NOT_TESTABLE",)]
    counts = {
        "valid_observations": len(evaluable),
        "supported_count": sum(1 for s in evaluable if s == "SUPPORTED"),
        "partially_supported_count": sum(1 for s in evaluable if s == "PARTIALLY_SUPPORTED"),
        "not_supported_count": sum(1 for s in evaluable if s in ("NOT_SUPPORTED", "CONTRADICTED")),
        "contradicted_count": sum(1 for s in evaluable if s == "CONTRADICTED"),
        "not_testable_count": sum(1 for s in statuses if s == "NOT_TESTABLE"),
    }
    support = counts["supported_count"] + counts["partially_supported_count"]
    n = counts["valid_observations"]

    def _transitions(seq: list[str]) -> int:
        t = 0
        for a, b in zip(seq, seq[1:]):
            if a != b:
                t += 1
        return t

    if n < 2:
        summary = "INSUFFICIENT_EVIDENCE"
    elif 0 < support < MIN_TREND_OBS and n < MIN_TREND_OBS:
        # positive claims need at least MIN_TREND_OBS evaluable laps
        summary = "INSUFFICIENT_EVIDENCE"
    elif counts["supported_count"] + counts["partially_supported_count"] == 0:
        summary = (
            "CONTRADICTED_OVER_TIME"
            if (counts["not_supported_count"] >= 2 and n >= 2)
            else "NOT_SUPPORTED"
        )
    elif n >= MIN_TREND_OBS and counts["contradicted_count"] == 0 and support == n:
        summary = "CONSISTENTLY_SUPPORTED"
    elif n >= MIN_TREND_OBS and counts["contradicted_count"] == 0 and support / n >= 0.7:
        summary = "MOSTLY_SUPPORTED"
    else:
        summary = "INTERMITTENTLY_SUPPORTED"
    return {
        "summary": summary,
        **counts,
        "support_fraction": round(support / n, 4) if n else None,
        "status_transitions": _transitions([s for s in statuses if s != "NOT_TESTABLE"]),
    }


def _trend_block(values: list[float | None], xs: list[int]) -> dict[str, Any]:
    """Deterministic trend block with the minimum-observation rule."""
    pairs = [(x, v) for x, v in zip(xs, values) if v is not None]
    if len(pairs) < MIN_TREND_OBS:
        return {"status": "INSUFFICIENT_EVIDENCE",
                "reason": f"need >= {MIN_TREND_OBS} valid observations, have {len(pairs)}"}
    x, y = [float(a) for a, _ in pairs], [b for _, b in pairs]
    slope = _ols_slope(x, y)
    return {
        "status": "VALID",
        "n": len(pairs),
        "slope_per_stint_lap": round(slope, 4),
        "first": y[0],
        "last": y[-1],
        "min": min(y),
        "max": max(y),
        "range": round(max(y) - min(y), 4),
        "method": f"OLS slope over stint-lap index (min {MIN_TREND_OBS} obs)",
    }


def _change_point(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    """Thresholded segmented-slope comparison (deterministic, bounded).

    Splits the valid lap sequence at the median index and compares first-half
    vs second-half OLS slopes. A change is reported only when both halves
    have >= MIN_TREND_OBS observations and the slope difference exceeds
    CHANGE_POINT_DELTA_S (s per stint lap). NOT_TESTABLE otherwise.
    """
    pairs = [(i, t["observed_delta_s"]) for i, t in enumerate(trajectory)
             if t.get("observed_delta_s") is not None]
    if len(pairs) < 2 * MIN_TREND_OBS:
        return {"status": "NOT_TESTABLE",
                "reason": f"need >= {2 * MIN_TREND_OBS} valid laps, have {len(pairs)}"}
    xs = [p[0] for p in pairs]
    mid = xs[len(xs) // 2]
    first = [(x, d) for x, d in pairs if x < mid]
    second = [(x, d) for x, d in pairs if x >= mid]
    if len(first) < MIN_TREND_OBS or len(second) < MIN_TREND_OBS:
        return {"status": "NOT_TESTABLE", "reason": "unbalanced halves"}
    s1 = _ols_slope([float(x) for x, _ in first], [d for _, d in first])
    s2 = _ols_slope([float(x) for x, _ in second], [d for _, d in second])
    delta = s2 - s1
    if abs(delta) < CHANGE_POINT_DELTA_S or (
        abs(s1) < CHANGE_POINT_MIN_SLOPE_S and abs(s2) < CHANGE_POINT_MIN_SLOPE_S
    ):
        return {"status": "STABLE",
                "first_half_slope": round(s1, 4), "second_half_slope": round(s2, 4),
                "slope_delta": round(delta, 4),
                "threshold": CHANGE_POINT_DELTA_S}
    return {"status": "CHANGE_DETECTED", "at_index": mid,
            "first_half_slope": round(s1, 4), "second_half_slope": round(s2, 4),
            "slope_delta": round(delta, 4), "threshold": CHANGE_POINT_DELTA_S,
            "direction": "widening" if delta > 0 else "narrowing"}


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def fuse_stint_evidence(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_a: str,
    driver_b: str,
    stint_number: int,
    session_type: str = "RACE",
    max_laps: int = DEFAULT_MAX_LAPS,
) -> dict[str, Any]:
    """Deterministic stint-level evidence fusion (Phase 6G)."""
    from racewise.data.historical.evidence_fusion import fuse_lap_evidence
    from racewise.data.historical.loss_attribution import VALID, VALID_CAVEATS

    if driver_a == driver_b:
        return {"analysis": "fuse_stint_evidence", "version": STINT_EVIDENCE_VERSION,
                "status": "UNAVAILABLE", "reason": "drivers must be distinct"}
    max_laps = max(2, min(int(max_laps), MAX_LAPS_CAP))

    base: dict[str, Any] = {
        "analysis": "fuse_stint_evidence", "version": STINT_EVIDENCE_VERSION,
        "season": season, "round": round_num, "session_type": session_type,
        "driver_a": driver_a, "driver_b": driver_b, "stint_number": stint_number,
    }

    stint_a = _resolve_stint(queries, season, round_num, session_type, driver_a, stint_number)
    stint_b = _resolve_stint(queries, season, round_num, session_type, driver_b, stint_number)
    if stint_a is None or stint_b is None:
        return {**base, "status": "UNAVAILABLE",
                "reason": "canonical stint identity missing for one or both drivers"}

    selected, excluded, _, _ = _select_common_laps(
        queries, season, round_num, session_type, driver_a, driver_b, stint_number, max_laps)
    if len(selected) < 2:
        return {**base, "status": "INSUFFICIENT_EVIDENCE",
                "reason": f"fewer than 2 common clean laps ({len(selected)})",
                "candidate_laps": len(selected) + len(excluded),
                "excluded_laps": excluded}

    trajectory: list[dict[str, Any]] = []
    for ln in selected:
        fused = fuse_lap_evidence(queries, season, round_num, driver_a, driver_b, ln, session_type)
        if fused.get("status") not in (VALID, VALID_CAVEATS):
            trajectory.append({"lap_number": ln, "status": fused.get("status"),
                               "reason": fused.get("reason")})
            continue
        facts = _temporal_facts(fused)
        trajectory.append({
            "lap_number": ln,
            "stint_lap_index": len(trajectory),
            "status": fused["status"],
            **facts,
            "hypotheses": {h["hypothesis_id"]: h["status"] for h in fused["hypotheses"]},
            "sector_deltas": [s.get("delta_s") for s in
                              (fused.get("authoritative_sector_decomposition") or [])],
        })

    usable = [t for t in trajectory if t.get("observed_delta_s") is not None]
    if not usable:
        return {**base, "status": "INSUFFICIENT_EVIDENCE",
                "reason": "no attributable laps in the stint sample",
                "trajectory": trajectory, "excluded_laps": excluded}

    deltas = [t["observed_delta_s"] for t in usable]
    idx = [t["stint_lap_index"] for t in usable]

    # performance trajectory + trend
    perf = _trend_block(deltas, idx)
    cum = []
    run = 0.0
    for d in deltas:
        run = round(run + d, 4)
        cum.append(run)

    # residual trajectory + conservation
    residuals = [t.get("residual_s") for t in usable]
    resid_trend = _trend_block(residuals, idx)
    components = [t.get("pace_component_s") for t in usable]
    cum_observed = round(sum(deltas), 4)
    cum_component = round(sum(c for c in components if c is not None), 4)
    cum_residual = round(cum_observed - cum_component, 4)

    # telemetry metric trends
    metric_trends = {}
    for m, fields in _METRIC_FIELDS.items():
        series = {f: [t["metrics"].get(m, {}).get(f) for t in usable] for f in fields}
        blocks = {}
        for f, vals in series.items():
            blk = _trend_block(vals, idx)
            if blk["status"] == "VALID":
                blocks[f] = blk
            else:
                blocks[f] = {"status": "INSUFFICIENT_EVIDENCE"}
        metric_trends[m] = blocks

    # context transitions (temporal regimes, never silently merged)
    transitions: list[dict[str, Any]] = []
    prev = None
    for t in usable:
        cur = (t.get("restricted", False), t.get("rain_in_window", False), t.get("compound"))
        if prev is not None and cur != prev:
            transitions.append({
                "at_lap_number": t["lap_number"],
                "from": {"restricted": prev[0], "rain": prev[1], "compound": prev[2]},
                "to": {"restricted": cur[0], "rain": cur[1], "compound": cur[2]},
            })
        prev = cur

    # hypothesis evolution
    hyp_ids = sorted({k for t in usable for k in t["hypotheses"]})
    hypotheses: dict[str, Any] = {}
    for h in hyp_ids:
        statuses = [t["hypotheses"].get(h, "NOT_TESTABLE") for t in usable]
        supported_laps = [t["lap_number"] for t in usable
                          if t["hypotheses"].get(h) in ("SUPPORTED", "PARTIALLY_SUPPORTED")]
        summary = _hypothesis_summary(statuses)
        summary.update({
            "first_supported_lap": supported_laps[0] if supported_laps else None,
            "last_supported_lap": supported_laps[-1] if supported_laps else None,
            "label": _HYPOthesis_LABELS.get(h, h),
        })
        hypotheses[h] = summary

    # stint-level conclusion (deterministic wording from computed facts)
    supported_h = [f"{h} ({v['summary']})" for h, v in hypotheses.items()
                   if v["summary"] in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED")]
    contradicted_h = [h for h, v in hypotheses.items()
                      if v["summary"] in ("CONTRADICTED_OVER_TIME", "NOT_SUPPORTED")]
    intermittent_h = [h for h, v in hypotheses.items() if v["summary"] == "INTERMITTENTLY_SUPPORTED"]
    untestable_h = [h for h, v in hypotheses.items() if v["summary"] == "INSUFFICIENT_EVIDENCE"]
    parts: list[str] = []
    parts.append(
        f"Across {len(usable)} comparable laps the observed delta (B - A) ran from "
        f"{deltas[0]}s to {deltas[-1]}s (cumulative {cum_observed}s)."
    )
    if perf["status"] == "VALID":
        parts.append(
            f"Performance trend {perf['slope_per_stint_lap']}s per stint lap "
            f"({'widening' if perf['slope_per_stint_lap'] > 0 else 'narrowing'} gap) - descriptive, not causal."
        )
    else:
        parts.append(f"Performance trend not established ({perf.get('reason')}).")
    if supported_h:
        parts.append("Evidence is consistent with: " + "; ".join(supported_h) + ".")
    if intermittent_h:
        parts.append("Intermittent support: " + ", ".join(intermittent_h) + ".")
    if contradicted_h:
        parts.append("Contradicted/not supported over time: " + ", ".join(contradicted_h) + ".")
    if untestable_h:
        parts.append("Not testable with available evidence: " + ", ".join(untestable_h) + ".")
    parts.append(
        f"Residual trajectory {'valid' if resid_trend['status'] == 'VALID' else 'not established'}; "
        f"cumulative residual {cum_residual}s is reported, not assigned to any hypothesis. "
        "Consistency over time is not causation."
    )
    conclusion = " ".join(parts)

    return {
        **base,
        "status": "VALID_WITH_CAVEATS" if any(t.get("status") == "VALID_WITH_CAVEATS" for t in usable) else "VALID_COMPARISON",
        "stint_metadata": {
            "driver_a_stint": stint_a, "driver_b_stint": stint_b,
            "laps_selected": len(selected), "max_laps": max_laps,
        },
        "selection": {
            "candidate_laps": len(selected) + len(excluded),
            "selected_laps": [t["lap_number"] for t in trajectory],
            "valid_laps": len(usable),
            "excluded": excluded,
        },
        "trajectory": trajectory,
        "performance": {
            **({"trend": perf} if perf else {}),
            "mean_delta_s": round(sum(deltas) / len(deltas), 4),
            "median_delta_s": round(_median(deltas), 4),
            "min_delta_s": min(deltas),
            "max_delta_s": max(deltas),
            "first_delta_s": deltas[0],
            "last_delta_s": deltas[-1],
            "cumulative_gap_s": {
                "value": cum_observed,
                "semantics": "cumulative observed delta across the SELECTED comparable laps; "
                             "not total race time lost (laps are a bounded sample, not a "
                             "continuous representative series unless selection covers the stint)",
                "cumulative_series": cum,
            },
        },
        "residuals": {
            "trend": resid_trend,
            "mean_residual_s": round(
                sum(r for r in residuals if r is not None)
                / max(len([r for r in residuals if r is not None]), 1), 4),
            "residual_range_s": [min(r for r in residuals if r is not None),
                                 max(r for r in residuals if r is not None)],
            "cumulative_observed_s": cum_observed,
            "cumulative_pace_component_s": cum_component,
            "cumulative_residual_s": cum_residual,
            "conservation": "cumulative observed = cumulative pace component + cumulative residual",
            "unresolved_note": "cumulative residual is unresolved evidence; never assigned to a hypothesis",
        },
        "telemetry_trends": metric_trends,
        "context_transitions": transitions,
        "change_point": _change_point(trajectory),
        "hypothesis_evolution": hypotheses,
        "conclusion": conclusion,
        "counterfactual_gate": (
            "telemetry-profile counterfactuals remain UNSUPPORTED: the deterministic "
            "simulator does not accept telemetry-profile inputs (Phase 6E/6F limitation preserved)"
        ),
        "methodology_version": STINT_EVIDENCE_VERSION,
        "provenance": {
            "lap_fusion_version": "evidence_fusion_v1",
            "stint_evidence_version": STINT_EVIDENCE_VERSION,
            "tables": ["canonical_stints", "canonical_lap_times", "canonical_telemetry",
                       "canonical_weather", "canonical_race_control", "canonical_pit_stops"],
            "provider": "fastf1",
            "selected_laps": [t["lap_number"] for t in trajectory],
        },
        "assumptions": [
            "stints come from canonical stint identity; never inferred from consecutive laps",
            "common-lap selection reuses the Phase 6E clean-lap rules and requires "
            "telemetry coverage for both drivers; every exclusion is reported",
            "trend = OLS slope over stint-lap index; minimum "
            f"{MIN_TREND_OBS} valid observations, outliers retained and visible",
            "cumulative gap accumulates over the selected comparable laps only",
            "hypothesis summaries are descriptive temporal facts, not confidence scores",
        ],
        "limitations": [
            "traffic/dirty-air remains unmeasurable with current signals",
            "tyre grip/temperature not modeled; compound and age only",
            "change-point detection is a bounded first/second-half slope comparison",
            "consistency of evidence over time is not causation",
        ],
    }
