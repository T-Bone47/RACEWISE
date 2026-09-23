"""Q13 benchmark family: performance regime & change-point intelligence (6K).

Runs the deterministic regime layer over a fixed representative matrix
(2022-2025, multiple circuits, real telemetry pairs) and records measured
semantics. Regime detection identifies temporal structure; it never asserts
causality, never emits confidence scores, and never manufactures regimes.

Categories:
    Q13.1  stable regime
    Q13.2  widening regime
    Q13.3  narrowing regime
    Q13.4  reversal (direction change across change points)
    Q13.5  genuine change point (documented thresholds + SSE gate)
    Q13.6  noise rejection (min-length rule; rejected candidates logged)
    Q13.7  stint-boundary alignment (regimes record canonical stints)
    Q13.8  regime crossing a stint boundary (analytical != canonical)
    Q13.9  telemetry-supported regime (paired speed profiles)
    Q13.10 telemetry-unavailable regime (explicit, never extrapolated)
    Q13.11 residual transition (conservation preserved per regime)
    Q13.12 hypothesis-state transition (6F/6G summaries across regimes)
    Q13.13 envelope sensitivity transition (6J deltas across regimes)
    Q13.14 full race timeline (+ bounded cross-race comparison)
    Q13.15 deterministic replay (hash-identical)
    Q13.16 MCP verification (bounds + negative controls through the registry)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.performance_regimes import (
    MAX_COMPARE_RACES,
    analyze_performance_regimes,
    compare_performance_regimes,
)

Q13_VERSION = "q13_performance_regimes_v1"

# Real telemetry pairs across seasons/circuits (same pairs as Q12, ordered
# driver_a=reference / driver_b=target to match the deficit convention).
MATRIX = [
    {"season": 2023, "round": 1, "driver_a": "max-verstappen", "driver_b": "sergio-perez"},
    {"season": 2022, "round": 4, "driver_a": "max-verstappen", "driver_b": "sergio-perez"},
    {"season": 2024, "round": 14, "driver_a": "lewis-hamilton", "driver_b": "oscar-piastri"},
    {"season": 2025, "round": 12, "driver_a": "lando-norris", "driver_b": "oscar-piastri"},
]


def run_q13(
    queries: CanonicalQueries,
    races: list[dict[str, Any]] | None = None,
    include_mcp: bool = True,
    include_compare: bool = True,
) -> dict[str, Any]:
    """Run the Q13 regime matrix and return the structured report.

    ``races`` restricts the matrix (used by tests to bound runtime);
    ``include_compare`` toggles the bounded cross-race comparison.
    """
    matrix = races if races is not None else MATRIX
    results: list[dict[str, Any]] = []
    for case in matrix:
        entry: dict[str, Any] = {**case}
        r = analyze_performance_regimes(
            queries, case["season"], case["round"],
            case["driver_a"], case["driver_b"], max_regimes=8)
        entry["status"] = r.get("status")
        entry["reason"] = r.get("reason")
        if r.get("status") != "VALID":
            results.append(entry)
            continue

        regimes = r["regimes"]
        patterns = [g["pattern"] for g in regimes]
        entry["regime_count"] = r["regime_count"]
        entry["comparable_lap_count"] = r["comparable_lap_count"]
        entry["patterns"] = patterns
        entry["slopes"] = [g["slope_s_per_lap"] for g in regimes]
        entry["min_regime_laps_observed"] = min(g["lap_count"] for g in regimes)

        # Q13.1-Q13.3 pattern presence
        entry["has_stable"] = "STABLE" in patterns
        entry["has_widening"] = "WIDENING" in patterns
        entry["has_narrowing"] = "NARROWING" in patterns
        # Q13.4 reversal: slope sign changes across consecutive regimes
        signs = [1 if g["slope_s_per_lap"] > 0 else (-1 if g["slope_s_per_lap"] < 0 else 0)
                 for g in regimes]
        entry["reversal"] = any(
            a * b < 0 for a, b in zip(signs, signs[1:]) if a != 0 and b != 0)

        # Q13.5 genuine change points
        cps = r["change_points"]
        entry["change_point_count"] = len(cps)
        entry["change_points"] = [
            {"transition_lap": c["transition_lap"],
             "previous_pattern": c["previous_pattern"],
             "new_pattern": c["new_pattern"],
             "context_alignment": [
                 {"type": a["type"], "relationship": a["relationship"]}
                 for a in c["context_alignment"]]}
            for c in cps]

        # Q13.6 noise rejection: min-length respected + rejections logged
        entry["rejected_change_points"] = r["rejected_change_points"]
        entry["regime_merges"] = len(r["regime_merges"])

        # Q13.7/Q13.8 stint alignment
        entry["regimes_crossing_stint_boundary"] = sum(
            1 for g in regimes if g["crosses_stint_boundary"])
        entry["stints_spanned"] = [g["stints_spanned"] for g in regimes]

        # Q13.9/Q13.10 telemetry states
        entry["telemetry_available_regimes"] = sum(
            1 for g in regimes if g["telemetry_state"] == "AVAILABLE")
        entry["telemetry_unavailable_regimes"] = sum(
            1 for g in regimes if g["telemetry_state"] == "TELEMETRY_UNAVAILABLE")
        entry["speed_profile_states"] = [g["speed_profile"]["state"] for g in regimes]
        entry["speed_profile_distances"] = [
            g["speed_profile"]["mean_abs_distance_kmh"] for g in regimes]

        # Q13.11 residual transitions
        entry["residuals"] = [
            {"state": g["residual"]["state"],
             "residual_total_s": g["residual"]["residual_total_s"],
             "laps_fused": g["residual"]["laps_fused"]}
            for g in regimes]
        entry["residual_conservation_preserved"] = all(
            g["residual"]["state"] in ("PRESERVED", "INSUFFICIENT_EVIDENCE")
            for g in regimes)

        # Q13.12 hypothesis-state transitions across regimes
        entry["hypothesis_transitions"] = _hypothesis_transitions(regimes)

        # Q13.13 envelope sensitivity transition across regimes
        sens = [(g["regime_index"], g["model_sensitivity"].get("status"),
                 g["model_sensitivity"].get("delta_s")) for g in regimes]
        entry["model_sensitivity"] = sens
        valid_deltas = [d for _i, st, d in sens if st == "VALID" and d is not None]
        entry["sensitivity_varies_across_regimes"] = (
            len(set(valid_deltas)) > 1 if valid_deltas else None)

        # Q13.14 timeline
        entry["timeline_entry_count"] = len(r["race_timeline"])
        entry["unavailable_intervals"] = len(r["unavailable_intervals"])

        # Q13.15 replay
        r2 = analyze_performance_regimes(
            queries, case["season"], case["round"],
            case["driver_a"], case["driver_b"], max_regimes=8)
        entry["replay_identical"] = r2.get("output_hash") == r.get("output_hash")
        entry["output_hash"] = r.get("output_hash")
        results.append(entry)

    report: dict[str, Any] = {
        "benchmark": "Q13_performance_regimes",
        "version": Q13_VERSION,
        "matrix": results,
        "negative_controls": _negative_controls(queries),
    }
    if include_compare and len(matrix) >= 2:
        report["cross_race_comparison"] = compare_performance_regimes(
            queries,
            [(c["season"], c["round"]) for c in matrix[:MAX_COMPARE_RACES]],
            matrix[0]["driver_a"], matrix[0]["driver_b"])
    if include_mcp:
        report["mcp"] = _mcp_verification(queries)
    return report


def _hypothesis_transitions(regimes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hypotheses whose regime summaries changed within one race."""
    if not regimes:
        return []
    out: list[dict[str, Any]] = []
    for h in regimes[0]["hypothesis_evolution"]:
        hid = h["hypothesis_id"]
        seq = []
        for g in regimes:
            s = next((x["summary"] for x in g["hypothesis_evolution"]
                      if x["hypothesis_id"] == hid), None)
            seq.append({"regime_index": g["regime_index"], "summary": s})
        distinct = {s["summary"] for s in seq if s["summary"] is not None}
        if len(distinct) > 1:
            out.append({"hypothesis_id": hid, "sequence": seq})
    return out


