"""End-to-end MCP server tests via subprocess stdio."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "src" / "racewise" / "mcp" / "server.py"


def _exchange(requests: list[dict]) -> list[dict]:
    env = dict(os.environ)
    env["FASTF1_CACHE_DIR"] = str(ROOT / ".fastf1-cache")
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    payload = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def test_initialize_and_list_tools():
    responses = _exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    assert responses[0]["result"]["serverInfo"]["name"] == "racewise"
    tools = responses[1]["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {"get_session", "get_laps", "get_stints", "analyze_tyre_degradation", "analyze_traffic", "analyze_pit_loss", "compare_driver_pace", "get_weather", "get_race_control", "get_pit_stops", "compare_sectors", "detect_pace_anomaly"} <= names


def test_tool_call_returns_provenance():
    responses = _exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_stints", "arguments": {"driver": "VER"}}},
    ])
    envelope = json.loads(responses[1]["result"]["content"][0]["text"])
    assert envelope["ok"] is True
    assert envelope["tool_version"]
    assert len(envelope["output_hash"]) == 64
    assert envelope["output"]["driver"] == "VER"


def test_invalid_tool_call_returns_structured_error():
    responses = _exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_laps", "arguments": {"driver": 123}}},
    ])
    envelope = json.loads(responses[1]["result"]["content"][0]["text"])
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "invalid_input"


def test_unknown_tool_is_rejected():
    responses = _exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "run_shell", "arguments": {}}},
    ])
    envelope = json.loads(responses[1]["result"]["content"][0]["text"])
    assert envelope["ok"] is False
    assert "allow-list" in envelope["error"]["message"]
