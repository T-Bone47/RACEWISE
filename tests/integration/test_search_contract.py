"""Phase 6Q: /api/catalog/search contract tests (deterministic, typed)."""
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


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from racewise.api.app import app

    return TestClient(app)


@requires_db
class TestSearchEndpoint:
    def test_empty_query_is_empty(self, client):
        j = client.get("/api/catalog/search", params={"q": ""}).json()
        assert j["status"] == "OK" and j["result_count"] == 0

    def test_races_and_drivers_deterministic(self, client):
        r1 = client.get("/api/catalog/search", params={"q": "2023 1"})
        j = client.get("/api/catalog/search", params={"q": "verstappen"})
        assert r1.status_code == 200 and j.status_code == 200
        types = {x["result_type"] for x in j.json()["results"]}
        assert "DRIVER" in types
        rep = client.get("/api/catalog/search", params={"q": "verstappen"})
        assert rep.content == j.content

    def test_hypothesis_closed_vocabulary(self, client):
        j = client.get("/api/catalog/search",
                       params={"q": "corner"}).json()
        assert any(r["result_type"] == "HYPOTHESIS"
                   and r["ref"]["hypothesis_id"] == "H1_corner_speed"
                   for r in j["results"])

    def test_violations(self, client):
        assert client.get("/api/catalog/search",
                          params={"q": "x", "result_type": "GHOST"}
                          ).status_code == 422
        assert client.get("/api/catalog/search",
                          params={"q": "x", "limit": 99}).status_code == 422

    def test_no_semantic_search_provenance(self, client):
        j = client.get("/api/catalog/search",
                       params={"q": "2023 1"}).json()
        assert j["provenance"]["method"] == "deterministic_exact_match_search"
