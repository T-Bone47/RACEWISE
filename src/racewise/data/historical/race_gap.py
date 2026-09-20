"""Race-level gap decomposition and evidence synthesis (Phase 6H).

Answers: "Where during the race was the performance relationship between
Driver A and Driver B created, recovered, or changed - and which portions of
that evolution are evidence-supported, context-driven, or unresolved?"

This is an orchestration/aggregation layer over existing deterministic
evidence (6E lap attribution, 6F lap fusion, 6G stint fusion). Nothing
underneath is rewritten.

Non-negotiable semantics (enforced by tests):
  - official_final_gap (canonical result milliseconds) is an authoritative
    fact and is NEVER replaced by the analytical comparable-lap gap; the two
    are different quantities and are reported side by side without being
    forced to reconcile.
  - "time lost" is never asserted as fact; the output uses OBSERVED GAP /
    COMPARABLE GAP language only.
  - non-comparable intervals are preserved with reasons - never dropped.
  - residuals are never assigned to a hypothesis.
  - unavailable evidence never becomes supported evidence.
  - race-control and weather are matched by exact lap-window overlap, never
    session-level classification.

Derived on read: zero storage growth. Deterministic: byte-identical output
for the same canonical store and methodology version.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries

RACE_GAP_VERSION = "race_gap_v1"

MAX_SEGMENTS_CAP = 24          # hard input bound for stint segments
DEFAULT_MAX_SEGMENTS = 12
WIDENING_THRESHOLD_S = 0.02    # per-lap delta trend thresholds (descriptive)
STABLE_THRESHOLD_S = 0.02


def _official_gap(queries: CanonicalQueries, season: int, round_num: int,
                  driver_a: str, driver_b: str) -> dict[str, Any] | None:
    """Authoritative classified race gap (B - A) from canonical results.

    Computed only when both drivers share the same laps-completed count and
    carry the same classification status family (finished vs finished) -
    otherwise None with a reason. Never reconstructed from lap sums.
    """
    results = queries.get_results(season, round_num, "RACE")
    ra = rb = None
    for r in results:
        if r["driver_key"] == driver_a:
            ra = r
        elif r["driver_key"] == driver_b:
            rb = r
    if ra is None or rb is None:
        return None
    out: dict[str, Any] = {
        "driver_a": {
            "position": ra.get("position") or ra.get("position_order"),
            "milliseconds": ra.get("milliseconds"), "time": ra.get("time"),
            "laps": ra.get("laps"), "status": ra.get("status"),
        },
        "driver_b": {
            "position": rb.get("position") or rb.get("position_order"),
            "milliseconds": rb.get("milliseconds"), "time": rb.get("time"),
            "laps": rb.get("laps"), "status": rb.get("status"),
        },
    }
    ms_a, ms_b = ra.get("milliseconds"), rb.get("milliseconds")
    if ms_a is not None and ms_b is not None and ra.get("laps") == rb.get("laps") \
            and (ra.get("status") or "Finished") == (rb.get("status") or "Finished"):
        out["gap_s"] = round((ms_b - ms_a) / 1000.0, 3)
        out["semantics"] = ("official classified finishing gap from canonical result "
                            "milliseconds (authoritative fact)")
    else:
        out["gap_s"] = None
        out["semantics"] = ("official gap not computable: different laps completed or "
                            "classification status; the classified positions remain factual")
    return out


def _lap_context(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    session_type: str,
) -> dict[str, Any]:
    """Load all per-lap context once: laps, stints, pits, race control."""
    laps_a = queries.get_lap_times(season, round_num, session_type, driver_a_key := "")  # placeholder replaced below
    raise RuntimeError("replaced by _load_context")


def _load_context(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    session_type: str,
    driver_a: str,
    driver_b: str,
) -> dict[str, Any]:
    from racewise.data.historical.loss_attribution import _NON_COMPARABLE_FLAGS

    ctx: dict[str, Any] = {}
    ctx["laps_a"] = {r["lap_number"]: r for r in
                     queries.get_lap_times(season, round_num, session_type, driver_a)}
    ctx["laps_b"] = {r["lap_number"]: r for r in
                     queries.get_lap_times(season, round_num, session_type, driver_b)}
    ctx["pits_a"] = queries.get_pit_stops(season, round_num, session_type, driver_a)
    ctx["pits_b"] = queries.get_pit_stops(season, round_num, session_type, driver_b)
    ctx["race_control"] = queries.get_race_control(season, round_num, session_type)
    ctx["stints_a"] = {s["stint_number"]: s for s in
                       queries.get_stints(season, round_num, session_type, driver_a)}
    ctx["stints_b"] = {s["stint_number"]: s for s in
                       queries.get_stints(season, round_num, session_type, driver_b)}
    ctx["non_comparable_flags"] = _NON_COMPARABLE_FLAGS
    return ctx


def _rc_restricted_laps(race_control: list[dict[str, Any]]) -> dict[int, str]:
    """Lap -> restriction label for SC/VSC/red/yellow events (exact lap field)."""
    restricted: dict[int, str] = {}
    for ev in race_control:
        cat = (ev.get("category") or "").upper()
        if not any(k in cat for k in ("SAFETY", "VSC", "RED", "YELLOW", "CHEQUERED")):
            continue
        lap = ev.get("lap")
        if lap is None:
            continue
        label = "race_control_restriction"
        restricted.setdefault(int(lap), label)
    return restricted


def _pit_laps(pits: list[dict[str, Any]]) -> set[int]:
    return {int(p["lap"]) for p in pits if p.get("lap") is not None}


def _classify_laps(
    ctx: dict[str, Any],
    restricted: dict[int, str],
    tel_a: set[int],
    tel_b: set[int],
) -> list[dict[str, Any]]:
    """Deterministic chronological timeline with per-lap comparability."""
    laps_a, laps_b = ctx["laps_a"], ctx["laps_b"]
    pit_a, pit_b = _pit_laps(ctx["pits_a"]), _pit_laps(ctx["pits_b"])
    common = sorted(set(laps_a) & set(laps_b))
    timeline: list[dict[str, Any]] = []

    def _entry(ln: int, comparable: bool | None, status: str, reason: str | None) -> dict[str, Any]:
        ra, rb = laps_a.get(ln, {}), laps_b.get(ln, {})
        stint = ra.get("stint") or rb.get("stint")
        delta = None
        if comparable and ra.get("time_s") and rb.get("time_s"):
            delta = round(rb["time_s"] - ra["time_s"], 4)
        return {
            "lap_number": ln,
            "stint": stint,
            "comparable": comparable,
            "status": status,
            "reason": reason,
            "observed_delta_s": delta,
            "compound": ra.get("compound") or rb.get("compound"),
            "tyre_life": ra.get("tyre_life") if ra.get("tyre_life") is not None else rb.get("tyre_life"),
            "restricted": restricted.get(ln),
            "pit_lap": ln in pit_a or ln in pit_b,
            "telemetry": ln in tel_a and ln in tel_b,
            "driver_a_lap_time": ra.get("time_s"),
            "driver_b_lap_time": rb.get("time_s"),
        }

    for ln in common:
        ra, rb = laps_a[ln], laps_b[ln]
        reasons = []
        if not (ra.get("time_s") and rb.get("time_s")):
            reasons.append("missing lap time")
        for flag in ctx["non_comparable_flags"]:
            if ra.get(flag) or rb.get(flag):
                reasons.append(flag)
        if ln in restricted:
            reasons.append("race-control restriction")
        if reasons:
            timeline.append(_entry(ln, None, "non_comparable", "; ".join(reasons)))
            continue
        timeline.append(_entry(ln, True, "comparable", None))

    # laps where one driver has no lap fact at all (retirement, off-sequence)
    only_a = sorted(set(laps_a) - set(laps_b))
    only_b = sorted(set(laps_b) - set(laps_a))
    for ln in only_a:
        timeline.append(_entry(ln, None, "unavailable", "no lap fact for driver_b"))
    for ln in only_b:
        timeline.append(_entry(ln, None, "unavailable", "no lap fact for driver_a"))
    timeline.sort(key=lambda t: t["lap_number"])
    return timeline


def _segment_stints(timeline: list[dict[str, Any]],
                    stints_a: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Group the timeline into stint segments by driver A's stint number."""
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for t in timeline:
        sn = t.get("stint")
        if sn is None or sn not in stints_a:
            if current is not None:
                segments.append(current)
                current = None
            segments.append({
                "kind": "unknown_stint", "stint_number": None,
                "laps": [t], "stint_info": None,
            })
            continue
        if current is None or current["stint_number"] != sn:
            if current is not None:
                segments.append(current)
            current = {"kind": "stint", "stint_number": sn, "laps": [],
                       "stint_info": stints_a.get(sn)}
        current["laps"].append(t)
    if current is not None:
        segments.append(current)
    return segments


