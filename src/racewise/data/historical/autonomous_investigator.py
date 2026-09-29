"""Phase 6T: autonomous engineering investigation orchestrator.

Drives a natural-language engineering question from intake to a
replayable, provenance-bound engineering answer by orchestrating the
existing deterministic Phase 6E→6S chain — never replacing it.

Architecture contract (docs/PHASE_6T_ARCHITECTURE.md):
- The deterministic engine (``run_engineering_investigation``) remains the
  only authority for data, calculations, evidence, hypothesis states,
  counterfactuals, provenance and replay. The orchestrator chooses
  whether/when to invoke it, never what it returns.
- Every autonomous decision is a pure function of declared inputs
  (question text, canonical context, catalog facts, prior tool results)
  with a fixed policy version, appended to a decision trace.
- Lifecycle: CREATED → QUESTION_PARSED → CONTEXT_RESOLVED → DATA_CHECKED →
  HYPOTHESES_SELECTED → EVIDENCE_PLANNED → EVIDENCE_COLLECTING →
  HYPOTHESES_EVALUATED → FALSIFICATION → COUNTERFACTUAL_CHECK →
  SYNTHESIS → VERIFICATION → COMPLETED, with closed terminal failure
  states. Failures are never hidden and never silently downgraded.
- Question text is DATA: instruction-like content is quarantined at
  intake and cannot redirect the pipeline.
- Autonomous orchestration and deterministic engine results are labelled
  distinctly in the trace (ORCHESTRATOR:* reasons vs engine trace).
"""
from __future__ import annotations

import time
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.performance_patterns import (
    _hash_obj, analyze_cross_race_performance_patterns,
)
from racewise.data.historical.question_intake import (
    INTAKE_INVALID, INTAKE_PARSED, INTAKE_UNRESOLVED, INTAKE_UNSUPPORTED,
    parse_question,
)

ANALYSIS = "phase_6t_autonomous_investigation"
ORCHESTRATOR_VERSION = "6t_orchestrator_v1"
POLICY_VERSION = "6t_policy_v1"

# ---------------------------------------------------------------------------
# closed vocabularies
# ---------------------------------------------------------------------------

LIFECYCLE = (
    "CREATED", "QUESTION_PARSED", "CONTEXT_RESOLVED", "DATA_CHECKED",
    "HYPOTHESES_SELECTED", "EVIDENCE_PLANNED", "EVIDENCE_COLLECTING",
    "HYPOTHESES_EVALUATED", "FALSIFICATION", "COUNTERFACTUAL_CHECK",
    "SYNTHESIS", "VERIFICATION", "COMPLETED",
)

FAILURE_STATES = (
    "INVALID_QUESTION", "CONTEXT_UNRESOLVED", "DATA_UNAVAILABLE",
    "INSUFFICIENT_EVIDENCE", "TOOL_FAILURE", "MODEL_FAILURE",
    "VERIFICATION_FAILURE", "BUDGET_EXHAUSTED", "UNSUPPORTED_QUESTION",
)

DECISION_TYPES = (
    "PARSE_QUESTION", "RESOLVE_CONTEXT", "CHECK_DATA", "SELECT_HYPOTHESES",
    "PLAN_EVIDENCE", "SELECT_TOOL", "SKIP_TOOL", "REQUEST_MORE_EVIDENCE",
    "RUN_COUNTERFACTUAL", "STOP_INVESTIGATION", "SYNTHESIZE", "VERIFY",
)

# per-facet data requirements per engine question type (canonical catalog
# availability columns; telemetry is advisory — its absence degrades
# hypothesis coverage honestly inside the engine instead of blocking).
DATA_REQUIREMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "LAP_PERFORMANCE": (("laps", "REQUIRED"), ("results", "ADVISORY"),
                        ("telemetry", "ADVISORY"), ("weather", "ADVISORY"),
                        ("race_control", "ADVISORY"), ("pit_stops", "ADVISORY")),
    "STINT_PERFORMANCE": (("laps", "REQUIRED"), ("stints", "REQUIRED"),
                          ("telemetry", "ADVISORY"), ("weather", "ADVISORY"),
                          ("pit_stops", "ADVISORY")),
    "RACE_GAP": (("results", "REQUIRED"), ("laps", "REQUIRED"),
                 ("pit_stops", "ADVISORY"), ("weather", "ADVISORY"),
                 ("race_control", "ADVISORY")),
    "PERFORMANCE_REGIME": (("laps", "REQUIRED"), ("results", "REQUIRED"),
                           ("telemetry", "ADVISORY")),
    "CROSS_RACE_PATTERN": (("laps", "REQUIRED"), ("results", "REQUIRED"),
                           ("telemetry", "ADVISORY")),
    "HYPOTHESIS_EVALUATION": (("laps", "REQUIRED"), ("telemetry", "ADVISORY")),
    "COUNTERFACTUAL_ELIGIBILITY": (("laps", "REQUIRED"),
                                   ("telemetry", "ADVISORY")),
}
QUALIFYING_DATA_REQUIREMENTS: tuple[tuple[str, str], ...] = (
    ("laps", "REQUIRED"), ("qualifying", "ADVISORY"),
)

