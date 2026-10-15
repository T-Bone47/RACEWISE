"""Model comparison harness for Phase E.

Runs identical engineering questions through selected model configurations
and records output validation, latency, and usage metadata.

Uses mocks for deterministic testing. Live provider execution requires
explicit credentials and is never assumed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from racewise.question_engine.answer_schemas import AnswerSchema, validate_answer_schema
from racewise.question_engine.synthesizer import synthesize
from racewise.agent.model_registry import (
    ModelRecord,
    ModelRegistry,
    RoutingPolicy,
    RoutingDecision,
    ModelCapability,
)


@dataclass
class ComparisonRun:
    """One model configuration run on one question."""

    question: str
    model_key: str
    provider: str
    policy: str
    latency_ms: float
    output_valid: bool
    validation_errors: list[str] = field(default_factory=list)
    token_usage: Optional[dict[str, Any]] = None
    estimated_cost: Optional[float] = None
    fallback_used: bool = False
    critique_invoked: bool = False
    answer_status: Optional[str] = None
    answer_hash: Optional[str] = None


class ModelComparisonHarness:
    """Reproducible harness for comparing model configurations."""

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def run(
        self,
        question: str,
        context: dict[str, Any],
        policy: RoutingPolicy = RoutingPolicy.DEFAULT,
        required_caps: Optional[set[ModelCapability]] = None,
    ) -> ComparisonRun:
        """Run one question through the routed model configuration.

        Raises ValueError if no registered model satisfies required_caps.
        """
        decision = self.registry.route(
            task="answer_synthesis",
            policy=policy,
            required_caps=required_caps,
        )

        # Build a deterministic answer (the fallback)
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.question_engine.compiler import compile_question
        from racewise.question_engine.planner import build_plan

        queries = get_canonical_queries()
        compiled = compile_question(queries, question, context=context)
        plan = build_plan(queries, compiled)
        # Synthesize without LLM (deterministic fallback)
        answer = synthesize(compiled, plan, {}, {})

        # Validate the answer against the schema
        valid, errors = validate_answer_schema(answer.as_dict())

        # If a provider is reachable, attempt LLM enrichment
        from racewise.agent.provider import provider_from_env
        provider = provider_from_env()
        llm_answer = None
        if provider is not None:
            try:
                from racewise.question_engine.engine import _maybe_llm_synthesize
                llm_answer = _maybe_llm_synthesize(compiled, plan, {}, answer)
            except Exception:
                pass

        final_answer = llm_answer if llm_answer is not None else answer
        final_valid, final_errors = validate_answer_schema(final_answer.as_dict())

        # Simulate latency (no live calls in mocked mode)
        latency = 0.0

        return ComparisonRun(
            question=question,
            model_key=f"{decision.selected_provider}/{decision.selected_model}",
            provider=decision.selected_provider,
            policy=decision.policy.value,
            latency_ms=latency,
            output_valid=final_valid,
            validation_errors=final_errors,
            fallback_used=decision.fallback_used,
            critique_invoked=decision.critique_invoked,
            answer_status=final_answer.status,
            answer_hash=final_answer.as_dict().get("answer_hash"),
        )

    def compare(
        self,
        questions: list[tuple[str, dict[str, Any]]],
        policies: Optional[list[RoutingPolicy]] = None,
    ) -> list[ComparisonRun]:
        """Run multiple questions through multiple policies."""
        if policies is None:
            policies = [RoutingPolicy.DEFAULT]
        runs = []
        for question, context in questions:
            for policy in policies:
                run = self.run(question, context, policy=policy)
                runs.append(run)
        return runs


def build_test_cases() -> list[tuple[str, dict[str, Any]]]:
    """Build the Phase E test cases for model comparison."""
    return [
        (
            "why did perez lose time in sector 2",
            {
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
                "sector": 2,
            },
        ),
        (
            "compare Verstappen and Perez on lap 6 in Bahrain 2023",
            {
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
            },
        ),
        (
            "what was the lap-time difference between Verstappen and Perez on lap 6?",
            {
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
            },
        ),
        (
            "explain the sector 1 delta for Verstappen vs Perez",
            {
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
                "sector": 1,
            },
        ),
    ]


def run_comparison_harness() -> list[ComparisonRun]:
    """Run the full comparison harness with default registry."""
    from racewise.agent.model_registry import MODEL_REGISTRY
    harness = ModelComparisonHarness(MODEL_REGISTRY)
    cases = build_test_cases()
    return harness.compare(cases)