def _segment_pattern(seg: dict[str, Any]) -> str:
    """Descriptive gap pattern over a segment's comparable laps (bounded OLS)."""
    deltas = [t["observed_delta_s"] for t in seg["laps"] if t.get("comparable")
              and t.get("observed_delta_s") is not None]
    if len(deltas) < 3:
        return "INSUFFICIENT_EVIDENCE"
    xs = list(range(len(deltas)))
    n = len(xs)
    mx = sum(xs) / n
    my = sum(deltas) / n
    denom = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (d - my) for x, d in zip(xs, deltas)) / denom if denom else 0.0
    if abs(slope) <= STABLE_THRESHOLD_S:
        return "STABLE"
    return "WIDENING" if slope > 0 else "NARROWING"


def _pit_windows(ctx: dict[str, Any],
                 timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Observed pit-window transitions: gap before/after, mechanism UNPROVEN."""
    delta_by_lap = {t["lap_number"]: t["observed_delta_s"] for t in timeline
                    if t.get("comparable") and t.get("observed_delta_s") is not None}
    windows: list[dict[str, Any]] = []
    for driver, pits in (("driver_a", ctx["pits_a"]), ("driver_b", ctx["pits_b"])):
        for p in pits:
            lap = p.get("lap")
            if lap is None:
                continue
            before = max((v for k, v in delta_by_lap.items() if k < lap), default=None)
            after = min((v for k, v in delta_by_lap.items() if k > lap), default=None)
            windows.append({
                "driver": driver,
                "lap": lap,
                "stop_number": p.get("stop_number"),
                "duration_s": p.get("duration"),
                "compound_before": p.get("compound_before"),
                "compound_after": p.get("compound_after"),
                "observed_gap_before_s": before,
                "observed_gap_after_s": after,
                "observed_transition_s": (round(after - before, 4)
                                          if before is not None and after is not None else None),
                "semantics": ("observed comparable-gap transition around the pit lap; the "
                              "mechanism (stop duration, transit, undercut/overcut, traffic, "
                              "tyre state) is NOT isolated by this observation"),
                "mechanism": "INSUFFICIENT_EVIDENCE",
            })
    windows.sort(key=lambda w: (w["lap"], w["driver"]))
    return windows


def _rc_windows(restricted: dict[int, str]) -> list[dict[str, Any]]:
    """Consecutive restricted-lap windows from exact lap-overlap matching."""
    windows: list[dict[str, Any]] = []
    for ln in sorted(restricted):
        if windows and ln == windows[-1]["end_lap"] + 1:
            windows[-1]["end_lap"] = ln
        else:
            windows.append({"start_lap": ln, "end_lap": ln,
                            "classification": restricted[ln]})
    return windows


def decompose_race_gap(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_a: str,
    driver_b: str,
    session_type: str = "RACE",
    max_segments: int = DEFAULT_MAX_SEGMENTS,
) -> dict[str, Any]:
    """Deterministic race-level gap decomposition (Phase 6H)."""
    from racewise.data.historical.stint_evidence import fuse_stint_evidence

    if driver_a == driver_b:
        return {"analysis": "decompose_race_gap", "version": RACE_GAP_VERSION,
                "status": "UNAVAILABLE", "reason": "drivers must be distinct"}
    max_segments = max(2, min(int(max_segments), MAX_SEGMENTS_CAP))

    base: dict[str, Any] = {
        "analysis": "decompose_race_gap", "version": RACE_GAP_VERSION,
        "season": season, "round": round_num, "session_type": session_type,
        "driver_a": driver_a, "driver_b": driver_b,
    }

    results = queries.get_results(season, round_num, "RACE")
    participants = {r["driver_key"] for r in results}
    if driver_a not in participants or driver_b not in participants:
        return {**base, "status": "UNAVAILABLE",
                "reason": "one or both drivers not in the canonical race result"}

    official = _official_gap(queries, season, round_num, driver_a, driver_b)

    # telemetry coverage per driver
    tel_a = _telemetry_laps(queries, season, round_num, session_type, driver_a)
    tel_b = _telemetry_laps(queries, season, round_num, session_type, driver_b)

    ctx = _load_context(queries, season, round_num, session_type, driver_a, driver_b)
    if not ctx["laps_a"] and not ctx["laps_b"]:
        return {**base, "status": "UNAVAILABLE", "reason": "no canonical lap facts",
                "official_result": official}
    restricted = _rc_restricted_laps(ctx["race_control"])
    timeline = _classify_laps(ctx, restricted, tel_a, tel_b)
    if not any(t["comparable"] for t in timeline):
        return {**base, "status": "INSUFFICIENT_EVIDENCE",
                "reason": "no comparable laps", "official_result": official,
                "timeline_summary": _timeline_summary(timeline)}

    segments = _segment_stints(timeline, ctx["stints_a"])
    # bound stint segments: keep segments with most comparable laps, then sort
    stint_segments = [s for s in segments if s["kind"] == "stint"]
    for s in segments:
        s["pattern"] = _segment_pattern(s)
        s["comparable_laps"] = sum(1 for t in s["laps"] if t["comparable"])
        s["lap_range"] = [s["laps"][0]["lap_number"], s["laps"][-1]["lap_number"]]

    # cumulative comparable gap (explicit semantics)
    comparable = [t for t in timeline if t["comparable"] and t.get("observed_delta_s") is not None]
    cum: list[dict[str, Any]] = []
    run = 0.0
    for t in comparable:
        run = round(run + t["observed_delta_s"], 4)
        cum.append({"lap_number": t["lap_number"], "cumulative_gap_s": run})
    analytical_gap = run

    # bounded stint-evidence chaining on the segments with most telemetry-covered laps
    stint_evidence_segments: list[dict[str, Any]] = []
    ranked = sorted(
        (s for s in stint_segments
         if sum(1 for t in s["laps"] if t.get("telemetry") and t["comparable"]) >= 2),
        key=lambda s: -sum(1 for t in s["laps"] if t.get("telemetry") and t["comparable"]))
    for s in ranked[:max_segments]:
        f = fuse_stint_evidence(queries, season, round_num, driver_a, driver_b,
                                s["stint_number"], session_type, max_laps=8)
        stint_evidence_segments.append({
            "stint_number": s["stint_number"],
            "status": f.get("status"),
            "valid_laps": f.get("selection", {}).get("valid_laps"),
            "trend": f.get("performance", {}).get("trend"),
            "hypothesis_summaries": {h: v.get("summary")
                                     for h, v in f.get("hypothesis_evolution", {}).items()},
            "cumulative_residual_s": f.get("residuals", {}).get("cumulative_residual_s"),
            "reason": f.get("reason"),
        })
    stint_evidence_segments.sort(key=lambda s: s["stint_number"] or 0)

    # race-level hypothesis evolution: per stint 6G summaries, then race rule
    race_hypotheses: dict[str, dict[str, Any]] = {}
    stint_statuses: dict[str, list[str]] = {}
    for s in stint_evidence_segments:
        for h, summ in (s.get("hypothesis_summaries") or {}).items():
            stint_statuses.setdefault(h, []).append(summ)
    for h, statuses in sorted(stint_statuses.items()):
        per_stint = [{"stint_number": seg["stint_number"], "summary": seg["hypothesis_summaries"].get(h)}
                     for seg in stint_evidence_segments if seg.get("hypothesis_summaries")]
        race_hypotheses[h] = _race_hypothesis_summary(statuses, per_stint)

    events = _gap_events(timeline, comparable, segments, stint_evidence_segments)

    residual = {
        "cumulative_comparable_gap_s": analytical_gap,
        "semantics": ("cumulative observed delta across comparable laps only; non-comparable "
                      "intervals exist and are itemized; this is NOT the official race gap and "
                      "the two MUST NOT be forced to reconcile"),
        "non_comparable_count": sum(1 for t in timeline if t["status"] == "non_comparable"),
        "unavailable_count": sum(1 for t in timeline if t["status"] == "unavailable"),
        "comparable_count": len(comparable),
        "official_vs_analytical": (
            "official_final_gap and cumulative_comparable_gap are different quantities "
            "(classified finishing gap vs summed comparable-lap deltas); no equality is implied"),
    }

    conclusion = _synthesis(official, analytical_gap, segments, events,
                            race_hypotheses, stint_evidence_segments, residual)

    return {
        **base,
        "status": "VALID_WITH_CAVEATS" if residual["non_comparable_count"] or
                  residual["unavailable_count"] else "VALID_COMPARISON",
        "official_result": official,
        "timeline_summary": _timeline_summary(timeline),
        "segments": [{k: v for k, v in s.items() if k != "laps"} for s in segments],
        "cumulative_comparable_gap_s": analytical_gap,
        "cumulative_series_tail": cum[-5:],
        "gap_events": events,
        "pit_windows": _pit_windows(ctx, timeline),
        "race_control_windows": _rc_windows(restricted),
        "stint_evidence": stint_evidence_segments,
        "hypothesis_evolution": race_hypotheses,
        "residual_accounting": residual,
        "counterfactual_gate": (
            "telemetry-profile counterfactuals remain UNSUPPORTED: the deterministic "
            "simulator does not accept telemetry-profile inputs (Phase 6E/6F/6G limitation preserved)"),
        "conclusion": conclusion,
        "methodology_version": RACE_GAP_VERSION,
        "provenance": {
            "tables": ["canonical_results", "canonical_lap_times", "canonical_stints",
                       "canonical_pit_stops", "canonical_race_control", "canonical_telemetry"],
            "provider": "fastf1",
            "stint_evidence_version": "stint_evidence_v1",
            "lap_fusion_version": "evidence_fusion_v1",
        },
        "assumptions": [
            "official gap from canonical result milliseconds; never reconstructed from lap sums",
            "comparable lap = both drivers' lap facts, valid times, no pit/flag/deleted flags, "
            "no race-control restriction",
            "stint segmentation follows driver A's canonical stint identity",
            "stint-evidence chaining is bounded (max_segments) and ranked by telemetry coverage",
            "gap patterns are descriptive OLS classifications, not causal claims",
        ],
        "limitations": [
            "no telemetry evidence beyond ingested coverage; gaps are preserved as unavailable",
            "pit-window mechanisms are not isolated (INSUFFICIENT_EVIDENCE by design)",
            "race-control matching uses exact lap fields; timing-only events are not mapped",
            "official gap and analytical comparable gap are not forced to reconcile",
        ],
    }


def _telemetry_laps(queries: CanonicalQueries, season: int, round_num: int,
                    session_type: str, driver_key: str) -> set[int]:
    from racewise.data.historical.stint_evidence import _telemetry_covered_laps

    return _telemetry_covered_laps(queries, season, round_num, session_type, driver_key)


def _timeline_summary(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_laps": len(timeline),
        "comparable": sum(1 for t in timeline if t["status"] == "comparable"),
        "non_comparable": sum(1 for t in timeline if t["status"] == "non_comparable"),
        "unavailable": sum(1 for t in timeline if t["status"] == "unavailable"),
        "reasons": _tally(t.get("reason") for t in timeline if t.get("reason")),
    }


def _tally(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def _gap_events(timeline, comparable, segments, stint_evidence_segments) -> list[dict[str, Any]]:
    """Deterministic race-level gap events from explicit methodology."""
    events: list[dict[str, Any]] = []
    deltas = [(t["lap_number"], t["observed_delta_s"]) for t in comparable]
    # rolling pattern change on consecutive 3-lap windows (simple, documented)
    def _w_slope(i: int) -> float | None:
        if i + 2 >= len(deltas):
            return None
        w = deltas[i:i + 3]
        xs = [0, 1, 2]
        my = sum(d for _, d in w) / 3
        return (sum((x - 1) * (d - my) for x, (_, d) in zip(xs, w)) / 2.0)
    prev_state = None
    for i in range(0, len(deltas) - 2):
        s = _w_slope(i)
        if s is None:
            continue
        state = "STABLE" if abs(s) <= STABLE_THRESHOLD_S else ("WIDENING" if s > 0 else "NARROWING")
        if prev_state is not None and state != prev_state:
            events.append({
                "type": f"GAP_{state}", "at_lap": deltas[i + 1][0],
                "previous_state": prev_state, "new_state": state,
                "method": "3-lap window OLS slope sign/magnitude change",
                "threshold_s_per_lap": STABLE_THRESHOLD_S,
            })
        prev_state = state
    for s in segments:
        if s["kind"] == "stint":
            events.append({"type": "STINT_CHANGE", "at_lap": s["lap_range"][0],
                           "stint_number": s["stint_number"],
                           "compound": (s.get("stint_info") or {}).get("compound")})
    if stint_evidence_segments:
        events.append({"type": "TELEMETRY_EVIDENCE_CHANGE",
                       "detail": "bounded stint-evidence chaining available for stints "
                                 + ",".join(str(s["stint_number"]) for s in stint_evidence_segments)})
    return events


def _race_hypothesis_summary(statuses: list[str], per_stint: list[dict[str, Any]]) -> dict[str, Any]:
    """Race-level hypothesis summary over stint-level summaries (deterministic)."""
    evaluable = [s for s in statuses if s not in ("INSUFFICIENT_EVIDENCE", "NOT_TESTABLE")]
    if not evaluable:
        return {"summary": "INSUFFICIENT_EVIDENCE", "per_stint": per_stint}
    if any(s in ("CONTRADICTED_OVER_TIME", "NOT_SUPPORTED") for s in evaluable) and \
            not any(s in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED") for s in evaluable):
        summary = "CONTRADICTED_OVER_TIME"
    elif all(s in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED") for s in evaluable):
        summary = "CONSISTENTLY_SUPPORTED"
    elif any(s in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED") for s in evaluable):
        summary = "INTERMITTENTLY_SUPPORTED"
    else:
        summary = "INTERMITTENTLY_SUPPORTED"
    return {"summary": summary, "per_stint": per_stint}


def _synthesis(official, analytical_gap, segments, events, race_hypotheses,
               stint_evidence_segments, residual) -> str:
    parts: list[str] = []
    if official and official.get("gap_s") is not None:
        parts.append(f"Official classified gap (B - A): {official['gap_s']}s.")
    else:
        parts.append("Official classified gap not computable from canonical results "
                     "(different laps or classification); positions remain factual.")
    parts.append(
        f"Analytical cumulative comparable gap: {analytical_gap}s across "
        f"{residual['comparable_count']} comparable laps; "
        f"{residual['non_comparable_count']} non-comparable and "
        f"{residual['unavailable_count']} unavailable laps are itemized in the timeline. "
        "These are different quantities; no forced reconciliation."
    )
    supported = [h for h, v in race_hypotheses.items()
                 if v["summary"] in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED")]
    contradicted = [h for h, v in race_hypotheses.items()
                    if v["summary"] in ("CONTRADICTED_OVER_TIME", "NOT_SUPPORTED")]
    if supported:
        parts.append("Evidence is consistent with: " + ", ".join(supported) + ".")
    if contradicted:
        parts.append("Contradicted/not supported across the race: " + ", ".join(contradicted) + ".")
    parts.append(
        f"Stint-level telemetry evidence covers stints "
        f"{','.join(str(s['stint_number']) for s in stint_evidence_segments) or 'none'}; "
        "segments without coverage are preserved as unavailable. The residual is reported, "
        "not assigned. Observed-gap language is not time-lost causation."
    )
    return " ".join(parts)
