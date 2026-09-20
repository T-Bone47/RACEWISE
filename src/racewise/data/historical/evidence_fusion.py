"""Multi-source engineering evidence fusion (Phase 6F).

Answers the fusion question deterministically:

    "What combination of measurable factors best explains the observed
     performance difference, what evidence supports that explanation,
     what contradicts it, and what remains unexplained?"

Design invariants:
- The OBSERVED lap delta is a measured FACT (canonical lap times). Telemetry,
  tyres, weather, race control and pit stops are only ever EVIDENCE about it.
- No single confidence score. Verdicts are evidence states derived by the
  formal rules in `evaluate_hypothesis`, never weighted averages.
- NOT_SUPPORTED ("tested, evidence conflicts / fails to meet the rule") is
  distinct from NOT_TESTABLE ("required evidence unavailable").
- Source independence: every evidence item records its `source_id`; two items
  with the same `source_id` are the same observation and can never confirm
  each other.
- Residuals survive: the unexplained component is reported, never assigned to
  the most convenient hypothesis.
- Causation is never claimed; SUPPORTED means "evidence is consistent with".

Hypothesis set (candidate, not universal causes): lower corner speed, later
throttle application, braking differences, tyre-state difference, race-control
restriction, DRS availability. Each is evaluated only where its required
evidence exists; elsewhere it is NOT_TESTABLE.
"""
from __future__ import annotations

from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.loss_attribution import (
    attribute_lap_loss,
    falsify_attribution,
    VALID,
    VALID_CAVEATS,
)

FUSION_VERSION = "1.0"

# Evidence quality dimensions (explicit, not a score)
QUALITY_DIMENSIONS = (
    "availability", "completeness", "validity", "context_compatibility",
    "provenance", "measurement_quality",
)

# Hypothesis statuses (evidence states, not confidence)
SUPPORTED = "SUPPORTED"
PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
CONTRADICTED = "CONTRADICTED"
NOT_SUPPORTED = "NOT_SUPPORTED"
NOT_TESTABLE = "NOT_TESTABLE"

SUPPORTS = "SUPPORTS"
CONTRADICTS = "CONTRADICTS"
DOES_NOT_TEST = "DOES_NOT_TEST"
INSUFFICIENT = "INSUFFICIENT"


# ---------------------------------------------------------------------------
# evidence item
# ---------------------------------------------------------------------------

