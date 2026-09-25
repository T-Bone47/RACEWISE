"""Phase 6P Q18 benchmark: engineering knowledge / investigation graph.

Every case builds the graph from REAL canonical 6N/6O outputs - no invented
nodes or relationships. Golden graph snapshots record node_count,
edge_count and output_hash; replay must reproduce the identical hash.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.investigation_graph import (
    MAX_DEPTH, MAX_EDGES, MAX_NODES, add_lineage_edges,
    build_graph_snapshot, build_investigation_graph, explain_investigation_path,
    graph_vocabulary, merge_investigation_graphs, replay_graph_snapshot,
    trace_evidence_to_source, trace_hypothesis_evidence, traverse_graph,
    verify_graph_snapshot,
)
from racewise.data.historical.investigation_memory import (
    compare_engineering_investigations,
)
from racewise.data.historical.q17_benchmarks import (
    LAP6, LAP11, RACEGAP24, REGIME22, STINT1, TELEMETRY_POOR,
)
from racewise.data.historical.q16_benchmarks import _discover_pattern

Q18_VERSION = "q18_investigation_graph_v1"


def _params(case: dict[str, Any]) -> dict[str, Any]:
    kw = {k: v for k, v in case.items()
          if k in ("question_type", "driver_a", "driver_b", "season",
                   "round", "lap_number", "stint_number", "pattern_id")}
    kw["round_num"] = kw.pop("round")
    return kw


def _run(queries: CanonicalQueries, case: dict[str, Any]) -> dict[str, Any]:
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )
    return run_engineering_investigation(queries, **_params(case))


def _golden_graph(label: str, case: dict[str, Any],
                  queries: CanonicalQueries) -> dict[str, Any]:
    """Run the investigation, build + snapshot + verify + replay the graph."""
    t0 = time.perf_counter()
    inv = _run(queries, case)
    graph = build_investigation_graph(queries, inv)
    if graph.get("status") in ("INVALID", "UNAVAILABLE"):
        return {"case": f"golden_{label}", "kind": "golden_graph",
                "status": graph["status"], "reason": graph.get("reason")}
    snap = build_graph_snapshot(graph)
    verdict = verify_graph_snapshot(snap)
    replay = replay_graph_snapshot(queries, snap)
    return {
        "case": f"golden_{label}", "kind": "golden_graph",
        "investigation_status": inv.get("status"),
        "verify_status": verdict["status"],
        "replay_status": replay["status"],
        "replay_identity_holds": replay["replay_hash"] == snap["output_hash"],
        "graph_hash": graph["output_hash"],
        "snapshot_hash": snap["output_hash"],
        "node_count": graph["node_count"],
        "edge_count": graph["edge_count"],
        "node_types": _type_histogram(graph),
        "edge_types": _edge_histogram(graph),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
    }


def _type_histogram(graph: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for n in graph.get("nodes") or []:
        out[n["node_type"]] = out.get(n["node_type"], 0) + 1
    return dict(sorted(out.items()))


def _edge_histogram(graph: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in graph.get("edges") or []:
        out[e["edge_type"]] = out.get(e["edge_type"], 0) + 1
    return dict(sorted(out.items()))


def run_q18(
    queries: CanonicalQueries,
    include_mcp: bool = True,
    discover_pattern: bool = True,
) -> dict[str, Any]:
    """Run the Q18 investigation-graph matrix."""
    cases: list[dict[str, Any]] = []
    t_all = time.perf_counter()

    inv_lap6 = _run(queries, LAP6)
    graph_lap6 = build_investigation_graph(queries, inv_lap6)
    snap_lap6 = build_graph_snapshot(graph_lap6)

    # --- Q18.1-Q18.4 golden investigation graphs ---------------------------
    for label, case in (("2023R1_LAP6", LAP6),
                        ("2023R1_STINT1", STINT1),
                        ("2024R14_RACE_GAP", RACEGAP24),
                        ("2022R4_PERFORMANCE_REGIME", REGIME22)):
        cases.append(_golden_graph(label, case, queries))

    # --- Q18.5 cross-race pattern graph ------------------------------------
    pattern_id = None
    pattern_block: dict[str, Any] = {"discovered": False}
    if discover_pattern:
        disc = _discover_pattern(queries, {"driver_a": LAP6["driver_a"],
                                           "driver_b": LAP6["driver_b"]})
        pattern_id = disc.get("pattern_id")
        if pattern_id:
            inv_x = _run(queries, {"question_type": "CROSS_RACE_PATTERN",
                                   "driver_a": LAP6["driver_a"],
                                   "driver_b": LAP6["driver_b"],
                                   "season": 2023, "round": 1,
                                   "pattern_id": pattern_id})
            gx = build_investigation_graph(queries, inv_x)
            pattern_block = {
                "discovered": True, "pattern_id": pattern_id,
                "investigation_status": inv_x.get("status"),
                "pattern_nodes": sum(
                    1 for n in gx.get("nodes") or []
                    if n["node_type"] == "PATTERN"),
                "node_count": gx.get("node_count"),
                "edge_count": gx.get("edge_count"),
            }
    cases.append({"case": "Q18.5_cross_race_pattern_graph",
                  **pattern_block})

    # --- Q18.6 hypothesis evidence trace ------------------------------------
    hyp = trace_hypothesis_evidence(
        graph_lap6, "H1_corner_speed",
        investigation_id=inv_lap6["investigation_id"])
    cases.append({
        "case": "Q18.6_hypothesis_evidence_trace",
        "status": hyp["status"],
        "supporting": len(hyp["supporting_evidence"]),
        "contradicting": len(hyp["contradicting_evidence"]),
        "non_decisive": len(hyp["non_decisive_evidence"]),
        "counterfactuals": len(hyp["counterfactuals"]),
        "no_ranking": all(
            "rank" not in json_keys(s) for s in
            hyp["supporting_evidence"] + hyp["contradicting_evidence"]),
    })

    # --- Q18.7 contradiction path (CONTRADICTS imported from 6N) ------------
    conflict_edges = [e for e in graph_lap6.get("edges") or []
                      if e["edge_type"] == "CONTRADICTS"
                      and e["source_node"].startswith("evidence:")
                      and e["target_node"].startswith("evidence:")]
    cases.append({
        "case": "Q18.7_contradiction_path",
        "contradicts_edges": len(conflict_edges),
        "imported_with_conflict_id": all(
            e["provenance"].get("conflict_id") for e in conflict_edges),
        "resolution_status": sorted({
            e["provenance"].get("resolution_status") or ""
            for e in conflict_edges}),
    })

    # --- Q18.8 counterfactual path (MODELLED, visually distinct node) -------
    cf_nodes = [n for n in graph_lap6.get("nodes") or []
                if n["node_type"] == "COUNTERFACTUAL"]
    cf_meta = cf_nodes[0]["metadata"] if cf_nodes else {}
    cases.append({
        "case": "Q18.8_counterfactual_path",
        "counterfactual_nodes": len(cf_nodes),
        "claim_class": cf_meta.get("claim_class"),
        "models_edges": sum(1 for e in graph_lap6.get("edges") or []
                            if e["edge_type"] == "MODELS"),
        "intervention": cf_meta.get("intervention"),
        "measured_delta_s": cf_meta.get("measured_delta_s"),
        "validation_state": cf_meta.get("validation_state"),
    })

    # --- Q18.9 memory lineage path ------------------------------------------
    mem_edges = [e for e in graph_lap6.get("edges") or []
                 if e["edge_type"] == "GENERATED_MEMORY"]
    mem_derived = [e for e in graph_lap6.get("edges") or []
                   if e["edge_type"] == "DERIVED_FROM"
                   and e["source_node"].startswith("memory:")]
    cases.append({
        "case": "Q18.9_memory_lineage_path",
        "memory_nodes": sum(1 for n in graph_lap6.get("nodes") or []
                            if n["node_type"] == "MEMORY"),
        "generated_memory_edges": len(mem_edges),
        "memory_derived_from_evidence": len(mem_derived),
        "no_orphan_memory": all(
            any(e["source_node"] == n["node_id"]
                for e in graph_lap6.get("edges") or [])
            for n in graph_lap6.get("nodes") or []
            if n["node_type"] == "MEMORY"),
    })

    # --- Q18.10 replay/compare lineage --------------------------------------
    inv_lap11 = _run(queries, LAP11)
    graph_lap11 = build_investigation_graph(queries, inv_lap11)
    merged = merge_investigation_graphs(graph_lap6, graph_lap11)
    cmp_res = compare_engineering_investigations(inv_lap6, inv_lap11)
    lin = (cmp_res.get("lineage") or [{}])[0]
    merged = add_lineage_edges(
        merged, lin.get("relationship", "COMPARED_WITH"),
        lin["source_investigation"], lin["target_investigation"],
        provenance=lin.get("provenance"))
    path_ab = explain_investigation_path(
        merged, inv_lap6["investigation_id"],
        f"investigation:{inv_lap11['investigation_id']}")
    cases.append({
        "case": "Q18.10_replay_compare_lineage",
        "relationship": lin.get("relationship"),
        "lineage_edge_added": bool(merged.get("lineage_edges_added")),
        "path_between_investigations": path_ab["status"],
        "merged_node_count": merged["node_count"],
        "merged_edge_count": merged["edge_count"],
    })

    # --- Q18.11 evidence-unavailable graph ----------------------------------
    inv_poor = _run(queries, TELEMETRY_POOR)
    graph_poor = build_investigation_graph(queries, inv_poor)
    poor_evidence = sum(1 for n in graph_poor.get("nodes") or []
                        if n["node_type"] in ("EVIDENCE", "COUNTERFACTUAL"))
    cases.append({
        "case": "Q18.11_evidence_unavailable_graph",
        "investigation_status": inv_poor.get("status"),
        "collection_status": (inv_poor.get("collection") or {}).get("status"),
        "evidence_nodes": poor_evidence,
        "graph_node_count": graph_poor.get("node_count"),
        "graph_edge_count": graph_poor.get("edge_count"),
        "honest_empty": poor_evidence == 0,
    })

    # --- Q18.12 bounded traversal negative controls --------------------------
    inv_id = inv_lap6["investigation_id"]
    root = f"investigation:{inv_id}"
    nc = {
        "depth_over_cap": traverse_graph(graph_lap6, root,
                                         max_depth=MAX_DEPTH + 1)["status"],
        "nodes_over_cap": traverse_graph(graph_lap6, root,
                                         max_nodes=MAX_NODES + 1)["status"],
        "edges_over_cap": traverse_graph(graph_lap6, root,
                                         max_edges=MAX_EDGES + 1)["status"],
        "unknown_node": traverse_graph(graph_lap6,
                                       "evidence:does-not-exist")["status"],
        "bad_kind": traverse_graph(graph_lap6, root,
                                   traversal_kind="FREEFORM")["status"],
        "bad_direction": traverse_graph(graph_lap6, root,
                                        direction="SIDEWAYS")["status"],
        "unknown_investigation_path": explain_investigation_path(
            graph_lap6, "ffffffffffffffff", root)["status"],
        "unknown_target_path": explain_investigation_path(
            graph_lap6, inv_id, "evidence:does-not-exist")["status"],
        "unknown_evidence_source": trace_evidence_to_source(
            graph_lap6, "evidence:does-not-exist")["status"],
        "unknown_hypothesis_trace": trace_hypothesis_evidence(
            graph_lap6, "H99_free_form")["status"],
        "graph_vocabulary_closed": (
            len(graph_vocabulary()["node_types"]) == 19
            and len(graph_vocabulary()["edge_types"]) == 26),
    }
    cases.append({"case": "Q18.12_bounded_traversal_negative_controls",
                  **nc})

    timings = sorted(c.get("elapsed_ms") for c in cases
                     if c.get("elapsed_ms") is not None)
    report: dict[str, Any] = {
        "benchmark": "Q18_investigation_graph",
        "version": Q18_VERSION,
        "vocabulary": graph_vocabulary(),
        "matrix": cases,
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


def json_keys(item: dict[str, Any]) -> list[str]:
    return sorted(item.keys())


def _negative_controls(queries: CanonicalQueries) -> dict[str, Any]:
    """Q18 negative controls. No silent repair, no silent fallback."""
    inv = _run(queries, LAP6)
    graph = build_investigation_graph(queries, inv)
    snap = build_graph_snapshot(graph)
    nc: dict[str, Any] = {}

    # tampered graph snapshot -> HASH_MISMATCH
    tampered = dict(snap)
    tampered["nodes"] = snap["nodes"][:-1]
    nc["tampered_snapshot"] = verify_graph_snapshot(tampered)["status"]

    # invalid schema -> INVALID_SCHEMA
    nc["invalid_schema"] = verify_graph_snapshot({"foo": 1})["status"]

    # replay of an invalid snapshot -> INVALID_SNAPSHOT (never rerun)
    corrupt = dict(snap)
    corrupt["node_count"] = snap["node_count"] + 1
    nc["replay_invalid_snapshot"] = replay_graph_snapshot(
        queries, corrupt)["status"]

    # invalid investigation -> INVALID graph (never a partial graph)
    bad = _run(queries, {**LAP6, "driver_b": LAP6["driver_a"]})
    # same driver is invalid input to the engine itself; emulate by type
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )
    invalid_inv = run_engineering_investigation(
        queries, question_type="NOT_A_TYPE", driver_a="max-verstappen",
        driver_b="sergio-perez", season=2023, round_num=1)
    g_bad = build_investigation_graph(queries, invalid_inv)
    nc["invalid_investigation"] = g_bad.get("status")
    nc["invalid_investigation_has_nodes"] = "nodes" in g_bad

    # invalid node type is impossible through the public builder; the
    # internal vocabulary check is asserted directly
    from racewise.data.historical.investigation_graph import _Graph
    g = _Graph()
    try:
        g.node("x:1", "NOT_A_TYPE", "x")
        nc["invalid_node_type_rejected"] = False
    except ValueError:
        nc["invalid_node_type_rejected"] = True
    try:
        g.node("evidence:x", "EVIDENCE", "x")
        g.node("evidence:y", "EVIDENCE", "y")
        g.edge("evidence:x", "evidence:y", "CONNECTED_TO")
        nc["invalid_edge_type_rejected"] = False
    except ValueError:
        nc["invalid_edge_type_rejected"] = True

    # unavailable scope: lap beyond the race builds a graph but the lap
    # node exists only where canonical data exists (never fabricated)
    inv999 = _run(queries, {**LAP6, "lap_number": 999})
    g999 = build_investigation_graph(queries, inv999)
    nc["lap999_graph_status"] = g999.get("status", "OK")
    nc["lap999_fabricated_lap_nodes"] = sum(
        1 for n in (g999.get("nodes") or []) if n["node_type"] == "LAP")
    return nc


def _mcp_verification(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.tools.contract import ToolError
    from racewise.tools.historical import build_historical_registry

    reg = build_historical_registry(queries)
    out: dict[str, Any] = {
        "historical_tool_count": len(reg._tools),
        "tools_registered": all(
            n in reg._tools for n in (
                "build_investigation_graph",
                "trace_investigation_path",
                "trace_evidence_source",
                "trace_hypothesis_evidence")),
    }
    lap6 = dict(LAP6)
    built = reg.execute("build_investigation_graph", lap6)["output"]
    out["graph_status"] = built.get("graph_version")
    out["node_count"] = built.get("node_count")
    out["edge_count"] = built.get("edge_count")
    rep = reg.execute("build_investigation_graph", lap6)["output"]
    out["repeat_identical"] = rep == built
    try:
        reg.execute("build_investigation_graph", {**lap6, "max_depth": 99})
        out["oversized_rejected"] = False
    except ToolError as e:
        out["oversized_rejected"] = e.code == "invalid_input"
    return out


if __name__ == "__main__":  # pragma: no cover - documentation measurement
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )

    print(run_q18(get_canonical_queries(), include_mcp=True))
