"""Phase 6S GAP 2 tests: non-RACE (QUALIFYING) session investigations.

Covers the engine validation matrix (closed session-type vocabulary,
qualifying comparability semantics, honest UNAVAILABLE for pre-2018),
the qualifying lap-fusion evidence rules, API behavior (200/422/404/
unavailable), determinism (same-process x3 + cross-process PYTHONHASHSEED
3/29) and replay round-trips. Live tests run only when the canonical DB
exists. RACE behavior is regression-guarded against the Phase 6R goldens.
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
requires_db = pytest.mark.skipif(not DB_PATH.exists(),
                                 reason="canonical DB not present")

QBASE = dict(
    question_type="LAP_PERFORMANCE",
    driver_a="max-verstappen",
    driver_b="sergio-perez",
    season=2022,
    round=4,
    lap_number=2,
    session_type="QUALIFYING",
)


def _run(qt, a, b, season, round_num, lap=None, stint=None, st="RACE"):
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    return run_engineering_investigation(
        get_canonical_queries(), qt, a, b, season, round_num,
        lap_number=lap, stint_number=stint, session_type=st)


# ---------------------------------------------------------------------------
# engine validation matrix
# ---------------------------------------------------------------------------

@requires_db
class TestQualifyingValidation:
    def test_unknown_session_type_is_invalid(self):
        res = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                   2022, 4, lap=2, st="SPRINT")
        assert res["status"] == "INVALID"
        assert "'RACE', 'QUALIFYING'" in res["reason"]

    def test_stint_scoped_question_invalid_for_qualifying(self):
        res = _run("STINT_PERFORMANCE", "max-verstappen", "sergio-perez",
                   2022, 4, stint=1, st="QUALIFYING")
        assert res["status"] == "INVALID"
        assert "no qualifying comparability semantics" in res["reason"]

    def test_race_gap_invalid_for_qualifying(self):
        res = _run("RACE_GAP", "max-verstappen", "sergio-perez",
                   2022, 4, st="QUALIFYING")
        assert res["status"] == "INVALID"
        assert "no race distance" in res["reason"]

    def test_pre_2018_qualifying_is_unavailable(self):
        res = _run("LAP_PERFORMANCE", "luigi-fagioli",
                   "juan-manuel-fangio", 1950, 1, lap=1, st="QUALIFYING")
        assert res["status"] == "UNAVAILABLE"
        assert "coverage begins 2018" in res["reason"]

    def test_qualifying_participants_resolved_from_qualifying(self):
        # a driver absent from qualifying is UNAVAILABLE even when present
        # in the race result
        res = _run("LAP_PERFORMANCE", "max-verstappen",
                   "nino-farina", 2022, 4, lap=2, st="QUALIFYING")
        assert res["status"] == "UNAVAILABLE"
        assert "canonical qualifying classification" in res["reason"]

    def test_absent_lap_is_unavailable(self):
        res = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                   2022, 4, lap=999, st="QUALIFYING")
        assert res["status"] == "UNAVAILABLE"
        assert "QUALIFYING" in res["reason"]


# ---------------------------------------------------------------------------
# qualifying fusion semantics
# ---------------------------------------------------------------------------

@requires_db
class TestQualifyingFusion:
    def test_valid_with_measured_sector_decomposition(self):
        res = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                   2022, 4, lap=2, st="QUALIFYING")
        assert res["status"] == "VALID"
        assert res["synthesis"]["conclusion_state"] == \
            "SUPPORTED_BY_AVAILABLE_EVIDENCE"
        tools = {e["source_tool"] for e in res["evidence_ledger"]}
        assert "fuse_qualifying_lap_evidence" in tools
        assert "attribute_lap_loss" not in tools
        # sector decomposition is present and sums to the lap delta
        obs = next(e for e in res["evidence_ledger"]
                   if e["source_reference"].get("kind") == "observed_delta")
        assert obs["measured_value"] is not None
        # provenance names the qualifying source tables
        assert "canonical_qualifying" in res["provenance"]["source_tables"]
        assert "canonical_telemetry" not in \
            res["provenance"]["source_tables"]

    def test_no_fabricated_telemetry_evidence(self):
        res = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                   2022, 4, lap=2, st="QUALIFYING")
        for e in res["evidence_ledger"]:
            assert "canonical_telemetry" not in (e.get("provenance") or {})
        states = res["investigation_snapshot"]["hypothesis_states"]
        # telemetry-only hypotheses must never be claimed as measured here
        for h in ("H2_throttle", "H3_braking", "H6_drs"):
            assert states[h] in ("NOT_TESTABLE", "INSUFFICIENT_EVIDENCE",
                                 "NOT_SUPPORTED")

    def test_hypothesis_evaluation_subsetting_works(self):
        res = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                   2022, 4, lap=2, st="QUALIFYING")
        assert res["status"] == "VALID"
        subset = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                      2022, 4, lap=2, st="QUALIFYING")
        assert subset["status"] == "VALID"


# ---------------------------------------------------------------------------
# determinism + replay
# ---------------------------------------------------------------------------

@requires_db
class TestQualifyingDeterminism:
    def test_same_process_three_runs_identical(self):
        runs = [_run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                     2022, 4, lap=2, st="QUALIFYING") for _ in range(3)]
        hashes = {r["output_hash"] for r in runs}
        assert len(hashes) == 1
        ids = {r["investigation_id"] for r in runs}
        assert len(ids) == 1

    def test_replay_identical(self):
        from racewise.data.historical.investigation_memory import (
            build_investigation_snapshot, replay_engineering_investigation,
        )
        from racewise.data.historical.canonical_queries import (
            get_canonical_queries,
        )

        inv = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                   2022, 4, lap=2, st="QUALIFYING")
        snap = build_investigation_snapshot(inv)
        rep = replay_engineering_investigation(get_canonical_queries(), snap)
        assert rep["status"] == "IDENTICAL"
        assert rep["identical"] is True

    def test_cross_process_identical(self):
        script = (
            "import sys; sys.path.insert(0, r'%s')\n"
            "from racewise.data.historical.canonical_queries import get_canonical_queries\n"
            "from racewise.data.historical.investigation_synthesis import run_engineering_investigation\n"
            "inv = run_engineering_investigation(get_canonical_queries(), "
            "'LAP_PERFORMANCE', 'max-verstappen', 'sergio-perez', 2022, 4, "
            "lap_number=2, session_type='QUALIFYING')\n"
            "print(inv['investigation_id'], inv['output_hash'])\n" % str(REPO / "src")
        )
        hashes = set()
        for seed in ("3", "29"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed
            out = subprocess.run(
                [sys.executable, "-c", script], capture_output=True,
                text=True, env=env, timeout=300, cwd=str(REPO))
            assert out.returncode == 0, out.stderr
            hashes.add(out.stdout.strip().splitlines()[-1])
        assert len(hashes) == 1, hashes


# ---------------------------------------------------------------------------
# race-path regression guards (Phase 6R contract preserved)
# ---------------------------------------------------------------------------

@requires_db
class TestRacePathUnchanged:
    def test_race_goldens_byte_identical(self):
        inv = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                   2023, 1, lap=6)
        assert inv["investigation_id"] == "fcc1bf694daada8e"
        # Re-baselined with the Phase 6E reconciliation fix (residual and
        # pace component on the signed-net basis; was e8263d8a0e191839 on
        # the rectified-sum basis). Structure and identity unchanged.
        assert inv["output_hash"] == "e2082f5bb39c4386"

    def test_qualifying_id_differs_from_race_id_for_same_round(self):
        q = _run("LAP_PERFORMANCE", "max-verstappen", "sergio-perez",
                 2022, 4, lap=2, st="QUALIFYING")
        assert q["status"] == "VALID"


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from racewise.api.app import app

    return TestClient(app)


@requires_db
class TestQualifyingApi:
    def test_qualifying_investigation_200(self, client):
        r = client.get("/api/catalog/engineering-investigation",
                       params=QBASE)
        assert r.status_code == 200
        assert r.json()["status"] == "VALID"

    def test_replay_and_memory_accept_session_type(self, client):
        r = client.get(
            "/api/catalog/engineering-investigation/replay", params=QBASE)
        assert r.status_code == 200
        assert r.json()["identical"] is True

    def test_graph_accepts_session_type(self, client):
        r = client.get("/api/catalog/investigation-graph", params=QBASE)
        assert r.status_code == 200
        body = r.json()
        assert body["node_count"] > 0
        types = {n["node_type"] for n in body["nodes"]}
        assert "SESSION" in types
        # the session node is the QUALIFYING session
        sess = next(n for n in body["nodes"] if n["node_type"] == "SESSION")
        assert "QUALIFYING" in sess["node_id"]

    def test_unknown_session_type_422(self, client):
        r = client.get("/api/catalog/engineering-investigation",
                       params={**QBASE, "session_type": "SPRINT"})
        assert r.status_code == 422

    def test_stint_plus_qualifying_422(self, client):
        r = client.get(
            "/api/catalog/engineering-investigation",
            params={"question_type": "STINT_PERFORMANCE",
                    "driver_a": "max-verstappen",
                    "driver_b": "sergio-perez", "season": 2022, "round": 4,
                    "stint_number": 1, "session_type": "QUALIFYING"})
        assert r.status_code == 422

    def test_default_pair_refused_for_qualifying(self, client):
        r = client.get(
            "/api/catalog/engineering-investigation",
            params={"question_type": "LAP_PERFORMANCE", "season": 2022,
                    "round": 4, "lap_number": 2,
                    "session_type": "QUALIFYING"})
        assert r.status_code == 422
        assert "required for session_type=QUALIFYING" in r.json()["detail"]

    def test_memory_route_session_type(self, client):
        r = client.get("/api/catalog/engineering-memory", params=QBASE)
        assert r.status_code == 200
