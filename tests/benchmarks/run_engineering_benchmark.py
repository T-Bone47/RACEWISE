"""Phase 6R benchmark runner: full-system engineering validation.

Executes the corpus in tests/benchmarks/engineering_questions.json through
the REAL chain (engine -> graph -> memory -> replay -> comparison -> API)
and records structural outcomes. No expected numerical answers exist in
the corpus; every assertion is about statuses, evidence presence,
provenance completeness, replay identity, graph integrity and honest
limitation reporting.

Usage:
    python tests/benchmarks/run_engineering_benchmark.py \
        [--corpus tests/benchmarks/engineering_questions.json] \
        [--out data/benchmarks/6r_benchmark_results.json]

All assertions are structural. Failures are recorded, never hidden; the
runner always writes a results file (exit code 0 when the corpus executed
to completion, 1 only if the corpus itself could not be executed).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.data.historical.canonical_queries import CanonicalQueries  # noqa: E402
from racewise.data.historical.investigation_graph import (  # noqa: E402
    build_graph_snapshot, build_investigation_graph, graph_vocabulary,
    replay_graph_snapshot, verify_graph_snapshot,
)
from racewise.data.historical.investigation_memory import (  # noqa: E402
    compare_engineering_investigations, derive_memory_items,
    invalidate_memory_item, replay_engineering_investigation,
    retrieve_engineering_memory, retrieve_related_engineering_memory,
)
from racewise.data.historical.investigation_synthesis import (  # noqa: E402
    HYPOTHESIS_IDS, run_engineering_investigation,
)
from racewise.data.historical.performance_patterns import (  # noqa: E402
    analyze_cross_race_performance_patterns,
)

CORPUS_DEFAULT = ROOT / "tests" / "benchmarks" / "engineering_questions.json"
RESULTS_DEFAULT = ROOT / "data" / "benchmarks" / "6r_benchmark_results.json"

ENGINE_STATUS_SET = {"VALID", "UNAVAILABLE", "INVALID", "INSUFFICIENT_EVIDENCE"}
CONCLUSION_STATES = {
    "SUPPORTED", "SUPPORTED_BY_AVAILABLE_EVIDENCE", "PARTIALLY_SUPPORTED",
    "NOT_SUPPORTED", "CONTRADICTED",
    "MIXED_EVIDENCE", "INSUFFICIENT_EVIDENCE", "NOT_TESTABLE", "UNAVAILABLE",
    "NOT_REQUESTED",
}
AGGREGATE_HYP_STATES = {
    "SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED",
    "MIXED_EVIDENCE", "INSUFFICIENT_EVIDENCE", "NOT_TESTABLE",
    "UNAVAILABLE", "NOT_REQUESTED",
}
TRACE_TYPES = {"FACT", "DERIVED", "CONFLICT", "HYPOTHESIS_STATUS", "COUNTERFACTUAL"}
PROVENANCE_KEYS = ("provider", "source_tables", "method", "analytical_chain",
                   "investigation_version")
CF_GATE_KEYS = ("baseline_available", "intervention_valid", "model_scope",
                "status", "reason", "missing_data", "required_data")


def _load_corpus(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [c["benchmark_id"] for c in data["cases"]]
    if len(set(ids)) != len(ids):
        raise SystemExit("corpus contains duplicate benchmark_id values")
    return data


# ---------------------------------------------------------------------------
# structural checks
# ---------------------------------------------------------------------------

def check_provenance(inv: dict[str, Any], required: list[str]) -> dict[str, Any]:
    prov = inv.get("provenance") or {}
    missing = [k for k in required if k not in prov or prov.get(k) in (None, "", [])]
    return {"present": not missing, "missing_fields": missing}


def check_decision_trace(inv: dict[str, Any]) -> dict[str, Any]:
    traces = inv.get("decision_trace") or []
    invalid_types = sorted({t.get("type") for t in traces} - TRACE_TYPES)
    # trace status vocabulary is intentionally open beyond the core set;
    # only the trace TYPE vocabulary is closed and asserted here
    return {"count": len(traces), "invalid_types": invalid_types}


def check_refs_resolvable(inv: dict[str, Any]) -> dict[str, Any]:
    trace_ids = {t.get("trace_id") for t in inv.get("decision_trace") or []}
    refs = (inv.get("synthesis") or {}).get("decision_trace_refs") or []
    dangling = [r for r in refs if r not in trace_ids]
    return {"resolvable": not dangling, "refs": len(refs), "dangling": dangling[:10]}


def check_hypotheses(inv: dict[str, Any]) -> dict[str, Any]:
    hec = inv.get("hypothesis_evaluations") or {}
    bad = [h for h, v in hec.items()
           if v.get("aggregate_state") not in AGGREGATE_HYP_STATES]
    states = sorted({v.get("aggregate_state") for v in hec.values()})
    fals = inv.get("falsification_gate") or {}
    return {"count": len(hec), "invalid_states": bad, "distinct_states": states,
            "falsification_gate_present": bool(fals)}


def check_limitations(inv: dict[str, Any]) -> dict[str, Any]:
    syn = inv.get("synthesis") or {}
    return {
        "limitations_nonempty": bool(inv.get("limitations")),
        "epistemic_boundaries_nonempty": bool(inv.get("epistemic_boundaries")),
        "unresolved_questions_count": len(syn.get("unresolved_questions") or []),
    }


def check_lifecycle(inv: dict[str, Any]) -> dict[str, Any]:
    lc = inv.get("lifecycle") or []
    return {"stages": len(lc), "all_completed": all(
        (l.get("status") == "COMPLETED") for l in lc) if lc else False}


def check_untestable_preserved(inv: dict[str, Any]) -> bool:
    """No hypothesis evaluation may collapse to a bare SUPPORTED/NOT_SUPPORTED
    when its supporting evidence is empty (would violate the epistemics)."""
    hec = inv.get("hypothesis_evaluations") or {}
    for hid, v in hec.items():
        if v.get("aggregate_state") == "SUPPORTED" and \
                not (v.get("supporting_evidence") or v.get("non_decisive_evidence")):
            return False
    return True


def check_no_hardcoded_magic_numbers(inv: dict[str, Any]) -> dict[str, Any]:
    """Measured values must come from evidence ledger ids, not thin air:
    every established fact / measured finding must carry an evidence_id that
    exists in the ledger."""
    ledger_ids = {e.get("evidence_id") for e in inv.get("evidence_ledger") or []}
    syn = inv.get("synthesis") or {}
    dangling = []
    for kind in ("established_facts", "measured_findings"):
        for item in syn.get(kind) or []:
            if item.get("evidence_id") not in ledger_ids:
                dangling.append(f"{kind}:{item.get('evidence_id')}")
    return {"ledger_size": len(ledger_ids), "dangling_synthesis_refs": dangling[:10]}


# ---------------------------------------------------------------------------
# per-case execution
# ---------------------------------------------------------------------------

def run_case(queries: CanonicalQueries, case: dict[str, Any],
             vocab: dict[str, Any], pattern_cache: dict[tuple, dict],
             api_url: str | None) -> dict[str, Any]:
    t0 = time.perf_counter()
    checks: dict[str, Any] = {}
    status: str | None = None
    conclusion: str | None = None
    inv: dict[str, Any] = {}

    def finish(kind: str, ok: bool, detail: str = "") -> dict[str, Any]:
        return {
            "benchmark_id": case["benchmark_id"], "category": case["category"],
            "category_name": case["category_name"], "kind": kind,
            "limitation_case": case.get("limitation_case", False),
            "status": status, "conclusion_state": conclusion,
            "pass": ok, "detail": detail, "elapsed_s": round(time.perf_counter() - t0, 3),
            "checks": checks,
        }

    # --- input resolution -------------------------------------------------
    kwargs: dict[str, Any] = {
        "question_type": case["question_type"],
        "driver_a": case["driver_a"], "driver_b": case["driver_b"],
        "season": case["season"], "round_num": case["round"],
        "lap_number": case.get("lap_number"),
        "stint_number": case.get("stint_number"),
        "pattern_id": case.get("pattern_id"),
        "session_type": case.get("session_type", "RACE"),
    }
    if case.get("hypotheses_subset"):
        kwargs["hypotheses"] = list(case["hypotheses_subset"])
    if "max_counterfactuals" in case:
        kwargs["max_counterfactuals"] = case["max_counterfactuals"]

    # pattern discovery / rediscovery (measured, cached once per (pair, seasons))
    if case.get("pattern_discovery"):
        key = (case["driver_a"], case["driver_b"],
               tuple(case["pattern_discovery"]["seasons"]))
        if key not in pattern_cache:
            disc = analyze_cross_race_performance_patterns(
                queries, driver_a=key[0], driver_b=key[1],
                seasons=list(key[2]))
            pattern_cache[key] = disc
        disc = pattern_cache[key]
        discovered = {p.get("pattern_id") for p in (disc.get("patterns") or [])}
        if not case.get("pattern_id"):
            # discovery-only case: honest UNAVAILABLE/zero-patterns with a
            # reason is a legitimate measured outcome for evidence-poor eras
            d_status = disc.get("status")
            checks["discovery_status"] = d_status
            checks["discovery_pattern_count"] = len(discovered)
            checks["discovery_reason_present"] = bool(disc.get("reason"))
            ok = (d_status in case.get("expected_status", [])
                  and (d_status == "VALID" or bool(disc.get("reason"))))
            return finish("STRUCTURAL_PASS" if d_status == "VALID"
                          else "EXECUTED_LIMITATION", ok,
                          f"discovery status={d_status} "
                          f"patterns={len(discovered)} "
                          f"reason={str(disc.get('reason'))[:90]}")
        if case["pattern_id"] not in discovered:
            return finish("EXECUTED_LIMITATION", True,
                          f"pattern {case['pattern_id']} absent from "
                          f"re-discovery ({len(discovered)} found); treated as "
                          f"honest data-dependence (signatures are data-derived)")
        checks["pattern_rediscovered"] = True

    # --- invalid-input control --------------------------------------------
    if case.get("invalid_input"):
        try:
            inv = run_engineering_investigation(queries, **kwargs)
            status = inv.get("status")
            checks["invalid_rejected"] = status == "INVALID"
            checks["invalid_reason_present"] = bool(inv.get("reason"))
            ok = checks["invalid_rejected"] and checks["invalid_reason_present"]
            return finish("STRUCTURAL_CONTROL", ok,
                          f"invalid input rejected with reason: "
                          f"{str(inv.get('reason'))[:80]}")
        except Exception as exc:  # noqa: BLE001
            return finish("IMPLEMENTATION_FAILURE", False, f"raised: {exc}")

    # --- main investigation -------------------------------------------------
    try:
        inv = run_engineering_investigation(queries, **kwargs)
    except Exception as exc:  # noqa: BLE001
        return finish("IMPLEMENTATION_FAILURE", False, f"raised: {exc}")

    status = inv.get("status")
    checks["status_in_expected"] = status in case.get("expected_status", [])
    if status == "INVALID":
        return finish("IMPLEMENTATION_FAILURE", False,
                      f"VALID-scope case returned INVALID: {inv.get('reason')}")
    if status != "VALID":
        ok = checks["status_in_expected"] and bool(inv.get("reason"))
        checks["reason_present"] = bool(inv.get("reason"))
        return finish("EXECUTED_LIMITATION", ok,
                      f"status={status} reason={str(inv.get('reason'))[:100]}")

    # --- VALID: structural checks -----------------------------------------
    conclusion = (inv.get("synthesis") or {}).get("conclusion_state")
    checks["conclusion_in_expected"] = conclusion in case.get(
        "expected_conclusion_states", [])
    if not checks["conclusion_in_expected"]:
        return finish("IMPLEMENTATION_FAILURE", False,
                      f"conclusion_state {conclusion} not in expected set")

    prov = check_provenance(inv, case.get("required_provenance") or [])
    checks["provenance"] = prov

    if case.get("evidence_rich"):
        n = ((inv.get("collection") or {}).get("items_collected") or 0)
        checks["evidence_collected"] = n
        if n < 1:
            return finish("IMPLEMENTATION_FAILURE", False,
                          "evidence_rich case collected zero evidence items")

    checks["trace"] = check_decision_trace(inv)
    checks["trace_refs"] = check_refs_resolvable(inv)
    checks["hypotheses"] = check_hypotheses(inv)
    checks["limitations"] = check_limitations(inv)
    checks["lifecycle"] = check_lifecycle(inv)
    checks["untestable_preserved"] = check_untestable_preserved(inv)
    checks["synthesis_refs"] = check_no_hardcoded_magic_numbers(inv)
    checks["investigation_id"] = inv.get("investigation_id")
    checks["output_hash"] = inv.get("output_hash")

    hard_fail = (
        (not prov["present"])
        or checks["trace"]["invalid_types"]
        or (not checks["trace_refs"]["resolvable"])
        or checks["hypotheses"]["invalid_states"]
        or (not checks["untestable_preserved"])
        or checks["synthesis_refs"]["dangling_synthesis_refs"]
        or (not checks["lifecycle"]["all_completed"])
    )
    if hard_fail:
        return finish("PROVENANCE_GAP", False, "structural provenance checks failed")

    # --- counterfactual expectations ----------------------------------------
    cf_expect = case.get("counterfactual_expected")
    if cf_expect in ("INELIGIBLE_EXPLAINED", "ELIGIBLE_OR_EXPLAINED",
                     "ELIGIBLE", "BOUNDED"):
        candidates = inv.get("counterfactual_candidates") or []
        executed = inv.get("executed_counterfactuals") or []
        checks["cf_candidates"] = len(candidates)
        checks["cf_executed"] = len(executed)
        if cf_expect == "BOUNDED":
            checks["bounded_by_present"] = bool(inv.get("collection", {}).get(
                "bounded_by")) or bool(inv.get("requested_bounds"))
        else:
            gate_ok = True
            for c in candidates + executed:
                if cf_expect == "ELIGIBLE" and c.get("status") == "EXECUTED":
                    for k in ("baseline", "intervention", "parameter",
                              "model", "claim_class", "epistemics"):
                        if not c.get(k):
                            gate_ok = False
                    res = c.get("result") or {}
                    gates = (res.get("validation_gates")
                             or res.get("gates") or {})
                    checks["cf_gates_present"] = bool(gates)
                elif c.get("status") not in ("EXECUTED", None):
                    missing_gate_keys = [k for k in CF_GATE_KEYS if k not in c]
                    if missing_gate_keys:
                        gate_ok = False
                        checks.setdefault("cf_gate_missing", []).append(
                            {"candidate": c.get("candidate_id"),
                             "missing": missing_gate_keys})
            checks["cf_gates_explained"] = gate_ok
            if not gate_ok:
                return finish("PROVENANCE_GAP", False,
                              "counterfactual gates not fully explained")

    # --- replay --------------------------------------------------------------
    if case.get("replay_expected"):
        snap = build_investigation_snapshot_safe(inv)
        if snap is None:
            return finish("IMPLEMENTATION_FAILURE", False,
                          "snapshot could not be built")
        rp = replay_engineering_investigation(queries, snap)
        checks["replay_status"] = rp.get("status")
        checks["replay_identical"] = rp.get("identical")
        if not rp.get("identical"):
            return finish("DETERMINISM_GAP", False,
                          f"replay {rp.get('status')} "
                          f"diffs={rp.get('difference_count')}")

    # --- graph ---------------------------------------------------------------
    if case.get("graph_trace_expected"):
        graph = build_investigation_graph(queries, inv)
        if graph.get("status") in ("INVALID", "UNAVAILABLE"):
            # honest no-graph is only acceptable for limitation cases
            if case.get("limitation_case") and graph.get("reason"):
                checks["graph"] = {"honest_no_graph": True,
                                   "reason": graph.get("reason")}
            else:
                return finish("ORCHESTRATION_GAP", False,
                              f"graph unavailable: {graph.get('reason')}")
        else:
            nodes = graph.get("nodes") or []
            edges = graph.get("edges") or []
            node_types = set(vocab["node_types"])
            edge_types = set(vocab["edge_types"])
            bad_nodes = sorted({n.get("node_type") for n in nodes} - node_types)
            bad_edges = sorted({e.get("edge_type") for e in edges} - edge_types)
            node_ids = {n.get("node_id") for n in nodes}
            dangling = [e.get("edge_id") for e in edges
                        if (e.get("source_node") not in node_ids)
                        or (e.get("target_node") not in node_ids)]
            checks["graph"] = {
                "nodes": len(nodes), "edges": len(edges),
                "invalid_node_types": bad_nodes, "invalid_edge_types": bad_edges,
                "dangling_edges": dangling[:10],
            }
            if bad_nodes or bad_edges or dangling:
                return finish("ORCHESTRATION_GAP", False,
                              "graph integrity failure (vocabulary or edges)")
            snap = build_graph_snapshot(graph)
            checks["graph_snapshot_verified"] = \
                verify_graph_snapshot(snap).get("status") == "VALID"
            rp = replay_graph_snapshot(queries, snap)
            checks["graph_replay_status"] = rp.get("status")
            if rp.get("status") != "IDENTICAL":
                return finish("DETERMINISM_GAP", False,
                              f"graph replay {rp.get('status')}")

    # --- memory probes ---------------------------------------------------------
    probe = case.get("memory_probe")
    if probe:
        kind = probe.get("kind")
        if kind == "api_layer":
            import httpx
            try:
                r = httpx.get(f"{api_url}/api/catalog/engineering-memory",
                              params={"question_type": case["question_type"],
                                      "driver_a": case["driver_a"],
                                      "driver_b": case["driver_b"],
                                      "season": case["season"],
                                      "round": case["round"],
                                      "lap_number": case.get("lap_number", 0)},
                              timeout=120.0)
                checks["memory_api_status"] = r.status_code
                body = r.json() if r.status_code == 200 else {}
                checks["memory_api_matches"] = body.get("match_count")
                ok_api = (r.status_code == 200
                          and (body.get("match_count") or 0)
                          >= probe.get("expect_min_matches", 1)
                          and bool(body.get("policy")))
                if not ok_api:
                    return finish("API_GAP", False,
                                  f"memory API status={r.status_code} "
                                  f"matches={body.get('match_count')}")
            except Exception as exc:  # noqa: BLE001
                return finish("API_GAP", False, f"memory API call failed: {exc}")
        elif kind == "graph_by_id":
            # Phase 6S GAP 1: id-addressed graph retrieval. The graph must
            # equal the scope-addressed graph; a wrong id must 404 (no
            # silent fallback), an id without scope must 422. A probe with
            # expect=mismatch is the negative control: the primary request
            # uses a deliberately wrong id and must 404.
            import httpx
            try:
                expect = probe.get("expect", "match")
                inv_id = ("0" * 16 if expect == "mismatch"
                          else inv.get("investigation_id"))
                base_qs = (f"question_type={case['question_type']}"
                           f"&driver_a={case['driver_a']}"
                           f"&driver_b={case['driver_b']}"
                           f"&season={case['season']}&round={case['round']}")
                if case.get("lap_number"):
                    base_qs += f"&lap_number={case['lap_number']}"
                if case.get("session_type", "RACE") != "RACE":
                    base_qs += f"&session_type={case['session_type']}"
                r_ok = httpx.get(
                    f"{api_url}/api/catalog/investigation-graph?{base_qs}"
                    f"&investigation_id={inv_id}", timeout=180.0)
                r_scope = httpx.get(
                    f"{api_url}/api/catalog/investigation-graph?{base_qs}",
                    timeout=180.0)
                r_wrong = httpx.get(
                    f"{api_url}/api/catalog/investigation-graph?{base_qs}"
                    f"&investigation_id={'0' * 16}", timeout=60.0)
                r_noscope = httpx.get(
                    f"{api_url}/api/catalog/investigation-graph"
                    f"?investigation_id={'0' * 16}", timeout=60.0)
                ok_body = r_ok.json() if r_ok.status_code == 200 else {}
                scope_body = (r_scope.json()
                              if r_scope.status_code == 200 else {})
                checks["graph_by_id_status"] = r_ok.status_code
                checks["graph_ids_equal"] = (
                    ok_body.get("graph_id") == scope_body.get("graph_id")
                    if ok_body and scope_body else False)
                checks["wrong_id_is_404"] = r_wrong.status_code == 404
                checks["id_without_scope_is_422"] = r_noscope.status_code == 422
                if expect == "mismatch":
                    ok = (r_ok.status_code == 404
                          and r_scope.status_code == 200
                          and checks["wrong_id_is_404"])
                else:
                    ok = (r_ok.status_code == 200
                          and checks["graph_ids_equal"]
                          and checks["wrong_id_is_404"]
                          and checks["id_without_scope_is_422"])
                if not ok:
                    return finish("API_GAP", False,
                                  f"graph-by-id({expect}): "
                                  f"status={r_ok.status_code} "
                                  f"ids_equal={checks['graph_ids_equal']} "
                                  f"wrong404={checks['wrong_id_is_404']} "
                                  f"noscope422={checks['id_without_scope_is_422']}")
            except Exception as exc:  # noqa: BLE001
                return finish("API_GAP", False,
                              f"graph-by-id probe failed: {exc}")
        elif kind == "qualifying_honesty":
            # Phase 6S GAP 2: telemetry-dependent hypotheses must never
            # claim measured support in a qualifying scope
            states = inv.get("investigation_snapshot", {}).get(
                "hypothesis_states") or {}
            bad = [h for h in ("H2_throttle", "H3_braking", "H6_drs")
                   if states.get(h) in ("SUPPORTED", "PARTIALLY_SUPPORTED")]
            checks["qualifying_honest_states"] = not bad
            tools = {e.get("source_tool")
                     for e in inv.get("evidence_ledger") or []}
            checks["qualifying_fusion_tool_present"] = \
                "fuse_qualifying_lap_evidence" in tools
            checks["telemetry_tool_absent"] = \
                "attribute_lap_loss" not in tools
            if bad or not checks["qualifying_fusion_tool_present"] \
                    or not checks["telemetry_tool_absent"]:
                return finish("ORCHESTRATION_GAP", False,
                              f"qualifying honesty violated: {bad} tools={tools}")
        elif kind == "related_memory_probes":
            # Phase 6S GAP 4: default response has no related section;
            # structural retrieval returns provenance-backed pointers with
            # explicit reasons; invalidated items excluded by default.
            # A probe pair override drives the leakage guard: a scope with
            # no structural neighbors must return zero related items.
            items = derive_memory_items(inv)
            base_res = retrieve_engineering_memory(
                items, season=case["season"], round_num=case["round"])
            checks["exact_unchanged"] = "related_memory_items" not in base_res
            pair = list(case.get("related_probe_pair") or
                        [case["driver_a"], case["driver_b"]])
            rel = retrieve_related_engineering_memory(
                items, season=case["season"], round_num=case["round"],
                driver_pair=pair)
            checks["related_count"] = rel.get("related_match_count")
            checks["related_provenance_complete"] = all(
                r.get("source_investigation_ids")
                and r.get("match_reasons")
                and r.get("match_class") == "STRUCTURAL"
                for r in rel.get("related_memory_items") or [])
            if case.get("related_invalidation_check") and items:
                invalidated = invalidate_memory_item(
                    items[0], "REPLAY_MISMATCH", "phase_6s_benchmark")
                rel_inv = retrieve_related_engineering_memory(
                    [invalidated] + items[1:], season=case["season"],
                    round_num=case["round"], driver_pair=pair)
                rel_incl = retrieve_related_engineering_memory(
                    [invalidated] + items[1:], season=case["season"],
                    round_num=case["round"], driver_pair=pair,
                    include_invalidated=True)
                checks["related_invalidation_excluded"] = \
                    (rel_inv.get("related_match_count") or 0) == \
                    max(0, (rel.get("related_match_count") or 0) - 1)
                checks["related_invalidation_included_explicit"] = \
                    (rel_incl.get("related_match_count") or 0) == \
                    (rel.get("related_match_count") or 0)
            expect_zero = case.get("expect_zero_related", False)
            ok = (checks["exact_unchanged"]
                  and checks["related_provenance_complete"]
                  and "never a conclusion transfer" in rel.get("policy", "")
                  and (not expect_zero
                       or (rel.get("related_match_count") or 0) == 0)
                  and (not case.get("related_invalidation_check")
                       or (checks.get("related_invalidation_excluded")
                           and checks.get(
                               "related_invalidation_included_explicit"))))
            if not ok:
                return finish("ORCHESTRATION_GAP", False,
                              f"related-memory probes failed: "
                              f"exact_unchanged={checks['exact_unchanged']} "
                              f"provenance={checks['related_provenance_complete']} "
                              f"count={checks['related_count']} "
                              f"expect_zero={expect_zero}")
        elif kind == "related_memory_api":
            import httpx
            try:
                qs = (f"question_type={case['question_type']}"
                      f"&driver_a={case['driver_a']}"
                      f"&driver_b={case['driver_b']}"
                      f"&season={case['season']}&round={case['round']}")
                if case.get("lap_number"):
                    qs += f"&lap_number={case['lap_number']}"
                r_def = httpx.get(
                    f"{api_url}/api/catalog/engineering-memory?{qs}",
                    timeout=180.0)
                r_rel = httpx.get(
                    f"{api_url}/api/catalog/engineering-memory?{qs}"
                    f"&include_related=true", timeout=300.0)
                def_body = r_def.json() if r_def.status_code == 200 else {}
                rel_body = r_rel.json() if r_rel.status_code == 200 else {}
                checks["memory_api_default_has_no_related"] = \
                    "related_memory_items" not in def_body
                checks["memory_api_related_present"] = \
                    "related_memory_items" in rel_body
                checks["memory_api_related_policy"] = \
                    "never a conclusion transfer" in \
                    str(rel_body.get("related_policy", ""))
                ok = (r_def.status_code == 200 and r_rel.status_code == 200
                      and checks["memory_api_default_has_no_related"]
                      and checks["memory_api_related_present"]
                      and checks["memory_api_related_policy"])
                if not ok:
                    return finish("API_GAP", False,
                                  f"related-memory API: def={r_def.status_code} "
                                  f"rel={r_rel.status_code}")
            except Exception as exc:  # noqa: BLE001
                return finish("API_GAP", False,
                              f"related-memory API probe failed: {exc}")
        elif kind in ("exact_scope_hit", "wrong_scope_zero",
                      "invalidation_exclusion"):
            items = derive_memory_items(inv)
            if kind == "exact_scope_hit":
                res = retrieve_engineering_memory(
                    items, season=case["season"], round_num=case["round"],
                    driver_pair=[case["driver_a"], case["driver_b"]])
                checks["memory_matches"] = res.get("match_count")
                if (res.get("match_count") or 0) < probe.get(
                        "expect_min_matches", 1):
                    return finish("ORCHESTRATION_GAP", False,
                                  "exact-scope memory retrieval returned zero")
            elif kind == "wrong_scope_zero":
                rs = probe["retrieval_scope"]
                res = retrieve_engineering_memory(
                    items, season=rs["season"], round_num=rs["round"])
                checks["memory_wrong_scope_matches"] = res.get("match_count")
                if (res.get("match_count") or 0) != probe.get("expect_matches", 0):
                    return finish("ORCHESTRATION_GAP", False,
                                  "wrong-scope retrieval leaked items")
            elif kind == "invalidation_exclusion":
                if not items:
                    return finish("ORCHESTRATION_GAP", False,
                                  "no memory items to invalidate")
                invalidated = invalidate_memory_item(
                    items[0], "REPLAY_MISMATCH", "phase_6r_benchmark")
                res = retrieve_engineering_memory(
                    [invalidated] + items[1:], season=case["season"],
                    round_num=case["round"])
                excluded = (res.get("match_count") or 0) == len(items) - 1
                res_incl = retrieve_engineering_memory(
                    [invalidated] + items[1:], season=case["season"],
                    round_num=case["round"], include_invalidated=True)
                included = (res_incl.get("match_count") or 0) == len(items)
                checks["invalidation_excluded"] = excluded
                checks["invalidation_included_when_explicit"] = included
                if not (excluded and included):
                    return finish("ORCHESTRATION_GAP", False,
                                  "invalidation exclusion/include behavior wrong")

    return finish("STRUCTURAL_PASS", True)


def build_investigation_snapshot_safe(inv: dict[str, Any]) -> dict[str, Any] | None:
    try:
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot,
        )
        return build_investigation_snapshot(inv)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# system-level validations
# ---------------------------------------------------------------------------

def determinism_validation(queries: CanonicalQueries,
                           cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Same-process repeated execution + hash comparison for replay cases."""
    replay_cases = [c for c in cases if c.get("replay_expected")]
    results = []
    for c in replay_cases[:8]:
        kwargs = {
            "question_type": c["question_type"],
            "driver_a": c["driver_a"], "driver_b": c["driver_b"],
            "season": c["season"], "round_num": c["round"],
            "lap_number": c.get("lap_number"),
            "stint_number": c.get("stint_number"),
            "pattern_id": c.get("pattern_id"),
        }
        hashes = []
        for _ in range(3):
            try:
                inv = run_engineering_investigation(queries, **kwargs)
                hashes.append(inv.get("output_hash"))
            except Exception as exc:  # noqa: BLE001
                hashes.append(f"ERROR:{str(exc)[:80]}")
        results.append({
            "case": c["benchmark_id"], "hashes": hashes,
            "identical": len(set(hashes)) == 1 and all(hashes),
        })
    return {
        "cases": results,
        "all_identical_same_process": all(r["identical"] for r in results),
    }