# Engine hypothesis ids (subset selection only; states are engine-decided).
HYPOTHESIS_IDS = (
    "H1_corner_speed", "H2_throttle", "H3_braking", "H4_tyre_state",
    "H5_race_control", "H6_drs",
)

BUDGET_DEFAULTS: dict[str, int] = {
    "max_tool_calls": 60,
    "max_runtime_ms": 120000,
    "max_counterfactuals": 2,
    "max_cross_race_scans": 2,
    "max_memory_neighbors": 2,  # both ±1-season neighbors = the 6S pool
}
BUDGET_BOUNDS: dict[str, tuple[int, int]] = {
    "max_tool_calls": (1, 200),
    "max_runtime_ms": (1000, 600000),
    "max_counterfactuals": (0, 2),
    "max_cross_race_scans": (0, 4),
    "max_memory_neighbors": (0, 2),
}

# Orchestration decisions that consume the tool-call budget.
_TOOL_DECISIONS = {"SELECT_TOOL", "REQUEST_MORE_EVIDENCE", "RUN_COUNTERFACTUAL"}


class AutonomousInvestigationError(Exception):
    """Reserved for future control-flow needs; the orchestrator returns
    failure states in-band instead of raising."""


def _av(col: Optional[str]) -> str:
    return str(col) if col else "UNAVAILABLE"


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

StageCallback = Any  # Callable[[dict[str, Any]], None]


