"""Phase 6M Q15 benchmark: cross-race hypothesis & evidence intelligence.

Every investigated pattern is a real recurring pattern discovered by the
Phase 6L corpus (Q14 lineage) - none are invented. All expected states are
derived from actual canonical data and asserted as honest semantics
(aggregation rules, contradiction preservation, explicit insufficiency).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.performance_evidence import MAX_OCCURRENCES

Q15_VERSION = "q15_cross_race_evidence_v1"

MATRIX = [
    # (label, driver_a, driver_b, seasons) - same corpus pairs as Q14
    {"label": "ver_per_2022_2023", "driver_a": "max-verstappen",
     "driver_b": "sergio-perez", "seasons": [2022, 2023]},
    {"label": "ver_per_2023_2024", "driver_a": "max-verstappen",
     "driver_b": "sergio-perez", "seasons": [2023, 2024]},
    {"label": "ham_pia_2024_2025", "driver_a": "lewis-hamilton",
     "driver_b": "oscar-piastri", "seasons": [2024, 2025]},
    {"label": "nor_pia_2025", "driver_a": "lando-norris",
     "driver_b": "oscar-piastri", "seasons": [2025]},
]


def _pick_patterns(patterns: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministically select benchmark patterns from real 6L output.

    Selection is by measured evidence content only (never manufactured):
      - most_informative: highest count of occurrence-cells with valid obs
      - most_contradictory: highest count of contradicted lap observations
      - telemetry_poor: pattern whose occurrences carry no telemetry at all
    """
    def _info(p: dict[str, Any]) -> int:
        return sum(1 for o in p["occurrences"]
                   for c in o["hypothesis_counts"].values()
                   if c["valid_observations"] > 0)

    def _contra(p: dict[str, Any]) -> int:
        return sum(1 for o in p["occurrences"]
                   for c in o["hypothesis_counts"].values()
                   if c["contradicted_count"] > 0)

    def _tel(p: dict[str, Any]) -> int:
        return sum(1 for o in p["occurrences"]
                   if o.get("telemetry_status") == "TELEMETRY_AVAILABLE")

    most_info = max(patterns, key=_info)
    most_contra = max(patterns, key=_contra)
    tel_poor = min(patterns, key=_tel)
    return {
        "most_informative": most_info["pattern_id"],
        "most_contradictory": most_contra["pattern_id"],
        "telemetry_poor": tel_poor["pattern_id"],
        "measured": {
            "most_informative_cells": _info(most_info),
            "most_contradictory_laps": _contra(most_contra),
            "telemetry_poor_telemetry_occurrences": _tel(tel_poor),
        },
    }


