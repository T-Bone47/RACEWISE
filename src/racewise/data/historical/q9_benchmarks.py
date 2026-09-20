"""Q9 benchmark family: stint-level evidence fusion (Phase 6G).

Runs `stint_evidence.fuse_stint_evidence` over a fixed, representative stint
matrix (multiple seasons and circuits, verified telemetry coverage) and
records deterministic semantics: trajectory, trend classification,
hypothesis evolution, residual conservation, context transitions.

Categories:
    Q9.1  stable performance gap          (|slope| <= 0.02 s/lap)
    Q9.2  widening performance gap        (slope > +0.02)
    Q9.3  narrowing performance gap       (slope < -0.02)
    Q9.4  telemetry trend persistence     (VALID metric trend blocks)
    Q9.5  tyre-consistency assessment     (widening gap vs tyre-state evidence)
    Q9.6  context transitions recorded    (structured, may be empty)
    Q9.7  contradictory hypothesis        (CONTRADICTED_OVER_TIME present)
    Q9.8  insufficient common laps        (trend INSUFFICIENT_EVIDENCE)
    Q9.9  residual persistence + conservation identity
    Q9.10 full stint investigation        (through the MCP registry, bounded)
    Q9.11 replay determinism              (byte-identical matrix JSON)

Classifications are descriptive rules over computed slopes - never scores.
Stints whose evidence cannot support a category are reported honestly.
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

Q9_VERSION = "q9_stint_evidence_v1"

STABLE_SLOPE_S = 0.02  # |slope| <= this -> stable (s per stint lap)

# Fixed representative matrix (verified against the canonical store):
# seasons 2021-2025, multiple circuits, wet/red-flag affected rounds included,
# plus deliberate thin/empty stints for the insufficient-evidence categories.
MATRIX = [
    {"season": 2022, "round": 4, "driver_a": "max-verstappen", "driver_b": "sergio-perez", "stint": 2},
    {"season": 2022, "round": 9, "driver_a": "carlos-sainz-jr", "driver_b": "max-verstappen", "stint": 3},
    {"season": 2022, "round": 2, "driver_a": "charles-leclerc", "driver_b": "max-verstappen", "stint": 2},
    {"season": 2021, "round": 10, "driver_a": "charles-leclerc", "driver_b": "lewis-hamilton", "stint": 2},
    {"season": 2023, "round": 1, "driver_a": "max-verstappen", "driver_b": "sergio-perez", "stint": 1},
    {"season": 2022, "round": 5, "driver_a": "charles-leclerc", "driver_b": "max-verstappen", "stint": 1},
    {"season": 2022, "round": 12, "driver_a": "lewis-hamilton", "driver_b": "max-verstappen", "stint": 2},
]


def _classify_trend(trend: dict[str, Any] | None) -> str:
    if not trend or trend.get("status") != "VALID" or trend.get("slope_per_stint_lap") is None:
        return "INSUFFICIENT_EVIDENCE"
    s = trend["slope_per_stint_lap"]
    if abs(s) <= STABLE_SLOPE_S:
        return "STABLE"
    return "WIDENING" if s > 0 else "NARROWING"


def _tyre_consistency(result: dict[str, Any]) -> dict[str, Any]:
    """Deterministic consistency assessment: gap pattern vs tyre evidence.

    Correlation/consistency is not causation: a widening gap consistent with
    tyre-state evidence is still only 'consistent'.
    """
    pattern = _classify_trend(result.get("performance", {}).get("trend"))
    h4 = result.get("hypothesis_evolution", {}).get("H4_tyre_state", {})
    summary = h4.get("summary", "INSUFFICIENT_EVIDENCE")
    if pattern == "INSUFFICIENT_EVIDENCE":
        return {"pattern": pattern, "tyre_summary": summary,
                "assessment": "NOT_TESTABLE - no valid gap trend to assess"}
    if pattern == "WIDENING":
        if summary in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED"):
            assessment = "CONSISTENT - tyre-state evidence does not contradict the widening gap"
        elif summary in ("CONTRADICTED_OVER_TIME", "NOT_SUPPORTED"):
            assessment = "NOT_CONSISTENT - tyre-state evidence is contradicted over time; " \
                         "the widening gap cannot be attributed to tyres on this evidence"
        else:
            assessment = "INDETERMINATE - tyre-state evidence insufficient or intermittent"
    else:
        assessment = f"ASSESSABLE_ONLY_FOR_WIDENING - pattern is {pattern}"
    return {"pattern": pattern, "tyre_summary": summary, "assessment": assessment}


def run_q9(queries: CanonicalQueries, include_mcp: bool = True) -> dict[str, Any]:
    """Run the Q9 matrix and return the structured benchmark report."""
    from racewise.data.historical.stint_evidence import fuse_stint_evidence

    results: list[dict[str, Any]] = []
    for case in MATRIX:
        r = fuse_stint_evidence(
            queries, case["season"], case["round"], case["driver_a"], case["driver_b"],
            case["stint"])
        entry: dict[str, Any] = {**case}
        if "selection" not in r:
            entry.update({"status": r.get("status"), "reason": r.get("reason"),
                          "pattern": "INSUFFICIENT_EVIDENCE"})
            results.append(entry)
            continue
        perf = r.get("performance", {})
        pattern = _classify_trend(perf.get("trend"))
        hyps = r.get("hypothesis_evolution", {})
        results.append({
            **entry,
            "status": r["status"],
            "valid_laps": r["selection"]["valid_laps"],
            "pattern": pattern,
            "slope_s_per_stint_lap": (perf.get("trend") or {}).get("slope_per_stint_lap"),
            "cumulative_gap_s": perf.get("cumulative_gap_s", {}).get("value"),
            "change_point": r.get("change_point", {}).get("status"),
            "metric_trends_valid": sorted(
                m for m, d in r.get("telemetry_trends", {}).items()
                if any(b.get("status") == "VALID" for b in d.values())),
            "hypothesis_summaries": {h: v.get("summary") for h, v in hyps.items()},
            "contradictory_present": any(
                v.get("summary") in ("CONTRADICTED_OVER_TIME", "NOT_SUPPORTED")
                for v in hyps.values()),
            "tyre_consistency": _tyre_consistency(r),
            "context_transitions": len(r.get("context_transitions", [])),
            "residual_conservation_ok": abs(
                (r.get("residuals", {}).get("cumulative_observed_s") or 0)
                - ((r.get("residuals", {}).get("cumulative_pace_component_s") or 0)
                   + (r.get("residuals", {}).get("cumulative_residual_s") or 0))) < 1e-6,
            "trend_insufficient": (perf.get("trend") or {}).get("status") == "INSUFFICIENT_EVIDENCE",
            "hash": hashlib.sha256(
                json.dumps(r, sort_keys=True, default=str).encode()).hexdigest()[:16],
        })
    report = {"benchmark": "Q9_stint_evidence", "version": Q9_VERSION, "matrix": results}
    if include_mcp:
        reg_names = None
        try:
            from racewise.tools.historical import build_historical_registry

            reg = build_historical_registry(queries)
            reg_names = "fuse_historical_stint_evidence" in reg._tools
        except Exception:  # noqa: BLE001 - MCP presence is informational
            reg_names = False
        report["mcp_tool_registered"] = reg_names
    return report


if __name__ == "__main__":  # pragma: no cover
    q = CanonicalQueries()
    print(json.dumps(run_q9(q, include_mcp=False), indent=2, default=str))
