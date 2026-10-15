"""Model provider abstraction.

The investigation engine depends only on the ModelProvider protocol.
Union Alpha (via OpenRouter) is one implementation; the provider is
configured externally via MODEL_PROVIDER / MODEL_ID / OPENROUTER_API_KEY.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ModelResponse:
    content: str
    model_id: str
    provider: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    def respond(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, response_format: dict | None = None) -> ModelResponse:
        ...


class ProviderUnavailable(RuntimeError):
    """Raised when a provider is requested but not configured/usable."""


class UnionAlphaProvider:
    """OpenRouter-hosted Union Alpha implementation of ModelProvider."""

    name = "union_alpha"

    def __init__(self, model_id: str, api_key: str, base_url: str = "https://openrouter.ai/api/v1") -> None:
        self.model_id = model_id
        self._api_key = api_key
        self._base_url = base_url

    def respond(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, response_format: dict | None = None) -> ModelResponse:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable("httpx not installed") from exc

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
        if response.status_code != 200:
            raise ProviderUnavailable(f"OpenRouter error {response.status_code}: {response.text[:200]}")
        data = response.json()
        message = data["choices"][0]["message"]
        return ModelResponse(
            content=message.get("content") or "",
            model_id=data.get("model", self.model_id),
            provider=self.name,
            tool_calls=message.get("tool_calls") or [],
            usage=data.get("usage", {}),
        )


class NvidiaNimProvider:
    """NVIDIA NIM implementation of ModelProvider.

    Uses NVIDIA's NIM endpoint (https://integrate.api.nvidia.com/v1).
    All settings configurable via environment variables.
    Credentials never logged or exposed.
    """

    name = "nvidia_nim"

    def __init__(
        self,
        model_id: str,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model_id = model_id
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds

    def respond(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict | None = None,
    ) -> ModelResponse:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise ProviderUnavailable("httpx not installed") from exc

        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(
                f"NVIDIA NIM timeout after {self._timeout_seconds}s"
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailable(
                f"NVIDIA NIM connection error: {exc}"
            ) from exc

        if response.status_code == 401:
            raise ProviderUnavailable("NVIDIA NIM authentication failed (invalid API key)")
        if response.status_code == 429:
            raise ProviderUnavailable("NVIDIA NIM rate limit exceeded")
        if response.status_code == 402:
            raise ProviderUnavailable("NVIDIA NIM quota exhausted")
        if response.status_code == 404:
            raise ProviderUnavailable(f"NVIDIA NIM model not found: {self.model_id}")
        if response.status_code >= 500:
            raise ProviderUnavailable(
                f"NVIDIA NIM server error {response.status_code}"
            )
        if response.status_code != 200:
            raise ProviderUnavailable(
                f"NVIDIA NIM error {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except Exception as exc:
            raise ProviderUnavailable("NVIDIA NIM returned malformed JSON") from exc

        if not data.get("choices"):
            raise ProviderUnavailable("NVIDIA NIM returned empty response")

        message = data["choices"][0].get("message", {})
        content = message.get("content") or ""
        if not content:
            raise ProviderUnavailable("NVIDIA NIM returned empty content")

        return ModelResponse(
            content=content,
            model_id=data.get("model", self.model_id),
            provider=self.name,
            tool_calls=message.get("tool_calls") or [],
            usage=data.get("usage", {}),
        )


def provider_from_env() -> ModelProvider | None:
    """Build the configured provider from environment variables.

    MODEL_PROVIDER=union_alpha (default), MODEL_ID, OPENROUTER_API_KEY.
    Returns None when credentials are absent — callers must degrade honestly.

    NVIDIA: MODEL_PROVIDER=nvidia_nim, NVIDIA_API_KEY, NVIDIA_MODEL, etc.
    """
    import os

    provider_name = os.environ.get("MODEL_PROVIDER", "union_alpha")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model_id = os.environ.get("MODEL_ID", "stealth/union-alpha")

    if provider_name == "union_alpha":
        if not api_key:
            return None
        return UnionAlphaProvider(model_id=model_id, api_key=api_key)

    if provider_name == "nvidia_nim":
        return _nvidia_provider_from_env()

    raise ProviderUnavailable(f"Unknown MODEL_PROVIDER '{provider_name}'")


def _nvidia_provider_from_env() -> ModelProvider | None:
    """Build NVIDIA NIM provider from environment.

    Returns None when NVIDIA_ENABLED is false or NVIDIA_API_KEY missing.
    All settings configurable via environment variables.
    """
    import os

    if os.environ.get("NVIDIA_ENABLED", "true").lower() != "true":
        return None

    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        return None

    model_id = os.environ.get("NVIDIA_MODEL", "openai/gpt-oss-20b")
    base_url = os.environ.get(
        "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
    )
    temperature = float(os.environ.get("NVIDIA_TEMPERATURE", "0.2"))
    max_tokens = int(os.environ.get("NVIDIA_MAX_TOKENS", "4096"))
    timeout = float(os.environ.get("NVIDIA_TIMEOUT_SECONDS", "60"))

    return NvidiaNimProvider(
        model_id=model_id,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout,
    )


# ---------------------------------------------------------------------------
# Prompt-template-backed generation (Phase D integration)
# ---------------------------------------------------------------------------


def generate_with_template(
    provider: ModelProvider,
    task: str,
    version: str = "latest",
    **template_vars: Any,
) -> ModelResponse:
    """Generate a response using a versioned prompt template.

    Selects the template for the given task, renders it with the provided
    variables, and invokes the provider. The template's output_schema is
    passed as response_format when the provider supports it.

    Raises ProviderUnavailable if the template is not found or required
    variables are missing.
    """
    from racewise.question_engine.prompt_templates import (
        PromptTask,
        PROMPT_REGISTRY,
    )

    try:
        task_enum = PromptTask(task)
    except ValueError:
        raise ProviderUnavailable(f"Unknown prompt task: {task}")

    template = PROMPT_REGISTRY.get(task_enum, version)

    # Validate required template variables
    required = _template_required_vars(template.user_template)
    missing = [v for v in required if v not in template_vars]
    if missing:
        raise ProviderUnavailable(
            f"Template {task} v{version} missing required variables: {missing}"
        )

    messages = template.render(**template_vars)
    response_format = None
    if template.output_schema:
        response_format = {"type": "json_schema", "json_schema": template.output_schema}

    return provider.respond(messages, response_format=response_format)


def _template_required_vars(template: str) -> list[str]:
    """Extract required variable names from a template string."""
    import re
    # Find all ${var} patterns
    return re.findall(r"\$\{(\w+)\}", template)
