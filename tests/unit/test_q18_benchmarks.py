"""Phase 6P Q18 benchmark tests: investigation-graph semantics.

The full Q18 matrix (4 golden graphs + 8 cases + negatives + MCP) is a
documentation measurement; the suite runs a bounded subset (the LAP6 golden
graph plus the negative-control block) through the module API so the whole
suite stays fast. All assertions are on deterministic semantics over real
canonical data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")


@pytest.fixture(scope="module")
def queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries(str(DB_PATH))


@requires_db
class TestQ18Matrix:
    def test_golden_graphs_verify_and_replay(self, queries):
        from racewise.data.historical.investigation_graph import (
            build_graph_snapshot, build_investigation_graph,
            replay_graph_snapshot, verify_graph_snapshot,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        for kw in (
            dict(question_type="LAP_PERFORMANCE", driver_a="max-verstappen",
                 driver_b="sergio-perez", season=2023, round_num=1,
                 lap_number=6),
            dict(question_type="STINT_PERFORMANCE", driver_a="max-verstappen",
                 driver_b="sergio-perez", season=2023, round_num=1,
                 stint_number=1),
            dict(question_type="RACE_GAP", driver_a="max-verstappen",
                 driver_b="sergio-perez", season=2024, round_num=14),
        ):
            inv = run_engineering_investigation(queries, **kw)
            g = build_investigation_graph(queries, inv)
            snap = build_graph_snapshot(g)
            assert verify_graph_snapshot(snap)["status"] == "VALID"
            rep = replay_graph_snapshot(queries, snap)
            assert rep["status"] == "IDENTICAL"
            assert rep["replay_hash"] == snap["output_hash"]
            assert g["node_count"] > 0 and g["edge_count"] >= g["node_count"]

    def test_q18_6_hypothesis_trace_semantics(self, queries):
        from racewise.data.historical.investigation_graph import (
            build_investigation_graph, trace_hypothesis_evidence,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="LAP_PERFORMANCE",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, lap_number=6)
        g = build_investigation_graph(queries, inv)
        t = trace_hypothesis_evidence(
            g, "H1_corner_speed", investigation_id=inv["investigation_id"])
        assert t["status"] == "OK"
        assert t["supporting_evidence"] and t["contradicting_evidence"]
        # descriptive only: entries carry provenance, never a rank
        for entry in t["supporting_evidence"] + t["contradicting_evidence"]:
            assert "provenance" in entry
            assert not any(k.startswith("rank") for k in entry)

    def test_q18_7_contradictions_imported_with_conflict_ids(self, queries):
        from racewise.data.historical.investigation_graph import (
            build_investigation_graph,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="LAP_PERFORMANCE",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, lap_number=6)
        g = build_investigation_graph(queries, inv)
        conflict_ids = {c["conflict_id"] for c in inv["evidence_conflicts"]}
        contra = [e for e in g["edges"]
                  if e["edge_type"] == "CONTRADICTS"
                  and e["source_node"].startswith("evidence:")
                  and e["target_node"].startswith("evidence:")]
        assert contra, "expected imported pairwise contradiction edges"
        assert all(e["provenance"].get("conflict_id") in conflict_ids
                   for e in contra)

    def test_q18_11_evidence_unavailable_graph_honest(self, queries):
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
        types = {n["node_type"] for n in g["nodes"]}
        assert "EVIDENCE" not in types
        assert "COUNTERFACTUAL" not in types
        assert "MEMORY" not in types

    def test_q18_12_bounded_traversal_negative_controls(self, queries):
        from racewise.data.historical.investigation_graph import (
            MAX_DEPTH, MAX_EDGES, MAX_NODES, build_investigation_graph,
            explain_investigation_path, trace_evidence_to_source,
            trace_hypothesis_evidence, traverse_graph,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="LAP_PERFORMANCE",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, lap_number=6)
        g = build_investigation_graph(queries, inv)
        root = f"investigation:{inv['investigation_id']}"
        assert traverse_graph(g, root, max_depth=MAX_DEPTH + 1)["status"] \
            == "INVALID"
        assert traverse_graph(g, root, max_nodes=MAX_NODES + 1)["status"] \
            == "INVALID"
        assert traverse_graph(g, root, max_edges=MAX_EDGES + 1)["status"] \
            == "INVALID"
        assert traverse_graph(g, "evidence:missing")["status"] == "NOT_FOUND"
        assert traverse_graph(g, root, traversal_kind="VIBES")["status"] \
            == "INVALID"
        assert explain_investigation_path(
            g, "ffffffffffffffff", root)["status"] == "UNAVAILABLE"
        assert explain_investigation_path(
            g, inv["investigation_id"], "evidence:missing")["status"] \
            == "NOT_FOUND"
        assert trace_evidence_to_source(g, "evidence:missing")["status"] \
            == "NOT_FOUND"
        assert trace_hypothesis_evidence(g, "H99_free_form")["status"] \
            == "NOT_FOUND"


@requires_db
class TestQ18Mcp:
    def test_mcp_boundary(self, queries):
        from racewise.tools.contract import ToolError
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(queries)
        assert len(reg._tools) == 31
        assert {"build_investigation_graph", "trace_investigation_path",
                "trace_evidence_source", "trace_hypothesis_evidence"} \
            <= set(reg._tools)
        lap6 = {"question_type": "LAP_PERFORMANCE",
                "driver_a": "max-verstappen", "driver_b": "sergio-perez",
                "season": 2023, "round": 1, "lap_number": 6}
        built = reg.execute("build_investigation_graph", lap6)["output"]
        assert built["node_count"] > 0 and built["edge_count"] > 0
        rep = reg.execute("build_investigation_graph", lap6)["output"]
        assert rep == built
        try:
            reg.execute("build_investigation_graph",
                        {**lap6, "max_depth": 99})
            raised = False
        except ToolError as e:
            raised = e.code == "invalid_input"
        assert raised
