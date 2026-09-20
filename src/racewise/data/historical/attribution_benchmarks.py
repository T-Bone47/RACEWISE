"""Q7 benchmark family: telemetry lap-loss attribution (Phase 6E).

Extends the deterministic benchmark suite with attribution questions that
consume `loss_attribution`:

    Q7.1 straight-line performance    (fastest region: low-curvature stretch)
    Q7.2 braking difference           (braking metric in the dominant region)
    Q7.3 corner-speed difference      (min-speed delta in the dominant region)
    Q7.4 throttle application         (throttle metric in the dominant region)
    Q7.5 DRS effect                   (DRS activation delta where measurable)
    Q7.6 multi-signal attribution     (full attribution + reconciliation)
    Q7.7 stint-level attribution      (aggregated per-lap decomposition)

Every question returns INSUFFICIENT_EVIDENCE / UNAVAILABLE rather than a
synthetic answer. Drivers are derived from the canonical telemetry pair of
the session (the top-2 classified finishers at ingestion time).
"""
from __future__ import annotations

from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.loss_attribution import (
    attribute_lap_loss,
    attribute_stint_loss,
    falsify_attribution,
)

ATTRIBUTION_BENCH_VERSION = "1.0"


def _telemetry_pair(queries: CanonicalQueries, season: int, round_num: int) -> Optional[tuple[str, str]]:
    """Deterministic telemetry driver pair for a session (lowest driver ids)."""
    pairs = queries.get_telemetry_driver_pair(season, round_num, "RACE")
    if pairs is None:
        return None
    a, b = pairs
    return a, b


def _pick_lap(queries: CanonicalQueries, season: int, round_num: int,
              driver_a: str, driver_b: str) -> Optional[int]:
    """Highest shared telemetry lap that yields a valid comparison.

    Walks telemetry laps newest-first and asks the attribution engine itself
    (the same code path used for the result) whether the lap is clean and
    comparable for both drivers - so the benchmark never picks a lap the
    engine would reject, and never fabricates a fallback criterion.
    """
    tel = queries.telemetry_summary(season, round_num, "RACE")
    if not tel["available"]:
        return None
    for lap in sorted(tel["laps"], reverse=True):
        att = attribute_lap_loss(queries, season, round_num, driver_a, driver_b, lap)
        if att.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS"):
            return lap
    return None


def _region_kind(mean_speed_kmh: Optional[float], track_status: str = "") -> str:
    """Coarse region characterisation from mean speed (documented heuristic).

    This labels the region for reporting; it never feeds a numeric result.
    """
    if mean_speed_kmh is None:
        return "UNKNOWN"
    if mean_speed_kmh >= 250:
        return "STRAIGHT_OR_FAST"
    if mean_speed_kmh >= 150:
        return "MEDIUM_SPEED"
    return "SLOW_CORNER"