def _negative_controls(queries: CanonicalQueries) -> dict[str, Any]:
    nc: dict[str, Any] = {}
    nc["1950"] = analyze_performance_regimes(
        queries, 1950, 1, "giuseppe-farina", "luigi-fagioli").get("status")
    # 2018: lap facts may exist but telemetry does not -> regimes (if any) must
    # all carry telemetry_state TELEMETRY_UNAVAILABLE (never inferred onward).
    r2018 = analyze_performance_regimes(
        queries, 2018, 1, "lewis-hamilton", "sebastian-vettel")
    nc["2018_status"] = r2018.get("status")
    if r2018.get("status") == "VALID":
        nc["2018_all_regimes_telemetry_unavailable"] = all(
            g["telemetry_state"] == "TELEMETRY_UNAVAILABLE" for g in r2018["regimes"])
    nc["missing_driver"] = analyze_performance_regimes(
        queries, 2023, 1, "nobody-here", "max-verstappen").get("status")
    nc["same_driver"] = analyze_performance_regimes(
        queries, 2023, 1, "max-verstappen", "max-verstappen").get("status")
    nc["max_regimes_oob"] = analyze_performance_regimes(
        queries, 2023, 1, "max-verstappen", "sergio-perez", max_regimes=99).get("status")
    nc["min_regime_laps_changed"] = analyze_performance_regimes(
        queries, 2023, 1, "max-verstappen", "sergio-perez", min_regime_laps=4).get("status")
    nc["start_after_end"] = analyze_performance_regimes(
        queries, 2023, 1, "max-verstappen", "sergio-perez",
        start_lap=30, end_lap=10).get("status")
    # narrow window -> too few comparable laps -> INSUFFICIENT_EVIDENCE
    nc["tiny_window"] = analyze_performance_regimes(
        queries, 2023, 1, "max-verstappen", "sergio-perez",
        start_lap=30, end_lap=31).get("status")
    # pair without ingested telemetry -> sensitivity UNAVAILABLE (absent data)
    r_pair = analyze_performance_regimes(
        queries, 2022, 4, "max-verstappen", "valtteri-bottas")
    nc["no_telemetry_pair_status"] = r_pair.get("status")
    if r_pair.get("status") == "VALID":
        nc["no_telemetry_pair_all_unavailable"] = all(
            g["telemetry_state"] == "TELEMETRY_UNAVAILABLE" for g in r_pair["regimes"])
        nc["no_telemetry_pair_sensitivity"] = sorted({
            g["model_sensitivity"].get("status") for g in r_pair["regimes"]})
    return nc


