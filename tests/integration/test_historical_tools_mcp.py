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
        # F1DB fastest-lap facts (one per driver) + FastF1 per-lap rows coexist
        # with distinct provenance; the F1DB fact count is still one per driver.
        f1db_rows = [r for r in out["laps"] if r.get("lap_number") is not None]
        assert out["n_records"] >= 20  # at least the 20 F1DB fastest-lap facts

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

    def test_telemetry_tools_via_mcp(self):
        """Phase 6C: bounded telemetry tools live over the real server."""
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "get_historical_telemetry_summary",
                        "arguments": {"season": 2023, "round": 1, "session_type": "RACE"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "get_historical_lap_telemetry",
                        "arguments": {"season": 2023, "round": 1, "session_type": "RACE",
                                      "driver_key": "max-verstappen", "lap_number": 57}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "compare_historical_telemetry_lap",
                        "arguments": {"season": 1950, "round": 6,
                                      "driver_a": "giuseppe-farina", "driver_b": "luigi-fagioli",
                                      "lap_number": 1}}},
        ])
        summary = json.loads(responses[1]["result"]["content"][0]["text"])
        assert summary["ok"] and summary["output"]["available"] is True
        assert summary["output"]["source_provider"] == "fastf1"
        laps = json.loads(responses[2]["result"]["content"][0]["text"])
        assert laps["ok"] and laps["output"]["available"] is True
        assert len(laps["output"]["samples"]) <= 2000  # hard output cap
        neg = json.loads(responses[3]["result"]["content"][0]["text"])
        assert neg["output"]["verdict"] == "INSUFFICIENT_EVIDENCE"  # 1950 negative control


@pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not ingested")
class TestMCPEngineeringInvestigation:
    """Phase 6N: run_engineering_investigation over the real MCP server."""

    def test_tools_list_includes_investigation(self):
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        names = {t["name"] for t in responses[1]["result"]["tools"]}
        assert "run_engineering_investigation" in names

    def _call(self, arguments: dict) -> dict:
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "run_engineering_investigation",
                        "arguments": arguments}},
        ])
        return json.loads(responses[1]["result"]["content"][0]["text"])

    def test_investigation_call_and_deterministic_repeat(self):
        args = {"question_type": "LAP_PERFORMANCE",
                "driver_a": "max-verstappen", "driver_b": "sergio-perez",
                "season": 2023, "round": 1, "lap_number": 6}
        first = self._call(args)
        assert first["ok"] is True
        inv = first["output"]
        assert inv["status"] == "VALID"
        assert inv["synthesis"]["conclusion_state"]
        assert inv["output_hash"]
        # runtime fields are excluded from the wire comparison
        strip = lambda d: {k: v for k, v in d.items() if k != "duration_ms"}
        assert strip(first) == strip(self._call(args))

    def test_invalid_input_via_wire(self):
        env = self._call({"question_type": "RACE_GAP",
                          "driver_a": "max-verstappen",
                          "driver_b": "max-verstappen",
                          "season": 2023, "round": 1})
        assert env["ok"] is False
        assert env["error"]["code"] == "invalid_input"


@pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not ingested")
class TestMCPInvestigationMemory:
    """Phase 6O: replay / verify / compare / memory over the real server."""

    LAP6 = {"question_type": "LAP_PERFORMANCE",
            "driver_a": "max-verstappen", "driver_b": "sergio-perez",
            "season": 2023, "round": 1, "lap_number": 6}

    def _call(self, name: str, arguments: dict) -> dict:
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": name, "arguments": arguments}},
        ])
        return json.loads(responses[1]["result"]["content"][0]["text"])

    def test_tools_list_includes_memory_tools(self):
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        names = {t["name"] for t in responses[1]["result"]["tools"]}
        assert {"replay_engineering_investigation",
                "verify_engineering_snapshot",
                "compare_engineering_investigations",
                "retrieve_engineering_memory"} <= names

    def test_replay_deterministic_repeat(self):
        strip = lambda d: {k: v for k, v in d.items() if k != "duration_ms"}
        first = self._call("replay_engineering_investigation", self.LAP6)
        assert first["ok"] is True
        assert first["output"]["status"] == "IDENTICAL"
        assert strip(first) == strip(
            self._call("replay_engineering_investigation", self.LAP6))

    def test_compare_and_memory_wire(self):
        cmp1 = self._call("compare_engineering_investigations", {
            "investigation_a": self.LAP6,
            "investigation_b": {**self.LAP6, "lap_number": 11}})
        assert cmp1["output"]["compatibility"]["state"] == \
            "PARTIALLY_COMPARABLE"
        mem = self._call("retrieve_engineering_memory", {
            "investigations": [self.LAP6], "season": 2023, "round": 1})
        assert mem["output"]["match_count"] > 0
        scope_miss = self._call("retrieve_engineering_memory", {
            "investigations": [self.LAP6], "season": 1999})
        assert scope_miss["output"]["match_count"] == 0

    def test_memory_unknown_param_rejected(self):
        env = self._call("retrieve_engineering_memory", {
            "investigations": [self.LAP6], "bogus": True})
        assert env["ok"] is False
        assert env["error"]["code"] == "invalid_input"


@pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not ingested")
class TestMCPInvestigationGraph:
    """Phase 6P: investigation graph tools over the real MCP server."""

    LAP6 = {"question_type": "LAP_PERFORMANCE",
            "driver_a": "max-verstappen", "driver_b": "sergio-perez",
            "season": 2023, "round": 1, "lap_number": 6}

    def test_tools_list_includes_graph_tools(self):
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        names = {t["name"] for t in responses[1]["result"]["tools"]}
        assert {"build_investigation_graph",
                "trace_investigation_path",
                "trace_evidence_source",
                "trace_hypothesis_evidence"} <= names

    def _call(self, name: str, arguments: dict) -> dict:
        responses = _exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": name, "arguments": arguments}},
        ])
        return json.loads(responses[1]["result"]["content"][0]["text"])

    def test_graph_build_deterministic_repeat(self):
        strip = lambda d: {k: v for k, v in d.items() if k != "duration_ms"}
        first = self._call("build_investigation_graph", self.LAP6)
        assert first["ok"] is True
        out = first["output"]
        assert out["node_count"] > 0 and out["edge_count"] > 0
        assert out["edge_count"] >= out["node_count"]
        assert strip(first) == strip(self._call(
            "build_investigation_graph", self.LAP6))

    def test_graph_path_and_traces(self):
        path = self._call("trace_investigation_path", {
            **self.LAP6, "target_node_type": "EVIDENCE",
            "target_key": "evidence_001"})
        assert path["output"]["status"] == "OK"
        assert path["output"]["path"][0]["node_type"] == "INVESTIGATION"
        assert path["output"]["path"][-1]["node_type"] == "EVIDENCE"
        src = self._call("trace_evidence_source", {
            **self.LAP6, "evidence_id": "evidence_001"})
        assert src["output"]["status"] == "OK"
        hyp = self._call("trace_hypothesis_evidence", {
            **self.LAP6, "hypothesis": "H1_corner_speed"})
        assert hyp["output"]["status"] == "OK"
        # CONTRADICTS edges come from the imported 6N evaluation, not topology
        assert "provenance" in hyp["output"]["supporting_evidence"][0]

    def test_graph_negative_controls(self):
        missing = self._call("trace_evidence_source", {
            **self.LAP6, "evidence_id": "evidence_999"})
        assert missing["ok"] is False
        assert missing["error"]["code"] == "invalid_input"
        bad_hyp = self._call("trace_hypothesis_evidence", {
            **self.LAP6, "hypothesis": "H99_free_form"})
        assert bad_hyp["ok"] is False
        depth = self._call("build_investigation_graph", {
            **self.LAP6, "max_depth": 99})
        assert depth["ok"] is False
        assert depth["error"]["code"] == "invalid_input"
