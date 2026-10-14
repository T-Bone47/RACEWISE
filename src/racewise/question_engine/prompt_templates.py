"""Prompt template system for RaceWise LLM integration (Phase C/D).

This module provides a structured prompt template system for LLM-assisted
answer generation, with versioned templates, structured output schemas,
and provider-agnostic design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from string import Template

from racewise.question_engine.answer_schemas import AnswerSchema, AnswerStatusEnum


class PromptRole(Enum):
    """Message roles for chat-based LLMs."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class PromptTask(Enum):
    """Task categories for prompt routing."""

    QUESTION_UNDERSTANDING = "question_understanding"
    INVESTIGATION_PLANNING = "investigation_planning"
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    EVIDENCE_SYNTHESIS = "evidence_synthesis"
    CONTRADICTION_ANALYSIS = "contradiction_analysis"
    COUNTERFACTUAL_EXPLANATION = "counterfactual_explanation"
    ANSWER_SYNTHESIS = "answer_synthesis"
    ANSWER_CRITIQUE = "answer_critique"
    STRUCTURED_EXTRACTION = "structured_extraction"
    FOLLOW_UP_HANDLING = "follow_up_handling"
    UNCERTAINTY_EXPLANATION = "uncertainty_explanation"


@dataclass(frozen=True)
class PromptMessage:
    """A single message in a prompt conversation."""

    role: PromptRole
    content: str
    name: Optional[str] = None

    def to_dict(self) -> dict[str, str]:
        d = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass(frozen=True)
