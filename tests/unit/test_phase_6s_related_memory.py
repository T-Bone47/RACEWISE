"""Phase 6S GAP 4 tests: structural related-memory retrieval.

The exact-scope layer is the documented contract and stays byte-identical
by default. The structural layer adds deterministic, declared-field-only
related matching (driver pair / driver overlap, hypothesis overlap,
adjacent season) with explicit provenance and a non-transfer policy.
No vectors, no embeddings, no opaque ranking. Pure tests use explicitly
synthetic fixture items; live tests run only when the canonical DB exists.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(),
                                 reason="canonical DB not present")

from racewise.data.historical.investigation_memory import (  # noqa: E402
    derive_memory_items, invalidate_memory_item,
    retrieve_engineering_memory, retrieve_related_engineering_memory,
)


def _fixture_item(mid, season, pair=("max-verstappen", "sergio-perez"),
                  hyps=("H4_tyre_state",), status="ACTIVE",
                  round_num=4, scope_type="RACE"):
    """Synthetic memory-item fixture (labeled test data, not history)."""
    return {
        "memory_id": mid,
        "statement": f"test fixture statement {mid}",
        "evidence_ids": [f"evidence_001"],
        "source_investigation_ids": [f"inv-{mid}"],
        "source_hashes": {"evidence_001": "deadbeef"},
        "scope": {"scope_type": scope_type, "season": season,
                  "round": round_num, "driver_pair": sorted(pair),
                  "circuit": None, "lap_number": None, "stint_number": None,
                  "pattern_id": None},
        "hypothesis_ids": list(hyps),
        "evidence_type": "FACT",
        "claim_class": "OBSERVED",
        "limitations": ["test fixture"],
        "created_from": "synthesis.established_facts",
        "validity_status": status,
        "output_hash": "cafebabe",
    }


class TestExactLayerUnchanged:
    def test_no_related_keys_by_default(self):
        items = [_fixture_item("m1", 2022)]
        res = retrieve_engineering_memory(items, season=2022, round_num=4)
        assert "related_memory_items" not in res
        assert "related_match_count" not in res
        assert res["match_count"] == 1

    def test_exact_match_still_works(self):
        items = [_fixture_item("m1", 2022), _fixture_item("m2", 2023)]
        res = retrieve_engineering_memory(items, season=2022)
        assert res["match_count"] == 1
        assert res["matching_memory_items"][0]["memory_id"] == "m1"


class TestStructuralMatching:
    def test_same_pair_different_round_is_related(self):
        items = [_fixture_item("m1", 2022, round_num=4),
                 _fixture_item("m2", 2022, round_num=9)]
        res = retrieve_related_engineering_memory(
            items, season=2022, round_num=4,
            driver_pair=["max-verstappen", "sergio-perez"])
        ids = {r["memory_id"] for r in res["related_memory_items"]}
        assert ids == {"m2"}
        item = res["related_memory_items"][0]
        assert item["match_class"] == "STRUCTURAL"
        assert item["match_reasons"] == ["same_driver_pair"]
        assert "never a conclusion" in item["transfer_policy"]

    def test_adjacent_season_reason(self):
        items = [_fixture_item("m1", 2022), _fixture_item("m2", 2021)]
        res = retrieve_related_engineering_memory(
            items, season=2022, round_num=4,
            driver_pair=["max-verstappen", "sergio-perez"])
        by_id = {r["memory_id"]: r for r in res["related_memory_items"]}
        assert by_id["m2"]["match_reasons"] == ["adjacent_season",
                                                "same_driver_pair"]
        # two seasons away: pair match only, no adjacency
        items.append(_fixture_item("m3", 2020))
        res2 = retrieve_related_engineering_memory(
            items, season=2022, round_num=4,
            driver_pair=["max-verstappen", "sergio-perez"])
        by_id2 = {r["memory_id"]: r["match_reasons"]
                  for r in res2["related_memory_items"]}
        assert by_id2["m3"] == ["same_driver_pair"]

    def test_driver_overlap_and_hypothesis_overlap(self):
        items = [_fixture_item("mx", 2019, pair=("max-verstappen",
                                                 "lando-norris"),
                               hyps=("H6_drs",)),
                 _fixture_item("mh", 2018, pair=("charles-leclerc",
                                                 "carlos-sainz-jr"),
                               hyps=("H4_tyre_state",))]
        res = retrieve_related_engineering_memory(
            items, season=2022, round_num=4, driver="max-verstappen",
            hypothesis="H4_tyre_state")
        by_id = {r["memory_id"]: r["match_reasons"]
                 for r in res["related_memory_items"]}
        assert by_id["mx"] == ["driver_overlap"]
        assert by_id["mh"] == ["hypothesis_overlap"]

    def test_exact_scope_excluded_from_related(self):
        items = [_fixture_item("m1", 2022, round_num=4),
                 _fixture_item("m2", 2022, round_num=9)]
        res = retrieve_related_engineering_memory(
            items, season=2022, round_num=4,
            driver_pair=["max-verstappen", "sergio-perez"])
        ids = {r["memory_id"] for r in res["related_memory_items"]}
        assert "m1" not in ids  # exact layer's result, not a related pointer

    def test_no_leakage_for_disjoint_scope(self):
        items = [_fixture_item("m1", 2022, pair=("charles-leclerc",
                                                 "carlos-sainz-jr"),
                                hyps=("H1_corner_speed",))]
        res = retrieve_related_engineering_memory(
            items, season=2024, round_num=8, driver="lando-norris")
        assert res["related_match_count"] == 0
        assert res["related_memory_items"] == []

    def test_invalidated_excluded_unless_included(self):
        items = [_fixture_item("m1", 2022, round_num=9)]
        invalidated = invalidate_memory_item(items[0], "REPLAY_MISMATCH",
                                             "test fixture")
        res = retrieve_related_engineering_memory(
            [invalidated], season=2022, round_num=4,
            driver_pair=["max-verstappen", "sergio-perez"])
        assert res["related_match_count"] == 0
        res2 = retrieve_related_engineering_memory(
            [invalidated], season=2022, round_num=4,
            driver_pair=["max-verstappen", "sergio-perez"],
            include_invalidated=True)
        assert res2["related_match_count"] == 1
        assert res2["related_memory_items"][0]["validity_status"] == \
            "INVALIDATED"
        assert res2["related_memory_items"][0]["invalidation"]["reason"] == \
            "REPLAY_MISMATCH"

    def test_provenance_fields_complete_on_related_items(self):
        items = [_fixture_item("m1", 2022, round_num=9),
                 _fixture_item("m2", 2021)]
        res = retrieve_related_engineering_memory(
            items, season=2022, round_num=4,
            driver_pair=["max-verstappen", "sergio-perez"])
        for r in res["related_memory_items"]:
            assert r["source_investigation_ids"]
            assert r["evidence_ids"]
            assert r["source_hashes"]
            assert r["scope"]["scope_type"]
            assert r["validity_status"]

    def test_determinism_same_process_three_runs(self):
        items = [_fixture_item(f"m{i}", 2020 + (i % 3), round_num=i)
                 for i in range(6)]
        outs = [
            retrieve_related_engineering_memory(
                items, season=2022, round_num=4,
                driver_pair=["max-verstappen", "sergio-perez"])
            for _ in range(3)
        ]
        sig = lambda o: [(r["memory_id"], r["match_reasons"])
                         for r in o["related_memory_items"]]
        assert sig(outs[0]) == sig(outs[1]) == sig(outs[2])

    def test_bounded_result(self):
        from racewise.data.historical.investigation_memory import (
            MAX_RELATED_MEMORY_ITEMS,
        )
        items = [_fixture_item(f"m{i}", 2022, round_num=100 + i)
                 for i in range(40)]
        res = retrieve_related_engineering_memory(
            items, season=2022, round_num=4,
            driver_pair=["max-verstappen", "sergio-perez"])
        assert res["related_match_count"] <= MAX_RELATED_MEMORY_ITEMS


# ---------------------------------------------------------------------------
# live: derived-from-engine items + API surface
# ---------------------------------------------------------------------------

@requires_db
class TestLiveRelatedMemory:
    def test_related_items_carry_engine_provenance(self):
        from racewise.data.historical.canonical_queries import (
            get_canonical_queries,
        )
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        q = get_canonical_queries()
        base = run_engineering_investigation(
            q, "LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
            2023, 1, lap_number=6)
        neighbor = run_engineering_investigation(
            q, "LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
            2022, 1, lap_number=6)
        pool = derive_memory_items(base)
        if neighbor.get("status") == "VALID":
            pool += derive_memory_items(neighbor)
        res = retrieve_related_engineering_memory(
            pool, season=2023, round_num=1,
            driver_pair=["max-verstappen", "sergio-perez"])
        for r in res["related_memory_items"]:
            assert r["scope"]["season"] != 2023 or r["scope"]["round"] != 1
            assert r["match_class"] == "STRUCTURAL"

    def test_api_include_related_and_default_identity(self):
        from fastapi.testclient import TestClient

        from racewise.api.app import app

        client = TestClient(app)
        base_params = dict(
            question_type="LAP_PERFORMANCE", driver_a="max-verstappen",
            driver_b="sergio-perez", season=2023, round=1, lap_number=6)
        r_default = client.get("/api/catalog/engineering-memory",
                               params=base_params)
        assert r_default.status_code == 200
        default_body = r_default.json()
        assert "related_memory_items" not in default_body

        r_rel = client.get("/api/catalog/engineering-memory",
                           params={**base_params, "include_related": True})
        assert r_rel.status_code == 200
        rel_body = r_rel.json()
        assert "related_memory_items" in rel_body
        assert "related_policy" in rel_body
        assert "related_neighbor_runs" in rel_body
        # exact layer untouched
        assert rel_body["matching_memory_items"] == \
            default_body["matching_memory_items"]
        assert rel_body["match_count"] == default_body["match_count"]
        for r in rel_body["related_memory_items"]:
            assert r["match_reasons"]
            assert r["source_investigation_ids"]

    def test_api_cross_process_determinism(self):
        script = (
            "import sys; sys.path.insert(0, r'%s')\n"
            "from racewise.data.historical.canonical_queries import get_canonical_queries\n"
            "from racewise.data.historical.investigation_synthesis import run_engineering_investigation\n"
            "from racewise.data.historical.investigation_memory import derive_memory_items, retrieve_related_engineering_memory\n"
            "q = get_canonical_queries()\n"
            "pool = derive_memory_items(run_engineering_investigation(q, 'LAP_PERFORMANCE', 'max-verstappen', 'sergio-perez', 2023, 1, lap_number=6))\n"
            "res = retrieve_related_engineering_memory(pool, season=2023, round_num=1, driver_pair=['max-verstappen', 'sergio-perez'])\n"
            "print(res['related_match_count'], [r['memory_id'] for r in res['related_memory_items']])\n"
            % str(REPO / "src")
        )
        outs = set()
        for seed in ("3", "29"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed
            out = subprocess.run([sys.executable, "-c", script],
                                 capture_output=True, text=True, env=env,
                                 timeout=300, cwd=str(REPO))
            assert out.returncode == 0, out.stderr
            outs.add(out.stdout.strip().splitlines()[-1])
        assert len(outs) == 1, outs
