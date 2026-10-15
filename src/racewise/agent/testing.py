"""Test doubles for the ModelProvider protocol (Phase F).

Scripted, recording, and failing providers for deterministic unit tests.
No network access. Never used in production paths.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from racewise.agent.provider import (
    ModelProvider,
    ModelResponse,
    ProviderUnavailable,
)


@dataclass
class ScriptedResponse:
    """One scripted provider response."""

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    model_id: str = "stub/model"


class StubProvider:
    """A ModelProvider that returns scripted responses in order.

    When the script is exhausted, the last response repeats. Records all
    received messages for assertion.
    """

    name = "stub"

    def __init__(self, script: list[ScriptedResponse]) -> None:
        if not script:
            raise ValueError("StubProvider requires at least one scripted response")
        self._script = script
        self._calls: list[dict[str, Any]] = []

    @property
    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)

    @property
    def call_count(self) -> int:
        return len(self._calls)

    def respond(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict | None = None,
    ) -> ModelResponse:
        self._calls.append({
            "messages": messages,
            "tools": tools,
            "response_format": response_format,
        })
        scripted = self._script[min(len(self._calls) - 1, len(self._script) - 1)]
        return ModelResponse(
            content=scripted.content,
            model_id=scripted.model_id,
            provider=self.name,
            tool_calls=list(scripted.tool_calls),
            usage=dict(scripted.usage),
        )


class RecordingProvider:
    """Wraps a provider and records latency + usage per call."""

    def __init__(self, inner: ModelProvider) -> None:
        self._inner = inner
        self.records: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return getattr(self._inner, "name", "recording")

    def respond(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict | None = None,
    ) -> ModelResponse:
        started = time.perf_counter()
        try:
            response = self._inner.respond(messages, tools, response_format)
            error = None
        except Exception as exc:  # noqa: BLE001 — recording must not hide errors
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.records.append({
            "latency_ms": round(elapsed_ms, 2),
            "usage": dict(response.usage),
            "model_id": response.model_id,
            "error": error,
        })
        return response


class FailingProvider:
    """A ModelProvider that always raises the configured error."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error or ProviderUnavailable("stubbed provider failure")
        self.calls = 0

    @property
    def name(self) -> str:
        return "failing"

    def respond(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict | None = None,
    ) -> ModelResponse:
        self.calls += 1
        raise self._error


__all__ = [
    "ScriptedResponse",
    "StubProvider",
    "RecordingProvider",
    "FailingProvider",
]