class PromptTemplate:
    """A versioned prompt template with structured output schema."""

    task: PromptTask
    version: str
    system_prompt: str
    user_template: str
    output_schema: Optional[str] = None  # JSON schema string
    temperature: float = 0.1
    max_tokens: int = 4096
    stop_sequences: tuple[str, ...] = ()

    def render(self, **kwargs: Any) -> list[dict[str, str]]:
        """Render the template with the given variables."""
        user_content = Template(self.user_template).safe_substitute(**kwargs)
        return [
            {"role": PromptRole.SYSTEM.value, "content": self.system_prompt},
            {"role": PromptRole.USER.value, "content": user_content},
        ]

    def render_messages(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Render as a list of message dicts for the LLM API."""
        return self.render(**kwargs)


class PromptRegistry:
    """Registry of versioned prompt templates."""

    def __init__(self) -> None:
        self._templates: dict[tuple[PromptTask, str], PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> None:
        """Register a prompt template."""
        key = (template.task, template.version)
        if key in self._templates:
            raise ValueError(f"Template already registered: {key}")
        self._templates[key] = template

    def get(self, task: PromptTask, version: str = "latest") -> PromptTemplate:
        """Get a prompt template by task and version."""
        if version == "latest":
            # Find the latest version for this task
            versions = [v for (t, v), tmpl in self._templates.items() if t == task]
            if not versions:
                raise KeyError(f"No templates registered for task: {task}")
            # Simple semantic version comparison (v1, v2, etc.)
            latest = max(versions, key=lambda v: tuple(map(int, v.lstrip("v").split("."))))
            return self._templates[(task, latest)]
        key = (PromptTask(task), version)
        if key not in self._templates:
            raise KeyError(f"Template not found: {key}")
        return self._templates[key]

    def list_tasks(self) -> list[PromptTask]:
        """List all registered task types."""
        return list({t for t, _ in self._templates.keys()})


# Global registry instance
PROMPT_REGISTRY = PromptRegistry()


# ---------------------------------------------------------------------------
# Built-in prompt templates (Phase C/D foundation)
# ---------------------------------------------------------------------------


# System prompt - the core RaceWise identity and constraints
RACEWISE_SYSTEM_PROMPT = """You are RaceWise, an evidence-driven Formula 1 engineering investigation system.

CORE PRINCIPLES:
1. EVIDENCE FIRST: Every claim must trace to a deterministic tool result. Never invent numbers.
2. HONEST UNCERTAINTY: Distinguish OBSERVED (measured), DERIVED (calculated), INFERRED (modelled), MODELLED (counterfactual). Never promote a model to a measurement.
3. FALSIFICATION FIRST: Every hypothesis must be tested against evidence. Report what was tested, what failed, and what remains untested.
3. NO FABRICATION: If evidence is missing, say so. If a mechanism cannot be established, say so. Never invent a braking/tyre/traffic explanation without evidence.
4. STRUCTURED OUTPUT: Return only the structured answer schema. No free-form prose unless explicitly requested.

CLAIM CLASSES (use exactly these):
- OBSERVED: Directly measured from authoritative source (canonical lap times, sector times)
- DERIVED: Calculated from observations via documented formula (sector sums, residuals)
- INFERRED: Modelled from evidence with documented assumptions (telemetry window estimates)
- MODELLED: Counterfactual or simulated (simulate_pit_timing, simulate_telemetry_counterfactual)

NEVER claim causation from correlation. Use: "evidence is consistent with" not "caused by".
NEVER invent braking/tyre/setup/traffic explanations without telemetry evidence.
When evidence is insufficient, state what is known, what is missing, and the next useful comparison.

OUTPUT FORMAT: Return ONLY the structured answer JSON matching the AnswerSchema. No prose."""


# Task-specific prompt templates
ANSWER_SYNTHESIS_TEMPLATE = PromptTemplate(
    task=PromptTask.ANSWER_SYNTHESIS,
    version="v1",
    system_prompt=RACEWISE_SYSTEM_PROMPT,
    user_template="""Synthesize a structured engineering answer from the following investigation results.

QUESTION: ${question}
SCOPE: ${scope_json}

INVESTIGATION RESULTS:
${results_json}

STRUCTURED ANSWER SCHEMA (return ONLY this JSON):
{
  "status": "ANSWERABLE|PARTIALLY_ANSWERABLE|ANALYSABLE_WITH_LIMITATIONS|INSUFFICIENT_EVIDENCE|DATA_UNAVAILABLE|NOT_TESTABLE|UNSUPPORTED_REQUEST|CONTEXT_UNRESOLVED",
  "question": "string",
  "scope": {},
  "short_answer": "One honest sentence. Never a confidence score, never a causal claim.",
  "established": [{"statement": "string", "detail": []}],
  "not_established": [{"statement": "string", "reason": "string", "missing_data": []}],
  "why_not": [],
  "observations": [{"statement": "string", "value": number, "unit": "string", "claim_class": "OBSERVED|DERIVED|INFERRED|MODELLED", "capability_id": "string"}],
  "calculations": [{"statement": "string", "value": number, "unit": "string", "claim_class": "DERIVED|INFERRED", "capability_id": "string", "hypothesis_id": "optional"}],
  "hypotheses": [{"hypothesis_id": "string", "state": "SUPPORTED|PARTIALLY_SUPPORTED|NOT_SUPPORTED|CONTRADICTED|MIXED_EVIDENCE|NOT_TESTABLE|INSUFFICIENT_EVIDENCE", "statement": "string", "supporting_evidence_ids": [], "contradicting_evidence_ids": [], "untestable_evidence_ids": [], "capability_id": "string"}],
  "supporting_evidence": [],
  "contradicting_evidence": [],
  "residuals": [{"statement": "string", "value": number, "unit": "string", "claim_class": "DERIVED", "never_assigned_to": "no mechanism"}],
  "counterfactuals": [{"id": "string", "intervention": "string", "predicted_delta_s": number, "uncertainty_s": number, "simulator_version": "string", "scenario_params": {}}],
  "spatial": [{"scope": "string", "measured_delta_s": number, "telemetry_estimated_loss_s": number, "claim_class": "OBSERVED"}],
  "evidence_ledger": [],
  "events": [],
  "counter_evidence": [],
  "answer_mode": "STANDARD",
  "engine_conclusion": "string",
  "assumptions": [],
  "limitations": [],
  "missing_evidence": [],
  "provenance": {},
  "decision_trace": [],
  "follow_ups": [{"label": "string", "capability_id": "string", "api_route": "string", "available": true}]
}

Return ONLY the JSON object. No additional text.""",
    output_schema=None,  # Will be filled with AnswerSchema JSON schema
    temperature=0.1,
    max_tokens=8192,
)

# Question understanding template
QUESTION_UNDERSTANDING_TEMPLATE = PromptTemplate(
    task=PromptTask.QUESTION_UNDERSTANDING,
    version="v1",
    system_prompt=RACEWISE_SYSTEM_PROMPT,
    user_template="""Parse this engineering question into a structured investigation specification.

QUESTION: ${question}

CONTEXT (if any): ${context_json}

Extract:
1. Requested outcome (what the user wants to know)
2. Relevant drivers, sessions, laps, sectors
3. Candidate performance metrics
4. Required evidence
5. Possible competing explanations
6. Missing context
7. Suitable analytical tools
7. What constitutes a sufficient answer

Return JSON:
{
  "requested_outcome": "string",
  "drivers": ["driver_key"],
  "session": {"season": 2023, "round": 1, "session_type": "RACE"},
  "lap": 6,
  "sector": 2,
  "metrics": ["lap_delta", "sector_delta", "speed_delta"],
  "required_evidence": ["lap_times", "sector_times", "telemetry"],
  "competing_explanations": ["corner_speed", "throttle", "braking", "tyre_degradation"],
  "missing_context": [],
  "tools": ["compare_laps", "attribute_lap_loss", "fuse_lap_evidence"],
  "sufficient_answer_criteria": "mechanism identified with supporting evidence"
}""",
    temperature=0.1,
    max_tokens=2048,
)

# Evidence synthesis template
EVIDENCE_SYNTHESIS_TEMPLATE = PromptTemplate(
    task=PromptTask.EVIDENCE_SYNTHESIS,
    version="v1",
    system_prompt=RACEWISE_SYSTEM_PROMPT,
    user_template="""Synthesize evidence for the following hypotheses.

HYPOTHESES:
${hypotheses_json}

EVIDENCE ITEMS:
${evidence_json}

For each hypothesis, determine:
1. SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED / CONTRADICTED / NOT_TESTABLE / INSUFFICIENT_EVIDENCE
2. Supporting evidence IDs
3. Contradicting evidence IDs
4. Untestable evidence IDs
5. Confidence (0.0-1.0)

Return JSON array of hypothesis evaluations.""",
    temperature=0.1,
    max_tokens=4096,
)

# Answer critique template (for independent model review)
ANSWER_CRITIQUE_TEMPLATE = PromptTemplate(
    task=PromptTask.ANSWER_CRITIQUE,
    version="v1",
    system_prompt="""You are an independent RaceWise answer critic. Your job is to find flaws in engineering answers.

CHECKLIST:
1. Does every numeric claim trace to a capability result?
2. Are claim classes correct (OBSERVED/DERIVED/INFERRED/MODELLED)?
3. Are counterfactuals labelled MODELLED?
4. Are residuals reported but never assigned to mechanisms?
4. Are hypothesis states from the engine, not invented?
5. Are counterfactuals clearly distinguished from observations?
6. Are causal claims supported by evidence or explicitly flagged as unsupported?
7. Are limitations and missing evidence acknowledged?
6. Is the short_answer honest (no confidence scores, no causal claims)?

Return JSON:
{
  "passed": true/false,
  "violations": [{"check": "string", "detail": "string"}],
  "summary": "string"
}""",
    user_template="""Critique the following answer:

QUESTION: ${question}
ANSWER: ${answer_json}

Return the critique JSON.""",
    temperature=0.0,
    max_tokens=4096,
)

# Hypothesis generation template
HYPOTHESIS_GENERATION_TEMPLATE = PromptTemplate(
    task=PromptTask.HYPOTHESIS_GENERATION,
    version="v1",
    system_prompt=RACEWISE_SYSTEM_PROMPT,
    user_template="""Generate plausible, meaningfully different engineering hypotheses for:

QUESTION: ${question}
OBSERVED DELTA: ${delta_s} s
SECTOR DELTAS: ${sector_deltas_json}
AVAILABLE EVIDENCE: ${evidence_summary}

Generate 3-5 hypotheses that are:
- Plausible given F1 physics
- Meaningfully different (different mechanisms)
- Testable with available evidence types
- Each with predicted observables and falsification conditions

Return JSON array:
[
  {
    "hypothesis_id": "H1_corner_speed",
    "statement": "string",
    "predicted_observables": ["lower minimum corner speed", "lower exit speed"],
    "required_evidence": ["sector_times", "speed_trace"],
    "potential_falsifiers": ["equal or higher minimum corner speed"],
    "mechanism_category": "corner_speed"
  }
]""",
    temperature=0.2,
    max_tokens=4096,
)

# Investigation planning template
INVESTIGATION_PLANNING_TEMPLATE = PromptTemplate(
    task=PromptTask.INVESTIGATION_PLANNING,
    version="v1",
    system_prompt=RACEWISE_SYSTEM_PROMPT,
    user_template="""Create an investigation plan for:

QUESTION: ${question}
STRUCTURED SPEC: ${spec_json}

Available capabilities:
${capabilities_json}

Data availability:
${availability_json}

Create a bounded, goal-directed plan:
1. Goal-directed steps
2. Evidence-aware (what\u2019s available vs needed)
3. Cost-conscious (budget limits)
4. Reproducible
4. Bounded scope
5. Can recognize missing prerequisites
6. Can stop when sufficient

Return JSON:
{
  "steps": [
    {"phase": "EVIDENCE_PLANNING", "tool": "capability_id", "purpose": "string", "why": "string"}
  ],
  "estimated_tool_calls": 10,
  "estimated_runtime_ms": 30000,
  "budget_risks": []
}""",
    temperature=0.1,
    max_tokens=2048,
)


# Register all templates
PROMPT_REGISTRY.register(ANSWER_SYNTHESIS_TEMPLATE)
PROMPT_REGISTRY.register(QUESTION_UNDERSTANDING_TEMPLATE)
PROMPT_REGISTRY.register(EVIDENCE_SYNTHESIS_TEMPLATE)
PROMPT_REGISTRY.register(ANSWER_CRITIQUE_TEMPLATE)
PROMPT_REGISTRY.register(HYPOTHESIS_GENERATION_TEMPLATE)
PROMPT_REGISTRY.register(INVESTIGATION_PLANNING_TEMPLATE)


# ---------------------------------------------------------------------------
# Prompt rendering utilities
# ---------------------------------------------------------------------------


def render_prompt(
    task: PromptTask,
    version: str = "latest",
    **kwargs: Any,
) -> list[dict[str, str]]:
    """Render a prompt template with the given variables."""
    template = PROMPT_REGISTRY.get(PromptTask(task), version)
    return template.render(**kwargs)


def render_prompt_messages(
    task: PromptTask,
    version: str = "latest",
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Render a prompt template as a list of message dicts for LLM API."""
    template = PROMPT_REGISTRY.get(PromptTask(task), version)
    return template.render_messages(**kwargs)


def get_output_schema(task: PromptTask) -> Optional[str]:
    """Get the JSON schema for a task's output."""
    template = PROMPT_REGISTRY.get(PromptTask(task))
    return template.output_schema


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

__all__ = [
    "PromptRole",
    "PromptTask",
    "PromptMessage",
    "PromptTemplate",
    "PromptRegistry",
    "PROMPT_REGISTRY",
    "RACEWISE_SYSTEM_PROMPT",
    "ANSWER_SYNTHESIS_TEMPLATE",
    "QUESTION_UNDERSTANDING_TEMPLATE",
    "EVIDENCE_SYNTHESIS_TEMPLATE",
    "ANSWER_CRITIQUE_TEMPLATE",
    "HYPOTHESIS_GENERATION_TEMPLATE",
    "INVESTIGATION_PLANNING_TEMPLATE",
    "render_prompt",
    "render_prompt_messages",
    "get_output_schema",
]