"""Phase 6N tests: engineering investigation synthesis & decision trace.

Pure tests cover the evidence item structure, hypothesis-evaluation state
rules (including the contradiction regression: SUPPORTED + CONTRADICTED can
never synthesize as an established explanation), synthesis conclusion
states, counterfactual eligibility semantics and the epistemic invariants -
all on synthetic ledgers with no DB. Live tests run only when the canonical
DB exists.
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


def _item(eid, hyps, supports=False, contradicts=False,
          evidence_type="FACT", claim_class="OBSERVED"):
    from racewise.data.historical.investigation_synthesis import _evidence_item

    return _evidence_item(
        eid,
        evidence_type=evidence_type,
        source_phase="6F",
        source_tool="fuse_lap_evidence",
        source_reference={"analysis": "test", "id": eid},
        claim=f"test claim {eid}",
        claim_class=claim_class,
        measured_value=0.5,
        units="s",
        state="TEST",
        hypothesis_ids=list(hyps),
        assumptions=[],
        limitations=[],
        supports=supports,
        contradicts=contradicts,
    )


# ---------------------------------------------------------------------------
# evidence ledger structure (pure)
# ---------------------------------------------------------------------------


class TestEvidenceItem:
    def test_source_hash_is_deterministic_16hex(self):
        a = _item("e1", [])
        b = _item("e1", [])
        assert a["source_hash"] == b["source_hash"]
        assert len(a["source_hash"]) == 16
        int(a["source_hash"], 16)

    def test_claim_classes_never_merged(self):
        obs = _item("e1", [], claim_class="OBSERVED")
        der = _item("e2", [], claim_class="DERIVED")
        assert obs["claim_class"] == "OBSERVED"
        assert der["claim_class"] == "DERIVED"
        assert obs["claim_class"] != der["claim_class"]

    def test_state_none_stays_none(self):
        # None state must serialize as null, never the string 'None'
        from racewise.data.historical.investigation_synthesis import _opt_str

        assert _opt_str(None) is None
        assert _opt_str("SUPPORTED") == "SUPPORTED"
        item = _item("e1", [])
        item["state"] = None
        assert "None" not in json.dumps(item)


# ---------------------------------------------------------------------------
# hypothesis evaluation + falsification gate (pure, synthetic ledgers)
# ---------------------------------------------------------------------------


def _evaluate(ledger, hyps=None):
    from racewise.data.historical.investigation_synthesis import (
        _evaluate_hypotheses,
    )

    return _evaluate_hypotheses(ledger, tuple(hyps) if hyps else None)


class TestHypothesisEvaluation:
    def test_support_with_neutral_is_partial(self):
        ledger = [
            _item("e1", ["H1_corner_speed"], supports=True),
            _item("e2", ["H1_corner_speed"]),
        ]
        ev, _gate = _evaluate(ledger)
        assert ev["H1_corner_speed"]["aggregate_state"] == "PARTIALLY_SUPPORTED"

    def test_contradiction_regression_supported_plus_contradicted_blocked(self):
        # THE contradiction regression: supporting AND contradicting evidence
        # (a direct conflict pair) must yield MIXED_EVIDENCE, never SUPPORTED,
        # and must be blocked by the falsification gate.
        ledger = [
            _item("e1", ["H1_corner_speed"], supports=True),
            _item("e2", ["H1_corner_speed"], contradicts=True),
        ]
        ev, gate = _evaluate(ledger)
        assert ev["H1_corner_speed"]["aggregate_state"] == "MIXED_EVIDENCE"
        assert ev["H1_corner_speed"]["falsification_status"] == "MIXED"
        assert ev["H1_corner_speed"]["unresolved_contradictions"] is True
        assert "H1_corner_speed" in gate["hypotheses_with_unresolved_contradictions"]
        assert "H1_corner_speed" not in gate["establishable_hypotheses"]

    def test_contradict_only_is_not_supported(self):
        ledger = [_item("e1", ["H3_braking"], contradicts=True)]
        ev, _ = _evaluate(ledger)
        assert ev["H3_braking"]["aggregate_state"] == "NOT_SUPPORTED"

    def test_support_only_is_supported(self):
        ledger = [
            _item("e1", ["H2_throttle"], supports=True),
            _item("e2", ["H2_throttle"], supports=True),
        ]
        ev, _ = _evaluate(ledger)
        assert ev["H2_throttle"]["aggregate_state"] == "SUPPORTED"
        assert "H2_throttle" in _evaluate(ledger)[1]["establishable_hypotheses"]

    def test_no_items_is_not_testable(self):
        ev, _ = _evaluate([])
        assert ev["H4_tyre_state"]["aggregate_state"] == "NOT_TESTABLE"
        assert ev["H4_tyre_state"]["requested"] is True

    def test_excluded_hypothesis_is_not_requested(self):
        ev, _ = _evaluate([], hyps=["H1_corner_speed"])
        assert ev["H1_corner_speed"]["requested"] is True
        assert ev["H6_drs"]["requested"] is False
        assert ev["H6_drs"]["aggregate_state"] == "NOT_REQUESTED"

    def test_untestable_items_yield_not_testable(self):
        # only non-decisive evidence -> INSUFFICIENT, never NOT_SUPPORTED
        ledger = [_item("e1", ["H5_race_control"])]
        ev, _ = _evaluate(ledger)
        assert ev["H5_race_control"]["aggregate_state"] in (
            "INSUFFICIENT_EVIDENCE", "NOT_TESTABLE")

    def test_never_scores_or_ranks(self):
        ledger = [_item("e1", ["H1_corner_speed"], supports=True)]
        ev, _ = _evaluate(ledger)
        blob = json.dumps(ev)
        for banned in ("confidence", "score", "rank", "probability",
                       "winner", "best_explanation"):
            assert banned not in blob


class TestEvidenceConflicts:
    def test_conflict_pair_recorded_and_preserved(self):
        from racewise.data.historical.investigation_synthesis import (
            _evidence_conflicts,
        )

        ledger = [
            _item("e1", ["H1_corner_speed"], supports=True),
            _item("e2", ["H1_corner_speed"], contradicts=True),
        ]
        conflicts = _evidence_conflicts(ledger)
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c["evidence_ids"] == ["e1", "e2"]
        assert c["hypothesis_ids"] == ["H1_corner_speed"]
        assert c["conflict_type"] == "DIRECT_CONTRADICTION"
        assert c["resolution_status"] == "UNRESOLVED"

    def test_no_conflict_without_shared_hypothesis(self):
        from racewise.data.historical.investigation_synthesis import (
            _evidence_conflicts,
        )

        ledger = [
            _item("e1", ["H1_corner_speed"], supports=True),
            _item("e2", ["H6_drs"], contradicts=True),
        ]
        assert _evidence_conflicts(ledger) == []


# ---------------------------------------------------------------------------
# counterfactual eligibility semantics (pure constants + module contract)
# ---------------------------------------------------------------------------


class TestCounterfactualSemantics:
    def test_state_vocabulary_is_closed(self):
        from racewise.data.historical.investigation_synthesis import (
            CF_ELIGIBLE, CF_INELIGIBLE, CF_INSUFFICIENT,
            CF_TEL_UNAVAILABLE, CF_UNSUPPORTED_MODEL,
        )

        assert {CF_ELIGIBLE, CF_INELIGIBLE, CF_INSUFFICIENT,
                CF_TEL_UNAVAILABLE, CF_UNSUPPORTED_MODEL} == {
            "ELIGIBLE", "INELIGIBLE", "INSUFFICIENT_EVIDENCE",
            "TELEMETRY_UNAVAILABLE", "UNSUPPORTED_MODEL"}

    def test_bounds(self):
        from racewise.data.historical.investigation_synthesis import (
            MAX_COUNTERFACTUALS, MAX_EVIDENCE_ITEMS,
        )

        assert MAX_EVIDENCE_ITEMS == 40
        assert MAX_COUNTERFACTUALS == 2

    def test_question_types_is_closed_vocabulary(self):
        from racewise.data.historical.investigation_synthesis import (
            QUESTION_TYPES,
        )

        assert QUESTION_TYPES == (
            "LAP_PERFORMANCE", "STINT_PERFORMANCE", "RACE_GAP",
            "PERFORMANCE_REGIME", "CROSS_RACE_PATTERN",
            "HYPOTHESIS_EVALUATION", "COUNTERFACTUAL_ELIGIBILITY",
        )

    def test_hypothesis_ids_reused_verbatim(self):
        from racewise.data.historical.investigation_synthesis import (
            HYPOTHESIS_IDS,
        )

        assert HYPOTHESIS_IDS == tuple(HIDS)


class TestEpistemicInvariants:
    def test_boundary_statements_present(self):
        from racewise.data.historical.investigation_synthesis import (
            EPISTEMIC_BOUNDARIES,
        )

        blob = " | ".join(EPISTEMIC_BOUNDARIES)
        for invariant in ("SUPPORT != PROOF",
                          "MODEL_SENSITIVITY != HISTORICAL_EFFECT",
                          "COUNTERFACTUAL != HISTORY",
                          "MISSING_DATA != NEGATIVE_EVIDENCE",
                          "NOT_TESTABLE != CONTRADICTED",
                          "INSUFFICIENT_EVIDENCE != NOT_SUPPORTED"):
            assert invariant in blob

    def test_synthesis_conclusion_states_closed(self):
        from racewise.data.historical.investigation_synthesis import (
            CONCL_INSUFFICIENT, CONCL_MIXED, CONCL_NOT_TESTABLE,
            CONCL_SUPPORTED, CONCL_UNAVAILABLE,
        )

        assert {CONCL_SUPPORTED, CONCL_MIXED, CONCL_INSUFFICIENT,
                CONCL_NOT_TESTABLE, CONCL_UNAVAILABLE} == {
            "SUPPORTED_BY_AVAILABLE_EVIDENCE", "MIXED_EVIDENCE",
            "INSUFFICIENT_EVIDENCE", "NOT_TESTABLE", "UNAVAILABLE"}


# ---------------------------------------------------------------------------
# live tests (canonical DB present)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries(str(DB_PATH))


@requires_db
class TestLiveInvestigation:
    def test_stint_investigation_full_contract(self, queries):
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="STINT_PERFORMANCE",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, stint_number=1)
        assert inv["status"] == "VALID"
        assert len(inv["evidence_ledger"]) > 0
        assert inv["synthesis"]["conclusion_state"] in (
            "SUPPORTED_BY_AVAILABLE_EVIDENCE", "MIXED_EVIDENCE",
            "INSUFFICIENT_EVIDENCE", "NOT_TESTABLE", "UNAVAILABLE")
        # hypothesis evaluations: closed states, never ranked
        states = {v["aggregate_state"]
                  for v in inv["hypothesis_evaluations"].values()}
        assert states <= {"SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED",
                          "CONTRADICTED", "NOT_TESTABLE",
                          "INSUFFICIENT_EVIDENCE", "MIXED_EVIDENCE",
                          "NOT_REQUESTED"}
        # every trace statement references evidence
        all_eids = {e["evidence_id"] for e in inv["evidence_ledger"]}
        for t in inv["decision_trace"]:
            assert set(t["basis"]) <= all_eids
        # gate blocked hypotheses never appear as established
        blocked = set(inv["falsification_gate"]
                      ["hypotheses_with_unresolved_contradictions"])
        est = set(inv["falsification_gate"]["establishable_hypotheses"])
        assert blocked.isdisjoint(est)
        # snapshot integrity
        snap = inv["investigation_snapshot"]
        assert snap["evidence_ids"] == [e["evidence_id"]
                                        for e in inv["evidence_ledger"]]

    def test_stint_counterfactual_modelled(self, queries):
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="STINT_PERFORMANCE",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, stint_number=1)
        executed = inv["executed_counterfactuals"]
        assert executed, "expected a 6I-eligible stint counterfactual"
        for cf in executed:
            assert cf["claim_class"] == "MODELLED"
            assert cf["epistemics"]
            assert "not a historical fact" in cf["epistemics"] or \
                "not history" in cf["epistemics"] or \
                "model sensitivity" in cf["epistemics"]

    def test_race_level_counterfactual_structurally_ineligible(self, queries):
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="COUNTERFACTUAL_ELIGIBILITY",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1)
        cands = inv["counterfactual_candidates"]
        assert cands
        assert all(c["status"] == "INELIGIBLE" for c in cands)
        assert not inv["executed_counterfactuals"]

    def test_replay_in_process_identical(self, queries):
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        kw = dict(question_type="LAP_PERFORMANCE",
                  driver_a="max-verstappen", driver_b="sergio-perez",
                  season=2023, round_num=1, lap_number=6)
        a = run_engineering_investigation(queries, **kw)
        b = run_engineering_investigation(queries, **kw)
        assert a["output_hash"] == b["output_hash"]
        assert a == b

    def test_unknown_pattern_preserves_unavailable(self, queries):
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="CROSS_RACE_PATTERN",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, pattern_id="does-not-exist")
        assert inv["status"] == "VALID"  # framing itself is well-formed
        assert inv["collection"]["status"] == "UNAVAILABLE"
        assert inv["synthesis"]["conclusion_state"] == "UNAVAILABLE"
        assert inv["evidence_ledger"] == []

    def test_lap_beyond_race_is_unavailable(self, queries):
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="LAP_PERFORMANCE",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, lap_number=999)
        assert inv["status"] == "UNAVAILABLE"
        assert "lap 999" in inv["reason"]

    def test_invalid_requests_rejected(self, queries):
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        assert run_engineering_investigation(
            queries, question_type="BOGUS", driver_a="max-verstappen",
            driver_b="sergio-perez", season=2023, round_num=1
        )["status"] == "INVALID"
        assert run_engineering_investigation(
            queries, question_type="RACE_GAP", driver_a="max-verstappen",
            driver_b="max-verstappen", season=2023, round_num=1
        )["status"] == "INVALID"
        assert run_engineering_investigation(
            queries, question_type="RACE_GAP", driver_a="max-verstappen",
            driver_b="sergio-perez", season=1949, round_num=1
        )["status"] == "INVALID"
        assert run_engineering_investigation(
            queries, question_type="RACE_GAP", driver_a="max-verstappen",
            driver_b="sergio-perez", season=2023, round_num=1,
            max_evidence_items=41
        )["status"] == "INVALID"

    def test_hypothesis_subset_not_requested_not_removed(self, queries):
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        inv = run_engineering_investigation(
            queries, question_type="RACE_GAP",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2024, round_num=14, hypotheses=["H1_corner_speed"])
        assert inv["hypotheses_in_scope"] == ["H1_corner_speed"]
        states = inv["hypothesis_evaluations"]
        assert states["H1_corner_speed"]["requested"] is True
        assert states["H6_drs"]["requested"] is False
        assert states["H6_drs"]["aggregate_state"] == "NOT_REQUESTED"

    def test_no_db_write_marker(self, queries):
        # investigations are derived-on-read: the DB file must be untouched
        before = DB_PATH.stat().st_mtime_ns, DB_PATH.stat().st_size
        from racewise.data.historical.investigation_synthesis import (
            run_engineering_investigation,
        )

        run_engineering_investigation(
            queries, question_type="STINT_PERFORMANCE",
            driver_a="max-verstappen", driver_b="sergio-perez",
            season=2023, round_num=1, stint_number=1)
        after = DB_PATH.stat().st_mtime_ns, DB_PATH.stat().st_size
        assert before == after


@requires_db
class TestSubprocessDeterminism:
    def _run(self, seed):
        code = (
            "import sys, json;"
            "sys.path.insert(0, r'%s');"
            "from racewise.data.historical.canonical_queries import CanonicalQueries;"
            "from racewise.data.historical.investigation_synthesis import run_engineering_investigation;"
            "q = CanonicalQueries(r'%s');"
            "inv = run_engineering_investigation("
            "q, question_type='LAP_PERFORMANCE', driver_a='max-verstappen',"
            "driver_b='sergio-perez', season=2023, round_num=1, lap_number=6);"
            "print(json.dumps({'h': inv['output_hash'],"
            "'c': inv['synthesis']['conclusion_state']}))"
            % (REPO / "src", DB_PATH)
        )
        env = dict(os.environ)  # inherit environment (PATH etc.)
        env["PYTHONHASHSEED"] = str(seed)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=300, env=env, cwd=str(REPO))
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_identical_across_hash_seeds(self):
        a = self._run(3)
        b = self._run(29)
        assert a == b
        assert a["c"] in ("MIXED_EVIDENCE", "SUPPORTED_BY_AVAILABLE_EVIDENCE",
                          "INSUFFICIENT_EVIDENCE", "NOT_TESTABLE",
                          "UNAVAILABLE")