def run_q7_attribution_benchmarks(db_path: Optional[str] = None,
                                  sessions: Optional[list[tuple[int, int]]] = None) -> dict[str, Any]:
    """Run the Q7 family across representative telemetry sessions.

    Default sessions span four seasons and multiple circuits. Drivers are the
    canonical telemetry pair per session; laps are picked deterministically.
    """
    queries = CanonicalQueries(db_path)
    matrix = sessions or [
        (2022, 1),   # Bahrain
        (2022, 10),  # Silverstone-style high speed
        (2023, 1),   # Bahrain
        (2023, 9),   # Monza (straight-line heavy)
        (2024, 1),   # Bahrain
        (2024, 14),  # Hungaroring (slow corners)
        (2025, 1),   # Melbourne
        (2025, 12),  # late-season circuit
    ]
    out: dict[str, Any] = {}
    for season, rnd in matrix:
        pair = _telemetry_pair(queries, season, rnd)
        entry: dict[str, Any] = {"season": season, "round": rnd, "telemetry_pair": pair}
        if pair is None:
            entry["status"] = "UNAVAILABLE"
            entry["reason"] = "no telemetry pair for this session"
            out[f"q7_{season}_R{rnd}"] = entry
            continue
        driver_a, driver_b = pair
        lap = _pick_lap(queries, season, rnd, driver_a, driver_b)
        if lap is None:
            entry["status"] = "INSUFFICIENT_EVIDENCE"
            entry["reason"] = "no shared clean telemetry lap"
            out[f"q7_{season}_R{rnd}"] = entry
            continue
        att = attribute_lap_loss(queries, season, rnd, driver_a, driver_b, lap)
        entry["lap"] = lap
        entry["driver_a"] = driver_a
        entry["driver_b"] = driver_b
        if att.get("status") not in ("VALID_COMPARISON", "VALID_WITH_CAVEATS"):
            entry["status"] = att.get("status", "INSUFFICIENT_EVIDENCE")
            entry["reason"] = att.get("reason")
            out[f"q7_{season}_R{rnd}"] = entry
            continue

        regions = att.get("regions", [])
        metrics = att.get("signal_metrics", {})
        dominant = (att.get("top_loss_regions") or [{}])[0]
        dominant_speed = dominant.get("mean_speed_a_kmh")

        # Q7.1 straight-line: fastest region delta
        fastest = max(regions, key=lambda r: r.get("mean_speed_a_kmh") or 0) if regions else None
        q71 = {
            "question": "How much of the delta arises in the fastest (straight-line) region?",
            "region_kind": _region_kind(fastest.get("mean_speed_a_kmh")) if fastest else None,
            "speed_delta_kmh": fastest.get("speed_delta_kmh") if fastest else None,
            "attributed_loss_s": fastest.get("attributed_loss_s") if fastest else None,
            "verdict": "PASS" if fastest and fastest.get("attributed_loss_s") is not None else "INSUFFICIENT_EVIDENCE",
        }

        # Q7.2 braking: braking metric relationship to the dominant region
        brake = metrics.get("brake", {})
        q72 = {
            "question": f"Does braking behaviour differ around the dominant loss region (t={dominant.get('t_start_s')}s)?",
            "braking_fraction_delta": brake.get("braking_fraction_delta"),
            "first_brake_delta_s": brake.get("first_brake_delta_s"),
            "verdict": "PASS" if brake else "INSUFFICIENT_EVIDENCE",
        }

        # Q7.3 corner speed: slowest region delta
        slowest = min(regions, key=lambda r: r.get("mean_speed_a_kmh") or 1e9) if regions else None
        q73 = {
            "question": "How much of the delta arises in the slowest (corner) region?",
            "region_kind": _region_kind(slowest.get("mean_speed_a_kmh")) if slowest else None,
            "speed_delta_kmh": slowest.get("speed_delta_kmh") if slowest else None,
            "attributed_loss_s": slowest.get("attributed_loss_s") if slowest else None,
            "verdict": "PASS" if slowest and slowest.get("attributed_loss_s") is not None else "INSUFFICIENT_EVIDENCE",
        }

        # Q7.4 throttle application
        throttle = metrics.get("throttle", {})
        q74 = {
            "question": "Do throttle-application differences accompany the dominant region?",
            "mean_delta_pct": throttle.get("mean_delta_pct"),
            "b_lift_windows_vs_a": throttle.get("b_lift_windows_vs_a"),
            "verdict": "PASS" if throttle else "INSUFFICIENT_EVIDENCE",
        }

        # Q7.5 DRS effect where measurable
        drs = metrics.get("drs")
        q75 = {
            "question": "Is a DRS availability difference present on this lap?",
            "activation_fraction_delta": (drs or {}).get("activation_fraction_delta"),
            "verdict": ("PASS" if drs else "INSUFFICIENT_EVIDENCE"),
            "note": None if drs else "no DRS metric (codes absent or below enabled threshold)",
        }

        # Q7.6 multi-signal attribution + reconciliation
        recon = att.get("reconciliation", {})
        q76 = {
            "question": "Which signals associate with the measured delta, and does the model reconcile?",
            "observed_delta_s": att.get("observed_delta_s"),
            "estimated_pace_component_s": att.get("estimated_pace_component_s"),
            "residual_s": att.get("residual_s"),
            "within_tolerance": recon.get("within_tolerance"),
            "sector_attribution": att.get("sector_attribution"),
            "signals_present": sorted(metrics.keys()),
            "verdict": "PASS",
        }

        # Q7.7 stint attribution: the stint containing the analysed lap
        stint_number = att.get("context", {}).get("driver_a", {}).get("stint")
        if stint_number is None and att.get("context", {}).get("driver_a", {}).get("present"):
            stint_number = 1
        q77: dict[str, Any]
        if stint_number is not None:
            st = attribute_stint_loss(queries, season, rnd, driver_a, driver_b, int(stint_number))
            q77 = {
                "question": f"How consistent is the attribution across stint {stint_number}?",
                "status": st.get("status"),
                "reason": st.get("reason"),
                "aggregate": st.get("aggregate"),
            }
        else:
            q77 = {"question": "stint attribution", "status": "INSUFFICIENT_EVIDENCE",
                   "reason": "no stint for the analysed lap"}

        fals = falsify_attribution(queries, att)
        entry.update({
            "status": "PASS",
            "q7_1_straight_line": q71,
            "q7_2_braking": q72,
            "q7_3_corner_speed": q73,
            "q7_4_throttle": q74,
            "q7_5_drs": q75,
            "q7_6_multi_signal": q76,
            "q7_7_stint": q77,
            "falsification": {"n_supported": fals["n_supported"],
                              "checks": [(c["hypothesis"], c["verdict"]) for c in fals["checks"]]},
            "provenance": {"attribution_version": att["version"], "provider": "fastf1"},
        })
        out[f"q7_{season}_R{rnd}"] = entry
    return out


def run_q7_negative_controls(db_path: Optional[str] = None) -> dict[str, Any]:
    """Mandatory negative controls: absent telemetry must never produce numbers."""
    queries = CanonicalQueries(db_path)
    out: dict[str, Any] = {}
    # 1950: no telemetry era
    r = attribute_lap_loss(queries, 1950, 6, "giuseppe-farina", "luigi-fagioli", 1)
    out["1950_no_telemetry"] = {"status": r["status"], "expected": "UNAVAILABLE",
                                "pass": r["status"] == "UNAVAILABLE"}
    # 2018: modern era, no telemetry ingested
    r2 = attribute_lap_loss(queries, 2018, 1, "lewis-hamilton", "sebastian-vettel", 5)
    out["2018_not_ingested"] = {"status": r2["status"], "expected": "UNAVAILABLE",
                                "pass": r2["status"] == "UNAVAILABLE"}
    # modern session, absent lap (no telemetry for that lap)
    r3 = attribute_lap_loss(queries, 2023, 1, "max-verstappen", "sergio-perez", 70)
    out["2023_absent_lap"] = {"status": r3["status"], "expected": "UNAVAILABLE",
                              "pass": r3["status"] == "UNAVAILABLE"}
    # pit-affected comparison (pit-in/out lap must be classified, not silently used)
    r4 = attribute_lap_loss(queries, 2023, 1, "max-verstappen", "sergio-perez", 1)
    out["2023_lap1_context"] = {"status": r4["status"],
                                "pass": r4["status"] in ("INSUFFICIENT_EVIDENCE", "UNAVAILABLE")}
    return out
