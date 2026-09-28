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
from racewise.persistence import get_store
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
_store = get_store()


def _init_session_catalog() -> None:
    """Initialize session catalog with known 2023 sessions if empty."""
    existing = _store.list_sessions()
    if existing:
        return

    known_sessions = [
        {"year": 2023, "round": 1, "event": "Bahrain", "session_type": "R"},
        {"year": 2023, "round": 2, "event": "Saudi Arabia", "session_type": "R"},
        {"year": 2023, "round": 3, "event": "Australia", "session_type": "R"},
    ]
    for s in known_sessions:
        session_key = f"{s['year']}-{s['event'].replace(' ', '')}-{s['session_type']}"
        _store.upsert_session(
            session_key=session_key,
            year=s["year"],
            round_num=s["round"],
            event=s["event"],
            session_type=s["session_type"],
            data_source="fastf1",
            availability="AVAILABLE",
        )


_init_session_catalog()


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
    session_type: str = "R"


class CounterfactualRequest(BaseModel):
    counterfactual_pit_lap: int
    pit_loss_s: float = 24.2
    degradation_s_per_lap: float = 0.06
    traffic_assumption_s_per_lap: float = 0.25


_INVESTIGATIONS: dict[str, InvestigationRecord] = {}


def _persist_engine_state(engine: InvestigationEngine, record: InvestigationRecord) -> None:
    """Persist the full engine state to the store."""
    inv_id = engine.investigation_id
    _store.update_investigation_state(inv_id, engine.state)

    for h in engine.hypotheses:
        _store.save_hypothesis(inv_id, h)

    for o in engine.observations:
        _store.save_observation(inv_id, o)

    for e in engine.evidence:
        _store.save_evidence(inv_id, e)

    for te in engine.tool_executions:
        _store.save_tool_execution(inv_id, te)

    for cf in engine.counterfactuals:
        _store.save_counterfactual(inv_id, cf)

    if engine.conclusion:
        cid = _store.save_conclusion(inv_id, engine.conclusion)
        _store.set_investigation_conclusion(inv_id, cid)

    for event in engine.event_log:
        _store.save_event(event)


def _load_engine_state(engine: InvestigationEngine, inv_id: str) -> None:
    """Load engine state from the store."""
    engine.hypotheses = _store.get_hypotheses(inv_id)
    engine.observations = _store.get_observations(inv_id)
    engine.evidence = _store.get_evidence(inv_id)
    engine.tool_executions = _store.get_tool_executions(inv_id)
    engine.counterfactuals = _store.get_counterfactuals(inv_id)
    engine.conclusion = _store.get_conclusion(inv_id)
    engine.event_log = _store.get_event_log(inv_id)


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
    _persist_engine_state(engine, record)


def _run_in_background(record: InvestigationRecord) -> None:
    try:
        _deterministic_plan(record.engine, record)
    except Exception as exc:  # noqa: BLE001
        record.engine._fail(InvestigationState.TOOL_FAILURE, str(exc))
        _persist_engine_state(record.engine, record)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "racewise", "version": "0.1.0", "model_provider": os.environ.get("MODEL_PROVIDER", "union_alpha"), "model_configured": provider_from_env() is not None}