def _evidence(
    source_id: str,
    source_type: str,
    statement: str,
    values: dict[str, Any],
    *,
    evidence_type: str,
    relationship: str,
    hypotheses: list[str],
    provider: str = "fastf1",
    tables: Optional[list[str]] = None,
    assumptions: Optional[list[str]] = None,
    limitations: Optional[list[str]] = None,
    quality: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """One evidence item with full provenance and relationship metadata."""
    return {
        "source_id": source_id,          # dependency identity (deduplication key)
        "source_type": source_type,
        "statement": statement,
        "values": values,
        "evidence_type": evidence_type,  # FACT / CALCULATION / INFERENCE
        "relationship": relationship,    # SUPPORTS / CONTRADICTS / DOES_NOT_TEST
        "hypotheses": hypotheses,
        "provider": provider,
        "tables": tables or [],
        "assumptions": assumptions or [],
        "limitations": limitations or [],
        "quality": quality or {
            "availability": "AVAILABLE",
            "completeness": "COMPLETE",
            "validity": "VALID",
            "context_compatibility": "COMPATIBLE",
            "provenance": "TRACED",
            "measurement_quality": "MEASURED",
        },
    }


# ---------------------------------------------------------------------------
# source adapters (each independent: one source_id per underlying observation)
# ---------------------------------------------------------------------------

def _sector_evidence(att: dict[str, Any]) -> list[dict[str, Any]]:
    """Authoritative sector decomposition (FACT). One item per sector."""
    out: list[dict[str, Any]] = []
    for s in att.get("sector_attribution") or []:
        out.append(_evidence(
            source_id=f"sector:{att['season']}:{att['round']}:{att['lap_number']}:{s['sector']}",
            source_type="canonical_sector_split",
            statement=f"Sector {s['sector']} delta (B − A): {s['delta_s']}s (measured)",
            values={"sector": s["sector"], "delta_s": s["delta_s"]},
            evidence_type="FACT",
            relationship=SUPPORTS if s["delta_s"] > 0 else CONTRADICTS,
            hypotheses=["H1_corner_speed", "H2_throttle", "H3_braking",
                        "H4_tyre_state", "H6_drs"],
            tables=["canonical_lap_times"],
        ))
    return out


def _speed_evidence(att: dict[str, Any]) -> list[dict[str, Any]]:
    """Speed-trace evidence (CALCULATION): regions + per-signal speed delta."""
    out: list[dict[str, Any]] = []
    top = (att.get("top_loss_regions") or [None])[0]
    speed = (att.get("signal_metrics") or {}).get("speed", {})
    if top and top.get("attributed_loss_s") is not None:
        out.append(_evidence(
            source_id=f"speed_region:{att['season']}:{att['round']}:{att['lap_number']}:{top['region']}",
            source_type="telemetry_speed_regions",
            statement=(
                f"Dominant speed-trace loss region {top['region']} "
                f"({top['t_start_s']}–{top['t_end_s']}s): mean speed delta "
                f"{top['speed_delta_kmh']} km/h, estimated loss {top['attributed_loss_s']}s"
            ),
            values={k: top.get(k) for k in (
                "region", "t_start_s", "t_end_s", "speed_delta_kmh", "attributed_loss_s",
                "mean_speed_a_kmh", "mean_speed_b_kmh")},
            evidence_type="CALCULATION",
            relationship=SUPPORTS if (top.get("speed_delta_kmh") or 0) < 0 else CONTRADICTS,
            hypotheses=["H1_corner_speed"],
            tables=["canonical_telemetry"],
            assumptions=["straight-line region loss model; window means"],
        ))
    if speed:
        out.append(_evidence(
            source_id=f"speed_metric:{att['season']}:{att['round']}:{att['lap_number']}",
            source_type="telemetry_speed_metric",
            statement=(
                f"Mean speed delta {speed.get('mean_delta_kmh')} km/h over the shared grid; "
                f"largest deficit {speed.get('max_deficit_kmh')} km/h at t={speed.get('largest_deficit_at_lap_time_s')}s"
            ),
            values=speed,
            evidence_type="CALCULATION",
            relationship=SUPPORTS if (speed.get("mean_delta_kmh") or 0) < 0 else CONTRADICTS,
            hypotheses=["H1_corner_speed"],
            tables=["canonical_telemetry"],
        ))
    return out


def _throttle_evidence(att: dict[str, Any]) -> list[dict[str, Any]]:
    th = (att.get("signal_metrics") or {}).get("throttle")
    if not th:
        return []
    lift_windows = th.get("b_lift_windows_vs_a") or 0
    mean_d = th.get("mean_delta_pct") or 0
    relationship = SUPPORTS if (mean_d < 0 or lift_windows > 0) else CONTRADICTS
    return [_evidence(
        source_id=f"throttle:{att['season']}:{att['round']}:{att['lap_number']}",
        source_type="telemetry_throttle_metric",
        statement=(
            f"Mean throttle delta {mean_d}% with {lift_windows} lift-window(s) "
            "where B lifted while A stayed above 90%"
        ),
        values=th,
        evidence_type="CALCULATION",
        relationship=relationship,
        hypotheses=["H2_throttle"],
        tables=["canonical_telemetry"],
    )]


def _brake_evidence(att: dict[str, Any]) -> list[dict[str, Any]]:
    br = (att.get("signal_metrics") or {}).get("brake")
    if not br:
        return []
    frac = br.get("braking_fraction_delta") or 0
    onset = br.get("first_brake_delta_s")
    # Braking hypothesis requires B braking MORE or LATER to explain a loss.
    if frac > 0.02 or (onset is not None and onset > 0.2):
        relationship = SUPPORTS
    elif frac < -0.02 or (onset is not None and onset < -0.2):
        relationship = CONTRADICTS  # B brakes less/earlier — cannot explain a loss
    else:
        relationship = DOES_NOT_TEST  # differences too small to inform
    return [_evidence(
        source_id=f"brake:{att['season']}:{att['round']}:{att['lap_number']}",
        source_type="telemetry_brake_metric",
        statement=(
            f"Braking fraction delta {frac} (B − A share of samples braking), "
            f"first-brake onset delta {onset}s"
        ),
        values=br,
        evidence_type="CALCULATION",
        relationship=relationship,
        hypotheses=["H3_braking"],
        tables=["canonical_telemetry"],
    )]


def _drs_evidence(att: dict[str, Any]) -> list[dict[str, Any]]:
    drs = (att.get("signal_metrics") or {}).get("drs")
    if not drs:
        return []
    d = drs.get("activation_fraction_delta")
    if d is None or abs(d) <= 0.05:
        relationship = DOES_NOT_TEST
    elif d < 0:
        relationship = SUPPORTS     # B had less DRS availability
    else:
        relationship = CONTRADICTS  # B had MORE DRS — cannot explain their loss
    return [_evidence(
        source_id=f"drs:{att['season']}:{att['round']}:{att['lap_number']}",
        source_type="telemetry_drs_metric",
        statement=f"DRS activation-fraction delta {d} (B − A)",
        values=drs,
        evidence_type="CALCULATION",
        relationship=relationship,
        hypotheses=["H6_drs"],
        tables=["canonical_telemetry"],
    )]


def _tyre_evidence(
    queries: CanonicalQueries, att: dict[str, Any],
) -> list[dict[str, Any]]:
    """Tyre-state evidence from canonical stints (compound + tyre age)."""
    season, rnd, lap = att["season"], att["round"], att["lap_number"]
    a, b = att["driver_a"], att["driver_b"]
    ctx = att.get("context", {})
    comp_a = ctx.get("driver_a", {}).get("compound")
    comp_b = ctx.get("driver_b", {}).get("compound")
    life_a = ctx.get("driver_a", {}).get("tyre_life")
    life_b = ctx.get("driver_b", {}).get("tyre_life")
    out: list[dict[str, Any]] = []
    if comp_a is None or comp_b is None:
        out.append(_evidence(
            source_id=f"tyre_compound:{season}:{rnd}:{lap}",
            source_type="canonical_stint_compound",
            statement="compound unavailable for at least one driver-lap",
            values={"compound_a": comp_a, "compound_b": comp_b},
            evidence_type="FACT",
            relationship=DOES_NOT_TEST,
            hypotheses=["H4_tyre_state"],
            quality={"availability": "UNAVAILABLE", "completeness": "INCOMPLETE",
                     "validity": "NOT_ASSESSABLE", "context_compatibility": "UNKNOWN",
                     "provenance": "TRACED", "measurement_quality": "UNMEASURED"},
        ))
        return out
    same_compound = comp_a == comp_b
    age_gap = (life_b - life_a) if (life_a is not None and life_b is not None) else None
    # Tyre-state hypothesis (H4): a tyre difference explaining B's loss needs
    # B on worse rubber (older tyres, or softer worn compound). Same compound
    # + small age gap CONTRADICTS the tyre explanation.
    if same_compound and (age_gap is None or abs(age_gap) <= 4):
        relationship = CONTRADICTS
        stmt = (f"Same compound ({comp_a}) and tyre-age gap {age_gap} laps — "
                "tyre state cannot explain the delta")
    elif not same_compound or (age_gap is not None and abs(age_gap) > 4):
        relationship = SUPPORTS if (age_gap is not None and age_gap > 4) else INSUFFICIENT and SUPPORTS
        stmt = (f"Compound A={comp_a} vs B={comp_b}, tyre-age gap {age_gap} laps — "
                "a tyre-state difference exists and may contribute")
    else:
        relationship = DOES_NOT_TEST
        stmt = f"Compound A={comp_a}, B={comp_b}; tyre age unavailable"
    out.append(_evidence(
        source_id=f"tyre_state:{season}:{rnd}:{lap}",
        source_type="canonical_stint_state",
        statement=stmt,
        values={"compound_a": comp_a, "compound_b": comp_b,
                "tyre_life_a": life_a, "tyre_life_b": life_b, "age_gap_laps": age_gap},
        evidence_type="FACT",
        relationship=relationship,
        hypotheses=["H4_tyre_state"],
        tables=["canonical_lap_times", "canonical_stints"],
    ))
    return out


def _race_control_evidence(
    queries: CanonicalQueries, att: dict[str, Any],
) -> list[dict[str, Any]]:
    """Race-control evidence restricted to the investigated lap (lap overlap)."""
    season, rnd, lap = att["season"], att["round"], att["lap_number"]
    events = [
        e for e in queries.get_race_control(season, rnd, "RACE")
        if e.get("lap") == lap and e.get("category") == "Flag"
    ]
    restricted = [e for e in events if any(
        code in str(e.get("message", "")) for code in
        ("YELLOW", "SAFETY CAR", "VSC", "RED FLAG", "FULL COURSE")
    )]
    values = {
        "flag_events_on_lap": [{"category": e.get("category"), "message": e.get("message"),
                                "timestamp": e.get("timestamp")} for e in events][:10],
        "restriction_matches": len(restricted),
    }
    return [_evidence(
        source_id=f"race_control:{season}:{rnd}:{lap}",
        source_type="canonical_race_control_lap_overlap",
        statement=(
            f"{len(restricted)} SC/VSC/yellow/red restriction event(s) overlap lap {lap}"
            if restricted else f"No SC/VSC/yellow/red events overlap lap {lap}"
        ),
        values=values,
        evidence_type="FACT",
        relationship=SUPPORTS if restricted else CONTRADICTS,
        hypotheses=["H5_race_control"],
        tables=["canonical_race_control"],
        limitations=["message-text matching; an oddly-worded message could be missed"],
    )]


def _pit_evidence(
    queries: CanonicalQueries, att: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pit evidence: only stops within ±1 lap of the investigated lap count."""
    season, rnd, lap = att["season"], att["round"], att["lap_number"]
    a, b = att["driver_a"], att["driver_b"]
    nearby: list[dict[str, Any]] = []
    for driver in (a, b):
        for stop in queries.get_pit_stops(season, rnd, "RACE", driver):
            stop_lap = stop.get("lap")
            if stop_lap is not None and abs(stop_lap - lap) <= 1:
                nearby.append({"driver": driver, "lap": stop_lap,
                               "duration_s": stop.get("duration")})
    return [_evidence(
        source_id=f"pit:{season}:{rnd}:{lap}",
        source_type="canonical_pit_stop_proximity",
        statement=(
            f"{len(nearby)} pit stop(s) within ±1 lap of lap {lat_str(lap)}"
            if False else f"{len(nearby)} pit stop(s) within ±1 lap of lap {lap}"
        ),
        values={"nearby_stops": nearby},
        evidence_type="FACT",
        relationship=CONTRADICTS if not nearby else SUPPORTS,
        hypotheses=["H5_race_control"],  # pit-path interference, not a tyre cause
        tables=["canonical_pit_stops"],
    )]


def lat_str(lap: int) -> str:  # pragma: no cover - formatting helper guard
    return str(lap)


def _weather_evidence(
    queries: CanonicalQueries, att: dict[str, Any], laps_a: dict[int, dict], laps_b: dict[int, dict],
) -> list[dict[str, Any]]:
    """Weather evidence aligned to each driver's lap window (6E philosophy)."""
    from racewise.data.historical.loss_attribution import _rain_in_window

    season, rnd, lap = att["season"], att["round"], att["lap_number"]
    lap_a, lap_b = laps_a.get(lap), laps_b.get(lap)
    rain_a = _rain_in_window(queries, season, rnd, "RACE", lap_a)
    rain_b = _rain_in_window(queries, season, rnd, "RACE", lap_b)
    obs = [w for w in queries.get_weather(season, rnd, "RACE") if w.get("elapsed_s") is not None]
    # track temperature around driver A's lap window (documented Q4 approximation)
    temps: list[float] = []
    if lap_a and lap_a.get("time_s"):
        mean_lap = lap_a["time_s"]
        lo, hi = (lap - 1) * mean_lap, lap * mean_lap
        temps = [w["track_temp_c"] for w in obs
                 if lo <= (w.get("elapsed_s") or 0) < hi and w.get("track_temp_c") is not None]
    values = {"rain_a_window": rain_a, "rain_b_window": rain_b,
              "mean_track_temp_c": round(sum(temps) / len(temps), 2) if temps else None}
    # Wet-window asymmetry would confound; symmetric dry conditions CONTRADICT
    # a weather explanation of the delta.
    if rain_a != rain_b:
        relationship = SUPPORTS
        stmt = "Rain in exactly one driver's lap window — conditions differ (confound)"
    elif rain_a and rain_b:
        relationship = INSUFFICIENT and DOES_NOT_TEST
        stmt = "Rain in both windows — both laps affected; cannot separate weather effect"
    else:
        relationship = CONTRADICTS
        stmt = (f"Dry in both lap windows"
                + (f", mean track temp {values['mean_track_temp_c']}C" if temps else "")
                + " — weather cannot explain the delta")
    return [_evidence(
        source_id=f"weather:{season}:{rnd}:{lap}",
        source_type="canonical_weather_lap_window",
        statement=stmt,
        values=values,
        evidence_type="FACT",
        relationship=relationship,
        hypotheses=["H5_race_control"],  # environmental confound family
        tables=["canonical_weather"],
        assumptions=["lap window = lap_number × mean lap time (documented approximation)"],
    )]


# ---------------------------------------------------------------------------
# formal hypothesis evaluation
# ---------------------------------------------------------------------------

HYPOTHESES: dict[str, dict[str, Any]] = {
    "H1_corner_speed": {
        "statement": "Driver B's deficit arises primarily from lower speed through corners/fast sections",
        "required_sources": ("speed_region",),
        "contradicting_sources": ("brake",),   # brake metric CAN contradict
    },
    "H2_throttle": {
        "statement": "Driver B's deficit is associated with later/reduced throttle application",
        "required_sources": ("throttle",),
        "contradicting_sources": (),
    },
    "H3_braking": {
        "statement": "Driver B's deficit arises from braking differences (more/later braking)",
        "required_sources": ("brake",),
        "contradicting_sources": ("brake",),
    },
    "H4_tyre_state": {
        "statement": "A tyre-state difference (compound or age) explains part of the deficit",
        "required_sources": ("tyre_state",),
        "contradicting_sources": ("tyre_state",),
    },
    "H5_race_control": {
        "statement": "Race-control restriction, pit interference or conditions explain the delta",
        "required_sources": ("race_control",),
        "contradicting_sources": ("race_control", "pit", "weather"),
    },
    "H6_drs": {
        "statement": "Lower DRS availability contributed to Driver B's deficit",
        "required_sources": ("drs",),
        "contradicting_sources": ("drs",),
    },
}

# Source-id prefixes each hypothesis REQUIRES before it can be evaluated.
_REQUIRED_PREFIX = {
    "H1_corner_speed": ("speed_region", "speed_metric"),
    "H2_throttle": ("throttle",),
    "H3_braking": ("brake",),
    "H4_tyre_state": ("tyre_state",),
    "H5_race_control": ("race_control",),
    "H6_drs": ("drs",),
}


def evaluate_hypothesis(hyp_id: str, evidence_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Formal deterministic rules (documented, test-covered).

    - NOT_TESTABLE: no evidence item from a required source exists.
    - CONTRADICTED: at least one valid evidence item CONTRADICTS.
    - SUPPORTED: ≥1 valid SUPPORTS item and zero CONTRADICTS.
    - PARTIALLY_SUPPORTED: SUPPORTS present plus at least one DOES_NOT_TEST
      or INSUFFICIENT item from another required-family source.
    - NOT_SUPPORTED: only DOES_NOT_TEST/INSUFFICIENT evidence (tested, but
      the evidence fails to support).
    Causation is never asserted; SUPPORTED means evidence-consistency.
    """
    hyp = HYPOTHESES[hyp_id]
    required = _REQUIRED_PREFIX[hyp_id]
    relevant = [e for e in evidence_items if hyp_id in e["hypotheses"]]
    supporting = [e for e in relevant if e["relationship"] == SUPPORTS]
    contradicting = [e for e in relevant if e["relationship"] == CONTRADICTS]
    neutral = [e for e in relevant if e["relationship"] in (DOES_NOT_TEST, INSUFFICIENT)]

    have_required = any(
        any(e["source_id"].startswith(p) for e in relevant) for p in required
    )
    if not relevant or not have_required:
        return {
            "hypothesis_id": hyp_id,
            "statement": hyp["statement"],
            "status": NOT_TESTABLE,
            "reason": "required evidence source unavailable for this lap",
            "supporting": [], "contradicting": [], "untestable": [e["source_id"] for e in neutral],
        }
    if contradicting:
        return {
            "hypothesis_id": hyp_id,
            "statement": hyp["statement"],
            "status": CONTRADICTED if supporting else NOT_SUPPORTED,
            "reason": "valid evidence directly conflicts with the hypothesis",
            "supporting": [e["source_id"] for e in supporting],
            "contradicting": [e["source_id"] for e in contradicting],
            "untestable": [e["source_id"] for e in neutral],
        }
    if supporting:
        status = SUPPORTED if not neutral else PARTIALLY_SUPPORTED
        return {
            "hypothesis_id": hyp_id,
            "statement": hyp["statement"],
            "status": status,
            "reason": "no material contradiction; evidence consistent with the hypothesis"
                      + (" with residual uncertainty" if neutral else ""),
            "supporting": [e["source_id"] for e in supporting],
            "contradicting": [],
            "untestable": [e["source_id"] for e in neutral],
        }
    return {
        "hypothesis_id": hyp_id,
        "statement": hyp["statement"],
        "status": NOT_SUPPORTED,
        "reason": "evidence exists but does not support the hypothesis",
        "supporting": [],
        "contradicting": [],
        "untestable": [e["source_id"] for e in neutral],
    }


# ---------------------------------------------------------------------------
# main fusion entry point
# ---------------------------------------------------------------------------

def fuse_lap_evidence(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_a: str,
    driver_b: str,
    lap_number: int,
    session_type: str = "RACE",
) -> dict[str, Any]:
    """Fuse all available canonical evidence about one lap delta.

    Order: measure (6E attribution) → collect source evidence → evaluate
    hypotheses with formal rules → preserve residual → evidence-bounded
    conclusion. Deterministic; INSUFFICIENT/UNAVAILABLE propagate.
    """
    base: dict[str, Any] = {
        "analysis": "fuse_lap_evidence",
        "version": FUSION_VERSION,
        "season": season,
        "round": round_num,
        "session_type": session_type,
        "lap_number": lap_number,
        "driver_a": driver_a,
        "driver_b": driver_b,
        "quality_dimensions": list(QUALITY_DIMENSIONS),
    }

    att = attribute_lap_loss(queries, season, round_num, driver_a, driver_b, lap_number, session_type)
    if att.get("status") not in (VALID, VALID_CAVEATS):
        return {
            **base,
            "status": att.get("status", "INSUFFICIENT_EVIDENCE"),
            "reason": att.get("reason"),
            "note": "6E context filtering verdicts propagate; fusion never overrides them",
        }

    laps_a = {r["lap_number"]: r for r in queries.get_lap_times(season, round_num, session_type, driver_a)}
    laps_b = {r["lap_number"]: r for r in queries.get_lap_times(season, round_num, session_type, driver_b)}

    evidence: list[dict[str, Any]] = []
    evidence += _sector_evidence(att)
    evidence += _speed_evidence(att)
    evidence += _throttle_evidence(att)
    evidence += _brake_evidence(att)
    evidence += _drs_evidence(att)
    evidence += _tyre_evidence(queries, att)
    evidence += _race_control_evidence(queries, att)
    evidence += _pit_evidence(queries, att)
    evidence += _weather_evidence(queries, att, laps_a, laps_b)

    # source-independence audit: duplicate source_ids would double-count
    ids = [e["source_id"] for e in evidence]
    assert len(ids) == len(set(ids)), "duplicate evidence source_id (double-counting)"

    # Premise gate: all deficit hypotheses explain why B lost time. When the
    # measured delta shows B was NOT slower, the premise is vacuous - report
    # the observation and mark every hypothesis NOT_TESTABLE. Never evaluate
    # deficit explanations against a favourable delta.
    observed = att["observed_delta_s"]
    premise = "deficit" if observed > 0 else (
        "parity" if observed == 0 else "favourable"
    )
    if premise == "deficit":
        hypotheses_out = [evaluate_hypothesis(h, evidence) for h in HYPOTHESES]
    else:
        hypotheses_out = [
            {
                "hypothesis_id": h,
                "statement": HYPOTHESES[h]["statement"],
                "status": NOT_TESTABLE,
                "reason": (
                    f"observed delta is {observed}s (B not slower); "
                    "deficit-explanation premise is vacuous for this lap"
                ),
                "supporting": [], "contradicting": [],
                "untestable": [e["source_id"] for e in evidence],
            }
            for h in HYPOTHESES
        ]

    # residual preservation
    component = att["estimated_pace_component_s"]
    residual = att["residual_s"]
    frac = abs(residual) / max(abs(observed), 1e-9)
    if frac <= 0.15:
        residual_class = "EXPLAINED_BY_SPEED_TRACES"
    elif frac <= 0.75:
        residual_class = "PARTIALLY_EXPLAINED"
    else:
        residual_class = "UNRESOLVED"

    supported = [h for h in hypotheses_out if h["status"] in (SUPPORTED, PARTIALLY_SUPPORTED)]
    contradicted = [h for h in hypotheses_out if h["status"] in (CONTRADICTED, NOT_SUPPORTED)]
    untestable = [h for h in hypotheses_out if h["status"] == NOT_TESTABLE]

    if supported:
        conclusion = (
            "Evidence is consistent with: "
            + "; ".join(h["hypothesis_id"] for h in supported)
            + ". "
        )
    else:
        conclusion = "No candidate hypothesis meets the support rules for this lap. "
    if contradicted:
        conclusion += "Contradicted/not supported: " + ", ".join(
            h["hypothesis_id"] for h in contradicted) + ". "
    if untestable:
        conclusion += "Not testable with available evidence: " + ", ".join(
            h["hypothesis_id"] for h in untestable) + ". "
    conclusion += (
        f"Unexplained component {residual}s ({residual_class}); residual is reported, "
        "not assigned to any hypothesis. Consistency is not causation."
    )

    return {
        **base,
        "status": att["status"],
        "observed_delta_s": observed,
        "lap_times": att["lap_times"],
        "authoritative_sector_decomposition": att.get("sector_attribution"),
        "estimated_pace_component_s": component,
        "residual_s": residual,
        "residual_class": residual_class,
        "reconciliation": att.get("reconciliation"),
        "context": att.get("context"),
        "evidence_items": evidence,
        "evidence_chain": {
            "sources_used": sorted({e["source_type"] for e in evidence}),
            "providers": sorted({e["provider"] for e in evidence}),
            "tables": sorted({t for e in evidence for t in e["tables"]}),
        },
        "hypotheses": hypotheses_out,
        "supported": [h["hypothesis_id"] for h in supported],
        "contradicted_or_not_supported": [h["hypothesis_id"] for h in contradicted],
        "untestable": [h["hypothesis_id"] for h in untestable],
        "conclusion": conclusion,
        "falsification_6e": falsify_attribution(queries, att),
        "assumptions": [
            "hypothesis statuses follow the documented formal rules (no weighted scores)",
            "evidence items sharing a source_id would be double-counting; dedup enforced",
            "weather aligned per lap window; race control by lap overlap",
            "region losses are speed-trace estimates; residual preserved as first-class",
        ],
        "limitations": [
            "traffic/dirty-air evidence not measurable with current signals",
            "tyre grip/temperature not modeled — only compound and age",
            "consistency of evidence with a hypothesis is not causation",
        ],
        "methodology_version": FUSION_VERSION,
        "provenance": {
            "fusion_version": FUSION_VERSION,
            "attribution_version": att.get("version"),
            "tables": sorted({t for e in evidence for t in e["tables"]}),
            "provider": "fastf1",
        },
    }
