"""RACEWISE MCP server: exposes the deterministic ToolRegistry to OpenCode.

Stdio JSON-RPC (MCP 2.0) server over stdin/stdout. Each tool call executes
the registered deterministic implementation with full boundary validation
and provenance hashes. No shell access, no model code execution.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from racewise.data.fastf1_adapter import FastF1Adapter
from racewise.tools.contract import ToolError
from racewise.tools.implementations import SessionContext, build_default_registry


def _jsonrpc(result_id: Any, result: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> str:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": result_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result or {}
    return json.dumps(message, allow_nan=False)


def _tool_envelope(name: str, arguments: dict[str, Any], registry: Any) -> dict[str, Any]:
    try:
        execution = registry.execute(name, arguments)
    except ToolError as exc:
        return {"ok": False, "error": exc.as_dict()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": {"code": "tool_exception", "message": str(exc)}}
    return {
        "ok": True,
        "tool": execution["tool"],
        "tool_version": execution["tool_version"],
        "input_hash": execution["input_hash"],
        "output": execution["output"],
        "output_hash": execution["output_hash"],
        "duration_ms": execution["duration_ms"],
    }


def serve() -> None:  # pragma: no cover - exercised via subprocess in integration tests
    cache_dir = os.environ.get("FASTF1_CACHE_DIR")
    context = SessionContext(FastF1Adapter(cache_dir=cache_dir), 2023, "Bahrain")
    registry = build_default_registry(context)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            print(_jsonrpc(None, error={"code": -32700, "message": "Parse error"}), flush=True)
            continue
        method = request.get("method")
        result_id = request.get("id")
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "racewise", "version": "0.2.0"},
                }
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                result = {"tools": registry.descriptions()}
            elif method == "tools/call":
                params = request.get("params") or {}
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                _tool_envelope(params.get("name", ""), params.get("arguments") or {}, registry),
                                allow_nan=False,
                            ),
                        }
                    ]
                }
            elif method == "ping":
                result = {}
            else:
                print(_jsonrpc(result_id, error={"code": -32601, "message": f"Unknown method {method}"}), flush=True)
                continue
        except Exception as exc:  # noqa: BLE001
            print(_jsonrpc(result_id, error={"code": -32603, "message": str(exc)[:300]}), flush=True)
            continue
        print(_jsonrpc(result_id, result), flush=True)


if __name__ == "__main__":
    serve()