def run_autonomous_investigation(
    queries: CanonicalQueries,
    question_text: str,
    context: Optional[dict[str, Any]] = None,
    constraints: Optional[dict[str, Any]] = None,
    on_stage: Optional[StageCallback] = None,
) -> dict[str, Any]:
    """Run one autonomous investigation from natural language to answer.

    Deterministic orchestration: the same question/context/constraints
    against the same canonical store produce the same run (identical
    decision trace and, where the engine is deterministic, identical
    result). Runtime fields (timings) are reported but excluded from the
    run identity hash.

    ``on_stage`` (optional) is invoked synchronously with each stage
    entry as it is appended — the real stage progression, used by the
    SSE streaming endpoint. It receives no runtime secret and cannot
    influence the run.
    """
    started = time.perf_counter()
    run: dict[str, Any] = {
        "analysis": ANALYSIS,
        "version": ORCHESTRATOR_VERSION,
        "policy_version": POLICY_VERSION,
        "question_text": question_text if isinstance(question_text, str) else None,
        "context": dict(context or {}),
        # the original (pre-resolution) intake context, kept verbatim so
        # replay/continue re-execute from the identical declared inputs
        "intake_context": dict(context or {}),
        "stage_ledger": [],
        "decision_trace": [],
        "budget": {},
        "tool_calls_consumed": 0,
    }
    ctx: dict[str, Any] = {"tool_calls": 0}

    def stage(name: str, status: str, detail: Optional[str] = None) -> None:
        entry = {"stage": name, "status": status, "detail": detail}
        run["stage_ledger"].append(entry)
        if on_stage is not None:
            try:
                on_stage(dict(entry))
            except Exception:  # noqa: BLE001 — a broken listener must not
                pass         # influence the investigation

    def decision(
        decision_type: str, reason: str, selected_action: str,
        input_state: Optional[dict[str, Any]] = None,
        tool: Optional[str] = None,
        tool_result_hash: Optional[str] = None,
        evidence_refs: Optional[list[str]] = None,
        output_state: Optional[dict[str, Any]] = None,
        counts_as_tool: bool = False,
    ) -> str:
        did = f"D{len(run['decision_trace']) + 1:03d}"
        run["decision_trace"].append({
            "decision_id": did,
            "order": len(run["decision_trace"]) + 1,
            "decision_type": decision_type,
            "input_state": input_state or {},
            "reason": f"ORCHESTRATOR: {reason}",
            "selected_action": selected_action,
            "tool": tool,
            "tool_result_hash": tool_result_hash,
            "evidence_refs": evidence_refs or [],
            "output_state": output_state or {},
        })
        if counts_as_tool and decision_type in _TOOL_DECISIONS:
            ctx["tool_calls"] += 1
            run["tool_calls_consumed"] = ctx["tool_calls"]
        return did

    def finish(status: str, reason: str, failed_stage: Optional[str],
               extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        run["status"] = status
        run["reason"] = reason
        run["failed_stage"] = failed_stage
        if status in FAILURE_STATES:
            stage("FAILED", status, reason)
            decision("STOP_INVESTIGATION", reason, f"terminal state {status}",
                     output_state={"failed_stage": failed_stage,
                                   "failure_state": status})
        _finalize(run, queries, started)
        if extra:
            run.update(extra)
        return run

    # --- 0 CREATED --------------------------------------------------------
    stage("CREATED", "COMPLETED", "orchestrator started")

    # --- budget validation --------------------------------------------------
    budget = dict(BUDGET_DEFAULTS)
    for key, value in (constraints or {}).items():
        if key not in budget:
            return finish("INVALID_QUESTION",
                          f"unknown budget constraint '{key}' "
                          f"(supported: {sorted(BUDGET_DEFAULTS)})",
                          "CREATED")
        lo, hi = BUDGET_BOUNDS[key]
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return finish("INVALID_QUESTION",
                          f"budget constraint '{key}' must be an integer",
                          "CREATED")
        if not lo <= iv <= hi:
            return finish("INVALID_QUESTION",
                          f"budget constraint '{key}' out of bounds "
                          f"[{lo}, {hi}]", "CREATED")
        budget[key] = iv
    run["budget"] = {"limits": dict(budget)}

    def budget_snapshot() -> dict[str, Any]:
        consumed = {"tool_calls": ctx["tool_calls"]}
        return {
            "limits": dict(budget),
            "consumed": consumed,
            "remaining": {"tool_calls": max(0, budget["max_tool_calls"]
                                            - ctx["tool_calls"])},
        }

    def require_tool_budget(what: str) -> Optional[str]:
        """Returns a BUDGET_EXHAUSTED reason when one more tool call would
        exceed the bound, else None."""
        if ctx["tool_calls"] + 1 > budget["max_tool_calls"]:
            return (f"max_tool_calls={budget['max_tool_calls']} reached "
                    f"before {what}")
        return None

    # --- 1 QUESTION_PARSED ------------------------------------------------
    stage("QUESTION_PARSED", "IN_PROGRESS")
    try:
        parsed = parse_question(queries, question_text, context,
                                (constraints or {}))
    except Exception as exc:  # noqa: BLE001 — honest TOOL_FAILURE contract
        return finish("TOOL_FAILURE", f"intake failed: {exc}",
                      "QUESTION_PARSED")
    run["question"] = {
        "text": parsed.get("question_text"),
        "status": parsed.get("status"),
        "reason": parsed.get("reason"),
        "missing": parsed.get("missing"),
        "candidates": parsed.get("candidates"),
        "supported_question_types": parsed.get("supported_question_types"),
        "question_object_hash": parsed.get("question_object_hash"),
        "provenance": parsed.get("provenance"),
    }
    if parsed.get("injection_scan"):
        run["injection_scan"] = parsed["injection_scan"]
    if parsed.get("status") == INTAKE_INVALID:
        return finish("INVALID_QUESTION", parsed.get("reason", ""),
                      "QUESTION_PARSED")
    if parsed.get("status") == INTAKE_UNSUPPORTED:
        return finish("UNSUPPORTED_QUESTION", parsed.get("reason", ""),
                      "QUESTION_PARSED")
    if parsed.get("status") != INTAKE_PARSED:
        decision("PARSE_QUESTION",
                 f"intake could not resolve critical context: "
                 f"{parsed.get('reason')}",
                 "stop with CONTEXT_UNRESOLVED",
                 input_state={"question_text": run["question"]["text"]},
                 output_state={"missing": parsed.get("missing"),
                               "candidates": parsed.get("candidates")})
        return finish("CONTEXT_UNRESOLVED", parsed.get("reason", ""),
                      "QUESTION_PARSED",
                      extra={"clarification": {
                          "missing": parsed.get("missing"),
                          "candidates": parsed.get("candidates"),
                          "reason": parsed.get("reason")}})
    decision("PARSE_QUESTION",
             "deterministic intake resolved the question into the canonical "
             "object",
             "proceed to context resolution",
             input_state={"question_text": run["question"]["text"]},
             output_state={
                 "question_type": parsed["question_type"],
                 "season": parsed["season"], "round": parsed["round"],
                 "driver_a": parsed["driver_a"], "driver_b": parsed["driver_b"],
                 "lap_number": parsed["lap_number"],
                 "stint_number": parsed["stint_number"],
                 "session_type": parsed["session_type"],
             })
    stage("QUESTION_PARSED", "COMPLETED")
    run["question"].update({
        "question_type": parsed["question_type"],
        "scope": {k: parsed[k] for k in
                  ("season", "round", "session_type", "driver_a", "driver_b",
                   "lap_number", "stint_number", "pattern_id")},
    })

    # --- 2 CONTEXT_RESOLVED ------------------------------------------------
    stage("CONTEXT_RESOLVED", "IN_PROGRESS")
    season_i, round_i = int(parsed["season"]), int(parsed["round"])
    race = queries.resolve_race(season_i, round_num=round_i)
    if race is None:
        return finish("DATA_UNAVAILABLE",
                      f"no canonical race for {season_i} R{round_i}",
                      "CONTEXT_RESOLVED")
    ctx["resolved_context"] = {
        "season": season_i, "round": round_i,
        "grand_prix": race.get("grand_prix"),
        "race_name": race.get("race_name") or race.get("grand_prix"),
        "session_type": parsed["session_type"],
        "driver_a": parsed["driver_a"], "driver_b": parsed["driver_b"],
        "lap_number": parsed["lap_number"],
        "stint_number": parsed["stint_number"],
        "pattern_id": parsed["pattern_id"],
    }
    run["context"] = ctx["resolved_context"]
    decision("RESOLVE_CONTEXT",
             "scope resolved against canonical race identity",
             "proceed to data availability check",
             output_state={"grand_prix": race.get("grand_prix")})
    stage("CONTEXT_RESOLVED", "COMPLETED")

    # --- 3 DATA_CHECKED (hard gate; no expensive tool runs before this) ----
    stage("DATA_CHECKED", "IN_PROGRESS")
    availability = queries.get_availability(season_i, round_i,
                                            parsed["session_type"])
    if availability is None:
        return finish("DATA_UNAVAILABLE",
                      f"session {season_i} R{round_i} "
                      f"{parsed['session_type']} is not in the canonical "
                      "catalog", "DATA_CHECKED")
    requirements = (QUALIFYING_DATA_REQUIREMENTS
                    if parsed["session_type"] == "QUALIFYING"
                    else DATA_REQUIREMENTS[parsed["question_type"]])
    facets: dict[str, dict[str, Any]] = {}
    blocking: list[str] = []
    for facet, need in requirements:
        col = availability.get(f"{facet}_availability")
        state = _av(col)
        facets[facet] = {"requirement": need, "availability": state}
        if need == "REQUIRED" and state == "UNAVAILABLE":
            blocking.append(facet)
    if blocking:
        return finish("DATA_UNAVAILABLE",
                      f"required data unavailable for {season_i} R{round_i} "
                      f"{parsed['session_type']}: {blocking}",
                      "DATA_CHECKED",
                      extra={"data_availability": facets})
    decision("CHECK_DATA",
             "catalog availability consulted before any expensive tool",
             "proceed to hypothesis selection",
             input_state={"requirements": {f: v["requirement"]
                                           for f, v in facets.items()}},
             output_state={"facets": {f: v["availability"]
                                      for f, v in facets.items()}})
    stage("DATA_CHECKED", "COMPLETED")
    run["data_availability"] = facets

    # --- 4 HYPOTHESES_SELECTED ---------------------------------------------
    stage("HYPOTHESES_SELECTED", "IN_PROGRESS")
    requested = parsed.get("hypotheses_requested")
    if requested:
        subset = [h for h in HYPOTHESIS_IDS if h in requested]
        why_selected = ("question text names specific mechanisms "
                        f"({', '.join(subset)})")
        why_not = {h: "not named by the question text" for h in HYPOTHESIS_IDS
                   if h not in subset}
    else:
        subset = []
        why_selected = ("no mechanisms named; the engine evaluates all six "
                        "canonical hypotheses")
        why_not = {}
    decision("SELECT_HYPOTHESES", why_selected,
             "engine evaluates the selected subset (or all six)",
             input_state={"named_in_text": requested},
             output_state={"selected": subset or list(HYPOTHESIS_IDS),
                           "why_not_selected": why_not})
    stage("HYPOTHESES_SELECTED", "COMPLETED")
    run["hypothesis_selection"] = {
        "selected": subset or list(HYPOTHESIS_IDS),
        "why_selected": why_selected,
        "why_not_selected": why_not,
        "policy": ("the orchestrator only narrows the evaluation scope; "
                   "all hypothesis states are decided by the engine"),
    }

    # --- 5 EVIDENCE_PLANNED --------------------------------------------------
    stage("EVIDENCE_PLANNED", "IN_PROGRESS")
    if parsed["question_type"] == "CROSS_RACE_PATTERN":
        pattern_id = parsed["pattern_id"]
        discovery_scan: Optional[dict[str, Any]] = None
        if pattern_id is None and budget["max_cross_race_scans"] > 0:
            budget_err = require_tool_budget("pattern discovery")
            if budget_err:
                return finish("BUDGET_EXHAUSTED", budget_err,
                              "EVIDENCE_PLANNED")
            decision("SELECT_TOOL",
                     "pattern id not supplied; run the bounded deterministic "
                     "cross-race pattern discovery to rediscover candidate "
                     "patterns for this pair",
                     "analyze_cross_race_performance_patterns",
                     tool="analyze_cross_race_performance_patterns",
                     counts_as_tool=True)
            scan_seasons = (parsed.get("pattern_seasons")
                            or sorted({season_i, season_i + 1}
                                      & set(range(1950, 2028))))
            t0 = time.perf_counter()
            disc = analyze_cross_race_performance_patterns(
                queries, driver_a=parsed["driver_a"],
                driver_b=parsed["driver_b"], seasons=scan_seasons)
            ctx["tool_calls"] += 1
            run["tool_calls_consumed"] = ctx["tool_calls"]
            discovery_scan = {
                "seasons_scanned": scan_seasons,
                "patterns_found": [p.get("pattern_id")
                                   for p in (disc.get("patterns") or [])],
                "status": disc.get("status"),
                "reason": disc.get("reason"),
                "runtime_ms": round((time.perf_counter() - t0) * 1000, 1),
            }
            run["pattern_discovery"] = discovery_scan
            if disc.get("status") != "VALID" or not disc.get("patterns"):
                return finish("DATA_UNAVAILABLE",
                              f"no recurring pattern discovered for "
                              f"{parsed['driver_a']}/{parsed['driver_b']} in "
                              f"{scan_seasons}: "
                              f"{disc.get('reason') or disc.get('status')}",
                              "EVIDENCE_PLANNED",
                              extra={"pattern_discovery": discovery_scan})
            pattern_id = disc["patterns"][0]["pattern_id"]
            decision("SELECT_TOOL",
                     "selected the top discovered pattern id for the "
                     "investigation scope",
                     f"pattern_id={pattern_id}",
                     tool_result_hash=_hash_obj({
                         "seasons_scanned": scan_seasons,
                         "patterns_found": discovery_scan["patterns_found"],
                         "status": discovery_scan["status"],
                         "reason": discovery_scan["reason"]}),
                     counts_as_tool=False)
        elif pattern_id is None:
            return finish("BUDGET_EXHAUSTED",
                          "max_cross_race_scans=0 forbids pattern discovery",
                          "EVIDENCE_PLANNED")
        parsed["pattern_id"] = pattern_id
        ctx["resolved_context"]["pattern_id"] = pattern_id
        run["context"]["pattern_id"] = pattern_id
    evidence_plan = [
        {"phase": step["phase"], "tool": step["tool"],
         "purpose": step["purpose"],
         "why_planned": f"the {parsed['question_type']} evidence plan "
                        "routes through this deterministic layer"}
        for step in _engine_evidence_plan(parsed["question_type"])
    ]
    decision("PLAN_EVIDENCE",
             "every planned item maps 1:1 to a deterministic tool; no "
             "imaginary evidence source",
             "proceed to collection",
             output_state={"plan": [s["tool"] for s in evidence_plan]})
    stage("EVIDENCE_PLANNED", "COMPLETED")
    run["evidence_plan"] = evidence_plan

    # --- 6 EVIDENCE_COLLECTING (adaptive loop around the engine) -------------
    stage("EVIDENCE_COLLECTING", "IN_PROGRESS")
    run["budget"] = budget_snapshot()
    budget_err = require_tool_budget("the engineering investigation")
    if budget_err:
        return finish("BUDGET_EXHAUSTED", budget_err, "EVIDENCE_COLLECTING")
    decision("SELECT_TOOL",
             "the planned scope is exactly one 6N engineering investigation; "
             "its engine executes the deterministic phase layers and is the "
             "authority for evidence and hypothesis states",
             "run_engineering_investigation",
             tool="run_engineering_investigation",
             input_state={"scope": ctx["resolved_context"],
                          "hypotheses_subset": subset or None},
             counts_as_tool=True)
    t0 = time.perf_counter()
    try:
        inv = _run_engineering_investigation(queries, parsed, subset or None,
                                             budget)
    except Exception as exc:  # noqa: BLE001 — honest TOOL_FAILURE contract
        return finish("TOOL_FAILURE",
                      f"deterministic engine failed: {exc}",
                      "EVIDENCE_COLLECTING")
    inv_runtime_ms = round((time.perf_counter() - t0) * 1000, 1)
    ctx["inv_runtime_ms"] = inv_runtime_ms
    run["_engine_runtime_ms"] = inv_runtime_ms
    if ctx["tool_calls"] >= budget["max_tool_calls"]:
        run["budget"] = budget_snapshot()
        return finish("BUDGET_EXHAUSTED",
                      f"max_tool_calls={budget['max_tool_calls']} consumed by "
                      "the investigation execution",
                      "EVIDENCE_COLLECTING")

    inv_status = inv.get("status")
    if inv_status == "INVALID":
        return finish("TOOL_FAILURE",
                      f"engine rejected the scope: {inv.get('reason')}",
                      "EVIDENCE_COLLECTING")
    if inv_status in ("UNAVAILABLE", "INSUFFICIENT_EVIDENCE"):
        # honest data-dependence: preserve the engine verdict verbatim
        state = ("INSUFFICIENT_EVIDENCE"
                 if inv_status == "INSUFFICIENT_EVIDENCE"
                 else "DATA_UNAVAILABLE")
        return finish(state, inv.get("reason") or inv_status,
                      "EVIDENCE_COLLECTING",
                      extra={"engine_result_ref": _engine_public_view(inv)})
    stage("EVIDENCE_COLLECTING", "COMPLETED")
    run["engine_result_ref"] = {
        "investigation_id": inv.get("investigation_id"),
        "output_hash": inv.get("output_hash"),
        "status": inv_status,
        "evidence_items": len(inv.get("evidence_ledger") or []),
        "layers_executed": (inv.get("provenance") or {}).get("layers_executed"),
        # runtime is a metric, never part of the deterministic identity
        "_runtime_ms": inv_runtime_ms,
    }
    ledger = inv.get("evidence_ledger") or []

    # adaptive inspection: contradictions request the remaining plan layers;
    # already-collected evidence identities are never re-collected
    conflicts = inv.get("evidence_conflicts") or []
    if conflicts:
        conflict_refs = sorted({eid for c in conflicts
                                for eid in (c.get("evidence_ids") or [])})
        decision("REQUEST_MORE_EVIDENCE",
                 f"engine reported {len(conflicts)} evidence conflict(s); "
                 "the remaining planned layers were already executed inside "
                 "the same engine run, so no further collection is possible "
                 "without inventing evidence",
                 "keep the conflict explicit in synthesis",
                 evidence_refs=conflict_refs,
                 counts_as_tool=False)
    stage("HYPOTHESES_EVALUATED", "COMPLETED",
          f"{len(inv.get('hypothesis_evaluations') or {})} hypotheses "
          "evaluated by the engine")
    gate_establishable = len(
        (inv.get("falsification_gate") or {})
        .get("establishable_hypotheses") or [])
    stage("FALSIFICATION", "COMPLETED",
          f"{len(conflicts)} conflict(s) preserved; gate: "
          f"{gate_establishable} establishable hypotheses")
    stage("COUNTERFACTUAL_CHECK", "COMPLETED",
          f"{len(inv.get('counterfactual_candidates') or [])} candidates, "
          f"{len(inv.get('executed_counterfactuals') or [])} executed "
          "(engine-eligible only)")
    run["hypothesis_states"] = {
        h: v.get("aggregate_state")
        for h, v in (inv.get("hypothesis_evaluations") or {}).items()}
    run["falsification_gate"] = inv.get("falsification_gate")
    run["evidence_conflicts"] = conflicts

    # --- 7 SYNTHESIS ----------------------------------------------------------
    stage("SYNTHESIS", "IN_PROGRESS")
    synth = inv.get("synthesis") or {}
    decision("SYNTHESIZE",
             "synthesis is generated from deterministic evidence only; the "
             "orchestrator adds no prose of its own",
             "embed the engine synthesis verbatim",
             evidence_refs=[e.get("evidence_id") for e in ledger[:10]],
             counts_as_tool=False)
    stage("SYNTHESIS", "COMPLETED",
          f"conclusion_state={synth.get('conclusion_state')}")

    # --- 8 VERIFICATION ---------------------------------------------------------
    stage("VERIFICATION", "IN_PROGRESS")
    verify_problems = _verify(run, inv)
    if verify_problems:
        return finish("VERIFICATION_FAILURE", "; ".join(verify_problems),
                      "VERIFICATION",
                      extra={"engine_result_ref": _engine_public_view(inv)})
    decision("VERIFY",
             "every finding carries an evidence reference and every "
             "numerical value a deterministic source hash; no unsupported "
             "causal language",
             "accept the result",
             output_state={"verified_checks": len(verify_problems) == 0},
             counts_as_tool=False)
    stage("VERIFICATION", "COMPLETED")

    # --- 9 COMPLETED + memory -----------------------------------------------------
    stage("COMPLETED", "COMPLETED")
    from racewise.data.historical.investigation_memory import (
        derive_memory_items, retrieve_related_engineering_memory,
    )
    memory_items = derive_memory_items(inv)
    run["memory"] = {
        "items_derived": len(memory_items),
        "policy": ("exact-scope, provenance-backed; derivation via the "
                   "unchanged Phase 6O rules"),
    }
    if budget["max_memory_neighbors"] > 0:
        pool = list(memory_items)
        neighbor_runs: list[dict[str, Any]] = []
        for nb_season in (season_i - 1, season_i + 1)[:max(
                0, budget["max_memory_neighbors"])]:
            nb_spec = {
                "question_type": parsed["question_type"],
                "driver_a": parsed["driver_a"], "driver_b": parsed["driver_b"],
                "season": nb_season, "round": round_i,
                "lap_number": parsed["lap_number"],
                "stint_number": parsed["stint_number"],
                "session_type": parsed["session_type"],
                "pattern_id": parsed["pattern_id"],
            }
            try:
                nb_inv = _run_engineering_investigation(queries, nb_spec,
                                                        subset or None,
                                                        budget)
            except Exception:  # noqa: BLE001 — neighbors never fabricate
                nb_inv = {"status": "TOOL_FAILURE"}
            if nb_inv.get("status") == "VALID":
                pool.extend(derive_memory_items(nb_inv))
            neighbor_runs.append({
                "season": nb_season, "status": nb_inv.get("status"),
                "investigation_id": nb_inv.get("investigation_id"),
            })
            decision("SELECT_TOOL",
                     f"related-memory neighbor pool: same spec at season "
                     f"{nb_season}",
                     "derive_memory_items(neighbor)",
                     tool="run_engineering_investigation",
                     counts_as_tool=True)
            if ctx["tool_calls"] > budget["max_tool_calls"]:
                run["budget"] = budget_snapshot()
                return finish("BUDGET_EXHAUSTED",
                              "neighbor expansion exceeded max_tool_calls",
                              "COMPLETED")
        related = retrieve_related_engineering_memory(
            pool, season=season_i, round_num=round_i,
            driver_pair=[parsed["driver_a"], parsed["driver_b"]],
            include_invalidated=False)
        run["memory"]["related"] = {
            "items": related["related_memory_items"],
            "match_count": related["related_match_count"],
            "policy": related["policy"],
            "neighbor_runs": neighbor_runs,
            "note": ("a related item is a provenance-backed pointer, never "
                     "a conclusion transfer"),
        }
    run["budget"] = budget_snapshot()
    run["status"] = "COMPLETED"
    run["reason"] = None
    run["failed_stage"] = None
    _finalize(run, queries, started)
    return run


def replay_autonomous_investigation(
    queries: CanonicalQueries, run_record: dict[str, Any],
) -> dict[str, Any]:
    """Replay a completed/failed autonomous run from its record.

    Re-executes intake → plan → engine from the recorded question text and
    context, then compares the deterministic surfaces (question object,
    stage ledger, decision trace, engine output hash, hypothesis states).
    IDENTICAL / CHANGED with the explicit changed dimensions.
    """
    base: dict[str, Any] = {
        "analysis": ANALYSIS, "version": ORCHESTRATOR_VERSION,
        "replay_of_run": run_record.get("run_id"),
    }
    required = ("question_text", "context", "question", "status",
                "stage_ledger", "decision_trace")
    missing = [k for k in required
               if k not in run_record and k not in (run_record.get("context")
                                                    or {})]
    if missing:
        base.update({"status": "INVALID_RECORD",
                     "reason": f"missing record fields: {missing}"})
        return base
    replay_constraints = (
        (run_record.get("budget") or {}).get("limits") or {})
    fresh = run_autonomous_investigation(
        queries, run_record["question_text"],
        # the original intake context (verbatim), never the resolved form:
        # replay must re-execute from the identical declared inputs
        run_record.get("intake_context") if "intake_context" in run_record
        else run_record.get("context"),
        replay_constraints)
    dims: list[dict[str, Any]] = []
    dims.append({"dimension": "STATUS",
                 "original": run_record.get("status"),
                 "replay": fresh.get("status"),
                 "changed": run_record.get("status") != fresh.get("status")})
    dims.append({"dimension": "QUESTION_OBJECT",
                 "original": (run_record.get("question") or {}).get(
                     "question_object_hash"),
                 "replay": (fresh.get("question") or {}).get(
                     "question_object_hash"),
                 "changed": (run_record.get("question") or {}).get(
                     "question_object_hash")
                 != (fresh.get("question") or {}).get("question_object_hash")})
    dims.append({"dimension": "ENGINE_INVESTIGATION_ID",
                 "original": (run_record.get("engine_result_ref") or {}).get(
                     "investigation_id"),
                 "replay": (fresh.get("engine_result_ref") or {}).get(
                     "investigation_id"),
                 "changed": (run_record.get("engine_result_ref") or {}).get(
                     "investigation_id")
                 != (fresh.get("engine_result_ref") or {}).get(
                     "investigation_id")})
    dims.append({"dimension": "STAGE_LEDGER",
                 "original": run_record.get("stage_ledger"),
                 "replay": fresh.get("stage_ledger"),
                 "changed": run_record.get("stage_ledger")
                 != fresh.get("stage_ledger")})
    dims.append({"dimension": "DECISION_TRACE",
                 "original": run_record.get("decision_trace"),
                 "replay": fresh.get("decision_trace"),
                 "changed": run_record.get("decision_trace")
                 != fresh.get("decision_trace")})
    dims.append({"dimension": "ENGINE_OUTPUT",
                 "original": (run_record.get("engine_result_ref") or {}).get(
                     "output_hash"),
                 "replay": (fresh.get("engine_result_ref") or {}).get(
                     "output_hash"),
                 "changed": (run_record.get("engine_result_ref") or {}).get(
                     "output_hash")
                 != (fresh.get("engine_result_ref") or {}).get("output_hash")})
    dims.append({"dimension": "HYPOTHESIS_STATES",
                 "original": run_record.get("hypothesis_states"),
                 "replay": fresh.get("hypothesis_states"),
                 "changed": run_record.get("hypothesis_states")
                 != fresh.get("hypothesis_states")})
    changed = [d["dimension"] for d in dims if d["changed"]]
    base.update({
        "status": "IDENTICAL" if not changed else "CHANGED",
        "identical": not changed,
        "changed_dimensions": changed,
        "dimensions": dims,
        "replay_run": {
            "status": fresh.get("status"),
            "engine_result_ref": fresh.get("engine_result_ref"),
            "stage_ledger": fresh.get("stage_ledger"),
        },
        "provenance": {
            "method": "deterministic_autonomous_run_replay",
            "orchestrator_version": ORCHESTRATOR_VERSION,
            "policy_version": POLICY_VERSION,
        },
    })
    return base


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _engine_evidence_plan(question_type: str) -> list[dict[str, str]]:
    from racewise.data.historical.investigation_synthesis import (
        QUESTION_EVIDENCE_PLAN,
    )
    return QUESTION_EVIDENCE_PLAN[question_type]


def _run_engineering_investigation(
    queries: CanonicalQueries, spec: dict[str, Any],
    hypotheses: Optional[list[str]], budget: dict[str, int],
) -> dict[str, Any]:
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )
    return run_engineering_investigation(
        queries,
        question_type=spec["question_type"],
        driver_a=spec["driver_a"], driver_b=spec["driver_b"],
        season=int(spec["season"]), round_num=int(spec["round"]),
        lap_number=spec.get("lap_number"),
        stint_number=spec.get("stint_number"),
        session_type=spec.get("session_type") or "RACE",
        pattern_id=spec.get("pattern_id"),
        hypotheses=hypotheses,
        max_counterfactuals=int(budget.get("max_counterfactuals", 2)),
    )