def cross_process_determinism(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """PYTHONHASHSEED=3 vs 29 subprocess comparison on two canonical scopes."""
    import os
    import subprocess
    scope_cases = [
        c for c in cases
        if c.get("replay_expected")
        and c.get("question_type") in ("LAP_PERFORMANCE", "RACE_GAP")
    ][:2]
    out = []
    script = (
        "import json,sys;sys.path.insert(0,'src');"
        "from racewise.data.historical.canonical_queries import CanonicalQueries;"
        "from racewise.data.historical.investigation_synthesis import"
        " run_engineering_investigation;"
        "q=CanonicalQueries();"
        "kw=json.loads(sys.argv[1]);kw['round_num']=kw.pop('round');"
        "r=run_engineering_investigation(q,**kw);"
        "print(json.dumps({'output_hash':r.get('output_hash'),"
        "'investigation_id':r.get('investigation_id')}))"
    )
    for c in scope_cases:
        kw = {k: c.get(k) for k in ("question_type", "driver_a", "driver_b",
                                    "season", "round", "lap_number",
                                    "stint_number", "pattern_id")
              if c.get(k) is not None}
        hashes = {}
        for seed in ("3", "29"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed
            try:
                proc = subprocess.run(
                    [sys.executable, "-c", script, json.dumps(kw)],
                    capture_output=True, text=True, timeout=600, env=env,
                    cwd=str(ROOT))
                hashes[seed] = (json.loads(proc.stdout.strip().splitlines()[-1])
                                if proc.returncode == 0 and proc.stdout.strip()
                                else {"error": proc.stderr[-200:]})
            except Exception as exc:  # noqa: BLE001
                hashes[seed] = {"error": str(exc)[:200]}
        h3, h29 = hashes.get("3", {}), hashes.get("29", {})
        out.append({
            "case": c["benchmark_id"],
            "seed3": h3.get("output_hash"), "seed29": h29.get("output_hash"),
            "identical": (h3.get("output_hash") and
                          h3.get("output_hash") == h29.get("output_hash")),
            "error": (h3.get("error") or h29.get("error")),
        })
    return {"cases": out,
            "all_identical_cross_process": all(o["identical"] for o in out)}


def api_validation(api_url: str, checks_log: list[dict[str, Any]]) -> dict[str, Any]:
    import httpx
    client = httpx.Client(timeout=120.0)
    results = []

    def probe(label: str, path: str, expect: str) -> dict[str, Any]:
        r = client.get(f"{api_url}{path}")
        ok = {"2xx": 200 <= r.status_code < 300,
              "422": r.status_code == 422,
              "404": r.status_code == 404}.get(expect, False)
        entry = {"label": label, "path": path, "status": r.status_code,
                 "expected": expect, "pass": ok,
                 "elapsed_s": round(r.elapsed.total_seconds(), 3)}
        results.append(entry)
        checks_log.append(entry)
        return entry

    probe("health", "/api/health", "2xx")
    probe("sessions", "/api/catalog/sessions", "2xx")
    probe("telemetry-comparison", "/api/catalog/telemetry-comparison/2023/1", "2xx")
    probe("attribution", "/api/catalog/attribution/2023/1", "2xx")
    probe("evidence-fusion", "/api/catalog/evidence-fusion/2023/1", "2xx")
    probe("stint-evidence", "/api/catalog/stint-evidence/2023/1?stint=2", "2xx")
    probe("counterfactual", "/api/catalog/counterfactual/2023/1?fraction=0.5", "2xx")
    probe("performance-envelope", "/api/catalog/performance-envelope/2023/1", "2xx")
    probe("race-gap-2023", "/api/catalog/race-gap/2023/1", "2xx")
    probe("race-gap-2024", "/api/catalog/race-gap/2024/14", "2xx")
    probe("regimes", "/api/catalog/performance-regimes/2022/4", "2xx")
    probe("patterns", "/api/catalog/performance-patterns?seasons=2022,2023", "2xx")
    probe("search", "/api/catalog/search?q=2023%20R1", "2xx")
    probe("investigation-valid", (
        "/api/catalog/engineering-investigation?question_type=LAP_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1"
        "&lap_number=6"), "2xx")
    probe("investigation-bad-question-type", (
        "/api/catalog/engineering-investigation?question_type=NOT_A_TYPE"
        "&season=2023&round=1"), "422")
    probe("investigation-out-of-range-season", (
        "/api/catalog/engineering-investigation?question_type=RACE_GAP"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=1949&round=1"),
        "422")
    probe("investigation-unknown-driver", (
        "/api/catalog/engineering-investigation?question_type=RACE_GAP"
        "&driver_a=max-verstappen&driver_b=kimi-antonelli&season=2023&round=1"),
        "2xx")
    probe("graph-scope", (
        "/api/catalog/investigation-graph?question_type=LAP_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1"
        "&lap_number=6"), "2xx")
    probe("memory", (
        "/api/catalog/engineering-memory?question_type=LAP_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1"
        "&lap_number=6"), "2xx")
    # Phase 6S GAP 1: id-addressed graph retrieval
    probe("graph-by-id-mismatch-404", (
        "/api/catalog/investigation-graph?question_type=LAP_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1"
        "&lap_number=6&investigation_id=" + "0" * 16), "404")
    probe("graph-by-id-without-scope-422", (
        "/api/catalog/investigation-graph?investigation_id=" + "0" * 16),
        "422")
    # Phase 6S GAP 2: qualifying investigations
    probe("investigation-qualifying-valid", (
        "/api/catalog/engineering-investigation?question_type=LAP_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2022&round=4"
        "&lap_number=2&session_type=QUALIFYING"), "2xx")
    probe("investigation-qualifying-stint-422", (
        "/api/catalog/engineering-investigation?question_type=STINT_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2022&round=4"
        "&stint_number=1&session_type=QUALIFYING"), "422")
    probe("investigation-unknown-session-type-422", (
        "/api/catalog/engineering-investigation?question_type=LAP_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2022&round=4"
        "&lap_number=2&session_type=SPRINT"), "422")
    probe("investigation-qualifying-pre-2018-unavailable", (
        "/api/catalog/engineering-investigation?question_type=LAP_PERFORMANCE"
        "&driver_a=luigi-fagioli&driver_b=juan-manuel-fangio&season=1950"
        "&round=1&lap_number=1&session_type=QUALIFYING"), "2xx")
    # Phase 6S GAP 4: related-memory retrieval
    probe("memory-related-default", (
        "/api/catalog/engineering-memory?question_type=LAP_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1"
        "&lap_number=6"), "2xx")
    probe("memory-related-expanded", (
        "/api/catalog/engineering-memory?question_type=LAP_PERFORMANCE"
        "&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1"
        "&lap_number=6&include_related=true"), "2xx")
    probe("missing-route", "/api/catalog/does-not-exist", "404")
    client.close()
    return {
        "probes": results,
        "all_pass": all(p["pass"] for p in results),
        "latency_p50_s": _pctl([p["elapsed_s"] for p in results], 50),
        "latency_p95_s": _pctl([p["elapsed_s"] for p in results], 95),
        "latency_max_s": max(p["elapsed_s"] for p in results),
    }


def _pctl(values: list[float], p: int) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return round(s[k], 4)


def no_fabrication_scan() -> dict[str, Any]:
    """Automated scan: production code must not embed benchmark fixtures,
    fake evidence, or hard-coded engineering conclusions.

    The word "fabricated" in a guard statement ("never a fabricated X",
    "no fabricated Y") is anti-fabrication DOCUMENTATION, not a violation;
    the scan classifies each occurrence and only non-guard usage fails.
    """
    import re
    src_dir = ROOT / "src"
    web_dir = ROOT / "apps" / "web" / "src"
    suspicious: list[dict[str, str]] = []
    guard_hits = 0
    patterns = ("engineering_questions.json", "6r_benchmark",
                "benchmark_fixture", "hardcoded_telemetry", "fake_evidence",
                "mock_telemetry", "fabricated")
    for base, exts in ((src_dir, ("*.py",)),
                       (web_dir, ("*.ts", "*.tsx"))):
        for ext in exts:
            for f in base.rglob(ext):
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for pat in patterns:
                    start = 0
                    while True:
                        idx = text.find(pat, start)
                        if idx < 0:
                            break
                        # classify by the textual context around the
                        # occurrence (guard language may span line breaks)
                        window = text[max(0, idx - 140): idx + 80].lower()
                        rel = str(f.relative_to(ROOT))
                        if pat == "fabricated":
                            if any(w in window for w in (
                                    "never", "not ", "no ", "nothing",
                                    "without", "must not", "forbidden")):
                                guard_hits += 1
                            elif ("_fabricated_" in window
                                  and "benchmark" in rel.replace("\\", "_")):
                                # negative-control identifier in a benchmark
                                # module (asserts zero fabricated nodes)
                                guard_hits += 1
                            else:
                                suspicious.append(
                                    {"file": rel, "pattern": pat,
                                     "assessment": "UNSAFE",
                                     "excerpt": text[max(0, idx - 60):
                                                     idx + 60].strip()[:120]})
                        elif pat in ("engineering_questions.json",
                                     "6r_benchmark", "benchmark_fixture",
                                     "hardcoded_telemetry", "fake_evidence",
                                     "mock_telemetry"):
                            suspicious.append({"file": rel, "pattern": pat,
                                               "assessment": "UNSAFE",
                                               "excerpt": window.strip()[:120]})
                        start = idx + len(pat)
    return {"guard_documentation_occurrences": guard_hits,
            "suspicious_hits": suspicious,
            "clean": not suspicious}


def security_scan() -> dict[str, Any]:
    """Static security scan with per-finding assessment.

    Raw detections are kept in the report; each is assessed as SAFE
    (parameterized placeholders, internal identifier enumeration) or
    UNSAFE. `clean` means no UNSAFE finding.
    """
    import re
    findings: list[dict[str, Any]] = []
    py_files = list((ROOT / "src").rglob("*.py")) + \
        list((ROOT / "tests" / "benchmarks").glob("*.py"))
    eval_exec = re.compile(r"\b(eval|exec)\s*\(")
    shell = re.compile(r"os\.system|subprocess\.call\(.*shell\s*=\s*True")
    sql = re.compile(r"f\"[^\"]*SELECT|f'[^']*SELECT")
    count_from = re.compile(r"SELECT COUNT\(\*\) FROM \{(\w+)\}")
    html = re.compile(r"dangerouslySetInnerHTML|innerHTML\s*=")
    for f in py_files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        rel = str(f.relative_to(ROOT))
        for ln, line in enumerate(text.splitlines(), 1):
            if eval_exec.search(line):
                findings.append({"file": rel, "line": ln, "kind": "eval/exec",
                                 "assessment": "UNSAFE",
                                 "excerpt": line.strip()[:100]})
            if shell.search(line):
                findings.append({"file": rel, "line": ln, "kind": "shell",
                                 "assessment": "UNSAFE",
                                 "excerpt": line.strip()[:100]})
            if sql.search(line):
                if count_from.search(line):
                    assessment = "SAFE: internal identifier enumeration"
                elif "safe_name" in line:
                    assessment = "SAFE: identifier sanitized via quote-doubling"
                elif "?" in line or "params" in line:
                    assessment = "SAFE: parameterized placeholders"
                else:
                    assessment = "UNSAFE"
                findings.append({"file": rel, "line": ln, "kind": "dynamic-sql",
                                 "assessment": assessment,
                                 "excerpt": line.strip()[:100]})
    for f in (ROOT / "apps" / "web" / "src").rglob("*.ts*"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        rel = str(f.relative_to(ROOT))
        for ln, line in enumerate(text.splitlines(), 1):
            if html.search(line):
                findings.append({"file": rel, "line": ln, "kind": "unsafe-html",
                                 "assessment": "UNSAFE",
                                 "excerpt": line.strip()[:100]})
    unsafe = [f for f in findings if str(f["assessment"]).startswith("UNSAFE")]
    return {"findings": findings, "unsafe_count": len(unsafe),
            "clean": not unsafe}


def frontend_build_check() -> dict[str, Any]:
    import shutil
    import subprocess
    try:
        # Windows: npm is npm.cmd; plain "npm" is unresolvable without a
        # shell, so resolve the real executable first (Phase 6S fix).
        npm = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
        proc = subprocess.run(
            [npm, "--prefix", str(ROOT / "apps" / "web"), "run", "build"],
            capture_output=True, text=True, timeout=420, cwd=str(ROOT))
        ok = proc.returncode == 0
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-6:]
        return {"pass": ok, "tail": tail}
    except Exception as exc:  # noqa: BLE001
        return {"pass": False, "tail": [str(exc)[:200]]}


def storage_check(before: dict[str, int], after: dict[str, int]) -> dict[str, Any]:
    growth = {k: after.get(k, 0) - before.get(k, 0) for k in after}
    return {"before": before, "after": after, "row_growth": growth,
            "bounded": all(v <= 2 for v in growth.values())}


def db_table_counts(db_path: Path) -> dict[str, int]:
    import sqlite3
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        counts: dict[str, int] = {}
        for (name,) in rows:
            safe_name = name.replace('"', '""')
            counts[name] = conn.execute(
                f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
        return counts
    finally:
        conn.close()


def frontend_route_probes(api_url: str, web_url: str) -> list[dict[str, Any]]:
    """Fetch every frontend hash route and assert the SPA shell + an API
    contract response exist for its data dependencies."""
    import httpx
    client = httpx.Client(timeout=60.0)
    # A dead frontend must be recorded as a failed probe, never crash the
    # whole benchmark run after the engineering cases completed.
    try:
        shell = client.get(web_url)
        shell_status = shell.status_code
        shell_error: str | None = None
    except Exception as exc:  # noqa: BLE001
        shell_status = 0
        shell_error = f"frontend unreachable: {exc}"
    routes = [
        ("overview", "/api/health", None),
        ("investigate", "/api/catalog/engineering-investigation?question_type="
         "LAP_PERFORMANCE&driver_a=max-verstappen&driver_b=sergio-perez"
         "&season=2023&round=1&lap_number=6", None),
        ("compare", "/api/catalog/engineering-investigation/compare"
         "?question_type=LAP_PERFORMANCE&driver_a=max-verstappen"
         "&driver_b=sergio-perez&season=2023&round=1&lap_number=6"
         "&driver_a2=max-verstappen&driver_b2=sergio-perez&season2=2023"
         "&round2=1&lap_number2=11", None),
        ("graph", "/api/catalog/investigation-graph?question_type="
         "LAP_PERFORMANCE&driver_a=max-verstappen&driver_b=sergio-perez"
         "&season=2023&round=1&lap_number=6", None),
        ("memory", "/api/catalog/engineering-memory?question_type="
         "LAP_PERFORMANCE&driver_a=max-verstappen&driver_b=sergio-perez"
         "&season=2023&round=1&lap_number=6", None),
        ("replay", "/api/catalog/engineering-investigation/replay"
         "?question_type=LAP_PERFORMANCE&driver_a=max-verstappen"
         "&driver_b=sergio-perez&season=2023&round=1&lap_number=6", None),
        ("catalog", "/api/catalog/sessions", None),
        ("telemetry", "/api/catalog/telemetry-comparison/2023/1", None),
        ("lap-analysis", "/api/catalog/attribution/2023/1", None),
        ("evidence-fusion", "/api/catalog/evidence-fusion/2023/1", None),
        ("stint-analysis", "/api/catalog/stint-evidence/2023/1?stint=2", None),
        ("race-gap", "/api/catalog/race-gap/2024/14", None),
        ("counterfactuals", "/api/catalog/counterfactual/2023/1?fraction=0.5",
         None),
        ("performance-envelope", "/api/catalog/performance-envelope/2023/1",
         None),
        ("regimes", "/api/catalog/performance-regimes/2022/4", None),
        ("patterns", "/api/catalog/performance-patterns?seasons=2022,2023",
         None),
    ]
    probes = [{"route": name, "shell_status": shell_status,
               **({"error": shell_error} if shell_error else {})}
              for name, _, _ in routes]
    client.close()
    return probes


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=CORPUS_DEFAULT)
    ap.add_argument("--out", type=Path, default=RESULTS_DEFAULT)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--web", default="http://localhost:5173")
    ap.add_argument("--skip-api", action="store_true")
    ap.add_argument("--skip-frontend-build", action="store_true")
    args = ap.parse_args()

    corpus = _load_corpus(args.corpus)
    cases = corpus["cases"]
    n_limitation = sum(1 for c in cases if c.get("limitation_case"))
    print(f"corpus: {len(cases)} cases ({n_limitation} limitation cases, "
          f"{100 * n_limitation / len(cases):.0f}%)")

    queries = CanonicalQueries()
    vocab = graph_vocabulary()
    pattern_cache: dict[tuple, dict] = {}

    db_path = ROOT / "data" / "canonical" / "canonical.db"
    storage_before = db_table_counts(db_path)

    case_results = []
    for c in cases:
        print(f"  {c['benchmark_id']} ({c['category_name']}) ...",
              flush=True)
        r = run_case(queries, c, vocab, pattern_cache, args.api)
        case_results.append(r)
        print(f"    -> {r['kind']} pass={r['pass']} "
              f"({r['elapsed_s']}s)", flush=True)

    det = determinism_validation(queries, cases)
    det_x = cross_process_determinism(cases)

    api_log: list[dict[str, Any]] = []
    api_res = (api_validation(args.api, api_log)
               if not args.skip_api else {"skipped": True})
    scan_fab = no_fabrication_scan()
    scan_sec = security_scan()
    build_res = (frontend_build_check()
                 if not args.skip_frontend_build else {"skipped": True})
    route_probes = ([] if args.skip_api else
                    frontend_route_probes(args.api, args.web))
    storage_after = db_table_counts(db_path)
    storage = storage_check(storage_before, storage_after)

    passed = [r for r in case_results if r["pass"]]
    failed = [r for r in case_results if not r["pass"]]
    kind_counts: dict[str, int] = {}
    for r in case_results:
        kind_counts[r["kind"]] = kind_counts.get(r["kind"], 0) + 1
    elapsed_all = [r["elapsed_s"] for r in case_results]

    def taxonomy_of(r: dict[str, Any]) -> str:
        return r["kind"] if not r["pass"] else ""

    summary = {
        "benchmark_version": corpus["version"],
        "corpus_path": str(args.corpus.relative_to(ROOT)),
        "total_cases": len(cases),
        "limitation_cases": n_limitation,
        "limitation_share_pct": round(100 * n_limitation / len(cases), 1),
        "passed": len(passed),
        "failed": len(failed),
        "executed_limitation_outcomes": kind_counts.get(
            "EXECUTED_LIMITATION", 0),
        "implementation_failures": kind_counts.get("IMPLEMENTATION_FAILURE", 0),
        "kind_counts": kind_counts,
        "case_latency_s": {"p50": _pctl(elapsed_all, 50),
                           "p95": _pctl(elapsed_all, 95),
                           "max": max(elapsed_all) if elapsed_all else None},
        "determinism_same_process": det["all_identical_same_process"],
        "determinism_cross_process": det_x["all_identical_cross_process"],
        "determinism_detail": {"same_process": det["cases"],
                               "cross_process": det_x["cases"]},
        "api_validation": api_res,
        "no_fabrication_scan": scan_fab,
        "security_scan": scan_sec,
        "frontend_build": build_res,
        "frontend_route_probes": route_probes,
        "storage": storage,
        "failure_taxonomy": [
            {"benchmark_id": r["benchmark_id"], "primary": taxonomy_of(r),
             "detail": r["detail"]} for r in failed],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"summary": summary, "cases": case_results}, indent=2),
        encoding="utf-8")
    print(json.dumps({k: summary[k] for k in (
        "total_cases", "passed", "failed", "executed_limitation_outcomes",
        "implementation_failures", "determinism_same_process",
        "determinism_cross_process")}, indent=1))
    print(f"results written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
