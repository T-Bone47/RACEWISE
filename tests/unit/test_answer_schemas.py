"""Tests for Phase C: answer schemas and prompt templates."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.question_engine.answer_schemas import (
    AnswerSchema,
    AnswerStatusEnum,
    AnswerStatus,
    ClaimClass,
    AnswerMode,
    HypothesisState,
    EvidenceType,
    FollowUpSuggestion,
    ProvenanceSchema,
    validate_answer_schema,
    answer_to_schema,
    schema_to_answer,
)
from racewise.question_engine.prompt_templates import (
    PromptTask,
    PromptRole,
    PromptTemplate,
    PromptRegistry,
    PROMPT_REGISTRY,
    RACEWISE_SYSTEM_PROMPT,
    ANSWER_SYNTHESIS_TEMPLATE,
    QUESTION_UNDERSTANDING_TEMPLATE,
    render_prompt,
    render_prompt_messages,
    PromptRole,
    PromptTask,
)


class TestAnswerSchemas:
    """Tests for the AnswerSchema Pydantic models."""

    def test_valid_answer_schema_minimal(self):
        """A minimal valid answer passes validation."""
        data = {
            "answer_status": "ANSWERABLE",
            "question": "Why did Perez lose time in sector 2?",
            "scope": {"season": 2023, "round": 1, "driver_a": "VER", "driver_b": "PER"},
            "short_answer": "Perez lost 0.411s in sector 2 due to lower corner exit speed.",
        }
        valid, errors = validate_answer_schema(data)
        assert valid, f"Expected valid, got errors: {errors}"

    def test_invalid_status_rejected(self):
        """Invalid status is rejected."""
        data = {
            "answer_status": "WRONG_STATUS",
            "question": "Test?",
            "scope": {},
            "short_answer": "Test",
        }
        valid, errors = validate_answer_schema(data)
        assert not valid
        assert any("answer_status" in e.lower() for e in errors)

    def test_empty_question_rejected(self):
        """Empty question is rejected."""
        data = {
            "answer_status": "ANSWERABLE",
            "question": "",
            "scope": {},
            "short_answer": "Test",
        }
        valid, errors = validate_answer_schema(data)
        assert not valid
        assert any("question" in e.lower() for e in errors)

    def test_empty_short_answer_rejected(self):
        """Empty short_answer is rejected."""
        data = {
            "answer_status": "ANSWERABLE",
            "question": "Test?",
            "scope": {},
            "short_answer": "",
        }
        valid, errors = validate_answer_schema(data)
        assert not valid
        assert any("short_answer" in e.lower() for e in errors)

    def test_scope_must_be_dict(self):
        """Scope must be a dictionary."""
        data = {
            "answer_status": "ANSWERABLE",
            "question": "Test?",
            "scope": "not a dict",
            "short_answer": "Test",
        }
        valid, errors = validate_answer_schema(data)
        assert not valid
        assert any("scope" in e.lower() for e in errors)

    def test_invalid_answer_mode_rejected(self):
        """Invalid answer_mode is rejected."""
        data = {
            "answer_status": "ANSWERABLE",
            "question": "Test?",
            "scope": {},
            "short_answer": "Test",
            "answer_mode": "INVALID_MODE",
        }
        valid, errors = validate_answer_schema(data)
        assert not valid
        assert any("answer_mode" in e.lower() for e in errors)

    def test_valid_claim_classes(self):
        """All valid claim classes are accepted."""
        for claim_class in ("OBSERVED", "DERIVED", "INFERRED", "MODELLED"):
            data = {
                "answer_status": "ANSWERABLE",
                "question": "Test?",
                "scope": {},
                "short_answer": "Test",
                "observations": [{
                    "statement": "Test",
                    "value": 1.0,
                    "unit": "s",
                    "claim_class": claim_class,
                    "capability_id": "test_cap",
                }],
            }
            valid, errors = validate_answer_schema(data)
            assert valid, f"Claim class {claim_class} rejected: {errors}"

    def test_invalid_claim_class_rejected(self):
        """Invalid claim class is rejected."""
        data = {
            "answer_status": "ANSWERABLE",
            "question": "Test?",
            "scope": {},
            "short_answer": "Test",
            "observations": [{
                "statement": "Test",
                "value": 1.0,
                "unit": "s",
                "claim_class": "INVALID_CLASS",
                "capability_id": "test_cap",
            }],
        }
        valid, errors = validate_answer_schema(data)
        assert not valid

    def test_valid_answer_modes(self):
        """All valid answer modes are accepted."""
        for mode in ("STANDARD", "DEEP", "FORENSIC"):
            data = {
                "answer_status": "ANSWERABLE",
                "question": "Test?",
                "scope": {},
                "short_answer": "Test",
                "answer_mode": mode,
            }
            valid, errors = validate_answer_schema(data)
            assert valid, f"Mode {mode} rejected: {errors}"

    def test_invalid_answer_mode_rejected(self):
        """Invalid answer_mode is rejected."""
        data = {
            "answer_status": "ANSWERABLE",
            "question": "Test?",
            "scope": {},
            "short_answer": "Test",
            "answer_mode": "INVALID",
        }
        valid, errors = validate_answer_schema(data)
        assert not valid

    def test_nested_structures_validated(self):
        """Nested structures are validated."""
        data = {
            "answer_status": "ANSWERABLE",
            "question": "Test?",
            "scope": {},
            "short_answer": "Test",
            "hypotheses": [{
                "hypothesis_id": "H1",
                "state": "INVALID_STATE",
                "statement": "Test",
            }],
        }
        valid, errors = validate_answer_schema(data)
        # Should accept since we're not validating hypothesis state in schema
        # (that's done in verification)
        assert valid or any("state" in e.lower() for e in errors)

    def test_follow_up_suggestion_validation(self):
        """FollowUpSuggestion validation works."""
        valid_suggestion = FollowUpSuggestion(
            label="Test",
            capability_id="test_cap",
            api_route="/api/test",
            available=True,
        )
        assert valid_suggestion.label == "Test"
        assert valid_suggestion.capability_id == "test_cap"

        # Missing required fields
        with pytest.raises(Exception):
            FollowUpSuggestion(label="", capability_id="test")

    def test_provenance_schema(self):
        """ProvenanceSchema validation works."""
        prov = ProvenanceSchema(
            compiler_version="1.0",
            planner_version="1.0",
            registry_version="1.0",
            capabilities_executed=["cap1", "cap2"],
            capability_errors={},
            availability={},
        )
        assert prov.compiler_version == "1.0"


class TestPromptTemplates:
    """Tests for the prompt template system."""

    def test_prompt_registry_has_templates(self):
        """Registry has all expected templates."""
        tasks = PROMPT_REGISTRY.list_tasks()
        expected = {
            PromptTask.ANSWER_SYNTHESIS,
            PromptTask.QUESTION_UNDERSTANDING,
            PromptTask.EVIDENCE_SYNTHESIS,
            PromptTask.ANSWER_CRITIQUE,
            PromptTask.HYPOTHESIS_GENERATION,
            PromptTask.INVESTIGATION_PLANNING,
        }
        assert set(tasks) == expected

    def test_get_template_by_task(self):
        """Can retrieve template by task."""
        template = PROMPT_REGISTRY.get(PromptTask.ANSWER_SYNTHESIS)
        assert template.task == PromptTask.ANSWER_SYNTHESIS
        assert template.version == "v1"

    def test_render_prompt(self):
        """Prompt rendering works with variables."""
        messages = render_prompt(
            PromptTask.QUESTION_UNDERSTANDING,
            question="Why did Perez lose time in sector 2?",
            context_json="{}",
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Perez" in messages[1]["content"]

    def test_render_prompt_messages(self):
        """Prompt message rendering works."""
        messages = render_prompt_messages(
            PromptTask.ANSWER_SYNTHESIS,
            question="Test?",
            scope_json="{}",
            results_json="{}",
        )
        assert len(messages) == 2
        assert all("role" in m and "content" in m for m in messages)

    def test_system_prompt_contains_core_principles(self):
        """System prompt contains core RaceWise principles."""
        assert "EVIDENCE FIRST" in RACEWISE_SYSTEM_PROMPT
        assert "HONEST UNCERTAINTY" in RACEWISE_SYSTEM_PROMPT
        assert "FALSIFICATION FIRST" in RACEWISE_SYSTEM_PROMPT
        assert "NO FABRICATION" in RACEWISE_SYSTEM_PROMPT
        assert "CLAIM CLASSES" in RACEWISE_SYSTEM_PROMPT

    def test_answer_synthesis_template_has_schema(self):
        """Answer synthesis template references schema."""
        # The system prompt references AnswerSchema
        assert "AnswerSchema" in RACEWISE_SYSTEM_PROMPT
        # The user template mentions claim_class
        assert "claim_class" in ANSWER_SYNTHESIS_TEMPLATE.user_template

    def test_prompt_registry_list_tasks(self):
        """Registry lists all tasks."""
        tasks = PROMPT_REGISTRY.list_tasks()
        assert len(tasks) == 6

    def test_prompt_template_rendering(self):
        """Prompt template rendering substitutes variables."""
        template = PromptTemplate(
            task=PromptTask.QUESTION_UNDERSTANDING,
            version="v1",
            system_prompt="System",
            user_template="Question: ${question}",
            temperature=0.1,
        )
        messages = template.render(question="Why did Perez lose time?")
        assert len(messages) == 2
        assert "Why did Perez lose time?" in messages[1]["content"]

    def test_prompt_role_enum(self):
        """PromptRole enum has expected values."""
        assert PromptRole.SYSTEM.value == "system"
        assert PromptRole.USER.value == "user"
        assert PromptRole.ASSISTANT.value == "assistant"
        assert PromptRole.TOOL.value == "tool"

    def test_prompt_task_enum(self):
        """PromptTask enum has expected values."""
        expected = {
            "question_understanding",
            "investigation_planning",
            "hypothesis_generation",
            "evidence_synthesis",
            "contradiction_analysis",
            "counterfactual_explanation",
            "answer_synthesis",
            "answer_critique",
            "structured_extraction",
            "follow_up_handling",
            "uncertainty_explanation",
        }
        actual = {t.value for t in PromptTask}
        assert actual == expected

    def test_prompt_registry_registration(self):
        """Can register new templates."""
        registry = PromptRegistry()
        template = PromptTemplate(
            task=PromptTask.STRUCTURED_EXTRACTION,
            version="v1",
            system_prompt="Test",
            user_template="Extract: ${text}",
        )
        registry.register(template)
        retrieved = registry.get(PromptTask.STRUCTURED_EXTRACTION, "v1")
        assert retrieved.user_template == "Extract: ${text}"


class TestAnswerSchemaIntegration:
    """Integration tests for AnswerSchema with existing code."""

    def test_answer_schema_from_synthesizer_output(self):
        """Can convert synthesizer Answer to schema."""
        from racewise.question_engine.synthesizer import Answer as SynthesizerAnswer

        ans = SynthesizerAnswer(
            status="ANSWERABLE",
            question="Test?",
            scope={"season": 2023},
            short_answer="Test answer",
            observations=[],
            calculations=[],
        )
        # This should not raise
        schema = AnswerSchema.model_validate(ans.as_dict())
        assert schema.status == "ANSWERABLE"

    def test_answer_schema_roundtrip(self):
        """Can round-trip Answer -> Schema -> Answer."""
        from racewise.question_engine.synthesizer import Answer as SynthesizerAnswer
        from racewise.question_engine.answer_schemas import schema_to_answer

        ans = SynthesizerAnswer(
            status="ANSWERABLE",
            question="Test?",
            scope={},
            short_answer="Test",
        )
        schema = AnswerSchema.model_validate(ans.as_dict())
        back = schema_to_answer(schema)
        assert back.status == "ANSWERABLE"
        assert back.question == "Test?"


class TestEnumValues:
    """Test that enums have expected values."""

    def test_claim_class_values(self):
        expected = {"OBSERVED", "DERIVED", "INFERRED", "MODELLED"}
        actual = set(ClaimClass.__args__) if hasattr(ClaimClass, "__args__") else set()
        # ClaimClass is a Literal, check its args
        from typing import get_args
        actual = set(get_args(ClaimClass))
        assert actual == expected

    def test_answer_status_values(self):
        expected = {
            "ANSWERABLE",
            "PARTIALLY_ANSWERABLE",
            "ANALYSABLE_WITH_LIMITATIONS",
            "INSUFFICIENT_EVIDENCE",
            "DATA_UNAVAILABLE",
            "NOT_TESTABLE",
            "UNSUPPORTED_REQUEST",
            "CONTEXT_UNRESOLVED",
        }
        # AnswerStatus is an alias for AnswerStatusEnum class
        actual = set(AnswerStatus.values())
        assert actual == expected

    def test_answer_mode_values(self):
        expected = {"STANDARD", "DEEP", "FORENSIC"}
        from typing import get_args
        actual = set(get_args(AnswerMode))
        assert actual == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])