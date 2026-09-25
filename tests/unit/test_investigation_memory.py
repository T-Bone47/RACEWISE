"""Phase 6O tests: investigation replay, comparison & engineering memory.

Pure tests cover snapshot integrity, replay statuses, structured
differences, comparison compatibility and descriptive deltas (including
the falsification invariant: vanished evidence is evidence loss, never
resolution), memory derivation/retrieval/invalidation scope rules and
determinism. Live tests run only when the canonical DB exists.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

HIDS = ["H1_corner_speed", "H2_throttle", "H3_braking",
        "H4_tyre_state", "H5_race_control", "H6_drs"]

LAP6 = {"question_type": "LAP_PERFORMANCE",
        "driver_a": "max-verstappen", "driver_b": "sergio-perez",
        "season": 2023, "round": 1, "lap_number": 6}
LAP11 = {**LAP6, "lap_number": 11}
RACEGAP24 = {"question_type": "RACE_GAP",
             "driver_a": "max-verstappen", "driver_b": "sergio-perez",
             "season": 2024, "round": 14}


def _params(case):
    kw = {k: v for k, v in case.items()
          if k in ("question_type", "driver_a", "driver_b", "season",
                   "round", "lap_number", "stint_number", "pattern_id")}
    kw["round_num"] = kw.pop("round")
    if "hypotheses" in case:
        kw["hypotheses"] = case["hypotheses"]
    return kw


def _run(queries, case):
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    return run_engineering_investigation(queries, **_params(case))


def _run_kw(queries, **kw):
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    return run_engineering_investigation(queries, **kw)


@pytest.fixture(scope="module")
def queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries(str(DB_PATH))


# ---------------------------------------------------------------------------
# snapshot (pure + hash)
# ---------------------------------------------------------------------------


class TestSnapshot:
    def _inv(self, queries):
        return _run(queries, LAP6)

    def test_snapshot_structure(self, queries):
        from racewise.data.historical.investigation_memory import (
            SNAPSHOT_VERSION, build_investigation_snapshot,
        )

        snap = build_investigation_snapshot(self._inv(queries))
        for key in ("snapshot_version", "investigation_id",
                    "investigation_input", "question", "hypotheses_in_scope",
                    "evidence_plan", "evidence_ledger",
                    "hypothesis_evaluations", "evidence_conflicts",
                    "falsification_gate", "counterfactual_candidates",
                    "executed_counterfactuals", "synthesis",
                    "decision_trace", "provenance", "analytical_chain",
                    "output_hash", "snapshot_hash", "source_hashes"):
            assert key in snap
        assert snap["snapshot_version"] == SNAPSHOT_VERSION

    def test_snapshot_hash_deterministic_and_identity_inputs(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot,
        )
        from racewise.data.historical.performance_patterns import _hash_obj

        inv = self._inv(queries)
        s1 = build_investigation_snapshot(inv)
        s2 = build_investigation_snapshot(_run(queries, LAP6))
        assert s1["snapshot_hash"] == s2["snapshot_hash"]
        # no runtime fields anywhere in the hashed body
        blob = json.dumps(
            {k: v for k, v in s1.items() if k != "snapshot_hash"})
        for banned in ("timestamp", "duration_ms", "pid", "uuid"):
            assert banned not in blob
        # identity depends on input + output hash
        identity = _hash_obj({
            "input": s1["investigation_input"],
            "output_hash": s1["output_hash"],
        })
        assert isinstance(identity, str) and len(identity) == 16

    def test_export_canonical_json_roundtrip(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, export_snapshot_canonical_json,
            verify_investigation_snapshot,
        )

        snap = build_investigation_snapshot(self._inv(queries))
        blob = export_snapshot_canonical_json(snap)
        assert json.loads(blob)["snapshot_hash"] == snap["snapshot_hash"]
        assert blob == export_snapshot_canonical_json(snap)

    def test_verify_valid_and_hash_mismatch(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, verify_investigation_snapshot,
        )

        snap = build_investigation_snapshot(self._inv(queries))
        assert verify_investigation_snapshot(snap)["status"] == "VALID"
        corrupt = dict(snap)
        corrupt["output_hash"] = "deadbeefdeadbeef"
        assert verify_investigation_snapshot(corrupt)["status"] == \
            "HASH_MISMATCH"
        tampered = dict(snap)
        tampered["evidence_ledger"] = snap["evidence_ledger"][:-1]
        assert verify_investigation_snapshot(tampered)["status"] == \
            "HASH_MISMATCH"

    def test_verify_schema_and_provenance_states(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, verify_investigation_snapshot,
        )
        from racewise.data.historical.performance_patterns import _hash_obj

        snap = build_investigation_snapshot(self._inv(queries))
        assert verify_investigation_snapshot({"foo": 1})["status"] == \
            "INVALID_SCHEMA"
        no_prov = {k: v for k, v in snap.items() if k != "provenance"}
        assert verify_investigation_snapshot(no_prov)["status"] == \
            "MISSING_PROVENANCE"
        incomplete = {k: v for k, v in snap.items()
                      if k not in ("decision_trace", "synthesis")}
        incomplete["snapshot_hash"] = _hash_obj(
            {k: v for k, v in incomplete.items() if k != "snapshot_hash"})
        assert verify_investigation_snapshot(incomplete)["status"] == \
            "INCOMPLETE_SNAPSHOT"
        # never silently repaired: verification returns a verdict, and a
        # snapshot whose stored hash disagrees stays HASH_MISMATCH
        broken = dict(snap)
        broken["snapshot_hash"] = "0" * 16
        v = verify_investigation_snapshot(broken)
        assert v["status"] == "HASH_MISMATCH"
        assert v["recomputed_hash"] == snap["snapshot_hash"]


# ---------------------------------------------------------------------------
# replay (live DB)
# ---------------------------------------------------------------------------


@requires_db
class TestReplay:
    def test_replay_identical(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, replay_engineering_investigation,
        )

        snap = build_investigation_snapshot(_run(queries, LAP6))
        rep = replay_engineering_investigation(queries, snap)
        assert rep["status"] == "IDENTICAL"
        assert rep["identical"] is True
        assert rep["differences"] == []
        assert rep["replay_hash"] == snap["snapshot_hash"]

    def test_replay_invalid_snapshot_never_reruns(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, replay_engineering_investigation,
        )

        snap = build_investigation_snapshot(_run(queries, LAP6))
        snap["output_hash"] = "0" * 16
        rep = replay_engineering_investigation(queries, snap)
        assert rep["status"] == "INVALID_SNAPSHOT"
        assert rep["replay_hash"] is None
        assert rep["differences"] == []

    def test_replay_tool_change_reports_structured_differences(self, queries):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, replay_engineering_investigation,
        )
        from racewise.data.historical.performance_patterns import _hash_obj

        snap = build_investigation_snapshot(_run(queries, LAP6))
        snap["evidence_ledger"] = [
            dict(e, source_tool="fuse_lap_evidence_v999")
            for e in snap["evidence_ledger"]]
        snap["source_hashes"] = {
            e["evidence_id"]: e["source_hash"]
            for e in snap["evidence_ledger"]}
        snap["snapshot_hash"] = _hash_obj(
            {k: v for k, v in snap.items() if k != "snapshot_hash"})
        rep = replay_engineering_investigation(queries, snap)
        assert rep["status"] == "DIFFERENT_TOOL_VERSION"
        assert rep["differences"], "must list exact differences"
        d = rep["differences"][0]
        assert {"path", "old_value", "new_value", "category"} <= set(d)
        assert d["category"] == "DATA_CHANGE"

    def test_replay_status_vocabulary(self, queries):
        from racewise.data.historical.investigation_memory import (
            REPLAY_STATUSES, build_investigation_snapshot,
            replay_engineering_investigation,
        )

        for rep in (replay_engineering_investigation(
                queries, build_investigation_snapshot(_run(queries, LAP6))),
                replay_engineering_investigation(
                    queries, {"foo": 1})):
            assert rep["status"] in REPLAY_STATUSES


# ---------------------------------------------------------------------------
# comparison (live DB)
# ---------------------------------------------------------------------------


@requires_db
class TestComparison:
    def test_self_comparison_comparable_and_zero_deltas(self, queries):
        from racewise.data.historical.investigation_memory import (
            compare_engineering_investigations,
        )

        inv = _run(queries, LAP6)
        c = compare_engineering_investigations(inv, inv)
        assert c["compatibility"]["state"] == "COMPARABLE"
        assert c["evidence_deltas"] == []
        assert c["synthesis_delta"]["transition"] == "SAME"
        assert c["decision_trace_delta"]["changed"] == []

    def test_partially_comparable_different_lap(self, queries):
        from racewise.data.historical.investigation_memory import (
            compare_engineering_investigations,
        )

        c = compare_engineering_investigations(
            _run(queries, LAP6), _run(queries, LAP11))
        assert c["compatibility"]["state"] == "PARTIALLY_COMPARABLE"
        assert c["compatibility"]["differing_scope_keys"] == ["lap_number"]
        assert c["synthesis_delta"]["transition"] in \
            ("SAME", "MORE_SUPPORTED", "LESS_SUPPORTED",
             "SUPPORTED_TO_MIXED", "MIXED_TO_INSUFFICIENT",
             "INSUFFICIENT_TO_SUPPORTED", "SUPPORTED_TO_INSUFFICIENT",
             "INSUFFICIENT_TO_TESTABLE", "UNAVAILABLE_TO_AVAILABLE",
             "AVAILABLE_TO_UNAVAILABLE")

    def test_not_comparable_across_question_types(self, queries):
        from racewise.data.historical.investigation_memory import (
            compare_engineering_investigations,
        )

        c = compare_engineering_investigations(
            _run(queries, LAP6), _run(queries, RACEGAP24))
        assert c["compatibility"]["state"] == "NOT_COMPARABLE"

    def test_hypothesis_deltas_cover_all_six_descriptive(self, queries):
        from racewise.data.historical.investigation_memory import (
            compare_engineering_investigations,
        )

        c = compare_engineering_investigations(
            _run(queries, LAP6), _run(queries, LAP11))
        assert [d["hypothesis_id"] for d in c["hypothesis_deltas"]] == HIDS
        assert all("no ranking" in d["note"] for d in c["hypothesis_deltas"])

    def test_falsification_vanished_evidence_never_resolved(self, queries):
        # invariant: RESOLVED_CONTRADICTION only when the conflict's
        # evidence still exists on side B
        from racewise.data.historical.investigation_memory import (
            compare_engineering_investigations,
        )

        a = _run(queries, LAP6)
        b = _run(queries, LAP11)
        b_ledger_ids = {e["evidence_id"] for e in b["evidence_ledger"]}
        c = compare_engineering_investigations(a, b)
        for d in c["falsification_deltas"]:
            if d["change_type"] == "RESOLVED_CONTRADICTION":
                assert all(e in b_ledger_ids
                           for e in d.get("evidence_ids") or [])

    def test_comparison_dimensions_complete(self, queries):
        from racewise.data.historical.investigation_memory import (
            COMPARISON_DIMENSIONS, compare_engineering_investigations,
        )

        c = compare_engineering_investigations(
            _run(queries, LAP6), _run(queries, LAP11))
        assert set(c["dimensions"]) == set(COMPARISON_DIMENSIONS)
        blob = json.dumps(c)
        for banned in ("BETTER", "WORSE", "SUPERIOR", "INFERIOR"):
            assert banned not in blob

    def test_comparison_repeat_identical(self, queries):
        from racewise.data.historical.investigation_memory import (
            compare_engineering_investigations,
        )

        a, b = _run(queries, LAP6), _run(queries, LAP11)
        assert compare_engineering_investigations(a, b) == \
            compare_engineering_investigations(a, b)


# ---------------------------------------------------------------------------
# engineering memory (pure + live)
# ---------------------------------------------------------------------------


class TestMemoryPure:
    def test_invalidation_reason_closed(self):
        from racewise.data.historical.investigation_memory import (
            INVALIDATION_REASONS, derive_memory_items, invalidate_memory_item,
        )

        item = {"memory_id": "m1", "validity_status": "ACTIVE"}
        out = invalidate_memory_item(item, "REPLAY_MISMATCH", "test")
        assert out["validity_status"] == "INVALIDATED"
        assert out["invalidation"]["prior_status"] == "ACTIVE"
        with pytest.raises(ValueError):
            invalidate_memory_item(item, "VIBES", "test")
        assert set(INVALIDATION_REASONS) == {
            "NEW_EVIDENCE", "SOURCE_INVALIDATED", "REPLAY_MISMATCH",
            "SCOPE_ERROR", "MODEL_VERSION_CHANGE", "HUMAN_REVIEW",
            "DATA_CORRECTION"}

    def test_retrieval_policy_disclaims_generalization(self):
        from racewise.data.historical.investigation_memory import (
            retrieve_engineering_memory,
        )

        out = retrieve_engineering_memory([])
        assert "never transfers" in out["policy"]


@requires_db
class TestMemoryLive:
    def test_items_are_scope_limited_and_provenance_backed(self, queries):
        from racewise.data.historical.investigation_memory import (
            MEMORY_SCOPES, derive_memory_items,
        )

        items = derive_memory_items(_run(queries, LAP6))
        assert items
        for it in items:
            assert it["evidence_ids"], "no memory without traceable evidence"
            assert it["scope"]["scope_type"] in MEMORY_SCOPES
            assert it["source_investigation_ids"]
            assert it["limitations"]
            assert it["validity_status"] == "ACTIVE"
            # scope-bound statement: mentions the concrete race scope
            assert "2023 R1" in it["statement"]

    def test_no_memory_from_unavailable_investigation(self, queries):
        from racewise.data.historical.investigation_memory import (
            derive_memory_items,
        )

        assert derive_memory_items(
            _run(queries, {**LAP6, "lap_number": 999})) == []

    def test_no_memory_without_traceable_evidence(self, queries):
        # 1950 R1: no telemetry at all -> no derivable memory items
        from racewise.data.historical.investigation_memory import (
            derive_memory_items,
        )

        poor = _run(queries, {"question_type": "RACE_GAP",
                              "driver_a": "nino-farina",
                              "driver_b": "juan-manuel-fangio",
                              "season": 1950, "round": 1})
        assert len(poor.get("evidence_ledger") or []) == 0
        assert derive_memory_items(poor) == []

    def test_modelled_memory_separate_from_history(self, queries):
        from racewise.data.historical.investigation_memory import (
            derive_memory_items,
        )

        items = derive_memory_items(_run(queries, LAP6))
        cf = [it for it in items if it["evidence_type"] == "COUNTERFACTUAL"]
        hist = [it for it in items if it["evidence_type"] in ("FACT",
                                                              "INFERENCE")]
        for it in cf:
            assert it["claim_class"] == "MODELLED"
            assert "not history" in it["statement"]
        for it in hist:
            assert it["claim_class"] in ("OBSERVED", "INFERRED")

    def test_retrieval_exact_scope(self, queries):
        from racewise.data.historical.investigation_memory import (
            derive_memory_items, retrieve_engineering_memory,
        )

        items = (derive_memory_items(_run(queries, LAP6))
                 + derive_memory_items(_run(queries, LAP11)))
        hit = retrieve_engineering_memory(items, season=2023, round_num=1)
        assert hit["match_count"] == len(items)
        miss = retrieve_engineering_memory(items, season=1999)
        assert miss["match_count"] == 0
        hyp = retrieve_engineering_memory(
            items, season=2023, hypothesis="H1_corner_speed")
        assert 0 < hyp["match_count"] <= len(items)
        assert hit == retrieve_engineering_memory(
            items, season=2023, round_num=1)

    def test_invalidation_excluded_by_default(self, queries):
        from racewise.data.historical.investigation_memory import (
            derive_memory_items, invalidate_memory_item,
            retrieve_engineering_memory,
        )

        items = derive_memory_items(_run(queries, LAP6))
        bad = invalidate_memory_item(items[0], "NEW_EVIDENCE", "audit")
        kept = retrieve_engineering_memory(items[1:], season=2023)
        mixed = retrieve_engineering_memory([bad] + items[1:], season=2023)
        assert mixed["match_count"] == len(items) - 1
        assert kept["match_count"] == len(items) - 1
        shown = retrieve_engineering_memory([bad] + items[1:], season=2023,
                                            include_invalidated=True)
        assert shown["match_count"] == len(items)


# ---------------------------------------------------------------------------
# lineage + cross-investigation learning guards
# ---------------------------------------------------------------------------


@requires_db
class TestLineage:
    def test_comparison_records_lineage_relationship(self, queries):
        from racewise.data.historical.investigation_memory import (
            LINEAGE_RELATIONSHIPS, compare_engineering_investigations,
        )

        c = compare_engineering_investigations(
            _run(queries, LAP6), _run(queries, LAP11))
        assert c["lineage"]
        rel = c["lineage"][0]
        assert rel["relationship"] in LINEAGE_RELATIONSHIPS
        assert rel["relationship"] == "COMPARED_WITH"
        assert rel["provenance"]


# ---------------------------------------------------------------------------
# determinism (subprocess, PYTHONHASHSEED)
# ---------------------------------------------------------------------------


@requires_db
class TestSubprocessDeterminism:
    def _run(self, seed):
        code = (
            "import sys, json;"
            "sys.path.insert(0, r'%s');"
            "from racewise.data.historical.canonical_queries import CanonicalQueries;"
            "from racewise.data.historical.investigation_synthesis import run_engineering_investigation;"
            "from racewise.data.historical.investigation_memory import ("
            "build_investigation_snapshot, replay_engineering_investigation,"
            "compare_engineering_investigations, derive_memory_items);"
            "q = CanonicalQueries(r'%s');"
            "kw = dict(question_type='LAP_PERFORMANCE', driver_a='max-verstappen',"
            "driver_b='sergio-perez', season=2023, round_num=1, lap_number=6);"
            "inv = run_engineering_investigation(q, **kw);"
            "snap = build_investigation_snapshot(inv);"
            "rep = replay_engineering_investigation(q, snap);"
            "items = derive_memory_items(inv);"
            "print(json.dumps({'snap': snap['snapshot_hash'],"
            "'replay': rep['status'], 'mem': len(items),"
            "'ids': [i['memory_id'] for i in items]}))"
            % (REPO / "src", DB_PATH)
        )
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = str(seed)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=300, env=env, cwd=str(REPO))
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_identical_across_hash_seeds(self):
        a = self._run(3)
        b = self._run(29)
        assert a == b
        assert a["replay"] == "IDENTICAL"
