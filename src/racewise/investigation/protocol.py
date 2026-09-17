"""Host-driven investigation protocol.

Union Alpha (via OpenCode) drives RACEWISE through validated phases.
The protocol validates every structured output, retries malformed output
with explicit errors, and transitions to MODEL_FAILURE on repeated failure.
Model decisions are recorded separately from deterministic outputs.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from racewise.domain.schemas import (
    Conclusion,
    Counterfactual,
    Evidence,
    EvidenceType,
    EventLogEntry,
    Hypothesis,
    InvestigationState,
    Observation,
)


class ProtocolError(Exception):
    """Raised when a phase output violates the contract."""

    def __init__(self, message: str, *, phase: str, errors: list[str]) -> None:
        super().__init__(message)
        self.phase = phase
        self.errors = errors


class ToolRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    purpose: str = ""
    hypothesis_ids: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    type: EvidenceType
    statement: str = Field(min_length=3, max_length=500)
    tool: Optional[str] = None
    tool_execution_id: Optional[str] = None
    observation_ids: list[str] = Field(default_factory=list)
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    strength: float = Field(0.0, ge=0.0, le=1.0)


class HypothesisItem(BaseModel):
    id: str = Field(min_length=1, max_length=16)
    statement: str = Field(min_length=3, max_length=300)
    predicted_observables: list[str] = Field(default_factory=list)
    potential_falsifiers: list[str] = Field(default_factory=list)
    priority: str = Field("normal", pattern="^(high|normal|low)$")
    status: str = Field("UNTESTED", pattern="^(UNTESTED|SUPPORTED|PARTIALLY_SUPPORTED|CONTRADICTED|UNRESOLVED|REJECTED)$")


class FrameOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    session: dict[str, Any] = Field(default_factory=dict)
    driver: Optional[str] = None
    comparison_drivers: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)


class HypothesesOutput(BaseModel):
    hypotheses: list[HypothesisItem] = Field(min_length=3, max_length=8)


class EvidencePlanOutput(BaseModel):
    rationale: str = Field(min_length=3)
    tool_requests: list[ToolRequest] = Field(min_length=1)


class EvaluationOutput(BaseModel):
    evidence: list[EvidenceItem] = Field(min_length=1)
    hypothesis_updates: list[dict[str, Any]] = Field(default_factory=list)


class FalsificationTarget(BaseModel):
    hypothesis_id: str
    challenge: str = Field(min_length=3)
    evidence_requests: list[ToolRequest] = Field(min_length=1)


class FalsificationOutput(BaseModel):
    targets: list[FalsificationTarget] = Field(min_length=1)
    outcome: str = Field(pattern="^(COMPLETED|INSUFFICIENT_EVIDENCE)$")


class CounterfactualRequestOutput(BaseModel):
    action: str = Field(pattern="^(RUN|SKIP)$")
    tool: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3)


class SynthesisOutput(BaseModel):
    conclusion: str = Field(min_length=10, max_length=2000)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    counterfactual_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ModelDecision(BaseModel):
    phase: str
    attempt: int
    output: dict[str, Any]
    valid: bool
    errors: list[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class ProtocolState(str, Enum):
    FRAME = "FRAME"
    HYPOTHESES = "HYPOTHESES"
    EVIDENCE_PLAN = "EVIDENCE_PLAN"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    EVALUATION = "EVALUATION"
    FALSIFICATION = "FALSIFICATION"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    SYNTHESIS = "SYNTHESIS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


PHASE_MODELS: dict[str, type[BaseModel]] = {
    ProtocolState.FRAME: FrameOutput,
    ProtocolState.HYPOTHESES: HypothesesOutput,
    ProtocolState.EVIDENCE_PLAN: EvidencePlanOutput,
    ProtocolState.EVALUATION: EvaluationOutput,
    ProtocolState.FALSIFICATION: FalsificationOutput,
    ProtocolState.COUNTERFACTUAL: CounterfactualRequestOutput,
    ProtocolState.SYNTHESIS: SynthesisOutput,
}


@dataclass
class ProtocolResult:
    ok: bool
    phase: str
    output: Optional[BaseModel] = None
    errors: list[str] = field(default_factory=list)
    retries_used: int = 0


class InvestigationProtocol:
    """Validates host-driven phase outputs against the RACEWISE contract."""

    MAX_RETRIES = 2

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.state = ProtocolState.FRAME
        self.model_decisions: list[ModelDecision] = []

    def submit(self, phase: str, payload: Any) -> ProtocolResult:
        """Validate a model response for a phase; record decision either way."""
        model = PHASE_MODELS.get(phase)
        if model is None:
            return ProtocolResult(ok=False, phase=phase, errors=[f"Unknown phase '{phase}'"])
        errors: list[str] = []
        parsed: Optional[BaseModel] = None
        try:
            parsed = model.model_validate(payload)
        except ValidationError as exc:
            errors = [f"{'.'.join(str(p) for p in err['loc']) or 'root'}: {err['msg']}" for err in exc.errors()]
        self.model_decisions.append(ModelDecision(phase=phase, attempt=len([d for d in self.model_decisions if d.phase == phase]) + 1, output=payload if isinstance(payload, dict) else {"raw": str(payload)[:2000]}, valid=parsed is not None, errors=errors))
        if parsed is None:
            failures = sum(1 for d in self.model_decisions if d.phase == phase and not d.valid)
            if failures > self.MAX_RETRIES:
                self.state = ProtocolState.FAILED
                self.engine.emit("MODEL_FAILURE", {"phase": phase, "errors": errors})
            return ProtocolResult(ok=False, phase=phase, errors=errors)
        self.state = ProtocolState(phase) if phase in ProtocolState.__members__ else self.state
        return ProtocolResult(ok=True, phase=phase, output=parsed)

    def attempts(self, phase: str) -> int:
        return sum(1 for d in self.model_decisions if d.phase == phase and d.valid)

    def record_tool_execution(self, tool: str, execution: dict[str, Any]) -> None:
        self.engine.emit("TOOL_EXECUTION_COMPLETED", {"tool": tool, "status": execution.get("status")})

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "model_decisions": [d.model_dump() for d in self.model_decisions],
        }
