"""Test which NVIDIA models work with the configured API key."""
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
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        print("SKIP: no API key")
        return 1

    import httpx
    base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

    # Models to test (from NVIDIA catalog, mentioned by user)
    models_to_test = [
        ("nvidia/llama-3.1-nemotron-70b-instruct", "Nemotron 70B"),
        ("nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super 120B"),
        ("nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra 550B"),
        ("nvidia/nemotron-4-340b-instruct", "Nemotron 4 340B"),
        ("deepseek-ai/deepseek-v4.1-flash", "DeepSeek V4.1 Flash"),
        ("deepseek-ai/deepseek-coder-6.7b-instruct", "DeepSeek Coder 6.7B"),
        ("moonshotai/kimi-k2.6", "Kimi K2.6"),
        ("moonshotai/kimi-k3", "Kimi K3"),
        ("openai/gpt-oss-20b", "GPT-OSS 20B"),
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": "user", "content": "Say 'OK' in one word."}],
        "max_tokens": 5,
    }

    working = []
    failed = []

    for model_id, label in models_to_test:
        payload["model"] = model_id
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = data.get("usage", {})
                working.append((model_id, label, content[:50], usage))
                print(f"  OK  {label:30s} ({model_id}) -> {content[:30]!r}")
            else:
                failed.append((model_id, label, resp.status_code, resp.text[:200]))
                print(f"FAIL  {label:30s} ({model_id}) -> {resp.status_code}: {resp.text[:120]}")
        except Exception as exc:
            failed.append((model_id, label, 0, str(exc)[:200]))
            print(f"ERR   {label:30s} ({model_id}) -> {type(exc).__name__}: {str(exc)[:100]}")

    print(f"\n=== SUMMARY ===")
    print(f"Working: {len(working)}")
    for model_id, label, content, usage in working:
        print(f"  {model_id}: {label} (usage: {usage})")
    print(f"Failed: {len(failed)}")
    for model_id, label, code, msg in failed:
        print(f"  {model_id}: {label} -> {code}: {msg[:80]}")

    return 0 if working else 1


if __name__ == "__main__":
    sys.exit(main())
