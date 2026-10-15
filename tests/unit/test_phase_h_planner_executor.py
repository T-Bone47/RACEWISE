"""Phase H tests: plan validation, bounded execution, stopping policy,
model-assisted planning (mocked).

All model interactions use stub providers — no network access. Live
behavior is covered by scripts/verify_nvidia_live.py, never here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.agent.provider import ProviderUnavailable
from racewise.agent.testing import (
    FailingProvider,
    ScriptedResponse,
    StubProvider,
)

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "data" / "canonical" / "canonical.db"
requires_db = pytest.mark.skipif(not DB_PATH.exists(), reason="canonical DB not present")

A = "max-verstappen"
B = "sergio-perez"
CTX = {"driver_a": A, "driver_b": B, "season": 2023, "round": 1,
       "lap_number": 6}


def _compiled_plan(question="why did perez lose time in sector 2",
                   context=None):
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.question_engine.compiler import compile_question
    from racewise.question_engine.planner import build_plan

    queries = get_canonical_queries()
    compiled = compile_question(
        queries, question, context=dict(context or {**CTX, "sector": 2}))
    plan = build_plan(queries, compiled)
    return compiled, plan


@requires_db
class TestValidatePlan:
    def test_built_plan_is_valid(self):
        from racewise.question_engine.planner import validate_plan

        _, plan = _compiled_plan()
        assert plan.status == "PLANNED"
        assert validate_plan(plan) == []

    def test_non_planned_plan_reports_status(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.question_engine.compiler import compile_question
        from racewise.question_engine.planner import build_plan, validate_plan

        queries = get_canonical_queries()
        compiled = compile_question(queries, "asdkjasd qwerty zzz")
        plan = build_plan(queries, compiled)
        problems = validate_plan(plan)
        assert problems and "not PLANNED" in problems[0]

    def test_duplicate_steps_detected(self):
        from racewise.question_engine.planner import validate_plan

        _, plan = _compiled_plan()
        assert plan.steps, "need a non-empty plan for this test"
        dup = list(plan.steps) + [plan.steps[0]]
        import dataclasses
        bad = dataclasses.replace(plan, steps=tuple(dup))
        problems = validate_plan(bad)
        assert any("duplicate step" in p for p in problems)

    def test_unknown_capability_detected(self):
        from racewise.question_engine.planner import validate_plan

        _, plan = _compiled_plan()
        assert plan.steps, "need a non-empty plan for this test"
        import dataclasses
        bad_step = dataclasses.replace(plan.steps[0],
                                       capability_id="not_a_capability")
        bad = dataclasses.replace(plan, steps=(bad_step,))
        problems = validate_plan(bad)
        assert any("unknown capability" in p for p in problems)

    def test_dependency_cycle_detected(self):
        # Synthetic cycle over real capability ids: the registry DAG can
        # never produce this, so the detector is exercised directly.
        import dataclasses
        from racewise.question_engine.planner import (
            PlannedStep,
            validate_plan,
        )

        _, plan = _compiled_plan()
        assert plan.steps, "need a non-empty plan for this test"
        a = PlannedStep(
            capability_id="compare_laps", sub_id="Q1", intents=("COMPARE",),
            analysis_level=1, testability="TESTABLE", cost="LOW",
            rationale="cycle test", depends_on=("attribute_lap_loss",))
        b = PlannedStep(
            capability_id="attribute_lap_loss", sub_id="Q1",
            intents=("ATTRIBUTE",), analysis_level=2, testability="TESTABLE",
            cost="MODERATE", rationale="cycle test",
            depends_on=("compare_laps",))
        bad = dataclasses.replace(plan, steps=(a, b))
        problems = validate_plan(bad)
        assert any("dependency cycle" in p for p in problems)


class TestValidateModelPlan:
    def _valid_proposal(self):
        return {"steps": [
            {"capability_id": "compare_laps", "arguments": {}},
            {"capability_id": "attribute_lap_loss", "arguments": {}},
        ]}

    def test_valid_proposal_accepted(self):
        from racewise.question_engine.planner import validate_model_plan

        ok, problems, ordered = validate_model_plan(self._valid_proposal())
        assert ok and not problems
        assert ordered == ["compare_laps", "attribute_lap_loss"]

    def test_non_object_rejected(self):
        from racewise.question_engine.planner import validate_model_plan

        ok, problems, _ = validate_model_plan(["not", "an", "object"])  # type: ignore[arg-type]
        assert not ok and problems

    def test_empty_steps_rejected(self):
        from racewise.question_engine.planner import validate_model_plan

        ok, problems, _ = validate_model_plan({"steps": []})
        assert not ok and problems

    def test_unknown_tool_rejected(self):
        from racewise.question_engine.planner import validate_model_plan

        ok, problems, _ = validate_model_plan(
            {"steps": [{"capability_id": "invent_teleportation", "arguments": {}}]})
        assert not ok
        assert any("unknown capability" in p for p in problems)

    def test_duplicate_tool_rejected(self):
        from racewise.question_engine.planner import validate_model_plan

        ok, problems, _ = validate_model_plan(
            {"steps": [{"capability_id": "compare_laps", "arguments": {}},
                        {"capability_id": "compare_laps", "arguments": {}}]})
        assert not ok
        assert any("duplicates" in p for p in problems)

    def test_standalone_capability_accepted_without_prerequisites(self):
        # Capabilities execute standalone with explicit arguments, so a
        # proposal naming attribute_stint_loss without analyze_stint is
        # executable and must NOT be rejected.
        from racewise.question_engine.planner import validate_model_plan

        ok, problems, ordered = validate_model_plan(
            {"steps": [{"capability_id": "attribute_stint_loss",
                         "arguments": {}}]})
        assert ok and not problems
        assert ordered == ["attribute_stint_loss"]

    def test_over_budget_rejected(self):
        from racewise.question_engine.capabilities import all_capabilities
        from racewise.question_engine.planner import validate_model_plan

        proposal = {"steps": [
            {"capability_id": c.capability_id, "arguments": {}}
            for c in all_capabilities()]}
        ok, problems, _ = validate_model_plan(
            proposal, budget={"max_capabilities": 2})
        assert not ok
        assert any("budget" in p for p in problems)


@requires_db
class TestExecutionLedger:
    def test_execution_records_cover_planned_steps(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.question_engine.engine import ask

        out = ask(get_canonical_queries(),
                  "why did perez lose time in sector 2",
                  context={**CTX, "sector": 2})
        execution = out.get("execution") or []
        assert execution, "ask() must return an execution ledger"
        for step in execution:
            assert step["capability_id"]
            assert step["status"] in ("SUCCEEDED", "FAILED", "SKIPPED")
            assert isinstance(step["duration_ms"], (int, float))
            assert step["retry_count"] == 0  # deterministic: never retried
            assert "error_class" in step
        assert any(s["status"] == "SUCCEEDED" for s in execution)
        assert out.get("stopping_reason"), "stopping reason must be recorded"

    def test_error_classes_are_closed_vocabulary(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.question_engine.engine import ask

        out = ask(get_canonical_queries(),
                  "why did perez lose time in sector 2",
                  context={**CTX, "sector": 2})
        for step in out.get("execution") or []:
            assert step["error_class"] in (
                None, "permanent_data", "permanent_deterministic")

    def test_unplannable_question_records_stopping_reason(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.question_engine.engine import ask

        out = ask(get_canonical_queries(), "asdkjasd qwerty zzz", context={})
        assert out.get("stopping_reason")
        assert "not executable" in out["stopping_reason"]

    def test_classify_error_policy(self):
        from racewise.agent.testing import FailingProvider  # noqa: F401 (import shape)
        from racewise.question_engine.engine import _classify_error
        from racewise.tools.contract import ToolError

        assert _classify_error(ToolError("x", missing=["laps"])) == "permanent_data"
        assert _classify_error(ValueError("boom")) == "permanent_deterministic"


class TestProposePlanWithModel:
    def _compiled(self):
        from racewise.data.historical.canonical_queries import get_canonical_queries
        from racewise.question_engine.compiler import compile_question

        queries = get_canonical_queries()
        return compile_question(
            queries, "why did perez lose time in sector 2",
            context={**CTX, "sector": 2})

    def test_valid_proposal_accepted(self):
        from racewise.question_engine.planner import propose_plan_with_model

        provider = StubProvider([ScriptedResponse(content=json.dumps({
            "steps": [
                {"capability_id": "compare_laps", "arguments": {}},
                {"capability_id": "attribute_lap_loss", "arguments": {}},
            ]}))])
        compiled = self._compiled()
        ok, problems, ordered = propose_plan_with_model(
            provider, compiled, {"available": ["laps", "telemetry"]})
        assert ok and not problems
        assert ordered == ["compare_laps", "attribute_lap_loss"]
        assert provider.call_count == 1

    def test_malformed_proposal_rejected_without_raise(self):
        from racewise.question_engine.planner import propose_plan_with_model

        provider = StubProvider([ScriptedResponse(content="not json{{")])
        compiled = self._compiled()
        ok, problems, ordered = propose_plan_with_model(
            provider, compiled, {})
        assert not ok and problems and ordered == []

    def test_unknown_tool_proposal_rejected(self):
        from racewise.question_engine.planner import propose_plan_with_model

        provider = StubProvider([ScriptedResponse(content=json.dumps({
            "steps": [{"capability_id": "invent_evidence", "arguments": {}}]}))])
        compiled = self._compiled()
        ok, problems, _ = propose_plan_with_model(provider, compiled, {})
        assert not ok
        assert any("unknown capability" in p for p in problems)

    def test_provider_failure_propagates(self):
        from racewise.agent.provider import ProviderUnavailable
        from racewise.question_engine.planner import propose_plan_with_model

        provider = FailingProvider(ProviderUnavailable("down"))
        compiled = self._compiled()
        with pytest.raises(ProviderUnavailable):
            propose_plan_with_model(provider, compiled, {})

    def test_unknown_task_name_rejected(self):
        from racewise.agent.provider import ProviderUnavailable, generate_with_template
        from racewise.agent.testing import StubProvider

        provider = StubProvider([ScriptedResponse(content="{}")])
        with pytest.raises(ProviderUnavailable):
            generate_with_template(provider, "NOT_A_TASK", question="x")

    def test_resolve_task_accepts_names_values_members(self):
        from racewise.question_engine.prompt_templates import (
            PromptTask,
            resolve_task,
        )

        assert resolve_task("INVESTIGATION_PLANNING") is PromptTask.INVESTIGATION_PLANNING
        assert resolve_task("investigation_planning") is PromptTask.INVESTIGATION_PLANNING
        assert resolve_task(PromptTask.INVESTIGATION_PLANNING) is PromptTask.INVESTIGATION_PLANNING
        with pytest.raises((ValueError, KeyError)):
            resolve_task("NOT_A_TASK")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
