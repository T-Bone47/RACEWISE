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
