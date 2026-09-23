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