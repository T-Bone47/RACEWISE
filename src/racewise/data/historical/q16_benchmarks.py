"""Phase 6N Q16 benchmark: engineering investigation synthesis & decision trace.

Every investigation is run against real canonical races and evidence from
the verified 6E-6M chain - none are invented. Where evidence is sparse the
expected output is INSUFFICIENT_EVIDENCE; where telemetry is unavailable the
state is preserved explicitly; nothing is fabricated to make a hypothesis
appear supported.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.investigation_synthesis import (
    MAX_COUNTERFACTUALS, MAX_EVIDENCE_ITEMS,
)
from racewise.data.historical.performance_patterns import _hash_obj

Q16_VERSION = "q16_engineering_investigation_v1"

# Deterministic golden investigations over representative established
# cases from previous phases (Q13/Q14/Q15 lineage).
GOLDENS: list[dict[str, Any]] = [
    {"label": "GOLDEN_01_lap_performance",
     "question_type": "LAP_PERFORMANCE",
     "driver_a": "max-verstappen", "driver_b": "sergio-perez",
     "season": 2023, "round": 1, "lap_number": 6},
    {"label": "GOLDEN_02_stint_performance",
     "question_type": "STINT_PERFORMANCE",
     "driver_a": "max-verstappen", "driver_b": "sergio-perez",
     "season": 2023, "round": 1, "stint_number": 1},
    {"label": "GOLDEN_03_race_gap",
     "question_type": "RACE_GAP",
     "driver_a": "max-verstappen", "driver_b": "sergio-perez",
     "season": 2024, "round": 14},
    {"label": "GOLDEN_04_performance_regime",
     "question_type": "PERFORMANCE_REGIME",
     "driver_a": "max-verstappen", "driver_b": "sergio-perez",
     "season": 2022, "round": 4},
    {"label": "GOLDEN_05_hypothesis_evaluation",
     "question_type": "HYPOTHESIS_EVALUATION",
     "driver_a": "max-verstappen", "driver_b": "sergio-perez",
     "season": 2023, "round": 1, "lap_number": 11},
    # pattern_id is discovered from the real 6L corpus at run time, scanned
    # at the same default corpus scope as the 6N collector (see
    # _discover_pattern); season/round anchor the question framing
    {"label": "GOLDEN_06_cross_race_pattern",
     "question_type": "CROSS_RACE_PATTERN",
     "driver_a": "max-verstappen", "driver_b": "sergio-perez",
     "season": 2023, "round": 1,
     "discover_pattern": True},
    {"label": "GOLDEN_07_counterfactual_eligibility",
     "question_type": "COUNTERFACTUAL_ELIGIBILITY",
     "driver_a": "max-verstappen", "driver_b": "sergio-perez",
     "season": 2023, "round": 1, "stint_number": 1},
    # telemetry-poor scope: honest INSUFFICIENT_EVIDENCE / NOT_TESTABLE
    {"label": "GOLDEN_08_telemetry_poor_race_gap",
     "question_type": "RACE_GAP",
     "driver_a": "nino-farina", "driver_b": "juan-manuel-fangio",
     "season": 1950, "round": 1},
]


def _discover_pattern(queries: CanonicalQueries, case: dict[str, Any]) -> dict[str, Any]:
    """Pick the most evidence-informative real 6L pattern (Q15 policy).

    Uses the SAME default corpus scope as the 6N collector (seasons=None,
    max_races=8): 6L pattern ids are corpus-scope-dependent, so discovery
    and collection must scan identically or the id will not resolve.
    """
    from racewise.data.historical.performance_patterns import (
        analyze_cross_race_performance_patterns,
    )

    pat = analyze_cross_race_performance_patterns(
        queries, case["driver_a"], case["driver_b"],
        seasons=None, max_races=8, max_patterns=20)
    if pat.get("status") != "VALID" or not pat.get("patterns"):
        return {"pattern_id": None, "reason": pat.get("reason"),
                "pattern_count": pat.get("pattern_count", 0)}

    def _info(p: dict[str, Any]) -> int:
        return sum(1 for o in p["occurrences"]
                   for c in o["hypothesis_counts"].values()
                   if c["valid_observations"] > 0)

    best = max(pat["patterns"], key=_info)
    return {"pattern_id": best["pattern_id"],
            "pattern_count": pat.get("pattern_count"),
            "measured_informative_cells": _info(best)}


def _investigate(queries: CanonicalQueries, case: dict[str, Any],
                 pattern_id: str | None) -> dict[str, Any]:
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    return run_engineering_investigation(
        queries,
        question_type=case["question_type"],
        driver_a=case["driver_a"], driver_b=case["driver_b"],
        season=case["season"], round_num=case["round"],
        lap_number=case.get("lap_number"),
        stint_number=case.get("stint_number"),
        pattern_id=pattern_id,
    )


def _summarize(inv: dict[str, Any]) -> dict[str, Any]:
    """Evidence-state summary of one investigation (no ranking)."""
    block: dict[str, Any] = {
        "status": inv.get("status"),
        "reason": inv.get("reason"),
        "evidence_count": len(inv.get("evidence_ledger", [])),
        "conclusion_state": (inv.get("synthesis") or {}).get("conclusion_state"),
        "hypothesis_states": {
            h: v["aggregate_state"]
            for h, v in (inv.get("hypothesis_evaluations") or {}).items()},
        "gate": {
            "any_unresolved_contradictions":
                (inv.get("falsification_gate") or {})
                .get("any_unresolved_contradictions"),
            "establishable": (inv.get("falsification_gate") or {})
            .get("establishable_hypotheses", []),
        },
        "conflict_count": len(inv.get("evidence_conflicts", [])),
        "counterfactuals": [
            {"kind": c["kind"],
             "delta_s": c.get("delta_s"), "claim_class": c.get("claim_class")}
            for c in inv.get("executed_counterfactuals", [])],
        "candidate_states": {
            c["kind"]: c["status"]
            for c in inv.get("counterfactual_candidates", [])},
        "trace_count": len(inv.get("decision_trace", [])),
        "output_hash": inv.get("output_hash"),
    }
    if inv.get("status") != "VALID":
        block["evidence_count"] = 0
        block["conclusion_state"] = None
        block["hypothesis_states"] = {}
        block["gate"] = None
        block["conflict_count"] = 0
        block["counterfactuals"] = []
        block["candidate_states"] = {}
        block["trace_count"] = 0
    return block


def run_q16(
    queries: CanonicalQueries,
    goldens: list[dict[str, Any]] | None = None,
    include_mcp: bool = True,
) -> dict[str, Any]:
    """Run the Q16 engineering investigation matrix and return the report.

    ``goldens`` restricts the cases (used by tests to bound runtime).
    """
    results: list[dict[str, Any]] = []
    for case in (goldens if goldens is not None else GOLDENS):
        entry: dict[str, Any] = {
            "label": case["label"],
            "question_type": case["question_type"],
            "season": case["season"], "round": case["round"],
            "driver_a": case["driver_a"], "driver_b": case["driver_b"],
        }
        t0 = time.perf_counter()
        pattern_id: str | None = case.get("pattern_id")
        if case.get("discover_pattern"):
            disc = _discover_pattern(queries, case)
            entry["pattern_discovery"] = disc
            pattern_id = disc["pattern_id"]
            if pattern_id is None:
                entry["status"] = "SKIPPED_NO_PATTERNS"
                entry["reason"] = disc.get("reason")
                results.append(entry)
                continue
        inv = _investigate(queries, case, pattern_id)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)
        entry["elapsed_ms"] = elapsed_ms
        entry["input_hash"] = _hash_obj({
            "question_type": case["question_type"],
            "driver_a": case["driver_a"], "driver_b": case["driver_b"],
            "season": case["season"], "round": case["round"],
            "lap_number": case.get("lap_number"),
            "stint_number": case.get("stint_number"),
            "pattern_id": pattern_id,
        })
        entry.update(_summarize(inv))
        # deterministic replay (Q16 core invariant)
        inv2 = _investigate(queries, case, pattern_id)
        entry["replay_identical"] = (inv2.get("output_hash")
                                     == inv.get("output_hash"))
        results.append(entry)

    timings = sorted(r["elapsed_ms"] for r in results
                     if "elapsed_ms" in r)
    report: dict[str, Any] = {
        "benchmark": "Q16_engineering_investigation",
        "version": Q16_VERSION,
        "bounds": {
            "max_evidence_items": MAX_EVIDENCE_ITEMS,
            "max_counterfactuals": MAX_COUNTERFACTUALS,
        },
        "matrix": results,
        "performance": {
            "p50_ms": timings[len(timings) // 2] if timings else None,
            "p95_ms": timings[min(len(timings) - 1,
                                  int(len(timings) * 0.95))] if timings else None,
            "max_ms": max(timings) if timings else None,
        },
        "negative_controls": _negative_controls(queries),
    }
    if include_mcp:
        report["mcp"] = _mcp_verification(queries)
    return report


def _negative_controls(queries: CanonicalQueries) -> dict[str, Any]:
    """Q16 negative controls (Section 39 vocabulary). No silent fallback."""
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    nc: dict[str, Any] = {}

    def status_of(**kw: Any) -> str:
        return run_engineering_investigation(queries, **kw).get("status", "")

    # (run_engineering_investigation spells the parameter round_num)

    # malformed request -> INVALID
    nc["same_driver"] = status_of(
        question_type="RACE_GAP", driver_a="max-verstappen",
        driver_b="max-verstappen", season=2023, round_num=1)
    nc["unknown_question_type"] = status_of(
        question_type="FREE_FORM_VIBES", driver_a="max-verstappen",
        driver_b="sergio-perez", season=2023, round_num=1)
    nc["season_below_bounds"] = status_of(
        question_type="RACE_GAP", driver_a="max-verstappen",
        driver_b="sergio-perez", season=1949, round_num=1)
    nc["round_above_bounds"] = status_of(
        question_type="RACE_GAP", driver_a="max-verstappen",
        driver_b="sergio-perez", season=2023, round_num=100)
    nc["max_evidence_items_oob"] = status_of(
        question_type="RACE_GAP", driver_a="max-verstappen",
        driver_b="sergio-perez", season=2023, round_num=1,
        max_evidence_items=MAX_EVIDENCE_ITEMS + 1)
    nc["missing_pattern_id"] = status_of(
        question_type="CROSS_RACE_PATTERN", driver_a="max-verstappen",
        driver_b="sergio-perez", season=2023, round_num=1)
    # data absent -> UNAVAILABLE (never silently broadened)
    nc["missing_race"] = status_of(
        question_type="RACE_GAP", driver_a="max-verstappen",
        driver_b="sergio-perez", season=2050, round_num=1)
    # a requested but nonexistent pattern: the investigation still runs
    # (framing VALID) but collection preserves UNAVAILABLE and the
    # conclusion is UNAVAILABLE - never a silently broadened query
    inv_bad_pid = run_engineering_investigation(
        queries, question_type="CROSS_RACE_PATTERN",
        driver_a="max-verstappen", driver_b="sergio-perez",
        season=2023, round_num=1, pattern_id="does-not-exist")
    nc["unknown_pattern_id_collection"] = (inv_bad_pid.get("collection")
                                           or {}).get("status")
    nc["unknown_pattern_id_conclusion"] = \
        (inv_bad_pid.get("synthesis") or {}).get("conclusion_state")
    nc["unknown_pattern_id_evidence"] = len(
        inv_bad_pid.get("evidence_ledger") or [])
    nc["lap_beyond_race"] = status_of(
        question_type="LAP_PERFORMANCE", driver_a="max-verstappen",
        driver_b="sergio-perez", season=2023, round_num=1, lap_number=999)

    # counterfactual negative controls: the reused 6I gates must hold
    nc["counterfactual"] = _counterfactual_negatives(queries)
    return nc


def _counterfactual_negatives(queries: CanonicalQueries) -> dict[str, Any]:
    """6N refuses race-level extrapolation; 6I refuses non-speed signals."""
    from racewise.data.historical.counterfactual import (
        simulate_telemetry_counterfactual,
    )
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    out: dict[str, Any] = {}
    # scope WITHOUT lap/stint: the only candidate is structurally ineligible
    inv = run_engineering_investigation(
        queries, question_type="COUNTERFACTUAL_ELIGIBILITY",
        driver_a="max-verstappen", driver_b="sergio-perez",
        season=2023, round_num=1)
    cands = inv.get("counterfactual_candidates", [])
    out["race_level_structurally_ineligible"] = bool(cands) and all(
        c["status"] == "INELIGIBLE" for c in cands)

    # scope WITH a stint: the only candidate kind is the 6I stint model
    inv2 = run_engineering_investigation(
        queries, question_type="COUNTERFACTUAL_ELIGIBILITY",
        driver_a="max-verstappen", driver_b="sergio-perez",
        season=2023, round_num=1, stint_number=1)
    cands2 = inv2.get("counterfactual_candidates", [])
    out["stint_scope_kind_is_speed_profile"] = bool(cands2) and all(
        c["kind"] == "STINT_SPEED_PROFILE" for c in cands2)

    # the reused 6I simulator still refuses non-speed interventions
    cf = simulate_telemetry_counterfactual(
        queries, 2023, 1, "max-verstappen", 6, "throttle",
        "REMOVE_DEFICIT", 0.5, reference_driver="sergio-perez",
        session_type="RACE")
    out["non_speed_refused_by_6i"] = (
        cf is not None and cf.get("status") == "UNSUPPORTED")
    return out


def _mcp_verification(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.tools.contract import ToolError
    from racewise.tools.historical import build_historical_registry

    reg = build_historical_registry(queries)
    name = "run_engineering_investigation"
    out: dict[str, Any] = {
        "tool_registered": name in reg._tools,
        "historical_tool_count": len(reg._tools),
    }
    if not out["tool_registered"]:
        return out
    # negative control through the real boundary (fails before corpus work)
    try:
        reg.execute(name, {"question_type": "RACE_GAP",
                           "driver_a": "max-verstappen",
                           "driver_b": "max-verstappen",
                           "season": 2023, "round": 1})
        out["same_driver_rejected"] = False
    except ToolError as e:
        out["same_driver_rejected"] = e.code == "invalid_input"
    return out


if __name__ == "__main__":  # pragma: no cover - documentation measurement
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )

    rep = run_q16(get_canonical_queries(), include_mcp=True)
    print(rep)
