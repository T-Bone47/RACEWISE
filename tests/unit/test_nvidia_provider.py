"""NVIDIA NIM provider contract tests (Phase E.1).

All tests use mocks — no live API calls. Live integration tests are
separate and require explicit credentials.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.agent.provider import (
    NvidiaNimProvider,
    ProviderUnavailable,
    provider_from_env,
    _nvidia_provider_from_env,
)


class TestNvidiaNimProviderInit:
    def test_init_with_defaults(self):
        p = NvidiaNimProvider(model_id="openai/gpt-oss-120b", api_key="test-key")
        assert p.model_id == "openai/gpt-oss-120b"
        assert p._base_url == "https://integrate.api.nvidia.com/v1"
        assert p._temperature == 0.2
        assert p._max_tokens == 4096
        assert p._timeout_seconds == 60.0

    def test_init_with_custom_settings(self):
        p = NvidiaNimProvider(
            model_id="meta/llama-3.1-70b",
            api_key="test-key",
            base_url="https://custom.example.com/v1/",
            temperature=0.5,
            max_tokens=2048,
            timeout_seconds=30.0,
        )
        assert p.model_id == "meta/llama-3.1-70b"
        assert p._base_url == "https://custom.example.com/v1"
        assert p._temperature == 0.5
        assert p._max_tokens == 2048
        assert p._timeout_seconds == 30.0

    def test_name_attribute(self):
        p = NvidiaNimProvider(model_id="test", api_key="key")
        assert p.name == "nvidia_nim"


class TestNvidiaNimProviderRespond:
    def _make_response(self, status_code=200, json_data=None, text=""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = text
        return resp

    def test_successful_response(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        json_data = {
            "choices": [{"message": {"content": "test response"}}],
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(200, json_data)
            result = p.respond([{"role": "user", "content": "hello"}])
        assert result.content == "test response"
        assert result.model_id == "test-model"
        assert result.provider == "nvidia_nim"
        assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5}

    def test_empty_content_raises(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        json_data = {"choices": [{"message": {"content": ""}}]}
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(200, json_data)
            with pytest.raises(ProviderUnavailable, match="empty content"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_no_choices_raises(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(200, {})
            with pytest.raises(ProviderUnavailable, match="empty response"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_malformed_json_raises(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(200)
            mock_client.return_value.__enter__.return_value.post.return_value.json.side_effect = \
                ValueError("bad json")
            with pytest.raises(ProviderUnavailable, match="malformed JSON"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_401_raises_auth_error(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="bad-key")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(401, text="unauthorized")
            with pytest.raises(ProviderUnavailable, match="authentication failed"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_429_raises_rate_limit(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(429, text="rate limited")
            with pytest.raises(ProviderUnavailable, match="rate limit"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_402_raises_quota_exhausted(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(402, text="quota exceeded")
            with pytest.raises(ProviderUnavailable, match="quota exhausted"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_404_raises_model_not_found(self):
        p = NvidiaNimProvider(model_id="unknown-model", api_key="key")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(404, text="model not found")
            with pytest.raises(ProviderUnavailable, match="model not found"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_500_raises_server_error(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(500, text="internal error")
            with pytest.raises(ProviderUnavailable, match="server error"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_timeout_raises(self):
        import httpx
        p = NvidiaNimProvider(model_id="test-model", api_key="key", timeout_seconds=0.001)
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = \
                httpx.TimeoutException("timeout")
            with pytest.raises(ProviderUnavailable, match="timeout"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_connection_error_raises(self):
        import httpx
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = \
                httpx.ConnectError("connection refused")
            with pytest.raises(ProviderUnavailable, match="connection error"):
                p.respond([{"role": "user", "content": "hello"}])

    def test_request_includes_temperature_and_max_tokens(self):
        p = NvidiaNimProvider(
            model_id="test-model", api_key="key",
            temperature=0.7, max_tokens=1024,
        )
        json_data = {"choices": [{"message": {"content": "ok"}}]}
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(200, json_data)
            p.respond([{"role": "user", "content": "hello"}])
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert payload["temperature"] == 0.7
            assert payload["max_tokens"] == 1024

    def test_request_includes_tools_when_provided(self):
        p = NvidiaNimProvider(model_id="test-model", api_key="key")
        json_data = {"choices": [{"message": {"content": "ok"}}]}
        tools = [{"type": "function", "function": {"name": "test"}}]
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = \
                self._make_response(200, json_data)
            p.respond([{"role": "user", "content": "hello"}], tools=tools)
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args.kwargs["json"]
            assert "tools" in payload


class TestNvidiaProviderFromEnv:
    def test_returns_none_when_disabled(self):
        with patch.dict("os.environ", {"NVIDIA_ENABLED": "false"}):
            assert _nvidia_provider_from_env() is None

    def test_returns_none_when_key_missing(self):
        with patch.dict("os.environ", {"NVIDIA_ENABLED": "true", "NVIDIA_API_KEY": ""}):
            assert _nvidia_provider_from_env() is None

    def test_returns_provider_when_configured(self):
        with patch.dict("os.environ", {
            "NVIDIA_ENABLED": "true",
            "NVIDIA_API_KEY": "test-key",
            "NVIDIA_MODEL": "test-model",
            "NVIDIA_TEMPERATURE": "0.5",
            "NVIDIA_MAX_TOKENS": "2048",
            "NVIDIA_TIMEOUT_SECONDS": "30",
        }):
            p = _nvidia_provider_from_env()
            assert p is not None
            assert p.model_id == "test-model"
            assert p._temperature == 0.5
            assert p._max_tokens == 2048
            assert p._timeout_seconds == 30.0

    def test_provider_from_env_with_nvidia_selected(self):
        with patch.dict("os.environ", {
            "MODEL_PROVIDER": "nvidia_nim",
            "NVIDIA_ENABLED": "true",
            "NVIDIA_API_KEY": "test-key",
        }):
            p = provider_from_env()
            assert p is not None
            assert p.name == "nvidia_nim"

    def test_provider_from_env_unknown_provider_raises(self):
        with patch.dict("os.environ", {"MODEL_PROVIDER": "unknown"}):
            with pytest.raises(ProviderUnavailable):
                provider_from_env()


class TestNvidiaRegistryIntegration:
    def test_nvidia_registered_in_default_registry(self):
        from racewise.agent.model_registry import MODEL_REGISTRY
        r = MODEL_REGISTRY.get("nvidia_nim/openai/gpt-oss-120b")
        assert r is not None
        # configured reflects os.environ, not .env files.
        # The .env has the key but os.environ doesn't (not loaded by registry).
        # supported=True because the adapter is implemented.
        # reachable=False because no live call has been made.
        # integration_tested=False because no live test has succeeded.
        assert r.supported is True
        assert r.reachable is False
        assert r.integration_tested is False

    def test_nvidia_capabilities_unknown(self):
        from racewise.agent.model_registry import MODEL_REGISTRY
        r = MODEL_REGISTRY.get("nvidia_nim/openai/gpt-oss-120b")
        # Capabilities unknown until verified
        assert r.supports_structured_output is None
        assert r.supports_tool_calls is None
        assert r.supports_streaming is None

    def test_nvidia_cost_unknown(self):
        from racewise.agent.model_registry import MODEL_REGISTRY
        r = MODEL_REGISTRY.get("nvidia_nim/openai/gpt-oss-120b")
        assert r.cost_per_1m_tokens is None  # unknown, not zero


class TestExistingProviderCompatibility:
    def test_union_alpha_still_works(self):
        with patch.dict("os.environ", {
            "MODEL_PROVIDER": "union_alpha",
            "OPENROUTER_API_KEY": "test-key",
        }):
            p = provider_from_env()
            assert p is not None
            assert p.name == "union_alpha"

    def test_union_alpha_returns_none_without_key(self):
        with patch.dict("os.environ", {
            "MODEL_PROVIDER": "union_alpha",
            "OPENROUTER_API_KEY": "",
        }):
            assert provider_from_env() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
