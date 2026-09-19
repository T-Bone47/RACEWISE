"""Phase 5.5B: historical tool layer + MCP visibility of canonical data.

Verifies the historical tools are contracted, query the real canonical store,
return data-derived availability, and are reachable through MCP (tools/list
and representative tools/call over the real server subprocess).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "canonical" / "canonical.db"
SERVER = ROOT / "src" / "racewise" / "mcp" / "server.py"

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.tools.contract import ToolError
from racewise.tools.historical import build_full_registry, build_historical_registry

requires_db = pytest.mark.skipif(
    not DB_PATH.exists(),
    reason="canonical DB not ingested yet (run: python -m racewise.data.historical.cli f1db)",
)


@pytest.fixture(scope="module")
def registry():
    queries = CanonicalQueries(str(DB_PATH))
    return build_historical_registry(queries)


@requires_db
class TestHistoricalTools:
    def test_registry_is_contracted(self, registry):
        names = registry.names()
        assert {
            "get_historical_session",
            "get_historical_results",
            "get_historical_qualifying",
            "get_historical_pit_stops",
            "get_historical_fastest_laps",
            "search_historical_catalog",
        } <= set(names)
        for tool in registry.descriptions():
            assert tool["output_schema"]
            # MCP envelope exposes tool_version inside the execute result;
            # descriptions carry the spec with limitations + schemas.
            assert tool["limitations"] is not None

    def test_get_session_1950(self, registry):
        out = registry.execute("get_historical_session", {"season": 1950, "round": 1})["output"]
        assert out["found"] is True
        assert "British Grand Prix" in out["race_name"]
        assert out["date"] == "1950-05-13"
        assert out["source_provider"] == "f1db"
        avail = out["availability"]
        assert avail["results_availability"] == "AVAILABLE"
        assert avail["pit_stops_availability"] == "UNAVAILABLE"
        assert avail["telemetry_availability"] == "UNAVAILABLE"

    def test_results_provenance_and_order(self, registry):
        out = registry.execute("get_historical_results", {"season": 1950, "round": 1})["output"]
        assert out["available"] is True
        assert out["source_provider"] == "f1db"
        assert out["results"][0]["driver"] == "Emilio Giuseppe Farina"
        assert out["results"][0]["time_millis"] == 8003600

    def test_pit_stops_no_data_is_not_zero(self, registry):
        """1950: pit stops UNAVAILABLE. 2023: AVAILABLE. Never conflated."""
        old = registry.execute("get_historical_pit_stops", {"season": 1950, "round": 1})["output"]
        assert old["available"] is False
        assert old["n_stops"] == 0
        new = registry.execute("get_historical_pit_stops", {"season": 2023, "round": 1})["output"]
        assert new["available"] is True
        assert new["n_stops"] == 50
        assert new["stops"][0]["duration_s"] > 20

    def test_fastest_laps_not_telemetry(self, registry):
        out = registry.execute("get_historical_fastest_laps", {"season": 2023, "round": 1})["output"]
        assert out["available"] is True
        assert out["full_telemetry_available"] is False
        assert out["n_records"] == 20  # one per driver

    def test_sprint_qualifying_q1_q2_q3(self, registry):
        out = registry.execute(
            "get_historical_qualifying",
            {"season": 2023, "round": 4, "session_type": "SPRINT_QUALIFYING"},
        )["output"]
        assert out["available"] is True
        top = out["rows"][0]
        assert top["q1"] and top["q2"] and top["q3"]

    def test_absent_session_is_explicit(self, registry):
        """A sprint at 2023 Bahrain does not exist; tool must say so."""
        out = registry.execute(
            "get_historical_session", {"season": 2023, "round": 1, "session_type": "SPRINT"}
        )["output"]
        assert out["found"] is False
        assert "RACE" in out["sessions_present"]
        assert "SPRINT" not in out["sessions_present"]

    def test_invalid_input_rejected(self, registry):
        with pytest.raises(ToolError):
            registry.execute("get_historical_results", {"season": "old", "round": 1})

    def test_unknown_tool_rejected(self, registry):
        with pytest.raises(ToolError):
            registry.execute("drop_database", {})


@requires_db
class TestFullRegistryComposition:
    def test_fastf1_and_historical_compose(self):
        from racewise.data.fastf1_adapter import FastF1Adapter
        from racewise.tools.implementations import SessionContext

        ctx = SessionContext(FastF1Adapter(cache_dir=str(ROOT / ".fastf1-cache")), 2023, "Bahrain")
        full = build_full_registry(ctx, CanonicalQueries(str(DB_PATH)))
        names = full.names()
        assert "analyze_tyre_degradation" in names  # FastF1 tool
        assert "get_historical_results" in names  # canonical tool

    def test_output_hashes_are_deterministic(self, registry):
        """Same input -> same output hash (replayable provenance)."""
        kwargs = {"season": 1950, "round": 1}
        h1 = registry.execute("get_historical_results", kwargs)["output_hash"]
        h2 = registry.execute("get_historical_results", kwargs)["output_hash"]
        assert h1 == h2
        assert len(h1) == 64


def _exchange(requests_payload: list[dict]) -> list[dict]:
    env = dict(os.environ)
    env["FASTF1_CACHE_DIR"] = str(ROOT / ".fastf1-cache")
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input="\n".join(json.dumps(r) for r in requests_payload) + "\n",
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


@pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not ingested")
class TestMCPHistoricalVisibility:
    def test_tools_list_includes_historical(self):
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        tools = responses[1]["result"]["tools"]
        names = {t["name"] for t in tools}
        assert {
            "get_historical_session",
            "get_historical_results",
            "get_historical_pit_stops",
            "search_historical_catalog",
        } <= names

    def test_representative_calls_via_mcp(self):
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "get_historical_session", "arguments": {"season": 1950, "round": 1}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "get_historical_results", "arguments": {"season": 1950, "round": 1}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "get_historical_pit_stops", "arguments": {"season": 2023, "round": 1}}},
        ])
        session_env = json.loads(responses[1]["result"]["content"][0]["text"])
        assert session_env["ok"] and session_env["output"]["found"]
        assert "British Grand Prix" in session_env["output"]["race_name"]
        results_env = json.loads(responses[2]["result"]["content"][0]["text"])
        assert results_env["ok"]
        assert results_env["output"]["results"][0]["driver"] == "Emilio Giuseppe Farina"
        assert len(results_env["output_hash"]) == 64
        pits_env = json.loads(responses[3]["result"]["content"][0]["text"])
        assert pits_env["ok"] and pits_env["output"]["n_stops"] == 50
