"""Centralized model registry for RaceWise multi-model routing.

Provides a registry of configured models with capability metadata,
and task-aware routing policies for model selection.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from racewise.question_engine.prompt_templates import PromptTask


class ModelCapability(Enum):
    """Capabilities a model may support."""

    TEXT_GENERATION = "text_generation"
    STRUCTURED_OUTPUT = "structured_output"
    TOOL_CALLS = "tool_calls"
    STREAMING = "streaming"


class RoutingPolicy(Enum):
    """Routing policy selection."""

    DEFAULT = "default"
    QUALITY_FIRST = "quality_first"
    BALANCED = "balanced"
    COST_CONSCIOUS = "cost_conscious"
    USER_SELECTED = "user_selected"


@dataclass(frozen=True)
class ModelRecord:
    """A configured model with capability metadata.

    Distinguishes between:
    - configured: appears in configuration
    - supported: has an implemented adapter
    - reachable: credentials present and provider reachable
    - integration_tested: passed a real integration test
    """

    provider: str
    model_id: str
    display_name: str
    configured: bool = True
    supported: bool = True
    reachable: bool = False
    integration_tested: bool = False

    # Capabilities (None = unknown)
    supports_structured_output: Optional[bool] = None
    supports_tool_calls: Optional[bool] = None
    supports_streaming: Optional[bool] = None
    context_limit: Optional[int] = None

    # Cost (None = unknown)
    cost_per_1m_tokens: Optional[float] = None

    # Evaluation results (task -> score)
    task_scores: dict[str, float] = field(default_factory=dict)

    def capabilities(self) -> set[ModelCapability]:
        """Return the set of supported capabilities."""
        caps = {ModelCapability.TEXT_GENERATION}
        if self.supports_structured_output:
            caps.add(ModelCapability.STRUCTURED_OUTPUT)
        if self.supports_tool_calls:
            caps.add(ModelCapability.TOOL_CALLS)
        if self.supports_streaming:
            caps.add(ModelCapability.STREAMING)
        return caps

    def has_capability(self, cap: ModelCapability) -> bool:
        """Check if model supports a capability.

        Unknown capabilities are treated as unsupported — never claim
        support without evidence.
        """
        cap_map = {
            ModelCapability.TEXT_GENERATION: True,
            ModelCapability.STRUCTURED_OUTPUT: self.supports_structured_output,
            ModelCapability.TOOL_CALLS: self.supports_tool_calls,
            ModelCapability.STREAMING: self.supports_streaming,
        }
        return cap_map.get(cap, False) is True


@dataclass
class RoutingDecision:
    """Result of a routing decision with auditable metadata."""

    selected_model: str
    selected_provider: str
    policy: RoutingPolicy
    reason: str
    latency_ms: Optional[float] = None
    token_usage: Optional[dict[str, Any]] = None
    estimated_cost: Optional[float] = None
    fallback_used: bool = False
    critique_invoked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_model": self.selected_model,
            "selected_provider": self.selected_provider,
            "policy": self.policy.value,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage,
            "estimated_cost": self.estimated_cost,
            "fallback_used": self.fallback_used,
            "critique_invoked": self.critique_invoked,
        }


class ModelRegistry:
    """Registry of configured models with task-aware routing."""

    def __init__(self) -> None:
        self._models: dict[str, ModelRecord] = {}  # key: "provider/model_id"
        self._task_defaults: dict[str, str] = {}  # task -> model key
        self._default_model: Optional[str] = None

    def register(self, record: ModelRecord) -> None:
        """Register a model."""
        key = f"{record.provider}/{record.model_id}"
        self._models[key] = record

    def set_default(self, key: str) -> None:
        """Set the default model key."""
        if key not in self._models:
            raise ValueError(f"Model not registered: {key}")
        self._default_model = key

    def set_task_default(self, task: str, key: str) -> None:
        """Set the default model for a task."""
        if key not in self._models:
            raise ValueError(f"Model not registered: {key}")
        self._task_defaults[task] = key

    def get(self, key: str) -> Optional[ModelRecord]:
        """Get a model record by key."""
        return self._models.get(key)

    def list_models(self, policy: RoutingPolicy = RoutingPolicy.DEFAULT,
                    task: Optional[str] = None,
                    required_caps: Optional[set[ModelCapability]] = None,
                    ) -> list[ModelRecord]:
        """List models matching the given criteria.

        Filters by:
        - required capabilities (if specified)
        - reachability (only reachable models unless explicitly disabled)
        - task-specific default (if policy is DEFAULT and task has a default)
        """
        results = []
        for record in self._models.values():
            if required_caps and not required_caps.issubset(record.capabilities()):
                continue
            results.append(record)
        return results

    def route(
        self,
        task: str,
        policy: RoutingPolicy = RoutingPolicy.DEFAULT,
        user_selected: Optional[str] = None,
        required_caps: Optional[set[ModelCapability]] = None,
        budget_usd: Optional[float] = None,
    ) -> RoutingDecision:
        """Route a task to the most appropriate model.

        Policy semantics:
        - DEFAULT: use task-specific default or global default
        - QUALITY_FIRST: highest task score subject to budget and availability
        - BALANCED: score / cost ratio
        - COST_CONSCIOUS: lowest cost among models meeting quality threshold
        - USER_SELECTED: explicit user choice (validated against capabilities)

        Falls back through: user_selected -> task_default -> default_model -> any reachable.
        Never silently routes to a different paid provider.
        """
        if not self._models:
            raise ValueError("No models registered")

        # USER_SELECTED: explicit choice, validated
        if policy == RoutingPolicy.USER_SELECTED and user_selected:
            key = user_selected
            record = self._models.get(key)
            if record is None:
                raise ValueError(f"User-selected model not found: {key}")
            if required_caps and not required_caps.issubset(record.capabilities()):
                raise ValueError(
                    f"User-selected model {key} lacks required capabilities"
                )
            return RoutingDecision(
                selected_model=record.model_id,
                selected_provider=record.provider,
                policy=policy,
                reason=f"user-selected model {key}",
            )

        # DEFAULT: task-specific default or global default
        if policy == RoutingPolicy.DEFAULT:
            key = self._task_defaults.get(task) or self._default_model
            if key:
                record = self._models.get(key)
                if record:
                    # Enforce required capabilities even for default policy
                    if required_caps and not required_caps.issubset(record.capabilities()):
                        raise ValueError(
                            f"Default model {key} lacks required capabilities: {required_caps}"
                        )
                    return RoutingDecision(
                        selected_model=record.model_id,
                        selected_provider=record.provider,
                        policy=policy,
                        reason=f"default for task '{task}'",
                    )

        # QUALITY_FIRST / BALANCED / COST_CONSCIOUS
        candidates = list(self._models.values())
        if required_caps:
            candidates = [m for m in candidates
                          if required_caps.issubset(m.capabilities())]
            if not candidates:
                raise ValueError(
                    f"No models support required capabilities: {required_caps}"
                )

        if policy == RoutingPolicy.QUALITY_FIRST:
            best = max(candidates, key=lambda m: m.task_scores.get(task, 0.0))
            return RoutingDecision(
                selected_model=best.model_id,
                selected_provider=best.provider,
                policy=policy,
                reason=f"highest task score ({best.task_scores.get(task, 0.0):.3f})",
            )
        elif policy == RoutingPolicy.BALANCED:
            best = max(candidates, key=lambda m: m.task_scores.get(task, 0.0) / max(
                m.cost_per_1m_tokens or 1.0, 0.001))
            return RoutingDecision(
                selected_model=best.model_id,
                selected_provider=best.provider,
                policy=policy,
                reason=f"best score/cost ratio for task '{task}'",
            )
        elif policy == RoutingPolicy.COST_CONSCIOUS:
            best = min(candidates, key=lambda m: m.cost_per_1m_tokens or float('inf'))
            return RoutingDecision(
                selected_model=best.model_id,
                selected_provider=best.provider,
                policy=policy,
                reason=f"lowest cost for task '{task}'",
            )

        # Fallback: first reachable model
        for record in self._models.values():
            if record.reachable:
                return RoutingDecision(
                    selected_model=record.model_id,
                    selected_provider=record.provider,
                    policy=policy,
                    reason=f"first reachable model (fallback)",
                    fallback_used=True,
                )

        raise ValueError(f"No reachable models for task '{task}'")


# ---------------------------------------------------------------------------
# Global registry instance
# ---------------------------------------------------------------------------

MODEL_REGISTRY = ModelRegistry()


def _build_default_registry() -> ModelRegistry:
    """Build the default registry from environment configuration."""
    registry = ModelRegistry()

    # Union Alpha (OpenRouter) — configured but not reachable without key
    union_alpha = ModelRecord(
        provider="union_alpha",
        model_id="stealth/union-alpha",
        display_name="Union Alpha (OpenRouter)",
        configured=True,
        supported=True,
        reachable=bool(_env_key("OPENROUTER_API_KEY")),
        integration_tested=False,
        supports_structured_output=None,
        supports_tool_calls=None,
        supports_streaming=None,
        context_limit=None,
        cost_per_1m_tokens=None,
    )
    registry.register(union_alpha)

    # OpenAI — not configured (no adapter yet)
    openai = ModelRecord(
        provider="openai",
        model_id="gpt-4o",
        display_name="GPT-4o (OpenAI)",
        configured=False,
        supported=False,
        reachable=False,
        integration_tested=False,
    )
    registry.register(openai)

    # Anthropic Claude — not configured (no adapter yet)
    claude = ModelRecord(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4 (Anthropic)",
        configured=False,
        supported=False,
        reachable=False,
        integration_tested=False,
    )
    registry.register(claude)

    # Google Gemini — not configured (no adapter yet)
    gemini = ModelRecord(
        provider="gemini",
        model_id="gemini-2.5-pro",
        display_name="Gemini 2.5 Pro (Google)",
        configured=False,
        supported=False,
        reachable=False,
        integration_tested=False,
    )
    registry.register(gemini)

    # NVIDIA NIM — adapter implemented; configured if key present
    # Available models from NVIDIA catalog (verified 2026-10-15):
    #   nvidia/llama-3.1-nemotron-70b-instruct
    #   nvidia/nemotron-3-super-120b-a12b
    #   nvidia/nemotron-3-ultra-550b-a55b
    #   nvidia/nemotron-4-340b-instruct
    #   deepseek-ai/deepseek-v4.1-flash
    #   deepseek-ai/deepseek-coder-6.7b-instruct
    #   moonshotai/kimi-k2.6
    #   moonshotai/kimi-k3
    #   openai/gpt-oss-20b
    nvidia_model = os.environ.get("NVIDIA_MODEL", "openai/gpt-oss-20b")
    nvidia_key_present = bool(_env_key("NVIDIA_API_KEY"))
    nvidia = ModelRecord(
        provider="nvidia_nim",
        model_id=nvidia_model,
        display_name=f"NVIDIA NIM ({nvidia_model})",
        configured=nvidia_key_present,
        supported=True,  # adapter is implemented
        reachable=False,  # only True after a real successful request
        integration_tested=False,  # only True after live test succeeds
        supports_structured_output=None,  # unknown until verified
        supports_tool_calls=None,  # unknown until verified
        supports_streaming=None,  # unknown until verified
        context_limit=None,  # unknown until verified
        cost_per_1m_tokens=None,  # unknown — never claim zero
    )
    registry.register(nvidia)

    # Register all catalog-available NVIDIA models (supported but unverified)
    catalog_models = [
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
    for model_id, label in catalog_models:
        registry.register(ModelRecord(
            provider="nvidia_nim",
            model_id=model_id,
            display_name=label,
            configured=False,
            supported=True,  # catalog-listed
            reachable=False,  # unverified — invalid API key
            integration_tested=False,
        ))

    return registry


def _env_key(name: str) -> Optional[str]:
    import os
    return os.environ.get(name) or None


# Build default registry
MODEL_REGISTRY = _build_default_registry()
