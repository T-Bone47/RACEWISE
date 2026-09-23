"""Q14 benchmark family: cross-race performance pattern intelligence (6L).

Runs the deterministic cross-race pattern layer over fixed representative
matrices (2022-2025, multiple circuits, real telemetry pairs) and records
measured semantics. A recurring pattern is an observation of repetition
across independent race instances; it is never causation, never a
significance claim, and never a ranking.

Categories:
    Q14.1  cross-race regime extraction (bounded corpus composition)
    Q14.2  repeated structure detection (coarse keys + seed-anchored split)
    Q14.3  context comparison (facets are associations, never causes)
    Q14.4  hypothesis comparison (6F consistency vocabulary per pattern)
    Q14.5  residual comparison (pattern states, never assigned)
    Q14.6  sensitivity comparison (same intervention, model-scoped)
    Q14.7  telemetry limitation behavior (missing stays missing)
    Q14.8  provenance (chains, thresholds, regime refs, no timestamps)
    Q14.9  deterministic hash (replay within/across invocations)
    Q14.10 pattern id stability (identical structural key => same id)
    Q14.11 negative controls (UNAVAILABLE / INVALID / bounds)
    Q14.12 MCP verification (registry + bounds + unknown params)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.performance_patterns import (
    MAX_PATTERNS,
    MAX_RACES,
    analyze_cross_race_performance_patterns,
)

Q14_VERSION = "q14_cross_race_patterns_v1"

# Real telemetry pairs across seasons/circuits (same pairs as Q12/Q13).
MATRIX = [
    {"driver_a": "max-verstappen", "driver_b": "sergio-perez", "seasons": [2022, 2023]},
    {"driver_a": "max-verstappen", "driver_b": "sergio-perez", "seasons": [2023, 2024]},
    {"driver_a": "lewis-hamilton", "driver_b": "oscar-piastri", "seasons": [2024, 2025]},
    {"driver_a": "lando-norris", "driver_b": "oscar-piastri", "seasons": [2025]},
]


def run_q14(
    queries: CanonicalQueries,
    matrix: list[dict[str, Any]] | None = None,
    include_mcp: bool = True,
) -> dict[str, Any]:
    """Run the Q14 cross-race pattern matrix and return the structured report.

    ``matrix`` restricts the cases (used by tests to bound runtime).
    """
    cases = matrix if matrix is not None else MATRIX
    results: list[dict[str, Any]] = []
    for case in cases:
        entry: dict[str, Any] = {**case}
        r = analyze_cross_race_performance_patterns(
            queries, case["driver_a"], case["driver_b"],
            seasons=case.get("seasons"),
            max_races=6, max_patterns=20)
        entry["status"] = r.get("status")
        entry["reason"] = r.get("reason")
        entry["corpus"] = {
            "eligible": r.get("corpus", {}).get("eligible_races"),
            "analyzed": r.get("corpus", {}).get("analyzed_races"),
        }
        entry["signature_count"] = r.get("signature_count")
        entry["structural_group_count"] = r.get("structural_group_count")
        entry["non_recurring_group_count"] = r.get("non_recurring_group_count")
        entry["pattern_count"] = r.get("pattern_count")
        if r.get("status") != "VALID":
            results.append(entry)
            continue

        patterns = r["patterns"] or []

        # Q14.2 repeated structure detection
        entry["recurring_classification_all"] = sorted(
            {p["recurrence_classification"] for p in patterns})
        entry["independent_races_min"] = min(
            p["independent_races"] for p in patterns)
        entry["occurrence_count_max"] = max(
            p["occurrence_count"] for p in patterns)
        entry["split_count"] = len(r.get("pattern_split_log") or [])
        entry["repeat_types"] = sorted({p["repeat_type"] for p in patterns})

        # Q14.3 context comparison (descriptive facets only)
        entry["facet_names"] = sorted({
            f["facet"] for p in patterns
            for f in p["context_summary"]["facets"]})

        # Q14.4 hypothesis comparison
        entry["hypothesis_consistencies"] = sorted({
            agg["consistency"] for p in patterns
            for agg in p["hypothesis_summary"].values()})
        entry["patterns_with_contradictory_hypotheses"] = sum(
            1 for p in patterns
            if any(a["consistency"] in ("CONTRADICTORY", "VARIABLE")
                   for a in p["hypothesis_summary"].values()))

        # Q14.5 residual comparison
        entry["residual_pattern_states"] = sorted({
            p["residual_summary"]["state"] for p in patterns})

        # Q14.6 sensitivity comparison
        entry["sensitivity_states"] = sorted({
            p["sensitivity_summary"]["state"] for p in patterns})
        measured = [p for p in patterns
                    if p["sensitivity_summary"]["state"] == "MEASURED"]
        entry["measured_sensitivity_spreads"] = [
            p["sensitivity_summary"].get("sensitivity_spread_s")
            for p in measured]

        # Q14.7 telemetry limitation behavior
        entry["telemetry_statuses_in_patterns"] = sorted({
            t for p in patterns
            for t in p["telemetry_summary"]["statuses"]})

        # Q14.8 provenance
        entry["provenance_chain"] = r["provenance"]["analytical_chain"]
        entry["provenance_table_count"] = len(r["provenance"]["source_tables"])
        entry["thresholds_documented"] = bool(r["thresholds"])
        entry["generated_at_null"] = all(
            p["provenance"]["generated_at"] is None for p in patterns)

        # Q14.9 deterministic hash (replay)
        r2 = analyze_cross_race_performance_patterns(
            queries, case["driver_a"], case["driver_b"],
            seasons=case.get("seasons"), max_races=6, max_patterns=20)
        entry["replay_identical"] = r2.get("output_hash") == r.get("output_hash")
        entry["output_hash"] = r.get("output_hash")

        results.append(entry)

    report: dict[str, Any] = {
        "benchmark": "Q14_cross_race_patterns",
        "version": Q14_VERSION,
        "matrix": results,
        "negative_controls": _negative_controls(queries),
    }
    if include_mcp:
        report["mcp"] = _mcp_verification(queries)
    return report


def _negative_controls(queries: CanonicalQueries) -> dict[str, Any]:
    nc: dict[str, Any] = {}

    # same driver: the request itself is malformed
    nc["same_driver"] = analyze_cross_race_performance_patterns(
        queries, "max-verstappen", "max-verstappen").get("status")

    # scope with no telemetry-capable sessions: absent data -> UNAVAILABLE
    nc["1950"] = analyze_cross_race_performance_patterns(
        queries, "giuseppe-farina", "luigi-fagioli",
        seasons=[1950]).get("status")
    nc["2018"] = analyze_cross_race_performance_patterns(
        queries, "lewis-hamilton", "sebastian-vettel",
        seasons=[2018]).get("status")

    # driver pair never co-present in the eligible corpus
    nc["pair_absent_from_corpus"] = analyze_cross_race_performance_patterns(
        queries, "giuseppe-farina", "lewis-hamilton",
        seasons=[2023]).get("status")

    # bound violations
    nc["max_races_oob"] = analyze_cross_race_performance_patterns(
        queries, "max-verstappen", "sergio-perez",
        max_races=MAX_RACES + 1).get("status")
    nc["max_races_zero"] = analyze_cross_race_performance_patterns(
        queries, "max-verstappen", "sergio-perez", max_races=0).get("status")
    nc["max_patterns_oob"] = analyze_cross_race_performance_patterns(
        queries, "max-verstappen", "sergio-perez",
        max_patterns=MAX_PATTERNS + 1).get("status")

    # tiny corpus (1 race): recurrence across >= 2 races impossible
    nc["single_race_corpus"] = analyze_cross_race_performance_patterns(
        queries, "max-verstappen", "sergio-perez",
        seasons=[2023], rounds=[5], max_races=1).get("status")
    return nc


def _mcp_verification(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.tools.contract import ToolError
    from racewise.tools.historical import build_historical_registry

    reg = build_historical_registry(queries)
    name = "analyze_cross_race_performance_patterns"
    out: dict[str, Any] = {
        "tool_registered": name in reg._tools,
        "historical_tool_count": len(reg._tools),
    }
    if not out["tool_registered"]:
        return out
    r = reg.execute(name, {
        "driver_a": "max-verstappen", "driver_b": "sergio-perez",
        "seasons": [2023], "max_races": 4})
    out["registry_status"] = r["output"].get("status")
    out["registry_hash"] = r["output"].get("output_hash")
    out["registry_pattern_count"] = r["output"].get("pattern_count")
    base = {"driver_a": "max-verstappen", "driver_b": "sergio-perez"}
    for label, extra in (
        ("max_races_oob", {"max_races": 21}),
        ("max_patterns_oob", {"max_patterns": 51}),
        ("same_driver", {"driver_b": "max-verstappen"}),
        ("seasons_not_list", {"seasons": 2023}),
        ("rounds_not_ints", {"rounds": ["a"]}),
        ("circuit_empty", {"circuit": "  "}),
        ("unknown_param", {"bogus": 1}),
    ):
        try:
            reg.execute(name, {**base, **extra})
            out[label] = "ACCEPTED"
        except ToolError as exc:
            out[label] = f"REJECTED: {exc.code}"
    return out


if __name__ == "__main__":  # pragma: no cover
    import json

    from racewise.data.historical.canonical_queries import get_canonical_queries

    print(json.dumps(run_q14(get_canonical_queries()), indent=2, sort_keys=True))