def _mcp_verification(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.tools.contract import ToolError
    from racewise.tools.historical import build_historical_registry

    reg = build_historical_registry(queries)
    name = "analyze_historical_performance_regimes"
    out: dict[str, Any] = {"tool_registered": name in reg._tools}
    if not out["tool_registered"]:
        return out
    r = reg.execute(name, {
        "season": 2022, "round": 4,
        "driver_a": "max-verstappen", "driver_b": "sergio-perez",
        "max_regimes": 6})
    out["registry_status"] = r["output"].get("status")
    out["registry_hash"] = r["output"].get("output_hash")
    base = {"season": 2022, "round": 4,
            "driver_a": "max-verstappen", "driver_b": "sergio-perez"}
    for label, extra in (
        ("max_regimes_99", {"max_regimes": 99}),
        ("min_regime_laps_4", {"min_regime_laps": 4}),
        ("start_after_end", {"start_lap": 30, "end_lap": 10}),
        ("start_lap_0", {"start_lap": 0}),
        ("same_driver", {"driver_b": "max-verstappen"}),
        ("unknown_param", {"bogus": 1}),
    ):
        try:
            reg.execute(name, {**base, **extra})
            out[label] = "ACCEPTED"
        except ToolError as exc:
            out[label] = f"REJECTED: {exc.code}"
    nc_1950 = reg.execute(name, {"season": 1950, "round": 1,
                                 "driver_a": "giuseppe-farina",
                                 "driver_b": "luigi-fagioli"})
    out["1950_registry_status"] = nc_1950["output"].get("status")
    return out


if __name__ == "__main__":  # pragma: no cover
    import json

    from racewise.data.historical.canonical_queries import get_canonical_queries

    print(json.dumps(run_q13(get_canonical_queries()), indent=2, sort_keys=True))