@app.get("/api/catalog/sessions")
def catalog_sessions(
    season: Optional[int] = None,
    season_from: Optional[int] = None,
    season_to: Optional[int] = None,
    country: Optional[str] = None,
    circuit: Optional[str] = None,
    session_type: Optional[str] = None,
    provider: Optional[str] = None,
    availability: Optional[str] = None,
    capability: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """Catalog Explorer: filtered, paginated session catalog (data-derived)."""
    from racewise.data.historical.catalog_api import get_catalog_api

    try:
        return get_catalog_api().list_sessions(
            season=season,
            season_from=season_from,
            season_to=season_to,
            country=country,
            circuit=circuit,
            session_type=session_type,
            provider=provider,
            availability=availability,
            capability=capability,
            search=search,
            page=page,
            page_size=page_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/catalog/sessions/{season}/{round}/{session_type}")
def catalog_session_detail(season: int, round: int, session_type: str) -> dict[str, Any]:
    """Catalog Explorer: full session detail (identity, providers, capabilities)."""
    from racewise.data.historical.catalog_api import get_catalog_api

    detail = get_catalog_api().session_detail(season, round, session_type)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    return detail


@app.get("/api/catalog/telemetry-comparison/{season}/{round}")
def catalog_telemetry_comparison(
    season: int, round: int,
    driver_a: str = "max-verstappen",
    driver_b: str = "sergio-perez",
    lap: Optional[int] = None,
) -> dict[str, Any]:
    """Bounded deterministic telemetry comparison for the frontend view.

    Delegates entirely to compare_telemetry_lap (signal whitelist, sample
    caps). Returns INSUFFICIENT_EVIDENCE when the session/lap has no
    telemetry - the UI must render that state, never a synthetic series.
    """
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.telemetry_analysis import compare_telemetry_lap

    api = get_catalog_api()
    detail = api.session_detail(season, round, "RACE")
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    if not detail["capabilities"].get("telemetry", {}).get("available"):
        return {
            "season": season, "round": round,
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": "no canonical telemetry ingested for this session (bounded Phase 6C policy)",
        }
    from racewise.data.historical.canonical_queries import get_canonical_queries

    if lap is None:
        summary = get_canonical_queries().telemetry_summary(season, round, "RACE")
        if not summary["available"]:
            return {
                "season": season, "round": round,
                "verdict": "INSUFFICIENT_EVIDENCE", "reason": "no telemetry rows",
            }
        lap = max(summary["laps"])
    return compare_telemetry_lap(
        get_canonical_queries(), season, round, driver_a, driver_b,
        lap_number=int(lap), session_type="RACE",
    )


@app.get("/api/catalog/attribution/{season}/{round}")
def catalog_attribution(
    season: int, round: int,
    driver_a: str = "max-verstappen",
    driver_b: str = "sergio-perez",
    lap: Optional[int] = None,
) -> dict[str, Any]:
    """Deterministic loss attribution for the frontend view (bounded).

    Delegates to attribute_lap_loss (measured delta -> sector/region
    decomposition + residual + falsification). Lap defaults to the highest
    shared telemetry lap with a valid comparison - never a fabricated one.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.loss_attribution import attribute_lap_loss

    api = get_catalog_api()
    detail = api.session_detail(season, round, "RACE")
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    if not detail["capabilities"].get("telemetry", {}).get("available"):
        return {
            "season": season, "round": round,
            "status": "UNAVAILABLE",
            "reason": "no canonical telemetry ingested for this session (bounded policy)",
        }
    queries = get_canonical_queries()
    if lap is None:
        from racewise.data.historical.loss_attribution import (
            VALID,
            VALID_CAVEATS,
        )

        summary = queries.telemetry_summary(season, round, "RACE")
        if not summary["available"]:
            return {"season": season, "round": round, "status": "UNAVAILABLE",
                    "reason": "no telemetry rows"}
        for candidate in sorted(summary["laps"], reverse=True):
            att = attribute_lap_loss(queries, season, round, driver_a, driver_b, candidate)
            if att.get("status") in (VALID, VALID_CAVEATS):
                return att
        return {
            "season": season, "round": round,
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "no telemetry lap yields a clean two-driver comparison",
        }
    return attribute_lap_loss(queries, season, round, driver_a, driver_b, int(lap))


@app.get("/api/catalog/evidence-fusion/{season}/{round}")
def catalog_evidence_fusion(
    season: int, round: int,
    driver_a: str = "max-verstappen",
    driver_b: str = "sergio-perez",
    lap: Optional[int] = None,
) -> dict[str, Any]:
    """Deterministic multi-source evidence fusion for the frontend view (bounded).

    Delegates to fuse_lap_evidence: measured observation -> independent
    evidence items -> formal hypothesis verdicts -> preserved residual ->
    evidence-bounded conclusion. Lap defaults to the highest shared telemetry
    lap that yields a valid comparison - never a fabricated one.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.evidence_fusion import fuse_lap_evidence
    from racewise.data.historical.loss_attribution import (
        VALID,
        VALID_CAVEATS,
    )

    api = get_catalog_api()
    detail = api.session_detail(season, round, "RACE")
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    if not detail["capabilities"].get("telemetry", {}).get("available"):
        return {
            "season": season, "round": round,
            "status": "UNAVAILABLE",
            "reason": "no canonical telemetry ingested for this session (bounded policy)",
        }
    queries = get_canonical_queries()
    if lap is None:
        summary = queries.telemetry_summary(season, round, "RACE")
        if not summary["available"]:
            return {"season": season, "round": round, "status": "UNAVAILABLE",
                    "reason": "no telemetry rows"}
        for candidate in sorted(summary["laps"], reverse=True):
            fused = fuse_lap_evidence(queries, season, round, driver_a, driver_b, candidate)
            if fused.get("status") in (VALID, VALID_CAVEATS):
                return fused
        return {
            "season": season, "round": round,
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "no telemetry lap yields a clean two-driver comparison",
        }
    return fuse_lap_evidence(queries, season, round, driver_a, driver_b, int(lap))


@app.get("/api/catalog/stint-evidence/{season}/{round}")
def catalog_stint_evidence(
    season: int, round: int,
    driver_a: str = "",
    driver_b: str = "",
    stint: Optional[int] = None,
) -> dict[str, Any]:
    """Deterministic stint-level evidence fusion for the frontend view (bounded).

    Drivers default to the session's canonical telemetry pair (Phase 6D
    policy). Stint defaults to the canonical stint with the most telemetry-
    covered common clean laps - never a fabricated one.
    """
    import logging

    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.stint_evidence import (
        _select_common_laps,
        fuse_stint_evidence,
    )

    api = get_catalog_api()
    detail = api.session_detail(season, round, "RACE")
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    if not detail["capabilities"].get("telemetry", {}).get("available"):
        return {
            "season": season, "round": round,
            "status": "UNAVAILABLE",
            "reason": "no canonical telemetry ingested for this session (bounded policy)",
        }
    queries = get_canonical_queries()
    if not driver_a or not driver_b:
        pair = queries.get_telemetry_driver_pair(season, round, "RACE")
        if pair is None:
            return {"season": season, "round": round, "status": "UNAVAILABLE",
                    "reason": "no telemetry driver pair"}
        driver_a, driver_b = pair
    if stint is not None:
        return fuse_stint_evidence(queries, season, round, driver_a, driver_b, int(stint))
    # default stint: most telemetry-covered common clean laps (deterministic)
    stints = queries.get_stints(season, round, "RACE", driver_a)
    best: tuple[int, int] | None = None  # (count, stint_number)
    for s in stints:
        try:
            selected, _excluded, _sa, _sb = _select_common_laps(
                queries, season, round, "RACE", driver_a, driver_b,
                int(s["stint_number"]), 10)
        except Exception:  # noqa: BLE001 - selection must not break the default
            logging.getLogger("racewise").debug("stint selection failed", exc_info=True)
            continue
        if best is None or len(selected) > best[0]:
            best = (len(selected), int(s["stint_number"]))
    if best is None or best[0] < 2:
        return {"season": season, "round": round, "status": "INSUFFICIENT_EVIDENCE",
                "reason": "no canonical stint with >= 2 telemetry-covered common clean laps"}
    return fuse_stint_evidence(queries, season, round, driver_a, driver_b, best[1])


@app.get("/api/catalog/counterfactual/{season}/{round}")
def catalog_counterfactual(
    season: int, round: int,
    driver: str = "",
    reference_driver: str = "",
    lap: Optional[int] = None,
    fraction: float = 0.5,
) -> dict[str, Any]:
    """Validated telemetry counterfactual for the frontend view (bounded).

    Deterministic REMOVE_DEFICIT speed intervention against the session's
    canonical telemetry pair. Lap defaults to the first telemetry lap with a
    VALID counterfactual result - never a fabricated one. All validation,
    transformation and simulation happen server-side; the frontend renders.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.counterfactual import (
        MAX_FRACTION_ABS,
        VALID,
        simulate_telemetry_counterfactual,
    )

    if not 0.0 <= abs(fraction) <= MAX_FRACTION_ABS or fraction != fraction:
        raise HTTPException(status_code=422, detail="fraction out of bounds")
    api = get_catalog_api()
    detail = api.session_detail(season, round, "RACE")
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    if not detail["capabilities"].get("telemetry", {}).get("available"):
        return {
            "season": season, "round": round,
            "status": "UNAVAILABLE",
            "reason": "no canonical telemetry ingested for this session (bounded policy)",
        }
    queries = get_canonical_queries()
    if not driver or not reference_driver:
        pair = queries.get_telemetry_driver_pair(season, round, "RACE")
        if pair is None:
            return {"season": season, "round": round, "status": "UNAVAILABLE",
                    "reason": "no telemetry driver pair"}
        driver = driver or pair[1]        # target: the pair's second driver
        reference_driver = reference_driver or pair[0]
    if lap is not None:
        return simulate_telemetry_counterfactual(
            queries, season, round, driver, int(lap), "speed",
            "REMOVE_DEFICIT", float(fraction), reference_driver=reference_driver)
    summary = queries.telemetry_summary(season, round, "RACE")
    if not summary["available"]:
        return {"season": season, "round": round, "status": "UNAVAILABLE",
                "reason": "no telemetry rows"}
    for candidate in summary["laps"]:  # chronological; first VALID wins
        res = simulate_telemetry_counterfactual(
            queries, season, round, driver, int(candidate), "speed",
            "REMOVE_DEFICIT", float(fraction), reference_driver=reference_driver)
        if res.get("status") == VALID:
            return res
    return {"season": season, "round": round, "status": "INSUFFICIENT_EVIDENCE",
            "reason": "no telemetry lap yields a VALID counterfactual"}


@app.get("/api/catalog/performance-envelope/{season}/{round}")
def catalog_performance_envelope(
    season: int, round: int,
    driver: str = "",
    reference_driver: str = "",
    scenario_type: str = "DEFICIT_REDUCTION",
    parameter: Optional[float] = None,
    stint: Optional[int] = None,
) -> dict[str, Any]:
    """Measured performance envelope + bounded scenario sweep (bounded).

    Drivers default to the session's canonical telemetry pair. The anchor lap
    defaults to the first clean telemetry-covered lap - never fabricated.
    All extraction, envelope construction, simulation and sensitivity happen
    server-side; the frontend renders only.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.performance_envelope import (
        SCENARIO_TYPES,
        analyze_performance_envelope,
    )

    if scenario_type not in SCENARIO_TYPES:
        raise HTTPException(status_code=422, detail="unknown scenario_type")
    if parameter is not None and (parameter != parameter or abs(parameter) > 1.0):
        raise HTTPException(status_code=422, detail="parameter out of bounds")
    api = get_catalog_api()
    detail = api.session_detail(season, round, "RACE")
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    if not detail["capabilities"].get("telemetry", {}).get("available"):
        return {
            "season": season, "round": round,
            "status": "UNAVAILABLE",
            "reason": "no canonical telemetry ingested for this session (bounded policy)",
        }
    queries = get_canonical_queries()
    if not driver or (not reference_driver and (scenario_type in ("DEFICIT_REDUCTION", "REFERENCE_BLEND") or stint is not None)):
        pair = queries.get_telemetry_driver_pair(season, round, "RACE")
        if pair is None:
            return {"season": season, "round": round, "status": "UNAVAILABLE",
                    "reason": "no telemetry driver pair"}
        driver = driver or pair[1]
        if not reference_driver:
            reference_driver = pair[0]
    return analyze_performance_envelope(
        queries, season, round, driver,
        scenario_type=scenario_type,
        parameter=parameter,
        reference_driver=reference_driver or None,
        session_type="RACE",
        stint_number=stint,
    )


@app.get("/api/catalog/race-gap/{season}/{round}")
def catalog_race_gap(
    season: int, round: int,
    driver_a: str = "",
    driver_b: str = "",
) -> dict[str, Any]:
    """Deterministic race-level gap decomposition for the frontend view (bounded).

    Drivers default to the session's canonical telemetry pair (Phase 6D
    policy). Read-only, bounded, server-computed.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.race_gap import decompose_race_gap

    api = get_catalog_api()
    detail = api.session_detail(season, round, "RACE")
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    if not detail["capabilities"].get("telemetry", {}).get("available"):
        return {
            "season": season, "round": round,
            "status": "UNAVAILABLE",
            "reason": "no canonical telemetry ingested for this session (bounded policy)",
        }
    queries = get_canonical_queries()
    if not driver_a or not driver_b:
        pair = queries.get_telemetry_driver_pair(season, round, "RACE")
        if pair is None:
            return {"season": season, "round": round, "status": "UNAVAILABLE",
                    "reason": "no telemetry driver pair"}
        driver_a, driver_b = pair
    return decompose_race_gap(queries, season, round, driver_a, driver_b)


@app.get("/api/catalog/performance-regimes/{season}/{round}")
def catalog_performance_regimes(
    season: int, round: int,
    driver_a: str = "",
    driver_b: str = "",
    max_regimes: int = 8,
    start_lap: Optional[int] = None,
    end_lap: Optional[int] = None,
) -> dict[str, Any]:
    """Performance regime & change-point analysis for the frontend view (bounded).

    Drivers default to the session's canonical telemetry pair (Phase 6D
    policy). Segmentation, context alignment, evidence fusion and sensitivity
    all happen server-side; the frontend renders only. Regime transitions are
    temporal associations - never causal claims.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.performance_regimes import analyze_performance_regimes

    if not 2 <= int(max_regimes) <= 12:
        raise HTTPException(status_code=422, detail="max_regimes out of bounds [2, 12]")
    if start_lap is not None and start_lap < 1:
        raise HTTPException(status_code=422, detail="start_lap must be >= 1")
    if end_lap is not None and end_lap < 1:
        raise HTTPException(status_code=422, detail="end_lap must be >= 1")
    if start_lap is not None and end_lap is not None and start_lap > end_lap:
        raise HTTPException(status_code=422, detail="start_lap must be <= end_lap")
    api = get_catalog_api()
    detail = api.session_detail(season, round, "RACE")
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found in canonical catalog")
    if not detail["capabilities"].get("telemetry", {}).get("available"):
        return {
            "season": season, "round": round,
            "status": "UNAVAILABLE",
            "reason": "no canonical telemetry ingested for this session (bounded policy)",
        }
    queries = get_canonical_queries()
    if not driver_a or not driver_b:
        pair = queries.get_telemetry_driver_pair(season, round, "RACE")
        if pair is None:
            return {"season": season, "round": round, "status": "UNAVAILABLE",
                    "reason": "no telemetry driver pair"}
        driver_a, driver_b = pair
    if driver_a == driver_b:
        raise HTTPException(status_code=422, detail="driver_a and driver_b must be distinct")
    return analyze_performance_regimes(
        queries, season, round, driver_a, driver_b,
        max_regimes=int(max_regimes),
        start_lap=start_lap, end_lap=end_lap,
    )


@app.get("/api/catalog/performance-patterns")
def catalog_performance_patterns(
    driver_a: str = "",
    driver_b: str = "",
    seasons: str = "",
    max_races: int = 6,
    max_patterns: int = 20,
) -> dict[str, Any]:
    """Cross-race recurring performance patterns for the frontend view (bounded).

    Query-style endpoint (cross-race scope does not fit the per-session
    {season}/{round} path). seasons is a comma-separated season list, e.g.
    '2022,2023'. Drivers default to the most recent telemetry season's
    canonical pair (Phase 6D policy). All segmentation, matching, recurrence
    and evidence aggregation happen server-side; the frontend renders only.
    A recurring pattern is NOT a cause; no rankings, no confidence scores.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.catalog_api import get_catalog_api
    from racewise.data.historical.performance_patterns import (
        MAX_PATTERNS, MAX_RACES, analyze_cross_race_performance_patterns,
    )

    if not 1 <= int(max_races) <= MAX_RACES:
        raise HTTPException(status_code=422,
                            detail=f"max_races out of bounds [1, {MAX_RACES}]")
    if not 1 <= int(max_patterns) <= MAX_PATTERNS:
        raise HTTPException(status_code=422,
                            detail=f"max_patterns out of bounds [1, {MAX_PATTERNS}]")
    season_list: Optional[list[int]] = None
    if seasons.strip():
        try:
            season_list = [int(s) for s in seasons.split(",") if s.strip()]
        except ValueError:
            raise HTTPException(status_code=422,
                                detail="seasons must be comma-separated integers")
        if not season_list:
            raise HTTPException(status_code=422, detail="seasons list is empty")
    queries = get_canonical_queries()
    if not driver_a or not driver_b:
        # default pair: canonical telemetry pair of the newest season in the
        # corpus scope (deterministic, Phase 6D policy extended cross-race)
        season_for_pair = (max(season_list) if season_list
                           else max((int(x["season"]) for x in
                                     get_catalog_api().list_sessions(
                                         session_type="RACE",
                                         capability="telemetry",
                                         page_size=200)["sessions"]),
                                    default=None))
        if season_for_pair is None:
            return {"status": "UNAVAILABLE",
                    "reason": "no telemetry-capable race sessions in the catalog"}
        first = min((x["round"] for x in
                     get_catalog_api().list_sessions(
                         season=season_for_pair, session_type="RACE",
                         capability="telemetry", page_size=200)["sessions"]),
                    default=None)
        if first is None:
            return {"status": "UNAVAILABLE",
                    "reason": f"no telemetry-capable race sessions in {season_for_pair}"}
        pair = queries.get_telemetry_driver_pair(season_for_pair, first, "RACE")
        if pair is None:
            return {"status": "UNAVAILABLE", "reason": "no telemetry driver pair"}
        driver_a, driver_b = pair
    if driver_a == driver_b:
        raise HTTPException(status_code=422,
                            detail="driver_a and driver_b must be distinct")
    return analyze_cross_race_performance_patterns(
        queries, driver_a, driver_b,
        seasons=season_list,
        max_races=int(max_races),
        max_patterns=int(max_patterns),
    )


@app.get("/api/catalog/performance-pattern-evidence")
def catalog_performance_pattern_evidence(
    driver_a: str = "",
    driver_b: str = "",
    pattern_id: str = "",
    seasons: str = "",
    max_occurrences: int = 8,
    max_races: int = 8,
) -> dict[str, Any]:
    """Cross-race evidence investigation of one recurring pattern (bounded).

    Query-style endpoint (6L convention: cross-race scope does not fit the
    per-session path). pattern_id is required and must be one of the
    recurring pattern ids from /api/catalog/performance-patterns browsed at
    the same max_races (6L pattern ids are corpus-scope-dependent). The six
    hypotheses are always reported independently and are never ranked;
    contradictions are preserved; residuals are never assigned; model
    sensitivity stays a model property. Evidence aggregation happens
    server-side; the frontend renders only.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.performance_evidence import (
        MAX_OCCURRENCES, analyze_cross_race_pattern_evidence,
    )
    from racewise.data.historical.performance_patterns import MAX_RACES

    if not pattern_id.strip():
        raise HTTPException(status_code=422, detail="pattern_id is required")
    if not 1 <= int(max_occurrences) <= MAX_OCCURRENCES:
        raise HTTPException(status_code=422,
                            detail=(f"max_occurrences out of bounds "
                                    f"[1, {MAX_OCCURRENCES}]"))
    if not 1 <= int(max_races) <= MAX_RACES:
        raise HTTPException(status_code=422,
                            detail=f"max_races out of bounds [1, {MAX_RACES}]")
    season_list: Optional[list[int]] = None
    if seasons.strip():
        try:
            season_list = [int(s) for s in seasons.split(",") if s.strip()]
        except ValueError:
            raise HTTPException(status_code=422,
                                detail="seasons must be comma-separated integers")
        if not season_list:
            raise HTTPException(status_code=422, detail="seasons list is empty")
    queries = get_canonical_queries()
    if not driver_a or not driver_b:
        # default pair: canonical telemetry pair of the newest season in the
        # corpus scope (same Phase 6D-derived policy as /performance-patterns)
        from racewise.data.historical.catalog_api import get_catalog_api
        season_for_pair = (max(season_list) if season_list
                           else max((int(x["season"]) for x in
                                     get_catalog_api().list_sessions(
                                         session_type="RACE",
                                         capability="telemetry",
                                         page_size=200)["sessions"]),
                                    default=None))
        if season_for_pair is None:
            return {"status": "UNAVAILABLE",
                    "reason": "no telemetry-capable race sessions in the catalog"}
        first = min((x["round"] for x in
                     get_catalog_api().list_sessions(
                         season=season_for_pair, session_type="RACE",
                         capability="telemetry", page_size=200)["sessions"]),
                    default=None)
        if first is None:
            return {"status": "UNAVAILABLE",
                    "reason": f"no telemetry-capable race sessions in {season_for_pair}"}
        pair = queries.get_telemetry_driver_pair(season_for_pair, first, "RACE")
        if pair is None:
            return {"status": "UNAVAILABLE", "reason": "no telemetry driver pair"}
        driver_a, driver_b = pair
    if driver_a == driver_b:
        raise HTTPException(status_code=422,
                            detail="driver_a and driver_b must be distinct")
    return analyze_cross_race_pattern_evidence(
        queries, driver_a, driver_b,
        pattern_id=pattern_id,
        seasons=season_list,
        max_occurrences=int(max_occurrences),
        max_races=int(max_races),
    )


@app.get("/api/catalog/engineering-investigation")
def catalog_engineering_investigation(
    question_type: str = "",
    driver_a: str = "",
    driver_b: str = "",
    season: int = 0,
    round: int = 0,
    lap_number: int = 0,
    stint_number: int = 0,
    session_type: str = "RACE",
    pattern_id: str = "",
    hypotheses: str = "",
    max_evidence_items: int = 40,
    max_counterfactuals: int = 2,
) -> dict[str, Any]:
    """Deterministic Phase 6N engineering investigation over the 6E-6M chain.

    Query-style endpoint (6L/6M convention). The legacy LLM-driven
    investigation flow stays untouched at POST /api/investigations; this
    endpoint is the deterministic orchestration layer and shares no state
    with it. question_type must be one of the closed 6N vocabulary; drivers
    default to the canonical telemetry pair (Phase 6D policy) when omitted.
    Every synthesis statement carries a decision trace to evidence IDs;
    hypotheses are never ranked; counterfactuals are MODELLED sensitivity,
    executed only when Phase 6I-eligible. All orchestration happens
    server-side; the frontend renders only.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.investigation_synthesis import (
        HYPOTHESIS_IDS, MAX_COUNTERFACTUALS, MAX_EVIDENCE_ITEMS,
        QUESTION_TYPES, run_engineering_investigation,
    )

    if question_type not in QUESTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"question_type must be one of {list(QUESTION_TYPES)}")
    if not 1950 <= int(season) <= 2100:
        raise HTTPException(status_code=422,
                            detail="season out of bounds [1950, 2100]")
    if not 1 <= int(round) <= 99:
        raise HTTPException(status_code=422,
                            detail="round out of bounds [1, 99]")
    if not 1 <= int(max_evidence_items) <= MAX_EVIDENCE_ITEMS:
        raise HTTPException(status_code=422,
                            detail=(f"max_evidence_items out of bounds "
                                    f"[1, {MAX_EVIDENCE_ITEMS}]"))
    if not 0 <= int(max_counterfactuals) <= MAX_COUNTERFACTUALS:
        raise HTTPException(status_code=422,
                            detail=(f"max_counterfactuals out of bounds "
                                    f"[0, {MAX_COUNTERFACTUALS}]"))
    if session_type not in ("RACE", "QUALIFYING"):
        # Phase 6S GAP 2: qualifying is investigable (single-lap
        # comparability semantics); anything else stays closed-vocabulary
        raise HTTPException(
            status_code=422,
            detail="session_type must be one of ['RACE', 'QUALIFYING']")
    if session_type == "QUALIFYING" and stint_number:
        raise HTTPException(
            status_code=422,
            detail=("STINT numbers have no qualifying comparability "
                    "semantics: a qualifying session is a sequence of "
                    "independent single-lap comparisons, not race stints"))
    hyp_list: Optional[list[str]] = None
    if hypotheses.strip():
        hyp_list = [h.strip() for h in hypotheses.split(",") if h.strip()]
        unknown = [h for h in hyp_list if h not in HYPOTHESIS_IDS]
        if unknown:
            raise HTTPException(status_code=422,
                                detail=f"unknown hypothesis ids: {unknown}")
        if not hyp_list:
            hyp_list = None
    queries = get_canonical_queries()
    if not driver_a or not driver_b:
        if session_type != "RACE":
            # default-pair policy derives from canonical telemetry coverage,
            # which exists for race sessions only; do not silently reuse a
            # race pair for a different session type
            raise HTTPException(
                status_code=422,
                detail=("driver_a and driver_b are required for "
                        f"session_type={session_type}"))
        # default pair: canonical telemetry pair of the requested season's
        # first telemetry-capable round (same Phase 6D-derived policy as the
        # other /catalog endpoints)
        first = min((x["round"] for x in
                     get_catalog_api().list_sessions(
                         season=int(season), session_type="RACE",
                         capability="telemetry", page_size=200)["sessions"]),
                    default=None)
        if first is None:
            return {"status": "UNAVAILABLE",
                    "reason": f"no telemetry-capable race sessions in {season}"}
        pair = queries.get_telemetry_driver_pair(int(season), first, "RACE")
        if pair is None:
            return {"status": "UNAVAILABLE", "reason": "no telemetry driver pair"}
        driver_a, driver_b = pair
    if driver_a == driver_b:
        raise HTTPException(status_code=422,
                            detail="driver_a and driver_b must be distinct")
    return run_engineering_investigation(
        queries,
        question_type=question_type,
        driver_a=driver_a,
        driver_b=driver_b,
        season=int(season),
        round_num=int(round),
        lap_number=int(lap_number) if lap_number else None,
        stint_number=int(stint_number) if stint_number else None,
        session_type=session_type,
        pattern_id=pattern_id if pattern_id.strip() else None,
        hypotheses=hyp_list,
        max_evidence_items=int(max_evidence_items),
        max_counterfactuals=int(max_counterfactuals),
    )


def _investigation_input_from_params(
    prefix: str,
    question_type: str,
    driver_a: str,
    driver_b: str,
    season: int,
    round_num: int,
    lap_number: int,
    stint_number: int,
    pattern_id: str,
    hypotheses: str,
    session_type: str = "RACE",
) -> dict[str, Any]:
    """Shared query-param parsing + validation for 6O/6P/6S endpoints that
    take a structured 6N investigation input (``prefix`` is 'a', 'b' or
    ''). ``session_type`` must already be closed-vocabulary-validated by the
    caller; RACE remains the default for every existing route."""
    from racewise.data.historical.investigation_synthesis import (
        HYPOTHESIS_IDS, QUESTION_TYPES,
    )

    p = f"{prefix}_"
    if question_type not in QUESTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"{p}question_type must be one of {list(QUESTION_TYPES)}")
    if not 1950 <= int(season) <= 2100:
        raise HTTPException(status_code=422,
                            detail=f"{p}season out of bounds [1950, 2100]")
    if not 1 <= int(round_num) <= 99:
        raise HTTPException(status_code=422,
                            detail=f"{p}round out of bounds [1, 99]")
    hyp_list: Optional[list[str]] = None
    if hypotheses.strip():
        hyp_list = [h.strip() for h in hypotheses.split(",") if h.strip()]
        unknown = [h for h in hyp_list if h not in HYPOTHESIS_IDS]
        if unknown:
            raise HTTPException(status_code=422,
                                detail=f"{p}unknown hypothesis ids: {unknown}")
        if not hyp_list:
            hyp_list = None
    return {
        "question_type": question_type,
        "driver_a": driver_a,
        "driver_b": driver_b,
        "season": int(season),
        "round_num": int(round_num),
        "lap_number": int(lap_number) if lap_number else None,
        "stint_number": int(stint_number) if stint_number else None,
        "session_type": session_type,
        "pattern_id": pattern_id if pattern_id.strip() else None,
        "hypotheses": hyp_list,
    }


@app.get("/api/catalog/engineering-investigation/replay")
def catalog_engineering_investigation_replay(
    question_type: str = "",
    driver_a: str = "",
    driver_b: str = "",
    season: int = 0,
    round: int = 0,
    lap_number: int = 0,
    stint_number: int = 0,
    pattern_id: str = "",
    hypotheses: str = "",
    session_type: str = "RACE",
) -> dict[str, Any]:
    """Phase 6O: deterministic replay of an engineering investigation.

    Rebuilds the snapshot from the structured input, reruns the exact 6N
    engine and reports IDENTICAL or the exact structured differences.
    Snapshots are data, never executed; nothing is persisted (zero storage
    growth). No ranking, no scores.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.investigation_memory import (
        build_investigation_snapshot, replay_engineering_investigation,
    )
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    spec = _investigation_input_from_params(
        "", question_type, driver_a, driver_b, season, round, lap_number,
        stint_number, pattern_id, hypotheses, session_type)
    queries = get_canonical_queries()
    inv = run_engineering_investigation(queries, **spec)
    if inv.get("status") == "INVALID":
        raise HTTPException(status_code=422,
                            detail=f"invalid investigation input: {inv.get('reason')}")
    if inv.get("status") != "VALID":
        return {"status": inv.get("status"), "reason": inv.get("reason")}
    snapshot = build_investigation_snapshot(inv)
    replay = replay_engineering_investigation(queries, snapshot)
    replay["snapshot"] = {
        "snapshot_hash": snapshot["snapshot_hash"],
        "investigation_id": snapshot.get("investigation_id"),
        "output_hash": snapshot.get("output_hash"),
    }
    return replay


@app.get("/api/catalog/engineering-investigation/compare")
def catalog_engineering_investigation_compare(
    a_question_type: str = "",
    a_driver_a: str = "",
    a_driver_b: str = "",
    a_season: int = 0,
    a_round: int = 0,
    a_lap_number: int = 0,
    a_stint_number: int = 0,
    a_pattern_id: str = "",
    a_hypotheses: str = "",
    a_session_type: str = "RACE",
    b_question_type: str = "",
    b_driver_a: str = "",
    b_driver_b: str = "",
    b_season: int = 0,
    b_round: int = 0,
    b_lap_number: int = 0,
    b_stint_number: int = 0,
    b_pattern_id: str = "",
    b_hypotheses: str = "",
    b_session_type: str = "RACE",
) -> dict[str, Any]:
    """Phase 6O: dimension-wise comparison of two 6N investigations.

    Descriptive deltas only: scope compatibility, evidence deltas,
    hypothesis state deltas, falsification deltas (vanished evidence stays
    evidence loss, never resolution), counterfactual deltas, synthesis
    transitions and decision-trace deltas. No score, no ranking.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.investigation_memory import (
        compare_engineering_investigations,
    )
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    queries = get_canonical_queries()
    sides: list[dict[str, Any]] = []
    for prefix, args in (("a", (a_question_type, a_driver_a, a_driver_b,
                               a_season, a_round, a_lap_number,
                               a_stint_number, a_pattern_id, a_hypotheses,
                               a_session_type)),
                         ("b", (b_question_type, b_driver_a, b_driver_b,
                                b_season, b_round, b_lap_number,
                                b_stint_number, b_pattern_id,
                                b_hypotheses, b_session_type))):
        spec = _investigation_input_from_params(prefix, *args)
        inv = run_engineering_investigation(queries, **spec)
        if inv.get("status") == "INVALID":
            raise HTTPException(
                status_code=422,
                detail=(f"invalid investigation {prefix}: {inv.get('reason')}"))
        sides.append(inv)
    return compare_engineering_investigations(sides[0], sides[1])


@app.get("/api/catalog/engineering-memory")
def catalog_engineering_memory(
    question_type: str = "",
    driver_a: str = "",
    driver_b: str = "",
    season: int = 0,
    round: int = 0,
    lap_number: int = 0,
    stint_number: int = 0,
    pattern_id: str = "",
    hypotheses: str = "",
    session_type: str = "RACE",
    driver: str = "",
    hypothesis: str = "",
    include_invalidated: bool = False,
    include_related: bool = False,
) -> dict[str, Any]:
    """Phase 6O: evidence-bound engineering memory by exact scope.

    Memory items are derived on-read from the supplied investigation input
    (structured, provenance-backed, scope-limited) and retrieved by exact
    scope matching - never semantic similarity, never generalization: a
    related prior investigation never transfers its conclusion. Nothing is
    persisted (zero storage growth).
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.investigation_memory import (
        derive_memory_items, retrieve_engineering_memory,
    )
    from racewise.data.historical.investigation_synthesis import (
        HYPOTHESIS_IDS, run_engineering_investigation,
    )

    spec = _investigation_input_from_params(
        "", question_type, driver_a, driver_b, season, round, lap_number,
        stint_number, pattern_id, hypotheses, session_type)
    if hypothesis and hypothesis not in HYPOTHESIS_IDS:
        raise HTTPException(status_code=422,
                            detail=f"hypothesis must be one of {list(HYPOTHESIS_IDS)}")
    queries = get_canonical_queries()
    inv = run_engineering_investigation(queries, **spec)
    if inv.get("status") == "INVALID":
        raise HTTPException(status_code=422,
                            detail=f"invalid investigation input: {inv.get('reason')}")
    if inv.get("status") != "VALID":
        return {"status": inv.get("status"), "reason": inv.get("reason"),
                "matching_memory_items": [], "match_count": 0}
    items = derive_memory_items(inv)
    exact = retrieve_engineering_memory(
        items,
        season=int(season) if season else None,
        round_num=int(round) if round else None,
        driver=driver if driver.strip() else None,
        hypothesis=hypothesis if hypothesis.strip() else None,
        pattern_id=pattern_id if pattern_id.strip() else None,
        scope_type=None,
        include_invalidated=bool(include_invalidated),
    )
    if not include_related:
        return exact

    # Phase 6S GAP 4: structural related-memory retrieval. The pool is
    # expanded deterministically and boundedly: the same investigation
    # spec in the adjacent seasons (±1), each contributing at most
    # MAX_MEMORY_ITEMS_PER_INVESTIGATION items. Neighbors that are not
    # VALID contribute zero items (no fabrication from absence).
    from racewise.data.historical.investigation_memory import (
        retrieve_related_engineering_memory,
    )

    pool = list(items)
    neighbor_runs: list[dict[str, Any]] = []
    base_season = int(season)
    for nb_season in (base_season - 1, base_season + 1):
        if not 1950 <= nb_season <= 2100:
            continue
        nb_spec = dict(spec)
        nb_spec["season"] = nb_season
        nb_inv = run_engineering_investigation(queries, **nb_spec)
        neighbor_runs.append({
            "season": nb_season,
            "status": nb_inv.get("status"),
            "investigation_id": nb_inv.get("investigation_id"),
            "items_derived": (len(derive_memory_items(nb_inv))
                              if nb_inv.get("status") == "VALID" else 0),
        })
        if nb_inv.get("status") == "VALID":
            pool.extend(derive_memory_items(nb_inv))
    related = retrieve_related_engineering_memory(
        pool,
        season=base_season if season else None,
        round_num=int(round) if round else None,
        driver=driver if driver.strip() else None,
        driver_pair=([spec["driver_a"], spec["driver_b"]]
                     if include_related else None),
        hypothesis=hypothesis if hypothesis.strip() else None,
        scope_type=None,
        include_invalidated=bool(include_invalidated),
    )
    exact["related_memory_items"] = related["related_memory_items"]
    exact["related_match_count"] = related["related_match_count"]
    exact["related_match_reason_vocabulary"] = \
        related["match_reason_vocabulary"]
    exact["related_policy"] = related["policy"]
    exact["related_neighbor_runs"] = neighbor_runs
    return exact


@app.get("/api/catalog/investigation-graph")
def catalog_investigation_graph(
    question_type: str = "",
    driver_a: str = "",
    driver_b: str = "",
    season: int = 0,
    round: int = 0,
    lap_number: int = 0,
    stint_number: int = 0,
    pattern_id: str = "",
    hypotheses: str = "",
    session_type: str = "RACE",
    investigation_id: str = "",
    max_depth: int = 4,
    max_nodes: int = 200,
    max_edges: int = 800,
) -> dict[str, Any]:
    """Phase 6P: deterministic investigation knowledge graph.

    Builds the graph from the structured 6N investigation input (closed
    node/edge vocabularies, every edge provenance-backed from existing 6N/6O
    outputs; SUPPORTS/CONTRADICTS are imported analytical relationships, not
    causality; MODELLED counterfactuals stay separate nodes). Derived-on-read;
    zero storage growth. Traversal inputs are bounded and rejected (never
    clamped) beyond the safe caps: max_depth <= 8, max_nodes <= 500,
    max_edges <= 1500.

    Addressing: by scope (default) or by investigation id. The 6N
    investigation id is a content hash of the canonical input and no stored
    investigation registry exists, so ``investigation_id`` must be supplied
    together with the full scope: the endpoint deterministically re-runs the
    investigation for that scope, recomputes the id, and verifies the
    binding. On match the graph is built by the unchanged builder — it is
    byte-identical to the scope-addressed graph of the same investigation.
    On mismatch (or a non-VALID investigation for the scope) the response is
    404: no investigation exists with that id for the requested scope. An id
    without a resolvable scope is rejected with 422 before any scope is
    parsed; no registry is invented and no silent fallback to a different
    investigation ever occurs.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.investigation_graph import (
        MAX_EDGES, MAX_NODES, build_investigation_graph,
    )
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    req_id = investigation_id.strip()
    has_scope = bool(
        question_type.strip() and driver_a.strip() and driver_b.strip()
        and int(season) > 0 and int(round) > 0)
    if session_type not in ("RACE", "QUALIFYING"):
        raise HTTPException(
            status_code=422,
            detail="session_type must be one of ['RACE', 'QUALIFYING']")
    if req_id and not has_scope:
        # id without a resolvable scope cannot be deterministically
        # reconstructed (no stored investigation registry exists)
        raise HTTPException(
            status_code=422,
            detail=("investigation_id requires the full scope (question_type, "
                    "drivers, season, round [, lap/stint/pattern]): the id is "
                    "a content hash of the canonical input and is "
                    "deterministically reconstructed, never looked up"))
    spec = _investigation_input_from_params(
        "", question_type, driver_a, driver_b, season, round, lap_number,
        stint_number, pattern_id, hypotheses, session_type)
    if not 1 <= int(max_depth) <= 8:
        raise HTTPException(status_code=422,
                            detail="max_depth out of bounds [1, 8]")
    if not 1 <= int(max_nodes) <= MAX_NODES:
        raise HTTPException(status_code=422,
                            detail=f"max_nodes out of bounds [1, {MAX_NODES}]")
    if not 1 <= int(max_edges) <= MAX_EDGES:
        raise HTTPException(status_code=422,
                            detail=f"max_edges out of bounds [1, {MAX_EDGES}]")
    queries = get_canonical_queries()
    inv = run_engineering_investigation(queries, **spec)
    if inv.get("status") == "INVALID":
        raise HTTPException(status_code=422,
                            detail=f"invalid investigation input: {inv.get('reason')}")
    if investigation_id.strip():
        # id-addressed retrieval: verify the scope→id binding, never fall
        # back silently to a different investigation
        inv_id = str(inv.get("investigation_id") or "")
        if inv.get("status") != "VALID" or inv_id != req_id:
            raise HTTPException(
                status_code=404,
                detail=(f"no investigation exists with id {req_id!r} for the "
                        "requested scope"))
    graph = build_investigation_graph(queries, inv)
    if graph.get("status") == "INVALID":
        raise HTTPException(status_code=422,
                            detail=("graph build rejected the investigation: "
                                    f"{graph.get('reason')}"))
    graph["addressing"] = "INVESTIGATION_ID" if req_id else "SCOPE"
    graph["requested_bounds"] = {"max_depth": int(max_depth),
                                 "max_nodes": int(max_nodes),
                                 "max_edges": int(max_edges)}
    return graph


@app.get("/api/catalog/investigation-graph/path")
def catalog_investigation_graph_path(
    question_type: str = "",
    driver_a: str = "",
    driver_b: str = "",
    season: int = 0,
    round: int = 0,
    lap_number: int = 0,
    stint_number: int = 0,
    pattern_id: str = "",
    hypotheses: str = "",
    session_type: str = "RACE",
    target_node_type: str = "",
    target_key: str = "",
    max_depth: int = 8,
) -> dict[str, Any]:
    """Phase 6P: ordered provenance path investigation -> target node.

    Every hop names its edge type and provenance. A path is provenance
    navigation, not a causal chain. Unknown targets end NOT_FOUND; unknown
    investigations end UNAVAILABLE - never a fabricated path.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.investigation_graph import (
        build_investigation_graph, explain_investigation_path,
    )
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    spec = _investigation_input_from_params(
        "", question_type, driver_a, driver_b, season, round, lap_number,
        stint_number, pattern_id, hypotheses, session_type)
    if not 1 <= int(max_depth) <= 8:
        raise HTTPException(status_code=422,
                            detail="max_depth out of bounds [1, 8]")
    if not target_node_type.strip() or not target_key.strip():
        raise HTTPException(status_code=422,
                            detail="target_node_type and target_key are required")
    queries = get_canonical_queries()
    inv = run_engineering_investigation(queries, **spec)
    if inv.get("status") == "INVALID":
        raise HTTPException(status_code=422,
                            detail=f"invalid investigation input: {inv.get('reason')}")
    if inv.get("status") != "VALID":
        return {"status": inv.get("status"), "reason": inv.get("reason")}
    graph = build_investigation_graph(queries, inv)
    target = _graph_target_node_id(
        graph, str(target_node_type), target_key.strip(),
        inv["investigation_id"])
    return explain_investigation_path(
        graph, inv["investigation_id"], target, max_depth=int(max_depth))


def _graph_target_node_id(
    graph: dict[str, Any],
    target_node_type: str,
    target_key: str,
    investigation_id: str,
) -> str:
    """Resolve (node type, key) to a node id inside this graph; 422 when the
    type is not in the closed vocabulary."""
    from racewise.data.historical.investigation_graph import (
        NODE_TYPES, graph_vocabulary,
    )

    prefixes = {t: t + ":" for t in NODE_TYPES}
    prefixes.update({
        "QUESTION": "question:",
        "DRIVER": "driver:",
        "DRIVER_PAIR": "driver_pair:",
        "SEASON": "season:",
        "RACE": "race:",
        "SESSION": "session:",
        "LAP": "lap:",
        "STINT": "stint:",
        "REGIME": "regime:",
        "PATTERN": "pattern:",
        "HYPOTHESIS": "hypothesis:",
        "EVIDENCE": "evidence:",
        "COUNTERFACTUAL": "evidence:evidence_cf_",
        "SYNTHESIS": "synthesis:",
        "DECISION_TRACE": f"decision_trace:{investigation_id}:",
        "MEMORY": "memory:",
        "ANALYTICAL_SOURCE": "analytical_source:",
        "SNAPSHOT": "snapshot:",
        "INVESTIGATION": f"investigation:{investigation_id}",
    })
    if target_node_type not in graph_vocabulary()["node_types"]:
        raise HTTPException(
            status_code=422,
            detail=(f"target_node_type must be one of "
                    f"{graph_vocabulary()['node_types']}"))
    if target_node_type == "INVESTIGATION":
        return prefixes[target_node_type]
    return f"{prefixes[target_node_type]}{target_key}"


@app.get("/api/catalog/investigation-graph/evidence")
def catalog_investigation_graph_evidence(
    question_type: str = "",
    driver_a: str = "",
    driver_b: str = "",
    season: int = 0,
    round: int = 0,
    lap_number: int = 0,
    stint_number: int = 0,
    pattern_id: str = "",
    hypotheses: str = "",
    session_type: str = "RACE",
    evidence_id: str = "",
) -> dict[str, Any]:
    """Phase 6P: evidence -> analytical source provenance trace.

    source tool / phase / hash plus the race/lap/stint/regime/pattern the
    evidence is measured on. Missing provenance is reported explicitly, never
    fabricated.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.investigation_graph import (
        build_investigation_graph, trace_evidence_to_source,
    )
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    spec = _investigation_input_from_params(
        "", question_type, driver_a, driver_b, season, round, lap_number,
        stint_number, pattern_id, hypotheses, session_type)
    if not evidence_id.strip():
        raise HTTPException(status_code=422, detail="evidence_id is required")
    queries = get_canonical_queries()
    inv = run_engineering_investigation(queries, **spec)
    if inv.get("status") == "INVALID":
        raise HTTPException(status_code=422,
                            detail=f"invalid investigation input: {inv.get('reason')}")
    if inv.get("status") != "VALID":
        return {"status": inv.get("status"), "reason": inv.get("reason")}
    ledger_ids = {e["evidence_id"] for e in inv.get("evidence_ledger") or []}
    if evidence_id not in ledger_ids:
        raise HTTPException(status_code=422,
                            detail=(f"evidence_id {evidence_id!r} is not part "
                                    "of this investigation"))
    graph = build_investigation_graph(queries, inv)
    return trace_evidence_to_source(graph, evidence_id.strip())


@app.get("/api/catalog/investigation-graph/hypothesis")
def catalog_investigation_graph_hypothesis(
    question_type: str = "",
    driver_a: str = "",
    driver_b: str = "",
    season: int = 0,
    round: int = 0,
    lap_number: int = 0,
    stint_number: int = 0,
    pattern_id: str = "",
    hypotheses: str = "",
    session_type: str = "RACE",
    hypothesis: str = "",
) -> dict[str, Any]:
    """Phase 6P: supporting / contradicting / non-decisive evidence for one
    hypothesis plus related MODELLED counterfactuals.

    Descriptive lists imported from the 6N evaluation (evidence-consistency,
    not causation); never ranked, never scored. SUPPORT is not PROOF.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.data.historical.investigation_graph import (
        build_investigation_graph, trace_hypothesis_evidence,
    )
    from racewise.data.historical.investigation_synthesis import (
        HYPOTHESIS_IDS, run_engineering_investigation,
    )

    spec = _investigation_input_from_params(
        "", question_type, driver_a, driver_b, season, round, lap_number,
        stint_number, pattern_id, hypotheses, session_type)
    if hypothesis not in HYPOTHESIS_IDS:
        raise HTTPException(status_code=422,
                            detail=f"hypothesis must be one of {list(HYPOTHESIS_IDS)}")
    queries = get_canonical_queries()
    inv = run_engineering_investigation(queries, **spec)
    if inv.get("status") == "INVALID":
        raise HTTPException(status_code=422,
                            detail=f"invalid investigation input: {inv.get('reason')}")
    if inv.get("status") != "VALID":
        return {"status": inv.get("status"), "reason": inv.get("reason")}
    graph = build_investigation_graph(queries, inv)
    return trace_hypothesis_evidence(
        graph, hypothesis, investigation_id=inv["investigation_id"])


@app.get("/api/catalog/search")
def catalog_search(
    q: str = "",
    result_type: str = "",
    season: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    """Phase 6Q global engineering search (deterministic, typed).

    Exact/structured matching first (driver keys, pattern ids, hashes,
    season/round), then deterministic substring matching over canonical
    identities (races, drivers, catalog sessions) and derived object ids
    (investigations, evidence, hypotheses, memories) when a structured
    investigation scope is supplied. No semantic/vector search, no scoring:
    results are typed, deduplicated and deterministically ordered. Empty
    query returns an empty result list (never a canned list).
    """
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )

    term = q.strip()
    if not term:
        return {"status": "OK", "query": "", "result_count": 0,
                "results": [],
                "provenance": {"method": "deterministic_exact_match_search"}}
    if not 1 <= int(limit) <= 50:
        raise HTTPException(status_code=422,
                            detail="limit out of bounds [1, 50]")
    if result_type and result_type not in _SEARCH_RESULT_TYPES:
        raise HTTPException(status_code=422,
                            detail=(f"result_type must be one of "
                                    f"{_SEARCH_RESULT_TYPES}"))
    queries = get_canonical_queries()
    results: list[dict[str, Any]] = []

    def add(result_type_: str, label: str, detail_: str,
            ref: dict[str, Any]) -> None:
        results.append({"result_type": result_type_, "label": label,
                        "detail": detail_, "ref": ref,
                        "provenance": {
                            "matched_on": term,
                            "match_mode": "exact_or_substring"}})

    low = term.lower()

    # --- race (canonical identity) -----------------------------------------
    if result_type in ("", "RACE"):
        try:
            season_i, round_i = (int(x) for x in low.replace("r", " ").split()) \
                if low.replace("r", " ").strip().replace(" ", "").isdigit() \
                else (None, None)
        except ValueError:
            season_i = round_i = None
        if season_i is not None and \
                queries.resolve_race(season_i, round_num=round_i) is not None:
            add("RACE", f"{season_i} R{round_i}",
                str(queries.resolve_race(season_i, round_num=round_i)["grand_prix"]),
                {"season": season_i, "round": round_i})
        seen_races: set[tuple[int, int]] = set()
        for season in range(1950, 2027):
            race = queries.resolve_race(season)
            # resolve_race without round returns None; scan the catalog
            # instead via a targeted LIKE through the catalog api is heavy,
            # so use direct canonical query here:
            break
        # substring over race grand_prix names via catalog api (bounded)
        try:
            from racewise.data.historical.catalog_api import get_catalog_api
            cat = get_catalog_api().list_sessions(search=term, page=1,
                                                  page_size=6)
            for s in cat.get("sessions", []):
                key = (s["season"], s["round"])
                if key in seen_races:
                    continue
                seen_races.add(key)
                add("RACE", f"{s['season']} R{s['round']}",
                    s.get("race_name") or "",
                    {"season": s["season"], "round": s["round"],
                     "session_type": s["session_type"]})
        except Exception:  # noqa: BLE001 - catalog is optional for search
            pass

    # --- driver (canonical driver_key identity) ----------------------------
    if result_type in ("", "DRIVER"):
        d = queries.get_driver(low)
        if d is not None:
            add("DRIVER", d["full_name"], d["driver_key"],
                {"driver_key": d["driver_key"]})
        else:
            matches = queries.get_driver_by_code(term.upper()) \
                if len(term) == 3 else []
            for d in matches[:3]:
                add("DRIVER", d["full_name"], d["driver_key"],
                    {"driver_key": d["driver_key"]})
            if not matches:
                # deterministic LIKE over driver_key / family name (bounded);
                # read-only, parameterized, no user input concatenated
                import sqlite3 as _sq
                try:
                    conn = _sq.connect(queries.db_path)
                    conn.row_factory = _sq.Row
                    rows = conn.execute(
                        "SELECT driver_key, full_name FROM canonical_drivers "
                        "WHERE driver_key LIKE ? OR family_name LIKE ? "
                        "ORDER BY driver_key LIMIT 4",
                        (f"%{low}%", f"%{term}%"),
                    ).fetchall()
                    conn.close()
                    for d in rows:
                        add("DRIVER", d["full_name"], d["driver_key"],
                            {"driver_key": d["driver_key"]})
                except Exception:  # noqa: BLE001 - store optional for search
                    pass

    # --- hypothesis (closed 6F vocabulary) ----------------------------------
    if result_type in ("", "HYPOTHESIS"):
        from racewise.data.historical.investigation_synthesis import (
            HYPOTHESIS_IDS,
        )
        for h in HYPOTHESIS_IDS:
            if low == h.lower() or low in h.lower() or \
                    low in h.lower().split("_", 1)[-1]:
                add("HYPOTHESIS", h,
                    "canonical 6F hypothesis (closed vocabulary)",
                    {"hypothesis_id": h})

    # --- investigation / memory (deterministic derived ids) -----------------
    if result_type in ("", "INVESTIGATION") and len(term) == 16 and \
            all(c in "0123456789abcdef" for c in low):
        add("INVESTIGATION", term[:12],
            "16-hex investigation id (paste into a workspace view to load "
            "its scope; ids are content-addressed)",
            {"investigation_id": term})

    if result_type in ("", "MEMORY") and len(term) == 16 and \
            all(c in "0123456789abcdef" for c in low):
        add("MEMORY", term[:12],
            "16-hex memory id (exact-scope retrieval key)",
            {"memory_id": term})

    # --- pattern id (structured, only plausible id shapes) ------------------
    if result_type in ("", "PATTERN") and len(term) == 16 and \
            all(c in "0123456789abcdef" for c in low) and \
            result_type != "MEMORY":
        pass  # 16-hex ids are handled above; no free-text pattern echo

    # --- evidence id (structured shape) --------------------------------------
    if result_type in ("", "EVIDENCE") and \
            term.lower().startswith("evidence_"):
        add("EVIDENCE", term,
            "evidence id (valid inside an investigation whose ledger "
            "contains it)",
            {"evidence_id": term})

    # deterministic order: type then label; cap results
    results.sort(key=lambda r: (r["result_type"], r["label"]))
    results = results[: int(limit)]
    return {
        "status": "OK", "query": term, "result_count": len(results),
        "results": results,
        "provenance": {"method": "deterministic_exact_match_search",
                       "note": "no semantic search; ids are content-"
                               "addressed and scope-bound"},
    }


_SEARCH_RESULT_TYPES = (
    "RACE", "DRIVER", "HYPOTHESIS", "INVESTIGATION", "EVIDENCE",
    "PATTERN", "MEMORY",
)


@app.get("/api/sessions")
def list_sessions() -> dict[str, Any]:
    sessions = _store.list_sessions()
    return {
        "sessions": [
            {
                "year": s["year"],
                "event": s["event"],
                "session_type": s["session_type"],
                "label": s.get("event_name") or f"{s['year']} {s['event']} Grand Prix - {s['session_type']}",
                "session_key": s["session_key"],
                "availability": s["availability"],
            }
            for s in sessions
        ]
    }


@app.get("/api/sessions/{session_key}/drivers")
def get_session_drivers(session_key: str) -> dict[str, Any]:
    """Get list of drivers for a session."""
    drivers = _store.get_session_drivers(session_key)
    return {"drivers": drivers}


@app.post("/api/sessions/sync")
def sync_sessions() -> dict[str, Any]:
    """Sync session catalog from FastF1 for known 2023 races."""
    known_sessions = [
        {"year": 2023, "round": 1, "event": "Bahrain", "session_type": "R"},
        {"year": 2023, "round": 2, "event": "Saudi Arabia", "session_type": "R"},
        {"year": 2023, "round": 3, "event": "Australia", "session_type": "R"},
        {"year": 2023, "round": 4, "event": "Azerbaijan", "session_type": "R"},
        {"year": 2023, "round": 5, "event": "Miami", "session_type": "R"},
        {"year": 2023, "round": 6, "event": "Monaco", "session_type": "R"},
        {"year": 2023, "round": 7, "event": "Spain", "session_type": "R"},
        {"year": 2023, "round": 8, "event": "Canada", "session_type": "R"},
        {"year": 2023, "round": 9, "event": "Austria", "session_type": "R"},
        {"year": 2023, "round": 10, "event": "Great Britain", "session_type": "R"},
        {"year": 2023, "round": 11, "event": "Hungary", "session_type": "R"},
        {"year": 2023, "round": 12, "event": "Belgium", "session_type": "R"},
        {"year": 2023, "round": 13, "event": "Netherlands", "session_type": "R"},
        {"year": 2023, "round": 14, "event": "Italy", "session_type": "R"},
        {"year": 2023, "round": 15, "event": "Singapore", "session_type": "R"},
        {"year": 2023, "round": 16, "event": "Japan", "session_type": "R"},
        {"year": 2023, "round": 17, "event": "Qatar", "session_type": "R"},
        {"year": 2023, "round": 18, "event": "United States", "session_type": "R"},
        {"year": 2023, "round": 19, "event": "Mexico City", "session_type": "R"},
        {"year": 2023, "round": 20, "event": "Brazil", "session_type": "R"},
        {"year": 2023, "round": 21, "event": "Las Vegas", "session_type": "R"},
        {"year": 2023, "round": 22, "event": "Abu Dhabi", "session_type": "R"},
    ]
    synced = 0
    failed = 0
    for s in known_sessions:
        try:
            session = _adapter.load_session(s["year"], s["event"], s["session_type"])
            summary = _adapter.session_summary(session)
            session_key = f"{s['year']}-{s['event'].replace(' ', '')}-{s['session_type']}"
            _store.upsert_session(
                session_key=session_key,
                year=s["year"],
                event=s["event"],
                session_type=s["session_type"],
                event_name=summary.event_name,
                circuit=summary.circuit,
                date=summary.date.isoformat() if summary.date else None,
                total_laps=summary.total_laps,
                drivers=summary.drivers,
                data_source="fastf1",
                availability="AVAILABLE",
            )
            synced += 1
        except Exception as e:
            session_key = f"{s['year']}-{s['event'].replace(' ', '')}-{s['session_type']}"
            _store.upsert_session(
                session_key=session_key,
                year=s["year"],
                event=s["event"],
                session_type=s["session_type"],
                data_source="fastf1",
                availability="DATA_UNAVAILABLE",
                availability_reason=str(e),
            )
            failed += 1
    return {"synced": synced, "failed": failed, "total": len(known_sessions)}


@app.post("/api/investigations")
async def create_investigation(req: CreateInvestigationRequest) -> dict[str, Any]:
    context = SessionContext(_adapter, req.year, req.event, req.session_type)
    registry = build_default_registry(context)
    provider = provider_from_env()
    engine = InvestigationEngine(registry, provider, req.question)

    # Persist initial investigation
    inv_id = _store.create_investigation(
        question=req.question,
        year=req.year,
        event=req.event,
        driver=req.driver,
        session_type=req.session_type,
        metadata={"session_type": req.session_type},
    )
    # Override the engine's investigation_id to match the stored one
    engine.investigation_id = inv_id
    engine._set_state(InvestigationState.CREATED)

    record = InvestigationRecord(engine, context, req.year, req.event, req.driver)
    _INVESTIGATIONS[inv_id] = record

    return {"investigation_id": inv_id, "state": engine.state.value}


@app.get("/api/investigations/{inv_id}/stream")
async def stream_investigation(inv_id: str) -> StreamingResponse:
    if inv_id not in _INVESTIGATIONS:
        # Try to load from persistent store
        if _store.get_investigation(inv_id):
            # Reconstruct engine from stored state
            inv_data = _store.get_investigation(inv_id)
            context = SessionContext(_adapter, inv_data["year"], inv_data["event"], inv_data["session_type"])
            registry = build_default_registry(context)
            provider = provider_from_env()
            engine = InvestigationEngine(registry, provider, inv_data["question"], investigation_id=inv_id)
            _load_engine_state(engine, inv_id)
            record = InvestigationRecord(engine, context, inv_data["year"], inv_data["event"], inv_data["driver"])
            _INVESTIGATIONS[inv_id] = record
        else:
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
        if _store.get_investigation(inv_id):
            inv_data = _store.get_investigation(inv_id)
            context = SessionContext(_adapter, inv_data["year"], inv_data["event"], inv_data["session_type"])
            registry = build_default_registry(context)
            provider = provider_from_env()
            engine = InvestigationEngine(registry, provider, inv_data["question"], investigation_id=inv_id)
            _load_engine_state(engine, inv_id)
            record = InvestigationRecord(engine, context, inv_data["year"], inv_data["event"], inv_data["driver"])
            _INVESTIGATIONS[inv_id] = record
        else:
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
        if _store.get_investigation(inv_id):
            inv_data = _store.get_investigation(inv_id)
            context = SessionContext(_adapter, inv_data["year"], inv_data["event"], inv_data["session_type"])
            registry = build_default_registry(context)
            provider = provider_from_env()
            engine = InvestigationEngine(registry, provider, inv_data["question"], investigation_id=inv_id)
            _load_engine_state(engine, inv_id)
            record = InvestigationRecord(engine, context, inv_data["year"], inv_data["event"], inv_data["driver"])
            _INVESTIGATIONS[inv_id] = record
        else:
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
    _persist_engine_state(record.engine, record)
    return {"counterfactual": cf.model_dump(), "note": "COUNTERFACTUAL estimate under stated assumptions, not an observed result."}


# -- New endpoints for investigation history and export --

@app.get("/api/investigations")
def list_investigations(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List all persisted investigations."""
    investigations = _store.list_investigations(limit=limit, offset=offset)
    return {"investigations": investigations, "limit": limit, "offset": offset}


@app.get("/api/investigations/{inv_id}/export")
def export_investigation(inv_id: str) -> dict[str, Any]:
    """Export full investigation as JSON."""
    exported = _store.export_investigation(inv_id)
    if not exported:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return exported


@app.delete("/api/investigations/{inv_id}")
def delete_investigation(inv_id: str) -> dict[str, Any]:
    """Delete an investigation."""
    if _store.delete_investigation(inv_id):
        _INVESTIGATIONS.pop(inv_id, None)
        return {"deleted": True, "investigation_id": inv_id}
    raise HTTPException(status_code=404, detail="Investigation not found")


@app.post("/api/investigations/{inv_id}/replay")
def replay_investigation(inv_id: str) -> dict[str, Any]:
    """Replay an investigation from persistent storage and verify hashes."""
    if not _store.get_investigation(inv_id):
        raise HTTPException(status_code=404, detail="Investigation not found")

    inv_data = _store.get_investigation(inv_id)
    context = SessionContext(_adapter, inv_data["year"], inv_data["event"], inv_data["session_type"])
    registry = build_default_registry(context)
    engine = InvestigationEngine(registry, provider=None, question=inv_data["question"], investigation_id=inv_id)

    event_log = _store.get_event_log(inv_id)
    replay_result = engine.replay_from_log(registry, event_log, inv_id)
    return replay_result.model_dump()


# -- Evidence Graph endpoints --

class EvidenceRelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str
    provenance: Optional[str] = None


@app.get("/api/investigations/{inv_id}/evidence-graph")
def get_evidence_graph(inv_id: str) -> dict[str, Any]:
    """Get evidence graph for an investigation."""
    if not _store.get_investigation(inv_id):
        raise HTTPException(status_code=404, detail="Investigation not found")

    evidence = _store.get_evidence(inv_id)
    relationships = _store.get_evidence_relationships(inv_id)
    
    nodes = [
        {
            "id": e.id,
            "type": e.type.value,
            "label": e.statement[:100] + ("..." if len(e.statement) > 100 else ""),
            "full_statement": e.statement,
            "strength": e.strength,
            "evidence_type": e.type.value,
        }
        for e in evidence
    ]
    
    edges = [
        {
            "id": r["id"],
            "source": r["source_id"],
            "target": r["target_id"],
            "relationship": r["relationship_type"],
            "provenance": r.get("provenance"),
        }
        for r in relationships
    ]
    
    return {"nodes": nodes, "edges": edges}


@app.post("/api/investigations/{inv_id}/evidence-graph")
def add_evidence_relationship(inv_id: str, req: EvidenceRelationshipRequest) -> dict[str, Any]:
    """Add a relationship between evidence nodes."""
    if not _store.get_investigation(inv_id):
        raise HTTPException(status_code=404, detail="Investigation not found")

    rel_id = _store.add_evidence_relationship(
        investigation_id=inv_id,
        source_id=req.source_id,
        target_id=req.target_id,
        relationship_type=req.relationship_type,
        provenance=req.provenance,
    )
    return {"relationship_id": rel_id, "status": "created"}