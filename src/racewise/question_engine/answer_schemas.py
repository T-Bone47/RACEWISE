"""Structured answer schemas with Pydantic validation for Phase C.

These models define the structured response schema for RaceWise answers,
providing runtime validation and serving as the contract for answer
generation (both deterministic and future LLM-based).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional
from typing import get_origin, get_args

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Annotated


# ---------------------------------------------------------------------------
# Claim classes and answer statuses (closed vocabularies)
# ---------------------------------------------------------------------------

ClaimClass = Literal["OBSERVED", "DERIVED", "INFERRED", "MODELLED"]

AnswerStatus = Literal[
    "ANSWERABLE",
    "PARTIALLY_ANSWERABLE",
    "ANALYSABLE_WITH_LIMITATIONS",
    "INSUFFICIENT_EVIDENCE",
    "DATA_UNAVAILABLE",
    "NOT_TESTABLE",
    "UNSUPPORTED_REQUEST",
    "CONTEXT_UNRESOLVED",
]

AnswerMode = Literal["STANDARD", "DEEP", "FORENSIC"]

HypothesisState = Literal[
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "NOT_SUPPORTED",
    "CONTRADICTED",
    "MIXED_EVIDENCE",
    "NOT_TESTABLE",
    "INSUFFICIENT_EVIDENCE",
]

EvidenceType = Literal["FACT", "CALCULATION", "INFERENCE", "MODELLED", "ASSUMPTION"]

EvidenceRelationshipType = Literal[
    "SUPPORTS", "CONTRADICTS", "DERIVES_FROM", "INFORMS", "CONSTRAINS"
]

InvestigationState = Literal[
    "CREATED", "FRAMING", "HYPOTHESIS_GENERATION", "EVIDENCE_PLANNING",
    "EVIDENCE_COLLECTION", "HYPOTHESIS_TESTING", "FALSIFICATION",
    "COUNTERFACTUAL_ANALYSIS", "SYNTHESIS", "VERIFICATION", "COMPLETED",
    "DATA_UNAVAILABLE", "TOOL_FAILURE", "MODEL_FAILURE",
    "INSUFFICIENT_EVIDENCE",
]

# ---------------------------------------------------------------------------
# Evidence and hypothesis schemas
# ---------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """A single piece of evidence with full provenance."""

    id: str
    type: EvidenceType
    statement: str
    observation_ids: list[str] = Field(default_factory=list)
    tool_execution_id: Optional[str] = None
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    strength: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str
    method_version: str
    tool_execution_id: Optional[str] = None
    claim_class: ClaimClass = "OBSERVED"

    @field_validator("strength")
    @classmethod
    def validate_strength(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 4)


class Hypothesis(BaseModel):
    """An engineering hypothesis with evaluation state."""

    id: str
    statement: str
    predicted_observables: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    potential_falsifiers: list[str] = Field(default_factory=list)
    state: HypothesisState = "PROPOSED"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    capability_id: Optional[str] = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 4)


class Observation(BaseModel):
    """An observed or calculated metric with provenance."""

    id: str
    metric: str
    value: Any
    unit: Optional[str] = None
    time_window: Optional[tuple[float, float]] = None
    source: str
    method_version: str
    tool_execution_id: Optional[str] = None
    claim_class: ClaimClass = "OBSERVED"


class EvidenceRelationship(BaseModel):
    """Relationship between two evidence items."""

    id: str
    investigation_id: str
    source_id: str
    target_id: str
    relationship_type: EvidenceRelationshipType
    provenance: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Counterfactual(BaseModel):
    """A counterfactual scenario with explicit assumptions."""

    id: str
    baseline_id: Optional[str] = None
    intervention: str
    assumptions: list[str] = Field(default_factory=list)
    predicted_delta_s: Optional[float] = None
    uncertainty_s: Optional[float] = None
    simulator_version: str
    scenario_params: dict[str, Any] = Field(default_factory=dict)


class Conclusion(BaseModel):
    """Engineering conclusion with evidence backing."""

    statement: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    counterfactual_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ToolExecution(BaseModel):
    """Record of a deterministic tool execution."""

    id: str
    investigation_id: str
    tool: str
    tool_version: str
    input: dict[str, Any]
    input_hash: str
    output: Optional[dict[str, Any]] = None
    output_hash: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: Optional[int] = None


class EventLogEntry(BaseModel):
    """Single event in the investigation trace."""

    event_id: str
    investigation_id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Main Answer schema
# ---------------------------------------------------------------------------


class AnswerStatusEnum(str):
    """Valid answer statuses."""

    ANSWERABLE = "ANSWERABLE"
    PARTIALLY_ANSWERABLE = "PARTIALLY_ANSWERABLE"
    ANALYSABLE_WITH_LIMITATIONS = "ANALYSABLE_WITH_LIMITATIONS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    NOT_TESTABLE = "NOT_TESTABLE"
    UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
    CONTEXT_UNRESOLVED = "CONTEXT_UNRESOLVED"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        return (
            cls.ANSWERABLE,
            cls.PARTIALLY_ANSWERABLE,
            cls.ANALYSABLE_WITH_LIMITATIONS,
            cls.INSUFFICIENT_EVIDENCE,
            cls.DATA_UNAVAILABLE,
            cls.NOT_TESTABLE,
            cls.UNSUPPORTED_REQUEST,
            cls.CONTEXT_UNRESOLVED,
        )

    @classmethod
    def validate(cls, v: str) -> str:
        if v not in cls.values():
            raise ValueError(f"Invalid answer status: {v}. Must be one of {cls.values()}")
        return v


# Alias for backward compatibility
AnswerStatus = AnswerStatusEnum


class AnswerSchema(BaseModel):
    """Structured engineering answer with full validation.

    This is the canonical schema for RaceWise answers. All answers produced
    by the system (deterministic or LLM-assisted) must conform to this schema.
    """

    # Core identity
    status: Annotated[str, Field(description="Answer status from closed vocabulary", validation_alias="answer_status", serialization_alias="answer_status")]
    question: str = Field(..., min_length=1, description="Original question text")
    scope: dict[str, Any] = Field(default_factory=dict, description="Investigation scope")
    short_answer: str = Field(..., min_length=1, description="One-sentence summary")

    # Structured findings
    established: list[dict[str, Any]] = Field(default_factory=list)
    not_established: list[dict[str, Any]] = Field(default_factory=list)
    why_not: list[dict[str, Any]] = Field(default_factory=list)

    # Evidence and reasoning
    observations: list[dict[str, Any]] = Field(default_factory=list)
    calculations: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    contradicting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    residuals: list[dict[str, Any]] = Field(default_factory=list)
    counterfactuals: list[dict[str, Any]] = Field(default_factory=list)
    spatial: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ledger: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    counter_evidence: list[dict[str, Any]] = Field(default_factory=list)

    # Answer metadata
    answer_mode: AnswerMode = "STANDARD"
    engine_conclusion: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    decision_trace: list[dict[str, Any]] = Field(default_factory=list)
    follow_ups: list[dict[str, Any]] = Field(default_factory=list)

    # Version tracking
    synthesizer_version: str = "question_engine_synthesizer_v1"
    registry_version: str = "0.1.0"

    # Computed hash (set after construction)
    answer_hash: Optional[str] = None

    # Validators
    @field_validator("observations", "calculations", "supporting_evidence", "contradicting_evidence")
    @classmethod
    def validate_claim_class(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate claim_class in evidence items."""
        from typing import get_args
        valid_classes = set(get_args(ClaimClass))

        for item in v:
            claim_class = item.get("claim_class")
            if claim_class and claim_class not in valid_classes:
                raise ValueError(f"Invalid claim_class: {claim_class}. Must be one of {valid_classes}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return AnswerStatusEnum.validate(v)

    @field_validator("answer_mode")
    @classmethod
    def validate_answer_mode(cls, v: str) -> str:
        valid_modes = ("STANDARD", "DEEP", "FORENSIC")
        if v not in valid_modes:
            raise ValueError(f"Invalid answer_mode: {v}. Must be one of {valid_modes}")
        return v

    @model_validator(mode="after")
    def validate_required_fields(self) -> "AnswerSchema":
        """Ensure required fields are present for valid answers."""
        if self.status in AnswerStatusEnum.values():
            if not self.question or not self.question.strip():
                raise ValueError("question must be non-empty")
            if not self.short_answer or not self.short_answer.strip():
                raise ValueError("short_answer must be non-empty")
            if not isinstance(self.scope, dict):
                raise ValueError("scope must be a dictionary")
        return self

    # Core identity
    status: Annotated[str, Field(description="Answer status from closed vocabulary", validation_alias="answer_status", serialization_alias="answer_status")]
    question: str = Field(..., min_length=1, description="Original question text")
    scope: dict[str, Any] = Field(default_factory=dict, description="Investigation scope")
    short_answer: str = Field(..., min_length=1, description="One-sentence summary")

    # Structured findings
    established: list[dict[str, Any]] = Field(default_factory=list)
    not_established: list[dict[str, Any]] = Field(default_factory=list)
    why_not: list[dict[str, Any]] = Field(default_factory=list)

    # Evidence and reasoning
    observations: list[dict[str, Any]] = Field(default_factory=list)
    calculations: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    contradicting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    residuals: list[dict[str, Any]] = Field(default_factory=list)
    counterfactuals: list[dict[str, Any]] = Field(default_factory=list)
    spatial: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ledger: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    counter_evidence: list[dict[str, Any]] = Field(default_factory=list)

    # Answer metadata
    answer_mode: AnswerMode = "STANDARD"
    engine_conclusion: Optional[str] = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    decision_trace: list[dict[str, Any]] = Field(default_factory=list)
    follow_ups: list[dict[str, Any]] = Field(default_factory=list)

    # Version tracking
    synthesizer_version: str = "question_engine_synthesizer_v1"
    registry_version: str = "0.1.0"

    # Computed hash (set after construction)
    answer_hash: Optional[str] = None

    # Validators
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return AnswerStatusEnum.validate(v)

    @field_validator("answer_mode")
    @classmethod
    def validate_answer_mode(cls, v: str) -> str:
        valid_modes = ("STANDARD", "DEEP", "FORENSIC")
        if v not in valid_modes:
            raise ValueError(f"Invalid answer_mode: {v}. Must be one of {valid_modes}")
        return v

    @model_validator(mode="after")
    def validate_required_fields(self) -> "AnswerSchema":
        """Ensure required fields are present for valid answers."""
        if self.status in AnswerStatusEnum.values():
            if not self.question or not self.question.strip():
                raise ValueError("question must be non-empty")
            if not self.short_answer or not self.short_answer.strip():
                raise ValueError("short_answer must be non-empty")
            if not isinstance(self.scope, dict):
                raise ValueError("scope must be a dictionary")
        return self


# ---------------------------------------------------------------------------
# Follow-up suggestion schema
# ---------------------------------------------------------------------------


class FollowUpSuggestion(BaseModel):
    """A suggested follow-up action with capability binding."""

    label: str = Field(..., min_length=1)
    capability_id: str = Field(..., min_length=1)
    api_route: Optional[str] = None
    available: bool = True


# ---------------------------------------------------------------------------
# Provenance schema
# ---------------------------------------------------------------------------


class ProvenanceSchema(BaseModel):
    """Provenance information for an answer."""

    compiler_version: Optional[str] = None
    planner_version: Optional[str] = None
    registry_version: str
    capabilities_executed: list[str] = Field(default_factory=list)
    capability_errors: dict[str, str] = Field(default_factory=dict)
    availability: dict[str, Any] = Field(default_factory=dict)
    autopsy: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def validate_answer_schema(answer_dict: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate an answer dictionary against the AnswerSchema.

    Returns (is_valid, list_of_errors).
    """
    try:
        AnswerSchema.model_validate(answer_dict)
        return True, []
    except Exception as e:
        return False, [str(e)]


def answer_to_schema(answer: "Answer") -> "AnswerSchema":
    """Convert a synthesizer Answer dataclass to AnswerSchema."""
    from racewise.question_engine.synthesizer import Answer as SynthesizerAnswer
    from racewise.tools.contract import canonical_hash

    if not isinstance(answer, SynthesizerAnswer):
        raise TypeError("Expected synthesizer Answer instance")

    data = answer.as_dict()
    if "answer_hash" not in data:
        payload = {k: v for k, v in data.items() if k != "provenance"}
        from racewise.tools.contract import canonical_hash
        data["answer_hash"] = canonical_hash(payload)

    return AnswerSchema.model_validate(data)


def schema_to_answer(schema: "AnswerSchema") -> "Answer":
    """Convert AnswerSchema back to synthesizer Answer dataclass."""
    from racewise.question_engine.synthesizer import Answer as SynthesizerAnswer
    from dataclasses import fields

    synthesizer_fields = {f.name for f in fields(SynthesizerAnswer)}
    data = schema.model_dump(exclude_none=True)
    filtered = {k: v for k, v in data.items() if k in synthesizer_fields}
    if "follow_ups" in filtered and isinstance(filtered["follow_ups"], list):
        filtered["follow_ups"] = tuple(filtered["follow_ups"])

    return SynthesizerAnswer(**filtered)


def validate_answer_claims(
    answer: "Answer",
    results: dict[str, Any],
    strict: bool = True,
) -> tuple[bool, list[str]]:
    """Comprehensive validation of an answer against capability results.

    Returns (is_valid, list_of_errors). In strict mode, any validation
    failure returns False.
    """
    from racewise.question_engine.verification import verify_answer

    report = verify_answer(answer, results)
    errors = [f"{v['check']}: {v['detail']}" for v in report.violations]

    schema_valid, schema_errors = validate_answer_schema(answer.as_dict())
    errors.extend(schema_errors)

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "ClaimClass",
    "AnswerStatusEnum",
    "AnswerStatus",
    "AnswerMode",
    "HypothesisState",
    "EvidenceType",
    "EvidenceRelationshipType",
    "InvestigationState",
    # Models
    "EvidenceItem",
    "Hypothesis",
    "Observation",
    "EvidenceRelationship",
    "Counterfactual",
    "Conclusion",
    "ToolExecution",
    "EventLogEntry",
    "AnswerSchema",
    "FollowUpSuggestion",
    "ProvenanceSchema",
    # Validators
    "validate_answer_schema",
    "answer_to_schema",
    "schema_to_answer",
    "validate_answer_claims",
    # Constants
    "ClaimClass",
    "AnswerStatus",
    "AnswerMode",
    "HypothesisState",
    "EvidenceType",
    "EvidenceRelationshipType",
    "InvestigationState",
]