"""RACEWISE FastAPI application.

Serves the investigation API with SSE streaming for live agent traces.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from racewise.agent.provider import provider_from_env
from racewise.data.fastf1_adapter import FastF1Adapter
from racewise.domain.schemas import (
    Conclusion,
    EvidenceType,
    Hypothesis,
    HypothesisStatus,
    InvestigationState,
)
from racewise.investigation.engine import InvestigationEngine
from racewise.simulator.strategy import simulate_pit_timing
from racewise.tools.implementations import SessionContext, build_default_registry

app = FastAPI(title="RACEWISE", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_adapter = FastF1Adapter(cache_dir=os.environ.get("FASTF1_CACHE_DIR"))


@dataclass
class InvestigationRecord:
    engine: InvestigationEngine
    context: SessionContext
    year: int
    event: str
    driver: str


class CreateInvestigationRequest(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    year: int = 2023
    event: str = "Bahrain"
    driver: str = "VER"


class CounterfactualRequest(BaseModel):
    counterfactual_pit_lap: int
    pit_loss_s: float = 24.2
    degradation_s_per_lap: float = 0.06
    traffic_assumption_s_per_lap: float = 0.25


_INVESTIGATIONS: dict[str, InvestigationRecord] = {}


def _deterministic_plan(engine: InvestigationEngine, record: InvestigationRecord) -> None:
    """Rules-based investigation plan (deterministic fallback when no LLM configured).

    Clearly labeled non-AI: fixed evidence plan, explicit falsification step.
    """
    driver = record.driver
    engine._set_state(InvestigationState.HYPOTHESIS_GENERATION)
    engine.add_hypothesis(Hypothesis(id="H1", statement=f"{driver} lost pace due to tyre degradation", predicted_observables=["degradation slope materially > 0"], potential_falsifiers=["clean-air pace comparable to rivals on same tyre age"]))
    engine.add_hypothesis(Hypothesis(id="H2", statement=f"{driver} lost pace due to traffic", predicted_observables=["traffic fraction > 0.3 in affected window"], potential_falsifiers=["rival cars not within 1s"]))
    engine.add_hypothesis(Hypothesis(id="H3", statement=f"{driver} pace loss is normal race-state drift, not an anomaly", predicted_observables=["no anomalous laps detected"], potential_falsifiers=["anomalous laps exist"]))

    engine._set_state(InvestigationState.EVIDENCE_COLLECTION)
    deg_out = engine.run_tool("analyze_tyre_degradation", {"driver": driver, "stint": 2})
    if "error" in deg_out:
        raise RuntimeError(deg_out["error"])
    deg = deg_out
    obs_deg = engine.observe("deg_slope_s_per_lap", deg["slope_s_per_lap"], "s/lap", "analyze_tyre_degradation", "1.0.0", None)
    anomalies_out = engine.run_tool("detect_pace_anomaly", {"driver": driver, "lap_start": 16, "lap_end": 35})
    anomalies = anomalies_out.get("anomalies", [])
    obs_anom = engine.observe("n_anomalous_laps", len(anomalies), "laps", "detect_pace_anomaly", "1.0.0", None)
    traffic_out = engine.run_tool("analyze_traffic", {"driver": driver, "lap_start": 16, "lap_end": 36})
    traffic = traffic_out if "error" not in traffic_out else {"traffic_fraction": 0.0}
    obs_traffic = engine.observe("traffic_fraction", traffic["traffic_fraction"], "fraction", "analyze_traffic", "1.0.0", None)

    engine._set_state(InvestigationState.HYPOTHESIS_TESTING)
    if deg["slope_s_per_lap"] > 0.15 and deg["r_squared"] > 0.4:
        engine.add_evidence(f"Degradation slope {deg['slope_s_per_lap']} s/lap (r2={deg['r_squared']})", EvidenceType.CALCULATION, [obs_deg.id], None, supports=["H1"], strength=0.6)
        engine.update_confidence("H1", 0.4, "material degradation slope")
        engine.set_status("H1", HypothesisStatus.SUPPORTED)
    else:
        engine.add_evidence(f"Degradation slope {deg['slope_s_per_lap']} s/lap (r2={deg['r_squared']}) is immaterial", EvidenceType.CALCULATION, [obs_deg.id], None, contradicts=["H1"], strength=0.5)
        engine.update_confidence("H1", -0.25, "no material degradation")
        engine.set_status("H1", HypothesisStatus.WEAKENED)

    if anomalies:
        engine.add_evidence(f"{len(anomalies)} anomalous laps detected", EvidenceType.CALCULATION, [obs_anom.id], None, supports=["H2"], strength=0.3)
        engine.update_confidence("H2", 0.15, "anomalous laps present")
    else:
        engine.add_evidence("No anomalous laps in window; pace loss is gradual, not incident-driven", EvidenceType.CALCULATION, [obs_anom.id], None, supports=["H3"], strength=0.4)
        engine.update_confidence("H3", 0.2, "no anomalies")
        engine.set_status("H3", HypothesisStatus.SUPPORTED)

    if traffic["traffic_fraction"] > 0.3:
        engine.add_evidence(f"Traffic fraction {traffic['traffic_fraction']} in window", EvidenceType.CALCULATION, [obs_traffic.id], None, supports=["H2"], strength=0.5)
        engine.update_confidence("H2", 0.3, "significant traffic")
        engine.set_status("H2", HypothesisStatus.SUPPORTED)
    else:
        engine.add_evidence(f"Traffic fraction {traffic['traffic_fraction']} is low", EvidenceType.CALCULATION, [obs_traffic.id], None, contradicts=["H2"], strength=0.45)
        engine.update_confidence("H2", -0.25, "little traffic")
        engine.set_status("H2", HypothesisStatus.WEAKENED)

    # Falsification: attack the leading hypothesis with an alternative lens.
    engine._set_state(InvestigationState.FALSIFICATION)
    leading = engine.leading_hypothesis()
    if leading is not None:
        pits_out = engine.run_tool("analyze_pit_loss", {"driver": driver})
        if "error" not in pits_out:
            pit_loss = pits_out.get("mean_total_loss_s")
            if pit_loss is not None:
                obs_pit = engine.observe("mean_pit_loss_s", pit_loss, "s", "analyze_pit_loss", "1.0.0", None)
                if leading.id == "H1":
                    engine.add_evidence(f"Pit loss {pit_loss}s is unrelated to in-stint pace; if a rival strategy effect existed, pit deltas would correlate", EvidenceType.INFERENCE, [obs_pit.id], None, contradicts=["H1"], strength=0.2)
                    engine.update_confidence("H1", -0.05, "falsification pass found weak counter-evidence only")

    # Counterfactual: would pitting 5 laps earlier have changed the outcome?
    engine._set_state(InvestigationState.COUNTERFACTUAL_ANALYSIS)
    pits = engine.run_tool("get_pit_stops", {"driver": driver})
    stops = pits.get("stops", []) if "error" not in pits else []
    if stops:
        original_pit = stops[-1]["pit_in_lap"]
        cf_params = {
            "laps": record.context.laps,
            "driver": driver,
            "original_pit_lap": int(original_pit),
            "counterfactual_pit_lap": int(original_pit) - 5,
            "pit_loss_s": 24.2,
            "degradation_s_per_lap": 0.06,
            "laps_remaining": 57,
            "traffic_assumption_s_per_lap": 0.25,
        }
        engine.run_counterfactual(cf_params)

    engine._set_state(InvestigationState.SYNTHESIS)
    supported = [h for h in engine.hypotheses if h.status == HypothesisStatus.SUPPORTED]
    if supported:
        top = max(supported, key=lambda h: h.confidence)
        engine.conclusion = Conclusion(
            statement=f"Deterministic evidence most strongly supports: {top.statement} (confidence {top.confidence:.2f}). See evidence log for provenance.",
            confidence=top.confidence,
            evidence_ids=[ev.id for ev in engine.evidence],
            counterfactual_ids=[cf.id for cf in engine.counterfactuals],
            limitations=[
                "Deterministic rules-based plan (no LLM configured): tool selection is fixed, not adaptive.",
                "Linear degradation model; traffic estimate is approximate.",
            ],
        )
    engine._set_state(InvestigationState.VERIFICATION)
    engine._set_state(InvestigationState.COMPLETED)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "racewise", "version": "0.1.0", "model_provider": os.environ.get("MODEL_PROVIDER", "union_alpha"), "model_configured": provider_from_env() is not None}


@app.get("/api/sessions")
def list_sessions() -> dict[str, Any]:
    return {
        "sessions": [
            {"year": 2023, "event": "Bahrain", "session_type": "R", "label": "2023 Bahrain Grand Prix - Race"},
        ]
    }


@app.post("/api/investigations")
async def create_investigation(req: CreateInvestigationRequest) -> dict[str, Any]:
    context = SessionContext(_adapter, req.year, req.event)
    registry = build_default_registry(context)
    provider = provider_from_env()
    engine = InvestigationEngine(registry, provider, req.question)
    record = InvestigationRecord(engine, context, req.year, req.event, req.driver)
    _INVESTIGATIONS[engine.investigation_id] = record
    return {"investigation_id": engine.investigation_id, "state": engine.state.value}


def _run_in_background(record: InvestigationRecord) -> None:
    try:
        _deterministic_plan(record.engine, record)
    except Exception as exc:  # noqa: BLE001
        record.engine._fail(InvestigationState.TOOL_FAILURE, str(exc))


@app.get("/api/investigations/{inv_id}/stream")
async def stream_investigation(inv_id: str) -> StreamingResponse:
    if inv_id not in _INVESTIGATIONS:
        raise HTTPException(status_code=404, detail="Investigation not found")
    record = _INVESTIGATIONS[inv_id]

    async def event_stream():
        yield f"data: {json.dumps({'type': 'investigation.started', 'question': record.engine.question})}\n\n"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run_in_background, record)
        for entry in record.engine.event_log:
            yield f"data: {json.dumps({'type': entry.type, 'payload': entry.payload, 'timestamp': entry.timestamp.isoformat()})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/investigations/{inv_id}")
def get_investigation(inv_id: str) -> dict[str, Any]:
    if inv_id not in _INVESTIGATIONS:
        raise HTTPException(status_code=404, detail="Investigation not found")
    engine = _INVESTIGATIONS[inv_id].engine
    return {
        "investigation_id": engine.investigation_id,
        "question": engine.question,
        "state": engine.state.value,
        "hypotheses": [h.model_dump() for h in engine.hypotheses],
        "evidence": [ev.model_dump() for ev in engine.evidence],
        "observations": [o.model_dump() for o in engine.observations],
        "counterfactuals": [cf.model_dump() for cf in engine.counterfactuals],
        "conclusion": engine.conclusion.model_dump() if engine.conclusion else None,
        "tool_executions": [
            {
                "id": te.id,
                "tool": te.tool,
                "status": te.status,
                "duration_ms": te.duration_ms,
                "input_hash": te.input_hash,
                "output_hash": te.output_hash,
            }
            for te in engine.tool_executions
        ],
        "event_log": [e.model_dump() for e in engine.event_log],
    }


@app.post("/api/investigations/{inv_id}/counterfactual")
def run_counterfactual(inv_id: str, req: CounterfactualRequest) -> dict[str, Any]:
    if inv_id not in _INVESTIGATIONS:
        raise HTTPException(status_code=404, detail="Investigation not found")
    record = _INVESTIGATIONS[inv_id]
    stops_out = record.engine.run_tool("get_pit_stops", {"driver": record.driver})
    stops = stops_out.get("stops", []) if "error" not in stops_out else []
    if not stops:
        raise HTTPException(status_code=422, detail="No pit stops for driver")
    original_pit = int(stops[-1]["pit_in_lap"])
    cf = record.engine.run_counterfactual(
        {
            "laps": record.context.laps,
            "driver": record.driver,
            "original_pit_lap": original_pit,
            "counterfactual_pit_lap": req.counterfactual_pit_lap,
            "pit_loss_s": req.pit_loss_s,
            "degradation_s_per_lap": req.degradation_s_per_lap,
            "laps_remaining": 57,
            "traffic_assumption_s_per_lap": req.traffic_assumption_s_per_lap,
        }
    )
    return {"counterfactual": cf.model_dump(), "note": "COUNTERFACTUAL estimate under stated assumptions, not an observed result."}
