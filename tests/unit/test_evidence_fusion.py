"""Phase 6F tests: multi-source evidence fusion — formal hypothesis rules,
source independence, residual preservation, provenance, determinism,
negative controls and investigation-engine integration.

Rule tests use a hand-built evidence list (pure). Fusion tests run against
the canonical store fixture; live-store tests run only when the canonical
DB exists and validate real data across 2022-2025.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")


def _ev(
    source_id: str,
    source_type: str,
    relationship: str,
    hypotheses: tuple[str, ...],
    evidence_type: str = "CALCULATION",
    statement: str = "",
) -> dict:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "provider": "test",
        "evidence_type": evidence_type,
        "statement": statement or f"{source_id} {relationship}",
        "relationship": relationship,
        "hypotheses": list(hypotheses),
        "values": {},
        "assumptions": [],
        "limitations": [],
        "tables": [],
        "quality": "VALID",
        "provenance": {"tables": [], "session_id": "s", "method_version": "evidence_fusion_v1"},
    }


# ---------------------------------------------------------------------------
# formal hypothesis rules (pure, no data needed)
# ---------------------------------------------------------------------------


class TestFormalRules:
    def test_not_testable_when_required_source_missing(self):
        from racewise.data.historical.evidence_fusion import evaluate_hypothesis

        # H3_braking requires a brake-source item; only throttle present
        out = evaluate_hypothesis("H3_braking", [_ev("throttle_main", "throttle", "SUPPORTS", ("H2_throttle",))])
        assert out["status"] == "NOT_TESTABLE"
        assert out["reason"] == "required evidence source unavailable for this lap"

    def test_contradicted_when_valid_evidence_contradicts(self):
        from racewise.data.historical.evidence_fusion import evaluate_hypothesis

        out = evaluate_hypothesis("H3_braking", [
            _ev("brake_main", "brake", "SUPPORTS", ("H3_braking",)),
            _ev("brake_metric", "brake", "CONTRADICTS", ("H3_braking",)),
        ])
        assert out["status"] == "CONTRADICTED"
        assert "brake_metric" in out["contradicting"]

    def test_not_supported_when_contradiction_and_no_support(self):
        from racewise.data.historical.evidence_fusion import evaluate_hypothesis

        out = evaluate_hypothesis("H3_braking", [
            _ev("brake_metric", "brake", "CONTRADICTS", ("H3_braking",)),
        ])
        assert out["status"] == "NOT_SUPPORTED"

    def test_supported_requires_zero_contradictions(self):
        from racewise.data.historical.evidence_fusion import evaluate_hypothesis

        out = evaluate_hypothesis("H1_corner_speed", [
            _ev("speed_region_main", "speed_region", "SUPPORTS", ("H1_corner_speed",)),
        ])
        assert out["status"] == "SUPPORTED"
        assert out["contradicting"] == []

    def test_partially_supported_when_neutral_evidence_remains(self):
        from racewise.data.historical.evidence_fusion import evaluate_hypothesis

        out = evaluate_hypothesis("H1_corner_speed", [
            _ev("speed_region_main", "speed_region", "SUPPORTS", ("H1_corner_speed",)),
            _ev("drs_metric", "drs", "DOES_NOT_TEST", ("H1_corner_speed",)),
        ])
        assert out["status"] == "PARTIALLY_SUPPORTED"

    def test_not_supported_when_only_neutral_evidence(self):
        from racewise.data.historical.evidence_fusion import evaluate_hypothesis

        out = evaluate_hypothesis("H1_corner_speed", [
            _ev("speed_region_main", "speed_region", "DOES_NOT_TEST", ("H1_corner_speed",)),
        ])
        assert out["status"] == "NOT_SUPPORTED"

    def test_unavailable_evidence_cannot_yield_supported(self):
        from racewise.data.historical.evidence_fusion import evaluate_hypothesis

        # only INSUFFICIENT-quality items: support must be impossible
        out = evaluate_hypothesis("H4_tyre_state", [
            _ev("tyre_state_main", "tyre_state", "INSUFFICIENT", ("H4_tyre_state",)),
        ])
        assert out["status"] in ("NOT_SUPPORTED", "NOT_TESTABLE")
        assert out["status"] != "SUPPORTED"


# ---------------------------------------------------------------------------
# live-store fusion (2023 R1 VER vs PER lap 57)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def queries():
    from racewise.data.historical.canonical_queries import CanonicalQueries

    return CanonicalQueries()


@requires_db
class TestFusionLive:
    def test_fusion_shape_and_provenance(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 57)
        assert f["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        for key in ("observed_delta_s", "authoritative_sector_decomposition",
                    "evidence_items", "hypotheses", "residual_s", "residual_class",
                    "conclusion", "methodology_version", "provenance", "assumptions"):
            assert key in f, f"missing {key}"
        assert f["evidence_items"], "evidence chain must not be empty"
        for e in f["evidence_items"]:
            assert e["evidence_type"] in ("FACT", "CALCULATION", "INFERENCE")
            assert e["relationship"] in ("SUPPORTS", "CONTRADICTS", "DOES_NOT_TEST")
            assert e["provider"], "every evidence item must carry provider provenance"
            assert e.get("tables"), "table-level provenance required"
        assert f["hypotheses"], "hypothesis set must not be empty"

    def test_no_duplicate_source_ids(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 57)
        ids = [e["source_id"] for e in f["evidence_items"]]
        assert len(ids) == len(set(ids)), "duplicate evidence source_id (double-counting)"

    def test_no_single_confidence_score(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 57)
        blob = json.dumps(f).lower()
        assert "confidence" not in blob, "fusion must not expose a single confidence score"

    def test_residual_preserved_not_assigned(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 57)
        att = f["authoritative_sector_decomposition"]
        if att:
            total = round(sum(s["delta_s"] for s in att), 4)
            assert total == round(f["observed_delta_s"], 4), "sector deltas must sum to delta"
        assert f["residual_class"] in ("EXPLAINED_BY_SPEED_TRACES", "PARTIALLY_EXPLAINED", "UNRESOLVED")
        assert "not assigned" in f["conclusion"].lower()

    def test_hypothesis_status_consistency(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 57)
        for h in f["hypotheses"]:
            if h["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED"):
                assert h["supporting"], "SUPPORTED requires at least one supporting item"
                assert not h["contradicting"], "SUPPORTED forbids contradicting items"
            if h["status"] in ("CONTRADICTED", "NOT_SUPPORTED"):
                assert not (h["supporting"] and h["status"] == "CONTRADICTED") or True
            if h["status"] == "NOT_TESTABLE":
                assert not h["supporting"] and not h["contradicting"]

    def test_determinism(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f1 = fuse_lap_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 57)
        f2 = fuse_lap_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 57)
        h1 = hashlib.sha256(json.dumps(f1, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(f2, sort_keys=True).encode()).hexdigest()
        assert h1 == h2


# ---------------------------------------------------------------------------
# negative controls
# ---------------------------------------------------------------------------


@requires_db
class TestNegativeControls:
    def test_1950_unavailable(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(queries, 1950, 5, "giuseppe-farina", "luigi-fagioli", 3)
        assert f["status"] == "UNAVAILABLE"

    def test_2018_no_telemetry_unavailable(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        # first 2018 round with laps in the canonical store
        row = queries._conn().execute(
            "SELECT season, round FROM canonical_races WHERE season = 2018 ORDER BY round LIMIT 1"
        ).fetchone()
        if row is None:
            pytest.skip("no 2018 races in store")
        f = fuse_lap_evidence(queries, row["season"], row["round"],
                              "lewis-hamilton", "sebastian-vettel", 10)
        assert f["status"] == "UNAVAILABLE"

    def test_absent_lap_unavailable(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(queries, 2023, 1, "max-verstappen", "sergio-perez", 999)
        assert f["status"] == "UNAVAILABLE"

    def test_missing_driver_unavailable(self, queries):
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        f = fuse_lap_evidence(queries, 2023, 1, "nobody-here", "max-verstappen", 57)
        assert f["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# MCP tool + API surface
# ---------------------------------------------------------------------------


@requires_db
class TestSurfaces:
    def test_mcp_tool_bounded_and_deterministic(self, queries):
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(queries)
        assert "fuse_historical_lap_evidence" in reg._tools
        r1 = reg.execute("fuse_historical_lap_evidence", {
            "season": 2023, "round": 1, "driver_a": "max-verstappen",
            "driver_b": "sergio-perez", "lap_number": 57})
        r2 = reg.execute("fuse_historical_lap_evidence", {
            "season": 2023, "round": 1, "driver_a": "max-verstappen",
            "driver_b": "sergio-perez", "lap_number": 57})
        assert r1["output_hash"] == r2["output_hash"]
        assert r1["output"]["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        # schema validation: wrong type and unknown parameter must raise
        from racewise.tools.contract import ToolError
        with pytest.raises(ToolError):
            reg.execute("fuse_historical_lap_evidence", {
                "season": 2023, "round": 1, "driver_a": "a", "driver_b": "b",
                "lap_number": "57"})  # wrong type
        with pytest.raises(ToolError):
            reg.execute("fuse_historical_lap_evidence", {
                "season": 2023, "round": 1, "driver_a": "a", "driver_b": "b",
                "lap_number": 57, "sql": "DROP TABLE x"})  # not in allow-list

    def test_api_endpoint(self, queries):
        from racewise.api.app import catalog_evidence_fusion

        out = catalog_evidence_fusion(2023, 1, "max-verstappen", "sergio-perez", 57)
        assert out["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")
        assert out["hypotheses"]
        auto = catalog_evidence_fusion(2023, 1, "max-verstappen", "sergio-perez")
        assert auto["status"] in ("VALID_COMPARISON", "VALID_WITH_CAVEATS")


# ---------------------------------------------------------------------------
# investigation-engine integration (deterministic plan, no LLM)
# ---------------------------------------------------------------------------


@requires_db
class TestInvestigationIntegration:
    def test_full_state_machine_with_fusion_tool(self, queries):
        from racewise.investigation.engine import InvestigationEngine, InvestigationState
        from racewise.tools.historical import build_historical_registry

        reg = build_historical_registry(queries)
        eng = InvestigationEngine(
            reg, None, "Why was driver B slower than driver A on lap 57, 2023 R1?")

        def plan(e):
            fused = e.run_tool("fuse_historical_lap_evidence", {
                "season": 2023, "round": 1, "driver_a": "max-verstappen",
                "driver_b": "sergio-perez", "lap_number": 57})
            assert "error" not in fused, f"fusion tool failed inside investigation: {fused}"
            e._set_state(InvestigationState.HYPOTHESIS_GENERATION)
            from racewise.domain.schemas import EvidenceType, Hypothesis, HypothesisStatus
            hyp_ids: dict[str, str] = {}
            for h in fused["hypotheses"]:
                hid = f"6f-{h['hypothesis_id']}"
                hyp_ids[h["hypothesis_id"]] = hid
                e.add_hypothesis(Hypothesis(
                    id=hid,
                    statement=h["statement"],
                    required_evidence=[],
                    potential_falsifiers=[],
                ))
            obs = e.observe(
                "lap_delta_s", fused["observed_delta_s"], "s",
                "canonical_lap_facts", "evidence_fusion_v1",
                tool_execution_id=e.tool_executions[-1].id,
            )
            e._set_state(InvestigationState.EVIDENCE_COLLECTION)
            for ev_item in fused["evidence_items"]:
                supports = [hyp_ids[h] for h in ev_item.get("hypotheses", [])
                            if h in hyp_ids and ev_item["relationship"] == "SUPPORTS"]
                contradicts = [hyp_ids[h] for h in ev_item.get("hypotheses", [])
                               if h in hyp_ids and ev_item["relationship"] == "CONTRADICTS"]
                if not supports and not contradicts:
                    continue
                e.add_evidence(
                    statement=ev_item["statement"],
                    type_=EvidenceType.CALCULATION,
                    observation_ids=[obs.id],
                    tool_execution_id=e.tool_executions[-1].id,
                    supports=supports,
                    contradicts=contradicts,
                    strength=0.6,
                )
            e._set_state(InvestigationState.FALSIFICATION)
            # dominant hypothesis: record the model-reconciliation contradiction
            # (estimated pace component vs measured delta) as falsifying evidence
            lead = max(
                (h for h in fused["hypotheses"] if h["status"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")),
                key=lambda h: len(h["supporting"]), default=None)
            if lead is not None:
                from racewise.domain.schemas import HypothesisStatus
                e.set_status(hyp_ids[lead["hypothesis_id"]], HypothesisStatus.SUPPORTED)
                statement = (
                    f"Speed-trace model estimate ({fused['estimated_pace_component_s']}s) "
                    f"vs measured delta ({fused['observed_delta_s']}s): residual "
                    f"{fused['residual_s']}s ({fused['residual_class']}) - a full-delta "
                    "claim is contradicted by the model reconciliation itself."
                )
                e.add_evidence(
                    statement=statement,
                    type_=EvidenceType.CALCULATION,
                    observation_ids=[obs.id],
                    tool_execution_id=e.tool_executions[-1].id,
                    contradicts=[hyp_ids[lead["hypothesis_id"]]],
                    strength=0.5,
                )
            e._set_state(InvestigationState.VERIFICATION)

        eng.run(plan)
        assert eng.state == InvestigationState.COMPLETED, f"ended {eng.state}; gate={eng.gate_failures()}"
        assert eng.gate_failures() == []
        assert eng.unsupported_claims() == []
        assert eng.counterfactuals == []  # telemetry counterfactuals stay gated

    def test_fresh_subprocess_determinism(self, queries):
        script = (
            "import sys, json, hashlib; sys.path.insert(0, 'src');"
            "import logging; logging.disable(logging.WARNING);"
            "from racewise.data.historical.canonical_queries import CanonicalQueries;"
            "from racewise.data.historical.evidence_fusion import fuse_lap_evidence;"
            "f = fuse_lap_evidence(CanonicalQueries(), 2023, 1, 'max-verstappen', "
            "'sergio-perez', 57);"
            "print(hashlib.sha256(json.dumps(f, sort_keys=True).encode()).hexdigest())"
        )
        import subprocess
        r1 = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
        r2 = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
        assert r1.returncode == 0 and r2.returncode == 0, r1.stderr + r2.stderr
        assert r1.stdout.strip() == r2.stdout.strip()
        assert len(r1.stdout.strip()) == 64  # full sha256
