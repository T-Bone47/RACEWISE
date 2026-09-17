"""API integration tests using FastAPI TestClient (no live model required)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from racewise.api.app import app

client = TestClient(app)


def test_list_sessions():
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"][0]["event"] == "Bahrain"


def test_create_and_stream_investigation():
    resp = client.post(
        "/api/investigations",
        json={"question": "Why did VER lose pace in stint 2 of Bahrain 2023?", "year": 2023, "event": "Bahrain", "driver": "VER"},
    )
    assert resp.status_code == 200
    inv_id = resp.json()["investigation_id"]

    with client.stream("GET", f"/api/investigations/{inv_id}/stream") as stream:
        assert stream.status_code == 200
        lines = [line for line in stream.iter_lines() if line.startswith("data: ")]
    assert any("investigation.started" in line for line in lines)
    assert any("done" in line for line in lines)


def test_get_investigation_after_stream():
    resp = client.post(
        "/api/investigations",
        json={"question": "Was VER stint 2 pace loss tyre related?", "year": 2023, "event": "Bahrain", "driver": "VER"},
    )
    inv_id = resp.json()["investigation_id"]
    with client.stream("GET", f"/api/investigations/{inv_id}/stream") as stream:
        for _ in stream.iter_lines():
            pass
    detail = client.get(f"/api/investigations/{inv_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["state"] == "COMPLETED"
    assert len(data["hypotheses"]) >= 3
    assert any(ev["contradicts"] for ev in data["evidence"]), "falsification must produce contradictory evidence"
    assert len(data["counterfactuals"]) == 1
    assert data["conclusion"] is not None
    assert len(data["conclusion"]["evidence_ids"]) > 0


def test_counterfactual_endpoint():
    resp = client.post(
        "/api/investigations",
        json={"question": "Would an earlier pit have helped VER?", "year": 2023, "event": "Bahrain", "driver": "VER"},
    )
    inv_id = resp.json()["investigation_id"]
    cf = client.post(f"/api/investigations/{inv_id}/counterfactual", json={"counterfactual_pit_lap": 31})
    assert cf.status_code == 200
    data = cf.json()
    assert data["counterfactual"]["simulator_version"] == "1.0.0"
    assert "COUNTERFACTUAL" in data["note"]
    assert data["counterfactual"]["predicted_delta_s"] is not None


def test_unknown_investigation_404():
    assert client.get("/api/investigations/nonexistent").status_code == 404