def run_q15(
    queries: CanonicalQueries,
    matrix: list[dict[str, Any]] | None = None,
    include_mcp: bool = True,
) -> dict[str, Any]:
    """Run the Q15 cross-race evidence matrix and return the structured report.

    ``matrix`` restricts the cases (used by tests to bound runtime).
    """
    from racewise.data.historical.performance_evidence import (
        analyze_cross_race_pattern_evidence,
    )
    from racewise.data.historical.performance_patterns import (
        analyze_cross_race_performance_patterns,
    )

    cases = matrix if matrix is not None else MATRIX
    results: list[dict[str, Any]] = []
    for case in cases:
        entry: dict[str, Any] = {k: v for k, v in case.items()}
        # Q15 scans the same corpus width as the 6L recon (max_races=8): the
        # measured evidence cells concentrate in the later races of each
        # season pair, and a narrower corpus honestly yields an evidence-poor
        # pool (every role would degenerate to the same first pattern).
        pat = analyze_cross_race_performance_patterns(
            queries, case["driver_a"], case["driver_b"],
            seasons=case.get("seasons"), max_races=8, max_patterns=20)
        if pat.get("status") != "VALID" or not pat.get("patterns"):
            entry["status"] = "SKIPPED_NO_PATTERNS"
            entry["reason"] = pat.get("reason")
            results.append(entry)
            continue
        picks = _pick_patterns(pat["patterns"])
        entry["pattern_pool"] = {
            "pattern_count": pat.get("pattern_count"),
            **picks,
        }

        investigations: dict[str, Any] = {}
        for role in ("most_informative", "most_contradictory",
                     "telemetry_poor"):
            inv = analyze_cross_race_pattern_evidence(
                queries, case["driver_a"], case["driver_b"],
                pattern_id=picks[role], seasons=case.get("seasons"),
                max_occurrences=6)
            block: dict[str, Any] = {
                "status": inv.get("status"),
                "pattern_id": picks[role],
            }
            if inv.get("status") == "VALID":
                profiles = inv["hypothesis_profiles"]
                block["aggregate_states"] = {
                    p["hypothesis_id"]: p["aggregate_state"]
                    for p in profiles}
                block["consistency_states"] = {
                    p["hypothesis_id"]: p["evidence_consistency"]
                    for p in profiles}
                block["cross_race_check"] = \
                    inv["cross_race_falsification_check"]["result"]
                block["falsification_statuses"] = {
                    k: v["falsification_status"]
                    for k, v in inv["falsification_summary"].items()}
                block["contradiction_hypotheses"] = \
                    inv["contradiction_summary"]["hypotheses_with_contradictions"]
                block["residual_pattern"] = \
                    inv["residual_summary"]["residual_pattern"]
                block["sensitivity_status"] = \
                    inv["sensitivity_summary"]["status"]
                if inv["sensitivity_summary"]["status"] == "VALID":
                    block["sensitivity_spread_s"] = \
                        inv["sensitivity_summary"]["spread_s"]
                block["context_facet_count"] = \
                    len(inv["context_comparison"])
                block["provenance_chain"] = \
                    inv["provenance"]["analytical_chain"]
                # deterministic replay (Q15.9)
                inv2 = analyze_cross_race_pattern_evidence(
                    queries, case["driver_a"], case["driver_b"],
                    pattern_id=picks[role], seasons=case.get("seasons"),
                    max_occurrences=6)
                block["replay_identical"] = (inv2.get("output_hash")
                                             == inv.get("output_hash"))
                block["output_hash"] = inv.get("output_hash")
            investigations[role] = block
        entry["investigations"] = investigations
        results.append(entry)

    report: dict[str, Any] = {
        "benchmark": "Q15_cross_race_evidence",
        "version": Q15_VERSION,
        "matrix": results,
        "negative_controls": _negative_controls(),
    }
    if include_mcp:
        report["mcp"] = _mcp_verification(queries)
    return report


def _negative_controls() -> dict[str, Any]:
    """Q15.8 negative controls (Section 28 vocabulary).

    Note: some controls require a real corpus scan, so they run against the
    default pair/scope and assert on the explicit status returned.
    """
    from racewise.data.historical.performance_evidence import (
        analyze_cross_race_pattern_evidence,
    )

    nc: dict[str, Any] = {}
    pair = ("max-verstappen", "sergio-perez")

    # same driver: malformed request -> INVALID
    nc["same_driver"] = analyze_cross_race_pattern_evidence(
        None, pair[0], pair[0], "any-pattern").get("status")

    # invalid bound -> INVALID
    nc["max_occurrences_oob"] = analyze_cross_race_pattern_evidence(
        None, pair[0], pair[1], "any-pattern",
        max_occurrences=MAX_OCCURRENCES + 1).get("status")

    # The remaining controls need a live corpus (they are covered by the
    # tool-boundary tests and the API tests):
    #   missing pattern_id      -> UNAVAILABLE (not among recurring patterns)
    #   non-recurring pattern   -> INSUFFICIENT_EVIDENCE
    #   missing driver pair     -> UNAVAILABLE (from the 6L layer)
    #   unavailable telemetry   -> TELEMETRY_UNAVAILABLE / INSUFFICIENT per cell
    nc["deferred_to_tool_and_api_tests"] = [
        "missing_pattern_id", "non_recurring_pattern", "missing_driver_pair",
        "telemetry_unavailable",
    ]
    return nc


def _mcp_verification(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.tools.contract import ToolError
    from racewise.tools.historical import build_historical_registry

    reg = build_historical_registry(queries)
    name = "analyze_cross_race_pattern_evidence"
    out: dict[str, Any] = {
        "tool_registered": name in reg._tools,
        "historical_tool_count": len(reg._tools),
    }
    if not out["tool_registered"]:
        return out
    # negative control through the real boundary (cheap: fails before any
    # corpus scan)
    try:
        reg.execute(name, {"driver_a": "max-verstappen",
                           "driver_b": "sergio-perez",
                           "pattern_id": "does-not-exist",
                           "max_occurrences": 99})
        out["bound_oob_rejected"] = False
    except ToolError as e:
        out["bound_oob_rejected"] = e.code == "invalid_input"
    return out


if __name__ == "__main__":  # pragma: no cover - documentation measurement
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )

    rep = run_q15(get_canonical_queries(), include_mcp=True)
    print(rep)
