"""Phase G end-to-end investigation benchmark (§3, §8).

Reproducible benchmark of representative F1 engineering questions over
REAL canonical data, exercising the complete path:

User question → classification → evidence → deterministic analysis →
hypothesis evaluation → synthesis → schema validation → verification.

Per-case metrics recorded (§8): question category, evidence completeness,
evidence-reference validity, numerical correctness, baseline preservation,
claim-class correctness, contradiction handling, uncertainty calibration,
unsupported-claim count, schema validity, deterministic-vs-model output.

Negative cases assert honest failure (UNKNOWN/INCONCLUSIVE shapes), never
fabricated success. Live-model evaluations stay separate: every case here
is deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.data.historical.canonical_queries import get_canonical_queries
from racewise.question_engine.answer_schemas import AnswerSchema
from racewise.question_engine.engine import ask, follow_up
from racewise.question_engine.verification import verify_answer

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

A = "max-verstappen"
B = "sergio-perez"
BASE = {"driver_a": A, "driver_b": B, "season": 2023, "round": 1,
        "lap_number": 6}
BASE_NOLAP = {"driver_a": A, "driver_b": B, "season": 2023, "round": 1}


def _run(question: str, context: dict[str, Any]) -> dict[str, Any]:
    queries = get_canonical_queries()
    return ask(queries, question, context=dict(context))


def _metrics(out: dict[str, Any]) -> dict[str, Any]:
    """Per-case metric record (§8). All fields derived, none invented."""
    ans = out.get("answer") or {}
    ver = out.get("verification") or {}
    obs = ans.get("observations") or []
    return {
        "status": out.get("status"),
        "n_observations": len(obs),
        "n_calculations": len(ans.get("calculations") or []),
        "n_hypotheses": len(ans.get("hypotheses") or []),
        "n_spatial": len(ans.get("spatial") or []),
        "n_residuals": len(ans.get("residuals") or []),
        "n_not_established": len(ans.get("not_established") or []),
        "claim_classes": sorted({e.get("claim_class") for e in obs}),
        "verification_passed": ver.get("passed"),
        "verification_violations": len(ver.get("violations") or []),
        "schema_valid": _schema_valid(ans),
    }


def _schema_valid(ans: dict[str, Any]) -> bool:
    try:
        AnswerSchema.model_validate(ans)
        return True
    except Exception:
        return False


def _obs_by_statement(ans: dict[str, Any], fragment: str) -> list[dict[str, Any]]:
    return [o for o in (ans.get("observations") or [])
            if fragment.lower() in str(o.get("statement") or "").lower()]


@requires_db
class TestInvestigationBenchmark:
    """End-to-end cases over real Bahrain 2023 data."""

    def test_perez_sector2_full_reconciliation(self):
        """Mandatory case (§6/§10.2): the complete fixed answer."""
        out = _run("why did perez lose time in sector 2",
                   {**BASE, "sector": 2})
        ans = out["answer"]
        m = _metrics(out)
        assert out["status"] in ("ANSWERABLE", "PARTIALLY_ANSWERABLE",
                                 "ANALYSABLE_WITH_LIMITATIONS")
        # measured baseline preserved as OBSERVED fact
        deltas = _obs_by_statement(ans, "observed lap delta")
        assert deltas and deltas[0]["value"] == pytest.approx(0.732, abs=1e-3)
        assert deltas[0]["claim_class"] == "OBSERVED"
        assert deltas[0]["value"] > 0  # B minus A sign convention
        # sector facts address sector 2 and sum to the delta
        spatial = {s["scope"]: s for s in (ans.get("spatial") or [])}
        assert spatial["sector 2"]["measured_delta_s"] == pytest.approx(0.411, abs=1e-3)
        sec_sum = round(sum(s["measured_delta_s"] for s in spatial.values()), 4)
        assert sec_sum == pytest.approx(deltas[0]["value"], abs=1e-3)
        # gross is DERIVED and non-additive; net is the reconcilable figure
        gross = _obs_by_statement(ans, "gross slower-phase exposure")
        net = _obs_by_statement(ans, "net time-loss estimate")
        assert gross and gross[0]["claim_class"] == "DERIVED"
        assert net and net[0]["claim_class"] == "DERIVED"
        assert gross[0]["value"] > net[0]["value"] > deltas[0]["value"]
        assert abs(net[0]["value"] - deltas[0]["value"]) < \
            abs(gross[0]["value"] - deltas[0]["value"])
        # residual present, reported, never assigned
        assert m["n_residuals"] >= 1
        # mechanism evidence tied to hypotheses, never invented
        calcs = ans.get("calculations") or []
        mech = [c for c in calcs if c.get("capability_id") == "compare_laps"]
        assert {c.get("hypothesis_id") for c in mech} >= {
            "H1_corner_speed", "H2_throttle", "H3_braking"}
        assert all(c["claim_class"] == "DERIVED" for c in mech)
        # verification + schema
        assert m["verification_passed"] is True
        assert m["verification_violations"] == 0
        assert m["schema_valid"] is True
        # Phase H: execution ledger + stopping reason ride along
        assert out.get("stopping_reason")
        assert any(s["status"] == "SUCCEEDED"
                   for s in (out.get("execution") or []))

    def test_lap_compare_preserves_baseline(self):
        out = _run("compare Verstappen and Perez on lap 6 in Bahrain 2023",
                   dict(BASE))
        ans = out["answer"]
        m = _metrics(out)
        deltas = _obs_by_statement(ans, "observed lap delta")
        assert deltas and deltas[0]["value"] == pytest.approx(0.732, abs=1e-3)
        assert deltas[0]["claim_class"] == "OBSERVED"
        assert m["verification_passed"] is True
        assert m["schema_valid"] is True

    def test_stint_question_executes_with_trend(self):
        out = _run("Did Verstappen degrade through the stint in Bahrain 2023 "
                   "compared to Perez?",
                   {**BASE_NOLAP, "stint_number": 1})
        ans = out["answer"]
        m = _metrics(out)
        assert out["status"] in ("ANSWERABLE", "PARTIALLY_ANSWERABLE",
                                 "ANALYSABLE_WITH_LIMITATIONS")
        calcs = ans.get("calculations") or []
        stint_calcs = [c for c in calcs
                       if c.get("capability_id") == "analyze_stint"]
        assert stint_calcs, "stint question must execute analyze_stint"
        assert any("slope" in str(c.get("statement") or "").lower()
                   for c in stint_calcs)
        assert all(c["claim_class"] == "DERIVED" for c in stint_calcs
                   if c.get("value") is not None)
        assert m["verification_passed"] is True
        assert m["schema_valid"] is True

    def test_falsification_states_hypotheses_with_evidence(self):
        out = _run("Was it braking or corner speed that cost Perez time on lap 6?",
                   dict(BASE))
        ans = out["answer"]
        m = _metrics(out)
        hyps = ans.get("hypotheses") or []
        assert hyps, "falsification question must surface hypothesis states"
        # States use the engine's bucket vocabulary (contradicted and
        # not-supported share a bucket by design — see _extract_hypotheses).
        for h in hyps:
            assert h.get("state") in (
                "SUPPORTED", "CONTRADICTED_OR_NOT_SUPPORTED", "UNTESTABLE")
            assert h.get("hypothesis_id"), "every hypothesis names its id"
        assert m["verification_passed"] is True
        assert m["schema_valid"] is True

    def test_missing_telemetry_is_honest(self):
        out = _run("Why did Verstappen lose time to Perez on lap 44 in Bahrain 2023?",
                   {**BASE_NOLAP, "lap_number": 44})
        ans = out["answer"]
        assert out["status"] in ("INSUFFICIENT_EVIDENCE", "DATA_UNAVAILABLE")
        assert ans.get("missing_evidence") or ans.get("not_established"), (
            "missing data must be named, not hidden")
        tel_obs = [o for o in (ans.get("observations") or [])
                   if o.get("capability_id") == "compare_laps"]
        assert not tel_obs, "no telemetry figures may appear without telemetry"

    def test_corner_question_carries_resolution_limit(self):
        out = _run("Which corner cost Perez the most time on lap 6?",
                   dict(BASE))
        ans = out["answer"]
        entries = ans.get("not_established") or []
        assert any("corner-level attribution" in str(e.get("statement") or "")
                   for e in entries), (
            "corner questions must carry the resolution limit")

    def test_historic_era_without_telemetry_is_honest(self):
        out = _run("Why was Fangio slower than Farina at Silverstone in 1950?",
                   {"driver_a": "juan-manuel-fangio",
                    "driver_b": "giuseppe-farina",
                    "season": 1950, "round": 1})
        assert out["status"] in ("INSUFFICIENT_EVIDENCE", "DATA_UNAVAILABLE",
                                 "ANALYSABLE_WITH_LIMITATIONS")
        ans = out["answer"]
        tel_obs = [o for o in (ans.get("observations") or [])
                   if o.get("capability_id") in ("compare_laps", "attribute_lap_loss")
                   and o.get("value") is not None]
        assert not tel_obs, "1950 has no telemetry; none may be claimed"

    def test_followup_narrows_to_sector(self):
        queries = get_canonical_queries()
        base = ask(queries, "compare Verstappen and Perez on lap 6 in Bahrain 2023",
                   context=dict(BASE))
        ctx = base.get("context") or {}
        f2 = follow_up(queries, ctx, "did Perez lose time in sector 2?")
        fans = f2.get("answer") or {}
        assert f2.get("continued_from") == ctx.get("investigation_id")
        assert (f2.get("inherited_scope") or {}).get("sector") == 2
        spatial = {s["scope"]: s for s in (fans.get("spatial") or [])}
        assert spatial.get("sector 2", {}).get("measured_delta_s") == \
            pytest.approx(0.411, abs=1e-3)

    def test_counterfactual_path_is_honest_about_scope(self):
        out = _run("What if Perez had pitted one lap earlier in Bahrain 2023?",
                   dict(BASE))
        ans = out["answer"]
        assert out["status"] == "INSUFFICIENT_EVIDENCE"
        ne = ans.get("not_established") or []
        assert any("simulate_telemetry_counterfactual" in str(e.get("statement") or "")
                   for e in ne), (
            "counterfactual served elsewhere must be named, not silently dropped")
        assert not (ans.get("counterfactuals") or []), (
            "no modelled counterfactual may appear without execution")


@requires_db
class TestStintAndGapTools:
    """Tool-level coverage where the ask path needs different scope."""

    def test_stint_tool_reports_trend_and_compounds(self):
        from racewise.data.historical.stint_evidence import fuse_stint_evidence
        out = fuse_stint_evidence(
            get_canonical_queries(), 2023, 1, A, B, 1)
        assert out["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        trend = (out.get("performance") or {}).get("trend") or {}
        assert isinstance(trend.get("slope_per_stint_lap"), (int, float))
        meta = out.get("stint_metadata") or {}
        for side in ("driver_a_stint", "driver_b_stint"):
            assert meta.get(side, {}).get("compound")

    def test_gap_tool_reports_measured_gap(self):
        from racewise.data.historical.race_gap import decompose_race_gap
        out = decompose_race_gap(
            get_canonical_queries(), 2023, 1, A, B)
        assert "error" not in out
        official = out.get("official_result") or {}
        gap = official.get("gap_s")
        assert isinstance(gap, (int, float)), (
            "gap decomposition must report the official classified gap")
        assert "semantics" in official, "gap semantics must be documented"
        # VER won Bahrain 2023 by ~12 s (classification fact, not computed)
        assert gap == pytest.approx(11.987, abs=1e-3)


def test_benchmark_summary(capsys):
    """Per-case metric table (§8). Informational; assertions live per case."""
    cases = [
        ("PEREZ_SECTOR2", "why did perez lose time in sector 2",
         {**BASE, "sector": 2}),
        ("LAP_COMPARE", "compare Verstappen and Perez on lap 6 in Bahrain 2023",
         dict(BASE)),
        ("FALSIFY", "Was it braking or corner speed that cost Perez time on lap 6?",
         dict(BASE)),
        ("MISSING_LAP44",
         "Why did Verstappen lose time to Perez on lap 44 in Bahrain 2023?",
         {**BASE_NOLAP, "lap_number": 44}),
        ("CORNER", "Which corner cost Perez the most time on lap 6?",
         dict(BASE)),
        ("HISTORIC_1950",
         "Why was Fangio slower than Farina at Silverstone in 1950?",
         {"driver_a": "juan-manuel-fangio", "driver_b": "giuseppe-farina",
          "season": 1950, "round": 1}),
    ]
    queries = get_canonical_queries()
    rows = []
    for cid, question, ctx in cases:
        try:
            out = ask(queries, question, context=dict(ctx))
            m = _metrics(out)
            rows.append((cid, m["status"], m["n_observations"], m["n_hypotheses"],
                         m["n_spatial"], m["n_residuals"],
                         m["verification_violations"], m["schema_valid"]))
        except Exception as exc:  # noqa: BLE001 — table must always render
            rows.append((cid, f"ERROR {type(exc).__name__}", 0, 0, 0, 0, -1, False))
    with capsys.disabled():
        print("\ncase | status | obs | hyp | spatial | resid | violations | schema")
        for r in rows:
            print(f"{r[0]:12s} | {str(r[1]):24s} | {r[2]:3d} | {r[3]:3d} | "
                  f"{r[4]:7d} | {r[5]:5d} | {r[6]:10d} | {r[7]}")
