"""RACEWISE domain schemas: canonical internal model.

Provider-specific structures (FastF1/OpenF1) are normalized into these
schemas at the adapter boundary and never exposed raw to the agent.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    FACT = "FACT"
    CALCULATION = "CALCULATION"
    INFERENCE = "INFERENCE"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    ASSUMPTION = "ASSUMPTION"


class HypothesisStatus(str, Enum):
    PROPOSED = "PROPOSED"
    SUPPORTED = "SUPPORTED"
    WEAKENED = "WEAKENED"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"


class InvestigationState(str, Enum):
    CREATED = "CREATED"
    FRAMING = "FRAMING"
    HYPOTHESIS_GENERATION = "HYPOTHESIS_GENERATION"
    EVIDENCE_PLANNING = "EVIDENCE_PLANNING"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    HYPOTHESIS_TESTING = "HYPOTHESIS_TESTING"
    FALSIFICATION = "FALSIFICATION"
    COUNTERFACTUAL_ANALYSIS = "COUNTERFACTUAL_ANALYSIS"
    SYNTHESIS = "SYNTHESIS"
    VERIFICATION = "VERIFICATION"
    COMPLETED = "COMPLETED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    TOOL_FAILURE = "TOOL_FAILURE"
    MODEL_FAILURE = "MODEL_FAILURE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Lap(BaseModel):
    session_key: str
    driver: str
    driver_number: Optional[int] = None
    team: Optional[str] = None
    lap_number: int
    lap_time_s: Optional[float] = None
    sector_1_s: Optional[float] = None
    sector_2_s: Optional[float] = None
    sector_3_s: Optional[float] = None
    compound: Optional[str] = None
    tyre_life: Optional[int] = None
    stint: Optional[int] = None
    is_pit_in_lap: bool = False
    is_pit_out_lap: bool = False
    track_status: Optional[str] = None
    position: Optional[int] = None
    is_accurate: Optional[bool] = None
    deleted: bool = False


class PitStop(BaseModel):
    session_key: str
    driver: str
    pit_in_lap: int
    pit_out_lap: Optional[int] = None
    compound_before: Optional[str] = None
    compound_after: Optional[str] = None


class Stint(BaseModel):
    session_key: str
    driver: str
    stint_number: int
    compound: Optional[str] = None
    lap_start: int
    lap_end: int
    lap_count: int


class WeatherRecord(BaseModel):
    session_key: str
    timestamp: Optional[datetime] = None
    air_temp_c: Optional[float] = None
    track_temp_c: Optional[float] = None
    humidity: Optional[float] = None
    rainfall: bool = False


class SessionSummary(BaseModel):
    session_key: str
    event_name: str
    session_type: str
    date: Optional[datetime] = None
    circuit: Optional[str] = None
    total_laps: Optional[int] = None
    drivers: list[str] = Field(default_factory=list)


class RaceControlEvent(BaseModel):
    session_key: str
    timestamp: Optional[datetime] = None
    category: Optional[str] = None
    message: str
    lap: Optional[int] = None


class Observation(BaseModel):
    id: str
    metric: str
    value: Any
    unit: Optional[str] = None
    time_window: Optional[str] = None
    source: str
    method_version: str
    tool_execution_id: Optional[str] = None


class Evidence(BaseModel):
    id: str
    type: EvidenceType
    statement: str
    observation_ids: list[str] = Field(default_factory=list)
    tool_execution_id: Optional[str] = None
    supports: list[str] = Field(default_factory=list)
    contradicts: list[str] = Field(default_factory=list)
    strength: float = Field(0.0, ge=0.0, le=1.0)


class Hypothesis(BaseModel):
    id: str
    statement: str
    predicted_observables: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    potential_falsifiers: list[str] = Field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)


class Counterfactual(BaseModel):
    id: str
    baseline_id: Optional[str] = None
    intervention: str
    assumptions: list[str] = Field(default_factory=list)
    predicted_delta_s: Optional[float] = None
    uncertainty_s: Optional[float] = None
    simulator_version: str
    scenario_params: dict[str, Any] = Field(default_factory=dict)


class Conclusion(BaseModel):
    statement: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    counterfactual_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ToolExecution(BaseModel):
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
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = None


class EventLogEntry(BaseModel):
    event_id: str
    investigation_id: str
    type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
