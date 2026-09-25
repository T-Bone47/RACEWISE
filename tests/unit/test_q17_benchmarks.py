"""Phase 6O Q17 benchmark tests: replay, comparison & memory semantics.

The full Q17 matrix (goldens + 12 cases + negatives + MCP) is a
documentation measurement; the suite runs a bounded subset through the
module API so the whole suite stays fast.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

LAP6 = {"question_type": "LAP_PERFORMANCE",
        "driver_a": "max-verstappen", "driver_b": "sergio-perez",
        "season": 2023, "round": 1, "lap_number": 6}


@pytest.fixture(scope="module")
def queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries(str(DB_PATH))


@requires_db
class TestQ17Goldens:
    def test_golden_snapshots_verify_and_replay(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, replay_engineering_investigation,
            verify_investigation_snapshot,
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
            snap = build_investigation_snapshot(inv)
            assert verify_investigation_snapshot(snap)["status"] == "VALID"
            rep = replay_engineering_investigation(queries, snap)
            assert rep["status"] == "IDENTICAL"
            assert rep["replay_hash"] == snap["snapshot_hash"]

    def test_replay_changed_tool_version_is_structured(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, replay_engineering_investigation,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )
        from racewise.data.historical.performance_patterns import _hash_obj

        inv = run_engineering_investigation(queries, **{
            "question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
            "driver_b": "sergio-perez", "season": 2023, "round_num": 1,
            "lap_number": 6})
        snap = build_investigation_snapshot(inv)
        snap["evidence_ledger"] = [
            dict(e, source_tool="fuse_lap_evidence_v999")
            for e in snap["evidence_ledger"]]
        snap["source_hashes"] = {e["evidence_id"]: e["source_hash"]
                                 for e in snap["evidence_ledger"]}
        snap["snapshot_hash"] = _hash_obj(
            {k: v for k, v in snap.items() if k != "snapshot_hash"})
        rep = replay_engineering_investigation(queries, snap)
        assert rep["status"] == "DIFFERENT_TOOL_VERSION"
        assert rep["differences"][0]["category"] == "DATA_CHANGE"
        assert {"path", "old_value", "new_value"} <= \
            set(rep["differences"][0])


@requires_db
class TestQ17ComparisonAndMemory:
    def test_comparison_and_memory_matrix(self, queries):
        from racewise.data.historical.investigation_memory import (
            compare_engineering_investigations, derive_memory_items,
            invalidate_memory_item, retrieve_engineering_memory,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv_a = run_engineering_investigation(queries, **{
            "question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
            "driver_b": "sergio-perez", "season": 2023, "round_num": 1,
            "lap_number": 6})
        inv_b = run_engineering_investigation(queries, **{
            "question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
            "driver_b": "sergio-perez", "season": 2023, "round_num": 1,
            "lap_number": 11})
        cmp1 = compare_engineering_investigations(inv_a, inv_b)
        assert cmp1["compatibility"]["state"] == "PARTIALLY_COMPARABLE"
        assert compare_engineering_investigations(inv_a, inv_b) == cmp1

        items = derive_memory_items(inv_a) + derive_memory_items(inv_b)
        assert all(it["evidence_ids"] for it in items)
        hit = retrieve_engineering_memory(items, season=2023)
        assert hit["match_count"] == len(items)
        assert retrieve_engineering_memory(items, season=1999)["match_count"] == 0
        bad = invalidate_memory_item(items[0], "SCOPE_ERROR", "test")
        mixed = retrieve_engineering_memory([bad] + items[1:], season=2023)
        assert mixed["match_count"] == len(items) - 1


@requires_db
class TestQ17NegativeControls:
    def test_snapshot_integrity_states(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, verify_investigation_snapshot,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        snap = build_investigation_snapshot(run_engineering_investigation(
            queries, **{
                "question_type": "LAP_PERFORMANCE",
                "driver_a": "max-verstappen", "driver_b": "sergio-perez",
                "season": 2023, "round_num": 1, "lap_number": 6}))
        assert verify_investigation_snapshot({})["status"] == "INVALID_SCHEMA"
        no_prov = {k: v for k, v in snap.items() if k != "provenance"}
        assert verify_investigation_snapshot(no_prov)["status"] == \
            "MISSING_PROVENANCE"
        corrupt = dict(snap)
        corrupt["output_hash"] = "f" * 16
        assert verify_investigation_snapshot(corrupt)["status"] == \
            "HASH_MISMATCH"


@requires_db
class TestQ17MCPBoundary:
    def test_mcp_verification(self, queries):
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(queries)
        assert reg.execute("replay_engineering_investigation", LAP6)[
            "output"]["status"] == "IDENTICAL"
        cmp1 = reg.execute(
            "compare_engineering_investigations",
            {"investigation_a": LAP6,
             "investigation_b": {**LAP6, "lap_number": 11}})["output"]
        assert cmp1["compatibility"]["state"] == "PARTIALLY_COMPARABLE"
        assert reg.execute("retrieve_engineering_memory",
                           {"investigations": [LAP6], "season": 2023}
                           )["output"]["match_count"] > 0
        from racewise.tools.contract import ToolError
        with pytest.raises(ToolError):
            reg.execute("replay_engineering_investigation",
                        {**LAP6, "bogus": 1})
        with pytest.raises(ToolError):
            reg.execute("retrieve_engineering_memory",
                        {"investigations": [LAP6] * 5})
