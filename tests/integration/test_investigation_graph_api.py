"""Phase 6P API integration tests: /api/catalog/investigation-graph surface."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(),
                                 reason="canonical DB not present")

BASE = dict(
    question_type="LAP_PERFORMANCE",
    driver_a="max-verstappen",
    driver_b="sergio-perez",
    season=2023,
    round=1,
    lap_number=6,
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from racewise.api.app import app

    return TestClient(app)


@requires_db
class TestInvestigationGraphApi:
    def test_graph_valid_and_deterministic(self, client):
        r1 = client.get("/api/catalog/investigation-graph", params=BASE)
        assert r1.status_code == 200
        body = r1.json()
        assert body["graph_version"] == "6p_graph_v1"
        assert body["node_count"] > 0 and body["edge_count"] > 0
        r2 = client.get("/api/catalog/investigation-graph", params=BASE)
        assert r1.content == r2.content

    def test_path_endpoint(self, client):
        r = client.get("/api/catalog/investigation-graph/path",
                       params={**BASE, "target_node_type": "EVIDENCE",
                               "target_key": "evidence_001"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "OK"
        assert body["path"][0]["node_type"] == "INVESTIGATION"
        assert body["path"][-1]["node_type"] == "EVIDENCE"

    def test_evidence_and_hypothesis_endpoints(self, client):
        r = client.get("/api/catalog/investigation-graph/evidence",
                       params={**BASE, "evidence_id": "evidence_001"})
        assert r.status_code == 200
        assert r.json()["status"] == "OK"
        h = client.get("/api/catalog/investigation-graph/hypothesis",
                       params={**BASE, "hypothesis": "H1_corner_speed"})
        assert h.status_code == 200
        assert h.json()["status"] == "OK"

    def test_violation_classes(self, client):
        assert client.get("/api/catalog/investigation-graph",
                          params={**BASE, "max_depth": 99}).status_code == 422
        assert client.get("/api/catalog/investigation-graph",
                          params={**BASE, "max_nodes": 9999}).status_code == 422
        assert client.get("/api/catalog/investigation-graph",
                          params={**BASE, "max_edges": 9999}).status_code == 422
        assert client.get(
            "/api/catalog/investigation-graph",
            params={**BASE, "question_type": "FREE_FORM"}).status_code == 422
        assert client.get(
            "/api/catalog/investigation-graph/hypothesis",
            params={**BASE, "hypothesis": "H99"}).status_code == 422
        assert client.get(
            "/api/catalog/investigation-graph/path",
            params={**BASE, "target_node_type": "GHOST",
                    "target_key": "x"}).status_code == 422
        assert client.get(
            "/api/catalog/investigation-graph/evidence",
            params={**BASE, "evidence_id": "evidence_999"}).status_code == 422
        assert client.get(
            "/api/catalog/investigation-graph/path",
            params={**BASE, "target_node_type": "EVIDENCE"}).status_code == 422

    def test_unavailable_scope_is_honest(self, client):
        r = client.get("/api/catalog/investigation-graph",
                       params={**BASE, "season": 2050})
        assert r.status_code == 200
        assert r.json()["status"] == "UNAVAILABLE"


@requires_db
class TestInvestigationIdAddressedGraph:
    """Phase 6S GAP 1: investigation-id-addressed graph retrieval.

    The 6N investigation id is a content hash of the canonical input and no
    stored registry exists, so the id-addressed path verifies the scope→id
    binding deterministically and never falls back to a different
    investigation.
    """

    def test_id_addressed_graph_is_identical_to_scope_route(self, client):
        scope = client.get("/api/catalog/engineering-investigation",
                           params=BASE).json()
        assert scope["status"] == "VALID"
        iid = scope["investigation_id"]
        r_scope = client.get("/api/catalog/investigation-graph", params=BASE)
        assert r_scope.status_code == 200
        r_id = client.get("/api/catalog/investigation-graph",
                          params={**BASE, "investigation_id": iid})
        assert r_id.status_code == 200
        body_scope, body_id = r_scope.json(), r_id.json()
        assert body_id["graph_id"] == body_scope["graph_id"]
        assert body_id["node_count"] == body_scope["node_count"]
        assert body_id["edge_count"] == body_scope["edge_count"]
        assert [n["node_id"] for n in body_id["nodes"]] == \
            [n["node_id"] for n in body_scope["nodes"]]
        assert [e["edge_id"] for e in body_id["edges"]] == \
            [e["edge_id"] for e in body_scope["edges"]]
        assert body_id["addressing"] == "INVESTIGATION_ID"
        assert body_scope["addressing"] == "SCOPE"

    def test_wrong_id_is_404_never_fallback(self, client):
        r = client.get("/api/catalog/investigation-graph",
                       params={**BASE, "investigation_id": "0" * 16})
        assert r.status_code == 404
        assert "no investigation exists with id" in r.json()["detail"]

    def test_nonvalid_scope_with_id_is_404(self, client):
        r = client.get("/api/catalog/investigation-graph",
                       params={**BASE, "season": 2050,
                               "investigation_id": "0" * 16})
        assert r.status_code == 404

    def test_id_without_scope_is_422(self, client):
        r = client.get("/api/catalog/investigation-graph",
                       params={"investigation_id": "0" * 16})
        assert r.status_code == 422
        assert "content hash" in r.json()["detail"]
        assert "never looked up" in r.json()["detail"]

    def test_invalid_scope_with_id_is_422(self, client):
        r = client.get("/api/catalog/investigation-graph",
                       params={**BASE, "question_type": "FREE_FORM",
                               "investigation_id": "0" * 16})
        assert r.status_code == 422

    def test_id_addressed_determinism(self, client):
        scope = client.get("/api/catalog/engineering-investigation",
                           params=BASE).json()
        iid = scope["investigation_id"]
        r1 = client.get("/api/catalog/investigation-graph",
                        params={**BASE, "investigation_id": iid})
        r2 = client.get("/api/catalog/investigation-graph",
                        params={**BASE, "investigation_id": iid})
        assert r1.status_code == r2.status_code == 200
        assert r1.content == r2.content
        # the canonical graph content is identical across addressing modes;
        # only the addressing marker differs by design
        a = client.get("/api/catalog/investigation-graph",
                       params={**BASE, "investigation_id": iid}).json()
        b = client.get("/api/catalog/investigation-graph",
                       params=BASE).json()
        a.pop("addressing"), b.pop("addressing")
        assert a == b