def _engine_public_view(inv: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": inv.get("status"),
        "reason": inv.get("reason"),
        "investigation_id": inv.get("investigation_id"),
        "output_hash": inv.get("output_hash"),
    }


def _verify(run: dict[str, Any], inv: dict[str, Any]) -> list[str]:
    """No-fabrication verification of the completed run.

    Checks the structural contract: engine VALID, findings traceable to
    evidence ids, numerical values hash-bound, claim classes closed,
    conclusion states closed. Returns a list of problems (empty = pass).
    """
    problems: list[str] = []
    if inv.get("status") != "VALID":
        problems.append(f"engine status {inv.get('status')} is not VALID")
    ledger = inv.get("evidence_ledger") or []
    evidence_ids = {e.get("evidence_id") for e in ledger}
    missing_hash = [e.get("evidence_id") for e in ledger
                    if not e.get("source_hash")]
    if missing_hash:
        problems.append(f"evidence items without source hashes: "
                        f"{missing_hash[:5]}")
    trace_basis = {b for t in (inv.get("decision_trace") or [])
                   for b in (t.get("basis") or [])}
    dangling = sorted(b for b in trace_basis
                      if b not in evidence_ids
                      and not str(b).startswith("CF-"))
    if dangling:
        problems.append(f"decision trace references unknown evidence: "
                        f"{dangling[:5]}")
    claim_classes = {e.get("claim_class") for e in ledger}
    bad_claims = sorted(c for c in claim_classes
                        if c not in ("OBSERVED", "DERIVED", "INFERRED",
                                     "MODELLED", None))
    if bad_claims:
        problems.append(f"unknown claim classes in ledger: {bad_claims}")
    synth = inv.get("synthesis") or {}
    if synth.get("conclusion_state") not in (
            "SUPPORTED_BY_AVAILABLE_EVIDENCE", "MIXED_EVIDENCE",
            "INSUFFICIENT_EVIDENCE", "NOT_TESTABLE", "UNAVAILABLE"):
        problems.append(f"unknown synthesis conclusion state: "
                        f"{synth.get('conclusion_state')}")
    return problems


