"""Phase 6P unit tests: graph construction, semantics, provenance, traversal,
paths, snapshots, determinism and negative controls.

Only deterministic semantics over real canonical data; no ranking, no
scores, no causality anywhere.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

LAP6_KW = dict(question_type="LAP_PERFORMANCE", driver_a="max-verstappen",
               driver_b="sergio-perez", season=2023, round_num=1,
               lap_number=6)


@pytest.fixture(scope="module")
def queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries(str(DB_PATH))


@pytest.fixture(scope="module")
def lap6(queries):
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    return run_engineering_investigation(queries, **LAP6_KW)


@pytest.fixture(scope="module")
def graph(queries, lap6):
    from racewise.data.historical.investigation_graph import (
        build_investigation_graph,
    )

    return build_investigation_graph(queries, lap6)


# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------


class TestVocabulary:
    def test_node_types_closed_19(self):
        from racewise.data.historical.investigation_graph import NODE_TYPES

        assert len(NODE_TYPES) == 19
        assert "INVESTIGATION" in NODE_TYPES and "SNAPSHOT" in NODE_TYPES

    def test_edge_types_closed_26(self):
        from racewise.data.historical.investigation_graph import EDGE_TYPES

        assert len(EDGE_TYPES) == 26
        assert "CONNECTED_TO" not in EDGE_TYPES

    def test_bounds(self):
        from racewise.data.historical.investigation_graph import (
            MAX_DEPTH, MAX_EDGES, MAX_NODES,
        )

        assert (MAX_DEPTH, MAX_NODES, MAX_EDGES) == (8, 500, 1500)

    def test_invalid_node_type_rejected(self):
        from racewise.data.historical.investigation_graph import _Graph

        g = _Graph()
        with pytest.raises(ValueError):
            g.node("x:1", "GHOST", "x")

    def test_invalid_edge_type_rejected(self):
        from racewise.data.historical.investigation_graph import _Graph

        g = _Graph()
        g.node("a", "EVIDENCE", "a")
        g.node("b", "EVIDENCE", "b")
        with pytest.raises(ValueError):
            g.edge("a", "b", "CONNECTED_TO")

    def test_edge_requires_existing_endpoints(self):
        from racewise.data.historical.investigation_graph import _Graph

        g = _Graph()
        g.node("a", "EVIDENCE", "a")
        with pytest.raises(ValueError):
            g.edge("a", "missing", "SUPPORTS")


# ---------------------------------------------------------------------------
# construction over a real investigation
# ---------------------------------------------------------------------------


@requires_db
class TestConstruction:
    def test_graph_shape(self, graph, lap6):
        assert graph["graph_version"] == "6p_graph_v1"
        assert graph["node_count"] == len(graph["nodes"])
        assert graph["edge_count"] == len(graph["edges"])
        assert graph["investigation_id"] == lap6["investigation_id"]
        assert len(graph["output_hash"]) == 16

    def test_required_core_nodes_present(self, graph):
        types = {n["node_type"] for n in graph["nodes"]}
        assert {"INVESTIGATION", "QUESTION", "DRIVER", "DRIVER_PAIR", "SEASON",
                "RACE", "SESSION", "LAP", "HYPOTHESIS", "EVIDENCE",
                "COUNTERFACTUAL", "SYNTHESIS", "DECISION_TRACE", "MEMORY",
                "ANALYTICAL_SOURCE", "SNAPSHOT"} <= types

    def test_node_payload_contract(self, graph):
        for n in graph["nodes"]:
            assert set(n) == {"node_id", "node_type", "label",
                              "canonical_reference", "metadata", "provenance"}
            assert n["node_type"] not in ("", None)

    def test_edge_payload_contract(self, graph):
        for e in graph["edges"]:
            assert set(e) == {"edge_id", "source_node", "target_node",
                              "edge_type", "provenance", "source_reference"}
            assert e["provenance"], f"edge without provenance: {e['edge_id']}"
            assert e["edge_type"] != "CONNECTED_TO"

    def test_evidence_ledger_fully_connected(self, graph, lap6):
        led_ids = {e["evidence_id"] for e in lap6["evidence_ledger"]}
        connected = {e["target_node"][len("evidence:"):]
                     for e in graph["edges"]
                     if e["edge_type"] == "HAS_EVIDENCE"
                     and e["source_node"] ==
                     f"investigation:{lap6['investigation_id']}"
                     and e["target_node"].startswith("evidence:")}
        assert led_ids <= connected

    def test_every_evidence_has_analytical_source(self, graph, lap6):
        inv_id = lap6["investigation_id"]
        has_edge = set()
        for e in graph["edges"]:
            if e["edge_type"] == "DERIVED_FROM" and \
                    e["source_node"].startswith("evidence:"):
                has_edge.add(e["source_node"])
        for e in graph["edges"]:
            if e["edge_type"] == "HAS_EVIDENCE" and \
                    e["source_node"] == f"investigation:{inv_id}":
                assert e["target_node"] in has_edge

    def test_supports_contradicts_imported_not_inferred(self, graph, lap6):
        sup = sum(1 for e in graph["edges"] if e["edge_type"] == "SUPPORTS")
        con = sum(1 for e in graph["edges"] if e["edge_type"] == "CONTRADICTS")
        evals = lap6["hypothesis_evaluations"]
        sup_expect = sum(len(v["supporting_evidence"])
                         for v in evals.values())
        con_expect = sum(len(v["contradicting_evidence"])
                         for v in evals.values())
        assert sup == sup_expect
        # contradiction edges = hypothesis-facing imports + pairwise conflict
        # imports (both from 6N blocks; nothing inferred from topology)
        conflict_pairs = len(lap6["evidence_conflicts"])
        assert con == con_expect + conflict_pairs
        for e in graph["edges"]:
            if e["edge_type"] == "SUPPORTS":
                assert "not causation" in json.dumps(e["provenance"])

    def test_contradiction_edges_carry_conflict_provenance(self, graph, lap6):
        conflict_ids = {c["conflict_id"]
                        for c in lap6["evidence_conflicts"]}
        for e in graph["edges"]:
            if e["edge_type"] == "CONTRADICTS" and \
                    e["source_node"].startswith("evidence:") and \
                    e["target_node"].startswith("evidence:"):
                assert e["provenance"].get("conflict_id") in conflict_ids
                assert e["provenance"].get("resolution_status") == "UNRESOLVED"

    def test_counterfactual_node_is_distinct_and_modelled(self, graph, lap6):
        cf_nodes = [n for n in graph["nodes"]
                    if n["node_type"] == "COUNTERFACTUAL"]
        assert len(cf_nodes) == len(lap6["executed_counterfactuals"])
        for n in cf_nodes:
            assert n["metadata"]["claim_class"] == "MODELLED"
            assert "not history" in n["metadata"]["note"]
            assert {"model", "intervention", "parameter", "baseline",
                    "measured_delta_s", "validation_state"} <= \
                set(n["metadata"])
        # MODELS edge anchors the modelled result to its lap
        models = [e for e in graph["edges"] if e["edge_type"] == "MODELS"]
        assert len(models) == len(cf_nodes)

    def test_memory_never_orphaned(self, graph, lap6):
        from racewise.data.historical.investigation_memory import (
            derive_memory_items,
        )
        expect = len(derive_memory_items(lap6))
        mem = [n for n in graph["nodes"] if n["node_type"] == "MEMORY"]
        assert len(mem) == expect
        generated = {e["target_node"] for e in graph["edges"]
                     if e["edge_type"] == "GENERATED_MEMORY"}
        for n in mem:
            assert n["node_id"] in generated  # every memory has a source
        derived = {e["source_node"] for e in graph["edges"]
                   if e["edge_type"] == "DERIVED_FROM"
                   and e["source_node"].startswith("memory:")}
        for n in mem:
            assert n["node_id"] in derived  # and at least one evidence

    def test_falsification_states_not_collapsed(self, graph, lap6):
        tests = [e for e in graph["edges"]
                 if e["edge_type"] == "TESTS"
                 and e["target_node"].startswith("hypothesis:")
                 and e["source_node"].startswith("investigation:")]
        states = {e["source_reference"]["aggregate_state"] for e in tests}
        assert states <= {"SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED",
                          "CONTRADICTED", "MIXED_EVIDENCE", "NOT_TESTABLE",
                          "INSUFFICIENT_EVIDENCE", "NOT_REQUESTED"}
        # one TESTS edge per canonical hypothesis, each carrying its 6N state
        assert len(tests) == 6
        states_by_h = {e["source_reference"]["hypothesis_id"]:
                       e["source_reference"]["aggregate_state"]
                       for e in tests}
        evals = lap6["hypothesis_evaluations"]
        assert states_by_h == {h: v["aggregate_state"]
                               for h, v in evals.items()}

    def test_snapshot_node_replay_of(self, graph, lap6):
        snap_edges = [e for e in graph["edges"]
                      if e["edge_type"] == "REPLAY_OF"]
        assert len(snap_edges) == 1
        assert snap_edges[0]["provenance"].get("snapshot_hash")

    def test_regime_nodes_for_regime_investigation(self, queries):
        from racewise.data.historical.investigation_graph import (
            build_investigation_graph,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="PERFORMANCE_REGIME",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2022, round_num=4)
        g = build_investigation_graph(queries, inv)
        regimes = [n for n in g["nodes"] if n["node_type"] == "REGIME"]
        assert len(regimes) == 6
        has_regime = sum(1 for e in g["edges"]
                         if e["edge_type"] == "HAS_REGIME")
        assert has_regime == len(regimes)

    def test_stint_nodes_for_stint_investigation(self, queries):
        from racewise.data.historical.investigation_graph import (
            build_investigation_graph,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="STINT_PERFORMANCE",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, stint_number=1)
        g = build_investigation_graph(queries, inv)
        stints = [n for n in g["nodes"] if n["node_type"] == "STINT"]
        assert len(stints) == 2
        for n in stints:
            assert {"lap_start", "lap_end", "compound"} <= \
                set(n["canonical_reference"])


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


@requires_db
class TestDeterminism:
    def test_in_process_repeat_identical(self, queries, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            build_investigation_graph,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        g2 = build_investigation_graph(
            queries, run_engineering_investigation(queries, **LAP6_KW))
        assert g2["output_hash"] == graph["output_hash"]
        assert g2["graph_id"] == graph["graph_id"]

    def test_snapshot_verify_and_replay(self, queries, graph):
        from racewise.data.historical.investigation_graph import (
            build_graph_snapshot, replay_graph_snapshot,
            verify_graph_snapshot,
        )

        snap = build_graph_snapshot(graph)
        assert verify_graph_snapshot(snap)["status"] == "VALID"
        rep = replay_graph_snapshot(queries, snap)
        assert rep["status"] == "IDENTICAL"
        assert rep["replay_hash"] == snap["output_hash"]

    def test_nodes_and_edges_canonically_sorted(self, graph):
        ids = [n["node_id"] for n in graph["nodes"]]
        assert ids == sorted(ids)
        keys = [(e["source_node"], e["edge_type"], e["target_node"],
                 e["edge_id"]) for e in graph["edges"]]
        assert keys == sorted(keys)

    def test_subprocess_hash_seed_independence(self):
        code = (
            "import sys, json;"
            "sys.path.insert(0, r'%s');"
            "from racewise.data.historical.canonical_queries import CanonicalQueries;"
            "from racewise.data.historical.investigation_synthesis import run_engineering_investigation;"
            "from racewise.data.historical.investigation_graph import build_investigation_graph;"
            "q = CanonicalQueries(r'%s');"
            "inv = run_engineering_investigation(q, question_type='LAP_PERFORMANCE',"
            "driver_a='max-verstappen', driver_b='sergio-perez', season=2023,"
            "round_num=1, lap_number=6);"
            "g = build_investigation_graph(q, inv);"
            "print(json.dumps({'hash': g['output_hash'],"
            "'nodes': g['node_count'], 'edges': g['edge_count']}))"
            % (REPO / "src", DB_PATH)
        )
        results = []
        for seed in (3, 29):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = str(seed)
            r = subprocess.run([sys.executable, "-c", code],
                               capture_output=True, text=True,
                               timeout=560, env=env, cwd=str(REPO))
            assert r.returncode == 0, r.stderr
            results.append(json.loads(r.stdout.strip().splitlines()[-1]))
        assert results[0] == results[1]
        assert results[0]["nodes"] > 0 and results[0]["edges"] > 0


# ---------------------------------------------------------------------------
# traversal + path queries
# ---------------------------------------------------------------------------


@requires_db
class TestTraversal:
    def test_neighbors_bounded(self, graph, lap6):
        from racewise.data.historical.investigation_graph import traverse_graph

        root = f"investigation:{lap6['investigation_id']}"
        t = traverse_graph(graph, root)
        assert t["status"] == "OK"
        assert t["node_count"] <= 200 and t["edge_count"] <= 800
        assert root in {n["node_id"] for n in t["nodes"]}

    def test_traversal_kinds(self, graph, lap6):
        from racewise.data.historical.investigation_graph import traverse_graph

        root = f"investigation:{lap6['investigation_id']}"
        ev = traverse_graph(graph, root, traversal_kind="EVIDENCE")
        assert ev["status"] == "OK" and ev["node_count"] > 1
        mem = traverse_graph(graph, root, traversal_kind="MEMORY")
        mem_ids = {n["node_id"] for n in mem["nodes"]}
        assert any(i.startswith("memory:") for i in mem_ids)
        src = traverse_graph(graph, "evidence:evidence_001",
                             traversal_kind="SOURCES")
        assert any(i.startswith("analytical_source:")
                   for i in {n["node_id"] for n in src["nodes"]})

    def test_bounds_rejected_not_clamped(self, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            MAX_DEPTH, MAX_NODES, traverse_graph,
        )

        root = f"investigation:{lap6['investigation_id']}"
        assert traverse_graph(graph, root, max_depth=MAX_DEPTH + 1)["status"] \
            == "INVALID"
        assert traverse_graph(graph, root, max_nodes=MAX_NODES + 1)["status"] \
            == "INVALID"
        assert traverse_graph(graph, root, max_edges=1501)["status"] == "INVALID"
        assert traverse_graph(graph, root, max_depth=0)["status"] == "INVALID"

    def test_unknown_node_and_kind(self, graph):
        from racewise.data.historical.investigation_graph import traverse_graph

        assert traverse_graph(graph, "evidence:nope")["status"] == "NOT_FOUND"
        assert traverse_graph(graph, "evidence:evidence_001",
                              traversal_kind="FREEFORM")["status"] == "INVALID"
        assert traverse_graph(graph, "evidence:evidence_001",
                              direction="SIDEWAYS")["status"] == "INVALID"


@requires_db
class TestPaths:
    def test_investigation_to_evidence_path(self, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            explain_investigation_path,
        )

        p = explain_investigation_path(
            graph, lap6["investigation_id"], "evidence:evidence_001")
        assert p["status"] == "OK"
        assert p["path"][0]["node_type"] == "INVESTIGATION"
        assert p["path"][-1]["node_type"] == "EVIDENCE"
        assert all("via_provenance" in s for s in p["path"])

    def test_unknown_investigation_unavailable(self, graph):
        from racewise.data.historical.investigation_graph import (
            explain_investigation_path,
        )

        p = explain_investigation_path(graph, "ffffffffffffffff",
                                       "evidence:evidence_001")
        assert p["status"] == "UNAVAILABLE"

    def test_unknown_target_not_found(self, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            explain_investigation_path,
        )

        p = explain_investigation_path(graph, lap6["investigation_id"],
                                       "evidence:evidence_999")
        assert p["status"] == "NOT_FOUND"

    def test_evidence_to_source_complete(self, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            trace_evidence_to_source,
        )

        t = trace_evidence_to_source(graph, "evidence_001")
        assert t["status"] == "OK"
        assert t["missing_provenance"] == []
        kinds = [s["edge_type"] for s in t["sources"]]
        assert "DERIVED_FROM" in kinds
        src = next(s for s in t["sources"]
                   if s["edge_type"] == "DERIVED_FROM")
        assert src["node_type"] == "ANALYTICAL_SOURCE"
        assert src["source_phase"] and src["source_tool"] and src["source_hash"]

    def test_unknown_evidence_not_found(self, graph):
        from racewise.data.historical.investigation_graph import (
            trace_evidence_to_source,
        )

        assert trace_evidence_to_source(graph, "evidence_999")["status"] \
            == "NOT_FOUND"

    def test_hypothesis_trace_descriptive(self, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            trace_hypothesis_evidence,
        )

        t = trace_hypothesis_evidence(graph, "H1_corner_speed",
                                      investigation_id=lap6["investigation_id"])
        assert t["status"] == "OK"
        assert len(t["supporting_evidence"]) == 2
        assert len(t["contradicting_evidence"]) == 1
        assert len(t["non_decisive_evidence"]) == 3
        # disjoint families
        sup = {r["node_id"] for r in t["supporting_evidence"]}
        con = {r["node_id"] for r in t["contradicting_evidence"]}
        nd = {r["node_id"] for r in t["non_decisive_evidence"]}
        assert not (sup & con or sup & nd or con & nd)

    def test_hypothesis_trace_unknown(self, graph):
        from racewise.data.historical.investigation_graph import (
            trace_hypothesis_evidence,
        )

        assert trace_hypothesis_evidence(graph, "H99_free_form")["status"] \
            == "NOT_FOUND"


# ---------------------------------------------------------------------------
# lineage import
# ---------------------------------------------------------------------------


@requires_db
class TestLineage:
    def test_compared_with_imported_from_6o(self, queries, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            add_lineage_edges, build_investigation_graph,
            explain_investigation_path, merge_investigation_graphs,
        )
        from racewise.data.historical.investigation_memory import (
            compare_engineering_investigations,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv11 = run_engineering_investigation(
            queries, **{**LAP6_KW, "lap_number": 11})
        g11 = build_investigation_graph(queries, inv11)
        merged = merge_investigation_graphs(graph, g11)
        lin = compare_engineering_investigations(lap6, inv11)["lineage"][0]
        out = add_lineage_edges(merged, lin["relationship"],
                                lin["source_investigation"],
                                lin["target_investigation"],
                                provenance=lin["provenance"])
        assert out["status"] == "OK"
        p = explain_investigation_path(
            out, lap6["investigation_id"],
            f"investigation:{inv11['investigation_id']}")
        assert p["status"] == "OK"
        assert p["path"][-1]["via_edge_type"] == "COMPARED_WITH"

    def test_invalid_relationship_rejected(self, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            add_lineage_edges,
        )

        inv_id = lap6["investigation_id"]
        out = add_lineage_edges(graph, "CONNECTED_TO", inv_id, inv_id)
        assert out["status"] == "INVALID"

    def test_missing_endpoint_not_found(self, graph, lap6):
        from racewise.data.historical.investigation_graph import (
            add_lineage_edges,
        )

        out = add_lineage_edges(graph, "COMPARED_WITH",
                                lap6["investigation_id"], "does-not-exist")
        assert out["status"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# negative controls / honesty
# ---------------------------------------------------------------------------


@requires_db
class TestNegativeControls:
    def test_invalid_investigation_has_no_graph(self, queries):
        from racewise.data.historical.investigation_graph import (
            build_investigation_graph,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        bad = run_engineering_investigation(
            queries, question_type="NOT_A_TYPE", driver_a="max-verstappen",
            driver_b="sergio-perez", season=2023, round_num=1)
        g = build_investigation_graph(queries, bad)
        assert g["status"] == "INVALID"
        assert "nodes" not in g

    def test_unavailable_scope_builds_no_fabricated_lap(self, queries):
        from racewise.data.historical.investigation_graph import (
            build_investigation_graph,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, **{**LAP6_KW, "lap_number": 999})
        g = build_investigation_graph(queries, inv)
        assert g["status"] == "UNAVAILABLE"

    def test_evidence_poor_graph_is_honest(self, queries):
        from racewise.data.historical.investigation_graph import (
            build_investigation_graph,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="RACE_GAP", driver_a="nino-farina",
            driver_b="juan-manuel-fangio", season=1950, round_num=1)
        g = build_investigation_graph(queries, inv)
        types = Counter(n["node_type"] for n in g["nodes"])
        assert types.get("EVIDENCE", 0) == 0
        assert types.get("COUNTERFACTUAL", 0) == 0
        assert types.get("MEMORY", 0) == 0

    def test_snapshot_tamper_hash_mismatch(self, graph):
        from racewise.data.historical.investigation_graph import (
            build_graph_snapshot, verify_graph_snapshot,
        )

        snap = build_graph_snapshot(graph)
        tampered = dict(snap)
        tampered["edges"] = snap["edges"][:-1]
        assert verify_graph_snapshot(tampered)["status"] == "HASH_MISMATCH"
        assert verify_graph_snapshot({"foo": 1})["status"] == "INVALID_SCHEMA"

    def test_replay_invalid_snapshot_never_reruns(self, queries, graph):
        from racewise.data.historical.investigation_graph import (
            build_graph_snapshot, replay_graph_snapshot,
            verify_graph_snapshot,
        )

        snap = build_graph_snapshot(graph)
        corrupt = dict(snap)
        corrupt["node_count"] = snap["node_count"] + 1
        assert verify_graph_snapshot(corrupt)["status"] == "HASH_MISMATCH"
        rep = replay_graph_snapshot(queries, corrupt)
        assert rep["status"] == "INVALID_SNAPSHOT"

    def test_epistemic_boundaries_present(self, graph):
        joined = " ".join(graph["epistemic_boundaries"])
        assert "not causation" in joined
        assert "never inferred" in joined or "not inferred" in joined \
            or "imported" in joined


# ---------------------------------------------------------------------------
# security posture of the module surface
# ---------------------------------------------------------------------------


class TestSecuritySurface:
    def test_no_dynamic_execution_in_module(self):
        import inspect

        import racewise.data.historical.investigation_graph as mod

        src = inspect.getsource(mod)
        for banned in ("eval(", "exec(", "os.system", "subprocess.",
                       "__import__", "sqlite3.connect"):
            assert banned not in src, banned
