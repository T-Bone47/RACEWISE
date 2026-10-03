"""Question engine API routes.

Mounted onto the main RACEWISE FastAPI app. Deliberately thin: every route
delegates to the deterministic question engine and returns its structured
result. No engineering logic, no formatting decisions and no prose generation
live here — the API surface is a window onto the engine, not a second
implementation of it.

Routes (§70):

    GET  /api/capabilities              the capability registry
    GET  /api/capabilities/{id}         one capability
    GET  /api/capabilities/coverage     intent -> capability coverage matrix
    POST /api/investigations/ask        compile + plan + execute + synthesise
    POST /api/investigations/{id}/follow-up
    POST /api/investigations/benchmark  run the question benchmark
    POST /api/investigations/autopsy    engineering autopsy timeline
    POST /api/investigations/decision-twin  bounded scenario sweep

The full investigation payloads stay large on purpose: the frontend needs the
full ledger, plan and verification report to render an answer honestly, and
trimming it server-side would mean choosing what the user is allowed to see.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

# The question engine is imported inside the handlers, never at module scope.
# Importing it eagerly here drags the canonical-query and question-intake
# stack into every API boot, which measurably regressed cold start (1000 ms ->
# 4455 ms) to serve routes most callers never touch. The capability registry is
# cheap and dependency-free, so it alone is imported eagerly.


# ---------------------------------------------------------------------------
# capability registry (§9, §61)
# ---------------------------------------------------------------------------

@router.get("/api/capabilities")
def list_capabilities() -> dict[str, Any]:
    """Every deterministic engineering capability RACEWISE actually has."""
    from racewise.question_engine import capabilities as cap

    return {
        "registry_version": cap.registry_version(),
        "count": len(cap.all_capabilities()),
        "capabilities": [c.as_dict() for c in cap.all_capabilities()],
    }


@router.get("/api/capabilities/coverage")
def capability_coverage() -> dict[str, Any]:
    """Machine-readable intent -> capability -> supported-resolution matrix."""
    from racewise.question_engine import capabilities as cap

    return cap.capability_matrix()


@router.get("/api/capabilities/{capability_id}")
def get_capability(capability_id: str) -> dict[str, Any]:
    """One capability, including its prerequisite closure."""
    from racewise.question_engine import capabilities as cap

    found = cap.capability(capability_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Unknown capability")
    payload = found.as_dict()
    payload["dependency_closure"] = list(cap.dependency_closure(capability_id))
    return payload


# ---------------------------------------------------------------------------
# ask (§70)
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    """One engineering question. No question-type selector by design."""

    question: str = Field(..., description="The engineering question, in any phrasing.")
    context: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Resolved investigation context. Supplied by a follow-up, or by the "
            "Command Center once a race is selected."
        ),
    )
    budget: Optional[dict[str, int]] = Field(default=None)


class FollowUpRequest(BaseModel):
    question: str
    budget: Optional[dict[str, int]] = None


@router.post("/api/investigations/ask")
def ask_question(payload: AskRequest) -> dict[str, Any]:
    """Answer one engineering question end to end.

    Returns the compiled question, the plan, the structured answer and the
    verification report. An unanswerable question is a successful response with
    an honest status, not an HTTP error — "we cannot establish this" is a
    result, and the frontend renders it as one.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.question_engine.engine import ask

    return ask(get_canonical_queries(), payload.question,
               context=payload.context, budget=payload.budget)


