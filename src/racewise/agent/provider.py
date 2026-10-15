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


def provider_from_env() -> ModelProvider | None:
    """Build the configured provider from environment variables.

    MODEL_PROVIDER=union_alpha (default), MODEL_ID, OPENROUTER_API_KEY.
    Returns None when credentials are absent — callers must degrade honestly.
    """
    import os

    provider_name = os.environ.get("MODEL_PROVIDER", "union_alpha")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model_id = os.environ.get("MODEL_ID", "stealth/union-alpha")
    if provider_name == "union_alpha":
        if not api_key:
            return None
        return UnionAlphaProvider(model_id=model_id, api_key=api_key)
    raise ProviderUnavailable(f"Unknown MODEL_PROVIDER '{provider_name}'")


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
