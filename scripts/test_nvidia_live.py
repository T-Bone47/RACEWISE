"""Live NVIDIA NIM integration test.

Runs only when NVIDIA_API_KEY is configured and NVIDIA_ENABLED=true.
Makes a real request to the NVIDIA API and verifies the response.
Never logs or exposes the API key.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_env():
    """Load .env file into os.environ (without overwriting existing)."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
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
        return 0

    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        print("SKIP: NVIDIA_API_KEY not configured")
        return 0

    from racewise.agent.provider import NvidiaNimProvider, ProviderUnavailable

    # Use an available model (the .env may have a retired one)
    model_id = "openai/gpt-oss-20b"  # available as of 2026-10-15
    base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    temperature = float(os.environ.get("NVIDIA_TEMPERATURE", "0.2"))
    max_tokens = int(os.environ.get("NVIDIA_MAX_TOKENS", "4096"))
    timeout = float(os.environ.get("NVIDIA_TIMEOUT_SECONDS", "60"))

    provider = NvidiaNimProvider(
        model_id=model_id,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout,
    )

    print(f"Model: {model_id}")
    print(f"Base URL: {base_url}")
    print(f"Temperature: {temperature}")
    print(f"Max tokens: {max_tokens}")
    print(f"Timeout: {timeout}s")
    print("Making live request...")

    try:
        response = provider.respond([
            {"role": "system", "content": "You are a Formula 1 engineering assistant."},
            {"role": "user", "content": "What is the capital of France? Reply in one word."},
        ])
        print(f"SUCCESS: response received")
        print(f"  model_id: {response.model_id}")
        print(f"  provider: {response.provider}")
        print(f"  content length: {len(response.content)}")
        print(f"  content preview: {response.content[:100]}...")
        print(f"  usage: {response.usage}")
        return 0
    except ProviderUnavailable as exc:
        print(f"FAILED: {exc}")
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