@router.post("/api/investigations/{investigation_id}/follow-up")
def ask_follow_up(investigation_id: str, payload: FollowUpRequest) -> dict[str, Any]:
    """Continue an investigation with a narrowed or extended question.

    The investigation id is echoed back for traceability. Continuation state is
    carried in the caller's ``context`` (the frontend holds the live
    investigation), which keeps the server stateless and the context auditable.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.question_engine.engine import follow_up

    return follow_up(get_canonical_queries(), {"investigation_id": investigation_id},
                     payload.question, budget=payload.budget)


@router.post("/api/investigations/benchmark")
def run_question_benchmark() -> dict[str, Any]:
    """Measure the general-question benchmark against the live canonical store."""
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.question_engine.benchmark import measure

    return measure(get_canonical_queries())


# ---------------------------------------------------------------------------
# engineering autopsy (§26) and decision twin (§40)
# ---------------------------------------------------------------------------

class AutopsyRequest(BaseModel):
    """A whole-race question. Produces a timeline, not a single measurement."""

    season: int
    round: int
    driver_a: str
    driver_b: str
    session_type: str = "RACE"
    residual_s: Optional[float] = Field(
        default=None,
        description=(
            "An unexplained-time residual already computed by a capability. "
            "Supplied, never recomputed here."
        ),
    )
    residual_source: Optional[str] = Field(default=None)


class DecisionTwinRequest(BaseModel):
    """A bounded scenario sweep. Every returned point is MODELLED."""

    season: int
    round: int
    driver: str
    lap_number: int
    reference_driver: Optional[str] = None
    dimension: str = Field(
        default="speed",
        description=(
            "Signal to intervene on. Only signals with a real deterministic "
            "lap-time model are accepted; others are refused with a reason."
        ),
    )
    intervention_type: str = "REMOVE_DEFICIT"
    fractions: Optional[list[float]] = Field(
        default=None,
        description=(
            "Scenario fractions. Values outside the intervention's valid range "
            "are refused, never clamped."
        ),
    )
    session_type: str = "RACE"


@router.post("/api/investigations/autopsy")
def run_autopsy(payload: AutopsyRequest) -> dict[str, Any]:
    """Curate a race timeline from deterministic change points and gap events.

    Returns the events in chronological order, each carrying the capability
    that produced it. Measurement-availability transitions are marked
    MEASUREMENT so they cannot be read as engineering events.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.question_engine.autopsy import build_timeline

    queries = get_canonical_queries()
    regimes: Optional[dict[str, Any]] = None
    race_gap: Optional[dict[str, Any]] = None
    # Either source may legitimately be unavailable for a given race. One
    # failing analysis degrades the timeline; it does not fail the request.
    try:
        from racewise.data.historical.performance_regimes import (
            analyze_performance_regimes,
        )
        regimes = analyze_performance_regimes(
            queries, payload.season, payload.round,
            payload.driver_a, payload.driver_b)
    except Exception:  # noqa: BLE001
        regimes = None
    try:
        from racewise.data.historical.race_gap import decompose_race_gap
        race_gap = decompose_race_gap(
            queries, payload.season, payload.round,
            payload.driver_a, payload.driver_b,
            session_type=payload.session_type)
    except Exception:  # noqa: BLE001
        race_gap = None

    return build_timeline(
        season=payload.season,
        round_num=payload.round,
        regimes=regimes,
        race_gap=race_gap,
        residual_s=payload.residual_s,
        residual_source=payload.residual_source,
    )


@router.post("/api/investigations/decision-twin")
def run_decision_twin(payload: DecisionTwinRequest) -> dict[str, Any]:
    """Model bounded interventions and report the response curve.

    A refusal is a valid result: an unsupported dimension or an out-of-range
    fraction returns a reasoned status, not a clamped scenario.
    """
    from racewise.data.historical.canonical_queries import get_canonical_queries
    from racewise.question_engine.decision_twin import build_twin

    return build_twin(
        get_canonical_queries(),
        season=payload.season,
        round_num=payload.round,
        driver=payload.driver,
        lap_number=payload.lap_number,
        reference_driver=payload.reference_driver,
        dimension=payload.dimension,
        fractions=tuple(payload.fractions) if payload.fractions else
        (0.0, 0.25, 0.5, 0.75, 1.0),
        intervention_type=payload.intervention_type,
        session_type=payload.session_type,
    )


def register(app: Any) -> None:
    """Mount these routes onto the main app."""
    app.include_router(router)