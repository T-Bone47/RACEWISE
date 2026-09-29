"""Phase 6T golden verification tests.

The committed golden file (phase_6t_goldens.json) must reproduce exactly
against the live canonical store: run identity, engine investigation id,
output hash, snapshot hash and graph hash are recomputed and compared;
replay verdicts must remain IDENTICAL. Determinism contract: the same
question/context under the same policy produces the same run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
GOLDENS = REPO / "tests" / "benchmarks" / "phase_6t_goldens.json"
requires_db = pytest.mark.skipif(not DB_PATH.exists(),
                                 reason="canonical DB not present")


def _load() -> dict:
    return json.loads(GOLDENS.read_text(encoding="utf-8"))


@requires_db
def test_golden_file_meets_phase_6t_minimums() -> None:
    data = _load()
    goldens = data["goldens"]
    assert len(goldens) >= 10
    ids = [g["golden_id"] for g in goldens]
    assert len(set(ids)) == len(ids)
    contradiction = sum(1 for g in goldens if "CONTRADICTION" in g["golden_id"])
    limitation = sum(1 for g in goldens
                     if "LIMITATION" in g["golden_id"]
                     or "INSUFFICIENT" in g["golden_id"])
    counterfactual = sum(1 for g in goldens
                         if "COUNTERFACTUAL" in g["golden_id"])
    qualifying = sum(1 for g in goldens if "QUALIFYING" in g["golden_id"])
    cross_race = sum(1 for g in goldens if "CROSS_RACE" in g["golden_id"])
    assert contradiction >= 3
    assert limitation >= 2
    assert counterfactual >= 2
    assert qualifying >= 2
    assert cross_race >= 1
    for g in goldens:
        assert g.get("run_id"), g["golden_id"]
        assert g.get("question_object_hash"), g["golden_id"]
        assert g.get("plan_hash"), g["golden_id"]
        assert g.get("provenance_hash"), g["golden_id"]


@requires_db
def test_goldens_reproduce_identically() -> None:
    from racewise.data.historical.autonomous_investigator import (
        run_autonomous_investigation,
    )
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )
    from racewise.data.historical.performance_patterns import _hash_obj

    queries = get_canonical_queries()
    for golden in _load()["goldens"]:
        run = run_autonomous_investigation(
            queries, golden["question"], context=dict(golden["context"]))
        assert run["run_id"] == golden["run_id"], \
            f"{golden['golden_id']}: run identity changed"
        assert (run.get("question") or {}).get("question_object_hash") == \
            golden["question_object_hash"], golden["golden_id"]
        assert _hash_obj(run.get("evidence_plan") or []) == \
            golden["plan_hash"], golden["golden_id"]
        assert (run.get("engine_result_ref") or {}).get(
            "investigation_id") == golden["engine_investigation_id"], \
            golden["golden_id"]
        assert (run.get("engine_result_ref") or {}).get("output_hash") == \
            golden["output_hash"], golden["golden_id"]
        assert run.get("stage_ledger") == golden["stage_ledger"], \
            golden["golden_id"]
        assert run.get("hypothesis_states") == golden["hypothesis_states"], \
            golden["golden_id"]


@requires_db
def test_golden_replay_verdicts_remain_identical() -> None:
    from racewise.data.historical.autonomous_investigator import (
        replay_autonomous_investigation as replay_run,
        run_autonomous_investigation as run_one,
    )
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )
    queries = get_canonical_queries()
    for golden in _load()["goldens"]:
        run = run_one(
            queries, golden["question"], context=dict(golden["context"]))
        report = replay_run(queries, run)
        assert report["status"] == "IDENTICAL", \
            f"{golden['golden_id']}: {report['changed_dimensions']}"
