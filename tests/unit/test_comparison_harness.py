"""Comparison harness tests (Phase E)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.agent.model_registry import (
    ModelRegistry,
    ModelRecord,
    RoutingPolicy,
    ModelCapability,
)
from racewise.agent.comparison_harness import (
    ModelComparisonHarness,
    ComparisonRun,
    build_test_cases,
)


class TestComparisonHarness:
    def _make_registry(self):
        reg = ModelRegistry()
        reg.register(ModelRecord(
            provider="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            reachable=True,
            supports_structured_output=True,
            supports_tool_calls=True,
            task_scores={"answer_synthesis": 0.9},
        ))
        reg.register(ModelRecord(
            provider="anthropic",
            model_id="claude-sonnet-4",
            display_name="Claude Sonnet 4",
            reachable=True,
            supports_structured_output=True,
            task_scores={"answer_synthesis": 0.85},
            cost_per_1m_tokens=0.003,
        ))
        reg.set_default("openai/gpt-4o")
        return reg

    def test_run_returns_comparison_run(self):
        reg = self._make_registry()
        harness = ModelComparisonHarness(reg)
        run = harness.run(
            "why did perez lose time in sector 2",
            context={
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
                "sector": 2,
            },
        )
        assert isinstance(run, ComparisonRun)
        assert run.output_valid is True
        assert run.provider == "openai"

    def test_run_with_quality_first_policy(self):
        reg = self._make_registry()
        harness = ModelComparisonHarness(reg)
        run = harness.run(
            "why did perez lose time in sector 2",
            context={
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
                "sector": 2,
            },
            policy=RoutingPolicy.QUALITY_FIRST,
        )
        assert run.policy == "quality_first"
        # gpt-4o has higher score
        assert run.provider == "openai"

    def test_run_with_cost_conscious_policy(self):
        reg = self._make_registry()
        harness = ModelComparisonHarness(reg)
        run = harness.run(
            "why did perez lose time in sector 2",
            context={
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
                "sector": 2,
            },
            policy=RoutingPolicy.COST_CONSCIOUS,
        )
        assert run.policy == "cost_conscious"
        # claude is cheaper
        assert run.provider == "anthropic"

    def test_run_with_required_capabilities(self):
        reg = self._make_registry()
        harness = ModelComparisonHarness(reg)
        run = harness.run(
            "why did perez lose time in sector 2",
            context={
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
                "sector": 2,
            },
            required_caps={ModelCapability.STRUCTURED_OUTPUT},
        )
        assert run.output_valid is True

    def test_run_with_unsupported_capabilities(self):
        reg = self._make_registry()
        harness = ModelComparisonHarness(reg)
        # Neither model supports streaming
        with pytest.raises(ValueError):
            harness.run(
                "why did perez lose time in sector 2",
                context={
                    "driver_a": "max-verstappen",
                    "driver_b": "sergio-perez",
                    "season": 2023,
                    "round": 1,
                    "lap_number": 6,
                    "sector": 2,
                },
                required_caps={ModelCapability.STREAMING},
            )

    def test_compare_multiple_questions(self):
        reg = self._make_registry()
        harness = ModelComparisonHarness(reg)
        cases = build_test_cases()
        runs = harness.compare(cases)
        assert len(runs) == len(cases)
        assert all(r.output_valid for r in runs)

    def test_compare_with_multiple_policies(self):
        reg = self._make_registry()
        harness = ModelComparisonHarness(reg)
        cases = build_test_cases()[:2]
        runs = harness.compare(
            cases,
            policies=[RoutingPolicy.DEFAULT, RoutingPolicy.QUALITY_FIRST],
        )
        assert len(runs) == 4  # 2 questions x 2 policies

    def test_run_records_answer_metadata(self):
        reg = self._make_registry()
        harness = ModelComparisonHarness(reg)
        run = harness.run(
            "why did perez lose time in sector 2",
            context={
                "driver_a": "max-verstappen",
                "driver_b": "sergio-perez",
                "season": 2023,
                "round": 1,
                "lap_number": 6,
                "sector": 2,
            },
        )
        assert run.answer_status is not None
        assert run.answer_hash is not None

    def test_run_with_no_reachable_models(self):
        reg = ModelRegistry()
        reg.register(ModelRecord(
            provider="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            reachable=False,
        ))
        harness = ModelComparisonHarness(reg)
        with pytest.raises(ValueError):
            harness.run(
                "why did perez lose time in sector 2",
                context={
                    "driver_a": "max-verstappen",
                    "driver_b": "sergio-perez",
                    "season": 2023,
                    "round": 1,
                    "lap_number": 6,
                    "sector": 2,
                },
            )


class TestBuildTestCases:
    def test_build_test_cases_returns_list(self):
        cases = build_test_cases()
        assert len(cases) >= 3
        for question, context in cases:
            assert isinstance(question, str)
            assert isinstance(context, dict)

    def test_perez_regression_case_present(self):
        cases = build_test_cases()
        questions = [q for q, _ in cases]
        assert any("perez" in q.lower() and "sector" in q.lower() for q in questions)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
