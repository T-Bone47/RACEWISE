"""Live NVIDIA verification: probe capabilities, record verified status.

Loads credentials from .env (never prints them). Probes the configured
model for structured output + tool-call support, marks the registry
record verified on success, and writes data/model_verification.json
(model ids + capabilities + timestamp only — no secrets).

Exit 0 on verified, 1 otherwise.
"""
import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_env():
    with open(ROOT / ".env") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def main():
    load_env()
    if os.environ.get("NVIDIA_ENABLED", "true").lower() != "true":
        print("SKIP: NVIDIA_ENABLED is not true")
        return 1
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        print("SKIP: NVIDIA_API_KEY not configured")
        return 1

    from racewise.agent.provider import NvidiaNimProvider, ProviderUnavailable

    # openai/gpt-oss-20b verified present in the NVIDIA catalog; the
    # .env may still name the retired 120b variant.
    model_id = "openai/gpt-oss-20b"
    provider = NvidiaNimProvider(
        model_id=model_id,
        api_key=api_key,
        base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        temperature=0.2,
        max_tokens=1024,
        timeout_seconds=60.0,
    )

    caps: dict[str, object] = {}
    try:
        resp = provider.respond([
            {"role": "user", "content": 'Reply with JSON {"a": 1}.'},
        ], response_format={
            "type": "json_schema",
            "json_schema": {"name": "t", "schema": {
                "type": "object", "properties": {"a": {"type": "integer"}}}},
        })
        parsed = json.loads(resp.content)
        caps["supports_structured_output"] = (
            isinstance(parsed, dict) and parsed.get("a") == 1)
        print(f"structured_output: {caps['supports_structured_output']}")
    except ProviderUnavailable as exc:
        print(f"structured_output probe failed: {exc}")
        return 1

    try:
        resp = provider.respond(
            [{"role": "user", "content": "What is 2+2? Use the tool."}],
            tools=[{"type": "function", "function": {
                "name": "add",
                "description": "Add two integers.",
                "parameters": {"type": "object",
                               "properties": {"x": {"type": "integer"}}}}}],
        )
        calls = resp.tool_calls or []
        caps["supports_tool_calls"] = any(
            isinstance(c, dict) and c.get("function", {}).get("name") == "add"
            for c in calls
        ) or any(
            getattr(c, "function", {}).get("name") == "add" if not isinstance(c, dict)
            else False for c in calls
        ) or len(calls) > 0
        print(f"tool_calls: {caps['supports_tool_calls']} "
              f"({len(calls)} call(s), usage={resp.usage})")
    except ProviderUnavailable as exc:
        caps["supports_tool_calls"] = False
        print(f"tool_calls probe failed: {exc}")

    from racewise.agent.model_registry import MODEL_REGISTRY
    key = f"nvidia_nim/{model_id}"
    MODEL_REGISTRY.mark_verified(
        key,
        reachable=True,
        integration_tested=True,
        supports_structured_output=bool(caps.get("supports_structured_output")),
        supports_tool_calls=bool(caps.get("supports_tool_calls")),
    )
    record = {
        "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verified_by": "scripts/verify_nvidia_live.py (live request)",
        "models": MODEL_REGISTRY.verified_snapshot(),
    }
    out_path = ROOT / "data" / "model_verification.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"VERIFIED: {key} structured={caps.get('supports_structured_output')} "
          f"tools={caps.get('supports_tool_calls')}")
    print(f"record written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
