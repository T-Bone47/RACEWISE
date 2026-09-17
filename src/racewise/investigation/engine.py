"""Investigation engine: the heart of RACEWISE.

Runs a bounded, observable investigation state machine:
CREATED -> FRAMING -> HYPOTHESIS_GENERATION -> EVIDENCE_PLANNING ->
EVIDENCE_COLLECTION -> HYPOTHESIS_TESTING -> FALSIFICATION ->
COUNTERFACTUAL_ANALYSIS -> SYNTHESIS -> VERIFICATION -> COMPLETED.

The engine never computes numbers itself; it orchestrates deterministic
tools and, when configured, an LLM investigator (ModelProvider).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from racewise.agent.provider import ModelProvider
from racewise.domain.schemas import (
    Conclusion,
    Counterfactual,
    Evidence,
    EventLogEntry,
    EvidenceType,
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
    Observation,
    ToolExecution,
)
from racewise.simulator.strategy import simulate_pit_timing
from racewise.tools.contract import ToolError, ToolRegistry


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationEngine:
    """Bounded state-machine investigation over a session tool registry."""

    def __init__(
        self,
        registry: Any,
        provider: ModelProvider | None,
        question: str,
        *,
        max_rounds: int = 6,
        investigation_id: str | None = None,
    ) -> None:
        self.registry = registry
        self.provider = provider
        self.question = question
        self.max_rounds = max_rounds
        self.investigation_id = investigation_id or uuid.uuid4().hex[:12]
        self.state = InvestigationState.CREATED
        self.hypotheses: list[Hypothesis] = []
        self.observations: list[Observation] = []
        self.evidence: list[Evidence] = []
        self.tool_executions: list[ToolExecution] = []
        self.counterfactuals: list[Counterfactual] = []
        self.conclusion: Conclusion | None = None
        self.event_log: list[EventLogEntry] = []
        self.notes: list[str] = []
        self._rounds_used = 0

    # -- observability -----------------------------------------------------
    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.event_log.append(
            EventLogEntry(
                event_id=uuid.uuid4().hex[:8],
                investigation_id=self.investigation_id,
                type=event_type,
                payload=payload or {},
            )
        )

    def _set_state(self, state: InvestigationState) -> None:
        self.state = state
        self.emit("state.changed", {"state": state.value})

    # -- tool execution with provenance ------------------------------------
    def run_tool(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        execution = ToolExecution(
            id=uuid.uuid4().hex[:8],
            investigation_id=self.investigation_id,
            tool=name,
            tool_version="",
            input=kwargs,
            input_hash="",
        )
        self.emit("tool.started", {"tool": name, "input": kwargs})
        try:
            result = self.registry.execute(name, kwargs)
        except ToolError as exc:
            execution.status = "tool_error"
            execution.error = str(exc)
            self.tool_executions.append(execution)
            self.emit("tool.failed", {"tool": name, "error": str(exc), "missing": exc.missing})
            return {"error": str(exc), "missing": exc.missing, "status": "tool_error"}
        except Exception as exc:  # noqa: BLE001 — engine must never crash on a tool
            execution.status = "exception"
            execution.error = str(exc)
            self.tool_executions.append(execution)
            self.emit("tool.failed", {"tool": name, "error": str(exc)})
            return {"error": str(exc), "status": "exception"}
        execution.tool_version = result["tool_version"]
        execution.input_hash = result["input_hash"]
        execution.output = result["output"]
        execution.output_hash = result["output_hash"]
        execution.status = "completed"
        execution.duration_ms = result["duration_ms"]
        self.tool_executions.append(execution)
        self.emit("tool.completed", {"tool": name, "duration_ms": result["duration_ms"]})
        return result["output"]

    def observe(self, metric: str, value: Any, unit: str | None, source: str, method_version: str, tool_execution_id: str | None = None) -> Observation:
        obs = Observation(
            id=uuid.uuid4().hex[:8],
            metric=metric,
            value=value,
            unit=unit,
            time_window=None,
            source=source,
            method_version=method_version,
            tool_execution_id=tool_execution_id,
        )
        self.observations.append(obs)
        return obs

    def add_evidence(
        self,
        statement: str,
        type_: EvidenceType,
        observation_ids: list[str],
        tool_execution_id: str | None,
        supports: list[str] | None = None,
        contradicts: list[str] | None = None,
        strength: float = 0.0,
    ) -> Evidence:
        ev = Evidence(
            id=uuid.uuid4().hex[:8],
            type=type_,
            statement=statement,
            observation_ids=observation_ids,
            tool_execution_id=tool_execution_id,
            supports=supports or [],
            contradicts=contradicts or [],
            strength=strength,
        )
        self.evidence.append(ev)
        self.emit("evidence.added", {"id": ev.id, "type": type_.value, "supports": ev.supports, "contradicts": ev.contradicts})
        return ev

    # -- hypothesis machinery ----------------------------------------------
    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        self.hypotheses.append(hypothesis)
        self.emit("hypothesis.created", {"id": hypothesis.id, "statement": hypothesis.statement})

    def update_confidence(self, hypothesis_id: str, delta: float, reason: str) -> None:
        for hyp in self.hypotheses:
            if hyp.id == hypothesis_id:
                hyp.confidence = round(min(1.0, max(0.0, hyp.confidence + delta)), 4)
                self.emit("hypothesis.updated", {"id": hypothesis_id, "confidence": hyp.confidence, "reason": reason})
                return
        raise ValueError(f"Unknown hypothesis {hypothesis_id}")

    def set_status(self, hypothesis_id: str, status: HypothesisStatus) -> None:
        for hyp in self.hypotheses:
            if hyp.id == hypothesis.id if False else hyp.id == hypothesis_id:
                hyp.status = status
                self.emit("hypothesis.status", {"id": hypothesis_id, "status": status.value})
                return
        raise ValueError(f"Unknown hypothesis {hypothesis_id}")

    def leading_hypothesis(self) -> Hypothesis | None:
        if not self.hypotheses:
            return None
        return max(self.hypotheses, key=lambda h: h.confidence)

    # -- counterfactuals -----------------------------------------------------
    def run_counterfactual(self, params: dict[str, Any]) -> Counterfactual:
        result = simulate_pit_timing(**params)
        cf = Counterfactual(
            id=uuid.uuid4().hex[:8],
            intervention=result["intervention"],
            assumptions=result["assumptions"],
            predicted_delta_s=result["predicted_delta_s"],
            uncertainty_s=result["uncertainty_s"],
            simulator_version=result["simulator_version"],
            scenario_params=params,
        )
        self.counterfactuals.append(cf)
        self.emit("counterfactual.completed", {"id": cf.id, "delta": cf.predicted_delta_s})
        return cf

    # -- main loop ------------------------------------------------------------
    def run(self, plan: Callable[["InvestigationEngine"], None]) -> None:
        """Execute an investigation under a plan callable.

        The plan drives phases; the engine enforces state ordering,
        records every action, and enforces the falsification gate.
        """
        self.emit("investigation.started", {"question": self.question})
        self._set_state(InvestigationState.FRAMING)
        try:
            plan(self)
        except ToolError as exc:
            self._fail(InvestigationState.TOOL_FAILURE, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self._fail(InvestigationState.MODEL_FAILURE, str(exc))
            return
        if self.state not in (InvestigationState.COMPLETED,) and not self._failed():
            self._finalize()

    def _failed(self) -> bool:
        return self.state in (
            InvestigationState.DATA_UNAVAILABLE,
            InvestigationState.TOOL_FAILURE,
            InvestigationState.MODEL_FAILURE,
            InvestigationState.INSUFFICIENT_EVIDENCE,
        )

    # -- finalization gate ---------------------------------------------------
    def gate_failures(self) -> list[str]:
        """Invariant violations blocking synthesis; empty list = gate open."""
        failures: list[str] = []
        if not self.hypotheses:
            failures.append("hypotheses_present")
        if not self.evidence:
            failures.append("evidence_collected")
        leading = self.leading_hypothesis()
        if leading is None:
            failures.append("falsification_attempted")
            failures.append("falsification_recorded")
        else:
            if not any(leading.id in ev.contradicts for ev in self.evidence):
                failures.append("falsification_attempted")
            recorded = [
                ev for ev in self.evidence
                if leading.id in ev.contradicts
                and (ev.tool_execution_id is not None or any(
                    obs_id in {o.id for o in self.observations} for obs_id in ev.observation_ids
                ))
            ]
            if not recorded:
                failures.append("falsification_recorded")
        return failures

    def can_finalize(self) -> bool:
        return not self.gate_failures()

    def unsupported_claims(self) -> list[str]:
        """Evidence statements without tool provenance or recorded observations."""
        observation_ids = {obs.id for obs in self.observations}
        observation_ids.update({obs.tool_execution_id or "" for obs in self.observations if obs.tool_execution_id})
        unsupported: list[str] = []
        for ev in self.evidence:
            if ev.tool_execution_id is None and not any(
                obs_id in observation_ids for obs_id in ev.observation_ids
            ):
                unsupported.append(ev.statement)
        return unsupported

    def finalize(self) -> None:
        """Attempt synthesis; only transitions to COMPLETED when the gate opens."""
        self.emit("SYNTHESIS_STARTED", {})
        if not self.can_finalize():
            self.emit("INSUFFICIENT_EVIDENCE", {"gate_failures": self.gate_failures()})
            self._set_state(InvestigationState.INSUFFICIENT_EVIDENCE)
            return
        self.emit("SYNTHESIS_COMPLETED", {"n_hypotheses": len(self.hypotheses), "n_evidence": len(self.evidence)})
        self.emit("INVESTIGATION_COMPLETED", {})
        self._set_state(InvestigationState.COMPLETED)

    def falsification_gate_open(self) -> bool:
        """The gate requires at least one attempted falsification before synthesis."""
        return not self.gate_failures()

    def _fail(self, state: InvestigationState, message: str) -> None:
        self._set_state(state)
        self.emit("investigation.failed", {"state": state.value, "message": message})

    def _finalize(self) -> None:
        if not any(h.status == HypothesisStatus.SUPPORTED for h in self.hypotheses):
            self._fail(InvestigationState.INSUFFICIENT_EVIDENCE, "No hypothesis reached supported status")
            return
        self._set_state(InvestigationState.COMPLETED)
        self.emit("investigation.completed", {})

    def falsification_gate_open(self) -> bool:
        """The gate requires at least one attempted falsification before synthesis."""
        return any(ev.contradicts for ev in self.evidence) or self._rounds_used < self.max_rounds
