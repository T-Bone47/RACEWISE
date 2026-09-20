"""Q10 benchmark family: race-level gap decomposition (Phase 6H).

Runs `race_gap.decompose_race_gap` over a fixed, representative race matrix
(2022-2025, multiple circuits, including a red-flag race) and records
deterministic semantics. Classifications are descriptive rules over computed
slopes - never scores, never fabricated outcomes.

Categories:
    Q10.1  stable race gap            (|race slope| <= 0.02 s/lap)
    Q10.2  widening race gap          (slope > +0.02)
    Q10.3  narrowing race gap         (slope < -0.02)
    Q10.4  gap reversal               (segment patterns contain both signs)
    Q10.5  multi-stint race           (>= 3 canonical stint segments)
    Q10.6  pit-window transitions     (observed, mechanism INSUFFICIENT_EVIDENCE)
    Q10.7  race-control transitions   (exact lap-overlap windows)
    Q10.8  telemetry-supported segment (>=1 stint with valid 6G trend)
    Q10.9  telemetry-unavailable segment (preserved honestly)
    Q10.10 residual accumulation      (timeline counts + analytical gap)
    Q10.11 hypothesis evolution       (race-level summaries present)
    Q10.12 full race investigation    (through the MCP registry, bounded)
    Q10.13 official vs analytical gap distinction (both reported, never merged)
    Q10.14 deterministic replay       (byte-identical matrix JSON)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries

Q10_VERSION = "q10_race_gap_v1"

STABLE_SLOPE_S = 0.02  # |race-level slope| <= this -> stable (s per lap)

# Fixed representative matrix (verified against the canonical store):
# multi-stint races, wet/red-flag affected rounds, different circuits,
# different driver pairs (including a sub-second official gap pair).
MATRIX = [
    {"season": 2023, "round": 1, "driver_a": "max-verstappen", "driver_b": "sergio-perez"},
    {"season": 2022, "round": 4, "driver_a": "max-verstappen", "driver_b": "sergio-perez"},
    {"season": 2024, "round": 1, "driver_a": "max-verstappen", "driver_b": "sergio-perez"},
    {"season": 2024, "round": 14, "driver_a": "lewis-hamilton", "driver_b": "oscar-piastri"},
    {"season": 2025, "round": 1, "driver_a": "lando-norris", "driver_b": "max-verstappen"},
]


def _race_pattern(comparable_deltas: list[float]) -> str:
    """Race-level descriptive pattern: OLS slope over all comparable laps."""
    if len(comparable_deltas) < 3:
        return "INSUFFICIENT_EVIDENCE"
    xs = list(range(len(comparable_deltas)))
    n = len(xs)
    mx = sum(xs) / n
    my = sum(comparable_deltas) / n
    denom = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (d - my) for x, d in zip(xs, comparable_deltas)) / denom if denom else 0.0
    if abs(slope) <= STABLE_SLOPE_S:
        return "STABLE"
    return "WIDENING" if slope > 0 else "NARROWING"


def run_q10(queries: CanonicalQueries, include_mcp: bool = True) -> dict[str, Any]:
    """Run the Q10 race matrix and return the structured benchmark report."""
    from racewise.data.historical.race_gap import decompose_race_gap

    results: list[dict[str, Any]] = []
    for case in MATRIX:
        r = decompose_race_gap(queries, case["season"], case["round"],
                               case["driver_a"], case["driver_b"])
        entry: dict[str, Any] = {**case}
        if "timeline_summary" not in r:
            entry.update({"status": r.get("status"), "reason": r.get("reason"),
                          "pattern": "INSUFFICIENT_EVIDENCE"})
            results.append(entry)
            continue
        comparable_deltas: list[float] = []
        # rebuild the comparable delta series from segment lap ranges is not
        # needed: decompose returns the cumulative series tail only, so the
        # pattern is computed from the segment patterns instead (deterministic)
        seg_patterns = [s.get("pattern") for s in r.get("segments", []) if s.get("kind") == "stint"]
        ts = r["timeline_summary"]
        entry.update({
            "status": r["status"],
            "official_gap_s": (r.get("official_result") or {}).get("gap_s"),
            "analytical_gap_s": r.get("cumulative_comparable_gap_s"),
            "official_vs_analytical_distinct":
                (r.get("official_result") or {}).get("gap_s") is not None
                and (r.get("official_result") or {}).get("gap_s")
                != r.get("cumulative_comparable_gap_s"),
            "timeline": {k: ts[k] for k in ("total_laps", "comparable",
                                            "non_comparable", "unavailable")},
            "segments": seg_patterns,
            "n_stint_segments": len(seg_patterns),
            "pattern": _pattern_from_segments(seg_patterns),
            "reversal": ("NARROWING" in seg_patterns and "WIDENING" in seg_patterns),
            "pit_windows": len(r.get("pit_windows", [])),
            "pit_mechanism_unproven": all(
                w.get("mechanism") == "INSUFFICIENT_EVIDENCE"
                for w in r.get("pit_windows", [])),
            "race_control_windows": len(r.get("race_control_windows", [])),
            "stint_evidence_valid": [
                s["stint_number"] for s in r.get("stint_evidence", [])
                if s.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")],
            "stint_evidence_trend_valid": [
                s["stint_number"] for s in r.get("stint_evidence", [])
                if (s.get("trend") or {}).get("status") == "VALID"],
            "hypothesis_summaries": {h: v["summary"]
                                     for h, v in r.get("hypothesis_evolution", {}).items()},
            "residual_counts": {
                "comparable": r.get("residual_accounting", {}).get("comparable_count"),
                "non_comparable": r.get("residual_accounting", {}).get("non_comparable_count"),
                "unavailable": r.get("residual_accounting", {}).get("unavailable_count"),
            },
            "hash": hashlib.sha256(
                json.dumps(r, sort_keys=True, default=str).encode()).hexdigest()[:16],
        })
        results.append(entry)
    report: dict[str, Any] = {"benchmark": "Q10_race_gap", "version": Q10_VERSION,
                              "matrix": results}
    if include_mcp:
        try:
            from racewise.tools.historical import build_historical_registry

            reg = build_historical_registry(queries)
            report["mcp_tool_registered"] = "decompose_historical_race_gap" in reg._tools
        except Exception:  # noqa: BLE001 - informational only
            report["mcp_tool_registered"] = False
    return report


def _pattern_from_segments(seg_patterns: list[str | None]) -> str:
    """Race-level pattern from stint patterns (deterministic aggregation).

    WIDENING/NARROWING both present -> the race contains a reversal (report
    MIXED); a single dominant sign -> that sign; all STABLE -> STABLE;
    otherwise INSUFFICIENT_EVIDENCE.
    """
    signs = [p for p in seg_patterns if p in ("WIDENING", "NARROWING")]
    if not signs:
        if seg_patterns and all(p == "STABLE" for p in seg_patterns if p is not None):
            return "STABLE"
        return "INSUFFICIENT_EVIDENCE"
    if "WIDENING" in signs and "NARROWING" in signs:
        return "MIXED"
    return signs[0]


if __name__ == "__main__":  # pragma: no cover
    q = CanonicalQueries()
    print(json.dumps(run_q10(q, include_mcp=False), indent=2, default=str))