def _finalize(run: dict[str, Any], queries: CanonicalQueries,
              started: float) -> None:
    """Compute the run identity and record metrics (excluded from identity)."""
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    engine_ms = run.pop("_engine_runtime_ms", None)
    ref = run.get("engine_result_ref")
    if isinstance(ref, dict) and "_runtime_ms" in ref:
        engine_ms = ref.pop("_runtime_ms")
    run["metrics"] = {
        "total_runtime_ms": elapsed_ms,
        "engine_runtime_ms": engine_ms,
        "tool_calls": run.get("tool_calls_consumed", 0),
        "cache": {"hits": 0, "misses": run.get("tool_calls_consumed", 0),
                  "policy": ("derived-on-read engine; cross-run evidence "
                             "reuse happens through identical content-hash "
                             "identities, not a result cache")},
    }
    # The run identity is the hash of the declared inputs plus the fixed
    # policy: every derived surface in the record is a deterministic
    # function of these, so hashing the inputs alone is stable and
    # replay-safe (runtime fields are excluded by construction).
    identity = {
        "analysis": run.get("analysis"),
        "version": run.get("version"),
        "policy_version": run.get("policy_version"),
        "question_text": run.get("question_text"),
        "context": run.get("context") or {},
        "constraints": (run.get("budget") or {}).get("limits"),
    }
    run["run_id"] = _hash_obj(identity)
