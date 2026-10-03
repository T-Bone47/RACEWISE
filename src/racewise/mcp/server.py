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
from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.tools.contract import ToolError
from racewise.tools.historical import build_full_registry
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


QUESTION_ENGINE_TOOLS = (
    "parse_engineering_question",
    "inspect_capability_registry",
)


def _question_engine_call(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    """High-level question-engine operations exposed over MCP.

    These are deliberately *not* the deterministic tool registry. They are the
    understanding layer above it: compile a question, discover capabilities.
    They return structured plans, never computed numbers — every number still
    comes from the allow-listed deterministic registry through ``tools/call``.

    No unrestricted execution: the method name is matched against a fixed tuple
    above and nothing else is reachable.
    """
    if method not in QUESTION_ENGINE_TOOLS:
        raise ValueError(f"Unknown question-engine method '{method}'")
    if method == "inspect_capability_registry":
        from racewise.question_engine import capabilities as cap

        capability_id = payload.get("capability_id")
        if capability_id:
            found = cap.capability(capability_id)
            if found is None:
                return {"ok": False, "error": f"Unknown capability '{capability_id}'"}
            payload_out = found.as_dict()
            payload_out["dependency_closure"] = list(
                cap.dependency_closure(capability_id))
            return {"ok": True, "capability": payload_out}
        return {
            "ok": True,
            "registry_version": cap.registry_version(),
            "capabilities": [c.as_dict() for c in cap.capabilities()],
        }

    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.question_engine.engine import ask

    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return {"ok": False, "error": "question must be a non-empty string"}
    result = ask(get_canonical_queries(), question, context=payload.get("context"))
    return {
        "ok": True,
        "status": result["status"],
        "compiled": result["compiled"],
        "plan": result["plan"],
        "answer": result["answer"],
        "verification": result["verification"],
    }


def serve() -> None:  # pragma: no cover - exercised via subprocess in integration tests
    cache_dir = os.environ.get("FASTF1_CACHE_DIR")
    context = SessionContext(FastF1Adapter(cache_dir=cache_dir), 2023, "Bahrain")
    try:
        queries = CanonicalQueries()
        registry = build_full_registry(context, queries)
    except Exception:  # noqa: BLE001 - canonical store optional at MCP startup
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
                tools = registry.descriptions()
                for t in tools:
                    if "parameters" in t:
                        t["inputSchema"] = t.pop("parameters")
                result = {"tools": tools}
            elif method == "question_engine/call":
                result = _question_engine_call(
                    str((request.get("params") or {}).get("method") or ""),
                    (request.get("params") or {}).get("arguments") or {},
                )
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
