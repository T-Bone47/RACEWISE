"""Phase 6N — Engineering Investigation Synthesis & Decision Trace.

Deterministic orchestration layer ABOVE the verified 6E → 6M analytical
chain. Given a structured engineering question (closed vocabulary, no
free-form executable logic), 6N:

    1. frames and validates the question,
    2. plans evidence collection using ONLY existing registered
       analytical layers (6E loss_attribution, 6F evidence_fusion,
       6G stint_evidence, 6H race_gap, 6I counterfactual, 6J envelope,
       6K regimes, 6L patterns, 6M evidence),
    3. collects an evidence ledger (FACT / CALCULATION / INFERENCE /
       COUNTERFACTUAL taxonomy reused from the existing layers),
    4. evaluates each of the six canonical hypotheses with the
       falsification gate (unresolved contradictions block synthesis),
    5. determines bounded counterfactual ELIGIBILITY without running,
    6. executes only ELIGIBLE counterfactuals through the exact 6I
       simulator (never a second simulator),
    7. synthesizes an evidence-bound conclusion whose every statement
       carries a decision trace referencing evidence IDs,
    8. produces full provenance and a deterministic output hash.

Multi-source reconciliation (§21/§22): evidence from different layers
addressing the same hypothesis is preserved SEPARATELY with per-source
provenance; a supporting item from one layer and a contradicting item
from another are classified DIRECT_CONTRADICTION only when one of them
is an explicit conflict record, otherwise they remain MEASUREMENT
disagreement across sources (MIXED_EVIDENCE) — never silently merged.

Epistemic invariants are enforced structurally:
    OBSERVED != DERIVED != INFERRED != MODELLED
    SUPPORT != PROOF, NO_FALSIFICATION_FOUND != CONFIRMED
    SIMILARITY != CAUSALITY, RECURRENCE != MECHANISM
    TEMPORAL_ALIGNMENT != CAUSAL_ATTRIBUTION
    MODEL_SENSITIVITY != HISTORICAL_EFFECT, COUNTERFACTUAL != HISTORY
    MISSING_DATA != NEGATIVE_EVIDENCE, NOT_TESTABLE != CONTRADICTED
    INSUFFICIENT_EVIDENCE != NOT_SUPPORTED

Derived-on-read: zero storage growth. No LLM, no free-form reasoning,
no hypothesis ranking, no confidence scores, no "best explanation".
"""
from __future__ import annotations

from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.performance_patterns import _hash_obj

ANALYSIS = "phase_6n_engineering_investigation"
INVESTIGATION_VERSION = "6n_investigation_v1"

# ---------------------------------------------------------------------------
# closed vocabularies
# ---------------------------------------------------------------------------

QUESTION_TYPES = (
    "LAP_PERFORMANCE",
    "STINT_PERFORMANCE",
    "RACE_GAP",
    "PERFORMANCE_REGIME",
    "CROSS_RACE_PATTERN",
    "HYPOTHESIS_EVALUATION",
    "COUNTERFACTUAL_ELIGIBILITY",
)

# The six canonical Phase 6F hypothesis IDs (reused verbatim).
HYPOTHESIS_IDS = (
    "H1_corner_speed",
    "H2_throttle",
    "H3_braking",
    "H4_tyre_state",
    "H5_race_control",
    "H6_drs",
)

# Hypothesis relevance per question type (planning contract). All question
# types consider all six hypotheses; NOT_REQUESTED is reserved for explicit
# caller subsetting (never silently applied).
QUESTION_HYPOTHESES: dict[str, Optional[tuple[str, ...]]] = {
    "LAP_PERFORMANCE": HYPOTHESIS_IDS,
    "STINT_PERFORMANCE": HYPOTHESIS_IDS,
    "RACE_GAP": HYPOTHESIS_IDS,
    "PERFORMANCE_REGIME": HYPOTHESIS_IDS,
    "CROSS_RACE_PATTERN": HYPOTHESIS_IDS,
    "HYPOTHESIS_EVALUATION": HYPOTHESIS_IDS,
    "COUNTERFACTUAL_ELIGIBILITY": HYPOTHESIS_IDS,
}

# Question type -> analytical layers consulted (evidence plan).
QUESTION_EVIDENCE_PLAN: dict[str, list[dict[str, str]]] = {
    "LAP_PERFORMANCE": [
        {"phase": "6E", "tool": "attribute_lap_loss", "purpose": "region attribution"},
        {"phase": "6F", "tool": "fuse_lap_evidence", "purpose": "hypothesis evidence fusion"},
        {"phase": "6I", "tool": "counterfactual_eligibility", "purpose": "bounded counterfactual"},
    ],
    "STINT_PERFORMANCE": [
        {"phase": "6G", "tool": "fuse_stint_evidence", "purpose": "stint trend + hypothesis evolution"},
        {"phase": "6F", "tool": "fuse_lap_evidence", "purpose": "bounded lap-level evidence on 6G-selected laps"},
        {"phase": "6I", "tool": "counterfactual_eligibility", "purpose": "stint counterfactual"},
    ],
    "RACE_GAP": [
        {"phase": "6H", "tool": "decompose_race_gap", "purpose": "gap decomposition + race hypotheses"},
    ],
    "PERFORMANCE_REGIME": [
        {"phase": "6K", "tool": "analyze_performance_regimes", "purpose": "regimes + hypothesis evolution"},
    ],
    "CROSS_RACE_PATTERN": [
        {"phase": "6L", "tool": "analyze_cross_race_performance_patterns", "purpose": "recurring patterns"},
        {"phase": "6M", "tool": "analyze_cross_race_pattern_evidence", "purpose": "pattern evidence"},
    ],
    "HYPOTHESIS_EVALUATION": [
        {"phase": "6F", "tool": "fuse_lap_evidence", "purpose": "formal hypothesis rules"},
    ],
    "COUNTERFACTUAL_ELIGIBILITY": [
        {"phase": "6I", "tool": "counterfactual_eligibility", "purpose": "eligibility without execution"},
    ],
}

# 6N aggregate hypothesis states (never ranked, never scored).
AGG_SUPPORTED = "SUPPORTED"
AGG_PARTIAL = "PARTIALLY_SUPPORTED"
AGG_NOT_SUPPORTED = "NOT_SUPPORTED"
AGG_CONTRADICTED = "CONTRADICTED"
AGG_NOT_TESTABLE = "NOT_TESTABLE"
AGG_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
AGG_MIXED = "MIXED_EVIDENCE"
AGG_NOT_REQUESTED = "NOT_REQUESTED"

# Falsification gate states.
GATE_SUPPORTED = "SUPPORTED"
GATE_CONTRADICTED = "CONTRADICTED"
GATE_MIXED = "MIXED"
GATE_NOT_TESTABLE = "NOT_TESTABLE"
GATE_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

# Synthesis conclusion states (closed; no BEST_EXPLANATION / WINNER exists).
CONCL_SUPPORTED = "SUPPORTED_BY_AVAILABLE_EVIDENCE"
CONCL_MIXED = "MIXED_EVIDENCE"
CONCL_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
CONCL_NOT_TESTABLE = "NOT_TESTABLE"
CONCL_UNAVAILABLE = "UNAVAILABLE"

# Claim classes (structural, not free text).
CLAIM_OBSERVED = "OBSERVED"
CLAIM_DERIVED = "DERIVED"
CLAIM_INFERRED = "INFERRED"
CLAIM_MODELLED = "MODELLED"

# Counterfactual eligibility states.
CF_ELIGIBLE = "ELIGIBLE"
CF_INELIGIBLE = "INELIGIBLE"
CF_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
CF_TEL_UNAVAILABLE = "TELEMETRY_UNAVAILABLE"
CF_UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"

# Evidence-conflict taxonomy.
CONFLICT_DIRECT = "DIRECT_CONTRADICTION"
CONFLICT_UNRESOLVED = "UNRESOLVED"

# Investigation lifecycle (InvestigationState vocabulary is REUSED
# symbolically as trace steps; the legacy LLM engine is not invoked).
LIFECYCLE = (
    "CREATED", "FRAMING", "HYPOTHESIS_GENERATION", "EVIDENCE_PLANNING",
    "EVIDENCE_COLLECTION", "HYPOTHESIS_TESTING", "FALSIFICATION",
    "COUNTERFACTUAL_ANALYSIS", "SYNTHESIS", "VERIFICATION", "COMPLETED",
)

EPISTEMIC_BOUNDARIES = [
    "OBSERVED != DERIVED != INFERRED != MODELLED",
    "SUPPORT != PROOF",
    "NO_FALSIFICATION_FOUND != CONFIRMED",
    "SIMILARITY != CAUSALITY",
    "RECURRENCE != MECHANISM",
    "TEMPORAL_ALIGNMENT != CAUSAL_ATTRIBUTION",
    "MODEL_SENSITIVITY != HISTORICAL_EFFECT",
    "COUNTERFACTUAL != HISTORY",
    "MISSING_DATA != NEGATIVE_EVIDENCE",
    "NOT_TESTABLE != CONTRADICTED",
    "INSUFFICIENT_EVIDENCE != NOT_SUPPORTED",
    "residual is unresolved evidence and is never assigned to a hypothesis",
]

MAX_EVIDENCE_ITEMS = 40
MAX_COUNTERFACTUALS = 2
MIN_SEASON = 1950
MAX_SEASON = 2100
DEFAULT_SESSION = "RACE"

# Bounded lap-level 6F collection inside stint investigations (§9).
STINT_LAP_PROBE_LIMIT = 3
STINT_LAP_COLLECT_LIMIT = 2

# Statuses from the 6F fusion family that count as usable results.
FUSION_VALID = ("VALID_COMPARISON", "VALID_WITH_CAVEATS", "VALID")


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ---------------------------------------------------------------------------
# question framing & validation
# ---------------------------------------------------------------------------

def _validate_question(params: dict[str, Any]) -> dict[str, Any]:
    """Deterministic question framing. Returns base + status.

    VALID / UNAVAILABLE (data absent) / INVALID (malformed request).
    Never broadens the request.
    """
    base: dict[str, Any] = {
        "analysis": ANALYSIS,
        "version": INVESTIGATION_VERSION,
        "question": {
            "type": params.get("question_type"),
            "scope": {
                "season": params.get("season"),
                "round": params.get("round"),
                "driver_a": params.get("driver_a"),
                "driver_b": params.get("driver_b"),
                "lap_number": params.get("lap_number"),
                "stint_number": params.get("stint_number"),
                "session_type": params.get("session_type", DEFAULT_SESSION),
                "pattern_id": params.get("pattern_id"),
            },
        },
    }
    qt = params.get("question_type")
    if qt not in QUESTION_TYPES:
        return {**base, "status": "INVALID",
                "reason": f"question_type must be one of {list(QUESTION_TYPES)}"}

    da, db = params.get("driver_a"), params.get("driver_b")
    if not isinstance(da, str) or not da.strip() or \
            not isinstance(db, str) or not db.strip():
        return {**base, "status": "INVALID",
                "reason": "driver_a and driver_b are required"}
    if da == db:
        return {**base, "status": "INVALID",
                "reason": "driver_a and driver_b must be distinct"}

    season, rnd = params.get("season"), params.get("round")
    if not _finite(season) or int(season) < MIN_SEASON or int(season) > MAX_SEASON:
        return {**base, "status": "INVALID",
                "reason": f"season out of bounds [{MIN_SEASON}, {MAX_SEASON}]"}
    if not _finite(rnd) or int(rnd) < 1 or int(rnd) > 99:
        return {**base, "status": "INVALID",
                "reason": "round out of bounds [1, 99]"}
    season_i, round_i = int(season), int(rnd)

    ln, sn = params.get("lap_number"), params.get("stint_number")
    if ln is not None and (not _finite(ln) or int(ln) < 1):
        return {**base, "status": "INVALID", "reason": "lap_number must be >= 1"}
    if sn is not None and (not _finite(sn) or int(sn) < 1):
        return {**base, "status": "INVALID", "reason": "stint_number must be >= 1"}
    if ln is not None and sn is not None:
        return {**base, "status": "INVALID",
                "reason": "provide lap_number or stint_number, not both"}

    if qt in ("LAP_PERFORMANCE", "HYPOTHESIS_EVALUATION") and ln is None:
        return {**base, "status": "INVALID",
                "reason": f"{qt} requires lap_number"}
    if qt == "STINT_PERFORMANCE" and sn is None:
        return {**base, "status": "INVALID",
                "reason": "STINT_PERFORMANCE requires stint_number"}
    if qt == "CROSS_RACE_PATTERN" and not isinstance(
            params.get("pattern_id"), str):
        return {**base, "status": "INVALID",
                "reason": "CROSS_RACE_PATTERN requires pattern_id"}

    # race existence (canonical fact)
    results = params["queries"].get_results(season_i, round_i, DEFAULT_SESSION)
    if not results:
        return {**base, "status": "UNAVAILABLE",
                "reason": f"no canonical race result for {season_i} R{round_i}"}
    participants = {r["driver_key"] for r in results}
    if da not in participants or db not in participants:
        missing = sorted({da, db} - participants)
        return {**base, "status": "UNAVAILABLE",
                "reason": f"driver(s) not in the canonical race result: {missing}"}

    # data-derived lap/stint existence checks (never silent broadening):
    # a requested lap must exist in canonical lap times; a requested stint
    # must exist in canonical stints (canonical facts, not assumptions).
    if ln is not None:
        laps = {int(r["lap_number"])
                for r in params["queries"].get_lap_times(
                    season_i, round_i, DEFAULT_SESSION, da)}
        if int(ln) not in laps:
            return {**base, "status": "UNAVAILABLE",
                    "reason": (f"lap {int(ln)} has no canonical lap time for "
                                f"{da} in {season_i} R{round_i}")}
    if sn is not None:
        stints = {int(r.get("stint_number", 0))
                  for r in params["queries"].get_stints(
                      season_i, round_i, DEFAULT_SESSION, da)}
        if int(sn) not in stints:
            return {**base, "status": "UNAVAILABLE",
                    "reason": (f"stint {int(sn)} not present for {da} in "
                                f"{season_i} R{round_i}")}
    return {**base, "status": "VALID"}


# ---------------------------------------------------------------------------
# evidence ledger
# ---------------------------------------------------------------------------

def _opt_str(value: Any) -> Optional[str]:
    """Pass-through str() for present values; None stays None (never 'None')."""
    return None if value is None else str(value)


def _evidence_item(
    evidence_id: str,
    *,
    evidence_type: str,
    source_phase: str,
    source_tool: str,
    source_reference: dict[str, Any],
    claim: str,
    claim_class: str,
    measured_value: Any,
    units: Optional[str],
    state: str,
    hypothesis_ids: list[str],
    assumptions: list[str],
    limitations: list[str],
    supports: bool,
    contradicts: bool,
) -> dict[str, Any]:
    """One ledger item. claim_class is structural (OBSERVED/DERIVED/
    INFERRED/MODELLED) — the classes are never merged into one statement."""
    return {
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "source_phase": source_phase,
        "source_tool": source_tool,
        "source_reference": source_reference,
        "source_hash": _hash_obj(source_reference),
        "claim": claim,
        "claim_class": claim_class,
        "measured_value": measured_value,
        "units": units,
        "state": state,
        "hypothesis_ids": hypothesis_ids,
        "assumptions": assumptions,
        "limitations": limitations,
        "supports": supports,
        "contradicts": contradicts,
    }


# ---------------------------------------------------------------------------
# 6F state mapping (same deterministic contract as Phase 6M)
# ---------------------------------------------------------------------------

def _map_summary(summary: Any, counts: dict[str, Any]) -> str:
    """Map a 6G/6H summary (+ lap-level counts) to the 6F vocabulary."""
    if summary == "NOT_TESTABLE":
        return "NOT_TESTABLE"
    supported = int((counts or {}).get("supported_count", 0)) + \
        int((counts or {}).get("partially_supported_count", 0))
    contradicted = int((counts or {}).get("contradicted_count", 0))
    observations = int((counts or {}).get("valid_observations", 0))
    if summary in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED"):
        return "SUPPORTED"
    if summary == "INTERMITTENTLY_SUPPORTED":
        return "CONTRADICTED" if contradicted > 0 else "PARTIALLY_SUPPORTED"
    if summary == "CONTRADICTED_OVER_TIME":
        return "NOT_SUPPORTED"
    if summary == "NOT_SUPPORTED":
        return "NOT_SUPPORTED"
    if observations <= 0:
        return "INSUFFICIENT_EVIDENCE"
    if supported > 0 and contradicted > 0:
        return "CONTRADICTED"
    if supported > 0:
        return "PARTIALLY_SUPPORTED"
    return "NOT_SUPPORTED"


def _summary_counts(entry: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(entry, dict):
        return entry.get("summary"), entry.get("counts", {}) or {}
    return entry, {}


# ---------------------------------------------------------------------------
# hypothesis evaluation + falsification gate
# ---------------------------------------------------------------------------

def _evaluate_hypotheses(
    ledger: list[dict[str, Any]],
    hypotheses: Optional[tuple[str, ...]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Per-hypothesis evaluation over ledger items + falsification gate.

    Aggregate rules (documented, deterministic; 6F states preserved):
      - not requested by the framing                -> NOT_REQUESTED
        (reported; never silently removed)
      - no ledger items for the hypothesis          -> NOT_TESTABLE
      - only INSUFFICIENT/UNAVAILABLE-flavored items-> INSUFFICIENT_EVIDENCE
      - supports and contradicts both present       -> CONTRADICTED when a
        DIRECT_CONTRADICTION conflict exists, else MIXED_EVIDENCE
      - supports only                               -> SUPPORTED, or
        PARTIALLY_SUPPORTED when non-decisive items exist
      - contradicts only                            -> NOT_SUPPORTED
    A hypothesis with unresolved contradictions can NOT be synthesized as
    an established explanation. SUPPORT != PROOF.
    """
    evaluations: dict[str, dict[str, Any]] = {}
    conflict_ids = {c for c in (e["evidence_id"] for e in ledger
                                if e["evidence_type"] == "CONFLICT")}
    for h in HYPOTHESIS_IDS:
        requested = hypotheses is None or h in hypotheses
        items = [e for e in ledger if h in e["hypothesis_ids"]]
        supporting = [e for e in items if e["supports"]]
        contradicting = [e for e in items if e["contradicts"]]
        neutral = [e for e in items if not e["supports"] and not e["contradicts"]]
        decisive = [e for e in items
                    if e["state"] not in ("INSUFFICIENT_EVIDENCE", "UNAVAILABLE",
                                          "NOT_TESTABLE")]

        if not requested:
            agg = AGG_NOT_REQUESTED
        elif not items:
            agg = AGG_NOT_TESTABLE
        elif not decisive:
            # tested but uninformative (only NOT_TESTABLE/INSUFFICIENT/
            # UNAVAILABLE states) — genuinely insufficient evidence
            agg = AGG_INSUFFICIENT
        elif supporting and contradicting:
            direct = any(e["evidence_id"] in conflict_ids
                         for e in contradicting) or \
                any(e["evidence_id"] in conflict_ids for e in supporting)
            agg = AGG_CONTRADICTED if direct else AGG_MIXED
        elif supporting:
            agg = AGG_PARTIAL if neutral else AGG_SUPPORTED
        elif contradicting:
            agg = AGG_NOT_SUPPORTED
        else:
            # decisive items exist but none supports and none contradicts —
            # NOT_TESTABLE/UNAVAILABLE evidence on tested hypotheses stays
            # with the insufficiency family, never negative support
            agg = AGG_INSUFFICIENT

        # falsification gate (a hypothesis with unresolved contradictions
        # cannot be synthesized as an established explanation)
        if agg == AGG_CONTRADICTED:
            gate = GATE_CONTRADICTED
        elif agg == AGG_MIXED:
            gate = GATE_MIXED
        elif agg in (AGG_SUPPORTED, AGG_PARTIAL):
            gate = GATE_SUPPORTED
        elif agg == AGG_NOT_SUPPORTED:
            gate = GATE_MIXED
        elif agg == AGG_NOT_REQUESTED:
            gate = GATE_NOT_TESTABLE
        elif agg == AGG_INSUFFICIENT:
            gate = GATE_INSUFFICIENT
        else:
            gate = GATE_NOT_TESTABLE

        evaluations[h] = {
            "hypothesis_id": h,
            "requested": requested,
            "aggregate_state": agg,
            "supporting_evidence": [e["evidence_id"] for e in supporting],
            "contradicting_evidence": [e["evidence_id"] for e in contradicting],
            "non_decisive_evidence": [e["evidence_id"] for e in neutral],
            "evidence_coverage": {
                "items_total": len(items),
                "supporting": len(supporting),
                "contradicting": len(contradicting),
                "non_decisive": len(neutral),
            },
            "falsification_status": gate,
            "unresolved_contradictions": agg in (AGG_CONTRADICTED, AGG_MIXED),
        }

    unresolved = [h for h, v in evaluations.items()
                  if v["unresolved_contradictions"]]
    gate = {
        "any_unresolved_contradictions": bool(unresolved),
        "hypotheses_with_unresolved_contradictions": unresolved,
        "establishable_hypotheses": [
            h for h, v in evaluations.items()
            if v["aggregate_state"] in (AGG_SUPPORTED, AGG_PARTIAL)
            and not v["unresolved_contradictions"]
        ],
        "rule": (
            "A hypothesis with unresolved contradictions is not synthesized "
            "as an established explanation. An established state is "
            "evidence-consistency, never proof."
        ),
    }
    return evaluations, gate


# ---------------------------------------------------------------------------
# counterfactual eligibility (no execution here)
# ---------------------------------------------------------------------------

def _stint_probe_laps(
    queries: CanonicalQueries, season_i: int, round_i: int,
    session_type: str, da: str, db: str, stint: int,
) -> list[int]:
    """First selected 6G laps of the stint (bounded probe set)."""
    from racewise.data.historical.stint_evidence import fuse_stint_evidence
    res = fuse_stint_evidence(queries, season_i, round_i, da, db, stint,
                              session_type)
    return list(((res.get("provenance") or {}).get("selected_laps") or [])
                [:STINT_LAP_PROBE_LIMIT])


def _counterfactual_eligibility(
    queries: CanonicalQueries,
    base: dict[str, Any],
    max_counterfactuals: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bounded candidate set with explicit eligibility.

    Only speed-profile lap/stint interventions through the exact 6I model
    are ever ELIGIBLE. Race-level telemetry extrapolation is structurally
    INELIGIBLE. Nothing is executed here.
    """
    q = base["question"]["scope"]
    season_i = int(q["season"])
    round_i = int(q["round"])
    candidates: list[dict[str, Any]] = []

    def _cand(kind: str, **kw: Any) -> dict[str, Any]:
        req: dict[str, Any] = {
            "season": season_i, "round": round_i,
            "session_type": q["session_type"], "kind": kind, **kw,
        }
        c: dict[str, Any] = {
            "candidate_id": _hash_obj(req),
            "kind": kind,
            "request": req,
            "required_data": [
                "paired target/reference speed telemetry for the same laps",
                "clean comparable lap classification (6E context exclusions)",
            ],
            "telemetry_required": True,
            "baseline_available": None,
            "intervention_valid": None,
            "model_scope": ("single-lap speed-profile (6I)" if kind == "LAP_SPEED_PROFILE"
                            else "stint aggregate of validated single-lap 6I counterfactuals"),
            "status": None,
            "reason": None,
            "missing_data": [],
        }
        if kind == "RACE_LEVEL":
            c.update(baseline_available=False, intervention_valid=False,
                     status=CF_INELIGIBLE,
                     reason="race-level telemetry extrapolation is "
                            "structurally ineligible (no per-lap model; "
                            "6I is lap/stint-scoped)")
            c["missing_data"] = ["per-lap model scope"]
            return c
        signal = kw.get("signal", "speed")
        itype = kw.get("intervention_type", "REMOVE_DEFICIT")
        if signal != "speed":
            c.update(status=CF_UNSUPPORTED_MODEL,
                     reason=f"signal '{signal}' has no lap-time model "
                            "(6I unmodeled signals)")
            c["missing_data"] = [f"no model for signal '{signal}'"]
            return c
        if itype not in ("REMOVE_DEFICIT", "BLEND_WITH_REFERENCE",
                         "SCALE_SIGNAL"):
            c.update(status=CF_INELIGIBLE,
                     reason=f"unsupported intervention type '{itype}'")
            return c
        # probe telemetry availability with the exact 6I extraction path
        from racewise.data.historical.counterfactual import extract_speed_profile
        if kind == "LAP_SPEED_PROFILE":
            probe_laps = [int(kw["lap_number"])]
        else:
            probe_laps = _stint_probe_laps(
                queries, season_i, round_i, q["session_type"],
                q["driver_a"], q["driver_b"], int(kw["stint_number"]))
            if not probe_laps:
                c.update(status=CF_INSUFFICIENT,
                         reason="stint has no selectable comparable laps (6G)")
                c["missing_data"] = ["comparable stint laps"]
                return c
        profile = None
        for lap in probe_laps:
            profile = extract_speed_profile(
                queries, season_i, round_i, q["session_type"],
                kw["driver"], lap)
            if isinstance(profile, dict) and profile.get("values"):
                break
        if not (isinstance(profile, dict) and profile.get("values")):
            c.update(status=CF_TEL_UNAVAILABLE,
                     reason="no extractable paired speed profile on the "
                            "probe laps (6I extraction returned "
                            f"{'no profile' if profile is None else 'thin data'})")
            c["missing_data"] = ["paired telemetry speed profiles"]
            return c
        c.update(baseline_available=True, intervention_valid=True,
                 status=CF_ELIGIBLE,
                 reason="6I speed-profile model covers this scope")
        c["probe_laps"] = probe_laps
        return c

    lap = q.get("lap_number")
    stint = q.get("stint_number")
    if lap is not None:
        candidates.append(_cand(
            "LAP_SPEED_PROFILE",
            driver=q["driver_a"], reference_driver=q["driver_b"],
            lap_number=int(lap), signal="speed",
            intervention_type="REMOVE_DEFICIT"))
    elif stint is not None:
        candidates.append(_cand(
            "STINT_SPEED_PROFILE",
            driver=q["driver_a"], reference_driver=q["driver_b"],
            stint_number=int(stint), signal="speed",
            intervention_type="REMOVE_DEFICIT"))
    else:
        candidates.append(_cand("RACE_LEVEL"))

    eligible = [c for c in candidates if c["status"] == CF_ELIGIBLE]
    return eligible[:max(0, int(max_counterfactuals))], candidates


def _execute_counterfactuals(
    queries: CanonicalQueries,
    eligible: list[dict[str, Any]],
    base: dict[str, Any],
) -> list[dict[str, Any]]:
    """Execute ONLY eligible candidates through the exact 6I simulators.

    Results stay MODELLED: model sensitivity to the specified
    intervention — never a historical fact, never a prediction.
    """
    executed: list[dict[str, Any]] = []
    from racewise.data.historical.counterfactual import (
        simulate_stint_counterfactual, simulate_telemetry_counterfactual,
    )
    for cand in eligible:
        req = cand["request"]
        if req["kind"] == "LAP_SPEED_PROFILE":
            res = simulate_telemetry_counterfactual(
                queries, req["season"], req["round"], req["driver"],
                req["lap_number"], req["signal"], req["intervention_type"],
                0.5, reference_driver=req["reference_driver"],
                session_type=req["session_type"])
            executed.append({
                "candidate_id": cand["candidate_id"],
                "kind": req["kind"],
                "baseline": "6I-extracted paired speed profile "
                            "(identity-checked inside 6I)",
                "intervention": {"type": req["intervention_type"],
                                 "fraction": 0.5},
                "parameter": {"signal": req["signal"], "fraction": 0.5},
                "model": "6I fixed-distance segment integration "
                         "(piecewise-linear speed trace)",
                "result": res,
                "delta_s": res.get("counterfactual_delta_s"),
                "claim_class": CLAIM_MODELLED,
                "epistemics": (
                    "MODELLED model sensitivity to the specified "
                    "intervention; not history, not prediction, "
                    "not causation"),
            })
        else:
            res = simulate_stint_counterfactual(
                queries, req["season"], req["round"], req["driver"],
                req["reference_driver"], req["stint_number"], req["signal"],
                req["intervention_type"], 0.5,
                session_type=req["session_type"])
            executed.append({
                "candidate_id": cand["candidate_id"],
                "kind": req["kind"],
                "baseline": "6G-selected common telemetry-covered laps",
                "intervention": {"type": req["intervention_type"],
                                 "fraction": 0.5},
                "parameter": {"signal": req["signal"], "fraction": 0.5},
                "model": "6I stint aggregate (per-lap validated "
                         "counterfactuals)",
                "result": res,
                "delta_s": (res.get("aggregate") or {}).get("mean_delta_s"),
                "claim_class": CLAIM_MODELLED,
                "epistemics": (
                    "MODELLED aggregate sensitivity over the sampled "
                    "laps; not history, not prediction, not causation"),
            })
    return executed


# ---------------------------------------------------------------------------
# evidence collection per question type
# ---------------------------------------------------------------------------

def _collect_evidence(
    queries: CanonicalQueries,
    base: dict[str, Any],
    max_evidence_items: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Collect the evidence ledger using ONLY existing analytical layers.

    Returns (ledger, raw_layer_statuses, collection_status). Any layer
    failure is recorded explicitly and never silently becomes prose.
    """
    q = base["question"]["scope"]
    qt = base["question"]["type"]
    season_i, round_i = int(q["season"]), int(q["round"])
    da, db = q["driver_a"], q["driver_b"]
    ledger: list[dict[str, Any]] = []
    raw: dict[str, Any] = {}
    n = 0

    def _add(**kw: Any) -> None:
        nonlocal n
        if n >= max_evidence_items:
            return
        n += 1
        ledger.append(_evidence_item(f"evidence_{n:03d}", **kw))

    def _add_hyp_state(source_phase: str, tool: str, hyp: str, st: str,
                       ref: dict[str, Any], limitations: list[str]) -> None:
        """One formal hypothesis-evaluation item (shared by all layers)."""
        supportive = st in ("SUPPORTED", "PARTIALLY_SUPPORTED")
        _add(
            evidence_type="INFERENCE",
            source_phase=source_phase, source_tool=tool,
            source_reference=ref,
            claim=f"formal evaluation of {hyp}",
            claim_class=CLAIM_INFERRED,
            measured_value=None, units=None, state=st,
            hypothesis_ids=[hyp],
            assumptions=["documented formal rules (no weighted scores)"],
            limitations=limitations,
            supports=supportive,
            contradicts=st == "CONTRADICTED")

    def _add_lap_items(res: dict[str, Any], lap: int) -> None:
        """Ledger items from one usable 6F lap fusion (§9/§11)."""
        base_ref = {"analysis": "fuse_lap_evidence", "season": season_i,
                    "round": round_i, "lap_number": lap,
                    "drivers": [da, db]}
        _add(
            evidence_type="FACT", source_phase="6E",
            source_tool="attribute_lap_loss",
            source_reference={**base_ref, "kind": "observed_delta"},
            claim=f"observed lap delta at lap {lap} ({da} vs {db})",
            claim_class=CLAIM_OBSERVED,
            measured_value=res.get("observed_delta_s"), units="s",
            state="OBSERVED", hypothesis_ids=[],
            assumptions=[], limitations=[],
            supports=False, contradicts=False)
        for sec in (res.get("authoritative_sector_decomposition") or []):
            if sec.get("delta_s") is None:
                continue
            _add(
                evidence_type="CALCULATION", source_phase="6E",
                source_tool="attribute_lap_loss",
                source_reference={**base_ref,
                                  "kind": "region",
                                  "region": sec.get("region")},
                claim=f"derived region loss ({sec.get('region')})",
                claim_class=CLAIM_DERIVED,
                measured_value=sec.get("delta_s"), units="s",
                state="OBSERVED",
                hypothesis_ids=["H1_corner_speed", "H2_throttle",
                                "H3_braking"],
                assumptions=["straight-line region loss model"],
                limitations=["speed-trace estimate, not a causal "
                             "decomposition"],
                supports=(sec.get("delta_s") or 0) > 0, contradicts=False)
        if res.get("residual_s") is not None:
            _add(
                evidence_type="CALCULATION", source_phase="6E",
                source_tool="attribute_lap_loss",
                source_reference={**base_ref, "kind": "residual"},
                claim="unexplained residual component (reported, "
                      "never assigned)",
                claim_class=CLAIM_DERIVED,
                measured_value=res.get("residual_s"), units="s",
                state=_opt_str(res.get("residual_class")),
                hypothesis_ids=list(HYPOTHESIS_IDS),
                assumptions=[],
                limitations=["residual is unresolved evidence, "
                             "never assigned"],
                supports=False, contradicts=False)
        hyp_out = {h["hypothesis_id"]: h
                   for h in (res.get("hypotheses") or [])}
        for h in HYPOTHESIS_IDS:
            blk = hyp_out.get(h)
            if blk is None:
                continue
            st = blk["status"]
            _add_hyp_state(
                "6F", "fuse_lap_evidence", h, st,
                {**base_ref, "kind": "hypothesis", "hypothesis": h,
                 "supporting_sources": blk.get("supporting", []),
                 "contradicting_sources": blk.get("contradicting", [])},
                ["evidence-consistency, not causation"])

    def _fuse_one_lap(lap: int) -> Optional[dict[str, Any]]:
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence
        res = fuse_lap_evidence(queries, season_i, round_i, da, db, lap,
                                q["session_type"])
        raw.setdefault("fuse_lap_evidence", []).append(
            {"lap": lap, "status": res.get("status")})
        if res.get("status") not in FUSION_VALID:
            return None
        return res

    def _collect_lap() -> Optional[str]:
        res = _fuse_one_lap(int(q["lap_number"]))
        if res is None:
            return "INSUFFICIENT_EVIDENCE"
        _add_lap_items(res, int(q["lap_number"]))
        return None

    def _collect_stint() -> Optional[str]:
        from racewise.data.historical.stint_evidence import fuse_stint_evidence
        res = fuse_stint_evidence(queries, season_i, round_i, da, db,
                                  int(q["stint_number"]), q["session_type"])
        raw["fuse_stint_evidence"] = {"status": res.get("status")}
        if res.get("status") not in FUSION_VALID:
            return str(res.get("status", "INSUFFICIENT_EVIDENCE"))
        base_ref = {"analysis": "fuse_stint_evidence", "season": season_i,
                    "round": round_i, "stint_number": int(q["stint_number"]),
                    "drivers": [da, db]}
        trend = res.get("trend") or {}
        _add(
            evidence_type="CALCULATION", source_phase="6G",
            source_tool="fuse_stint_evidence",
            source_reference={**base_ref, "kind": "trend"},
            claim=f"stint {int(q['stint_number'])} delta OLS slope "
                  f"({da} vs {db})",
            claim_class=CLAIM_DERIVED,
            measured_value=trend.get("slope_s_per_lap"), units="s/lap",
            state=_opt_str(trend.get("classification")),
            hypothesis_ids=[],
            assumptions=["OLS over telemetry-covered comparable laps"],
            limitations=["slope is a measured trend, not a cause"],
            supports=False, contradicts=False)
        for h, ev in (res.get("hypothesis_evolution") or {}).items():
            summ, counts = _summary_counts(ev)
            st = _map_summary(summ, counts)
            _add_hyp_state(
                "6G", "fuse_stint_evidence", h, st,
                {**base_ref, "kind": "hypothesis_evolution",
                 "hypothesis": h, "summary": summ, "counts": counts},
                ["evidence-consistency, not causation"])
        cum = (res.get("residual_accounting") or {}).get(
            "cumulative_residual_s")
        if cum is not None:
            _add(
                evidence_type="CALCULATION", source_phase="6G",
                source_tool="fuse_stint_evidence",
                source_reference={**base_ref,
                                  "kind": "cumulative_residual"},
                claim="cumulative stint residual (conserved; unresolved)",
                claim_class=CLAIM_DERIVED,
                measured_value=cum, units="s", state="UNRESOLVED",
                hypothesis_ids=[],
                assumptions=["cumulative conservation identity"],
                limitations=["never assigned to any hypothesis"],
                supports=False, contradicts=False)
        # §9: bounded lap-level 6F evidence on the stint's own selected laps
        # (per-source provenance preserved separately; never merged into the
        # stint-level statements)
        selected = ((res.get("provenance") or {}).get("selected_laps") or [])
        collected = 0
        for lap in selected[:STINT_LAP_PROBE_LIMIT]:
            if collected >= STINT_LAP_COLLECT_LIMIT:
                break
            lap_res = _fuse_one_lap(int(lap))
            if lap_res is None:
                continue
            collected += 1
            _add_lap_items(lap_res, int(lap))
        return None

    def _collect_race_gap() -> Optional[str]:
        from racewise.data.historical.race_gap import decompose_race_gap
        res = decompose_race_gap(queries, season_i, round_i, da, db,
                                 q["session_type"])
        raw["decompose_race_gap"] = {"status": res.get("status")}
        if res.get("status") not in FUSION_VALID:
            return str(res.get("status", "INSUFFICIENT_EVIDENCE"))
        base_ref = {"analysis": "decompose_race_gap", "season": season_i,
                    "round": round_i, "drivers": [da, db]}
        official = res.get("official_result") or {}
        for side in ("driver_a", "driver_b"):
            blk = official.get(side) or {}
            if blk.get("position") is not None:
                _add(
                    evidence_type="FACT", source_phase="6H",
                    source_tool="decompose_race_gap",
                    source_reference={**base_ref, "kind": "official_result",
                                      "side": side},
                    claim=f"official classification for {side} "
                          f"(position {blk.get('position')})",
                    claim_class=CLAIM_OBSERVED,
                    measured_value=blk.get("position"), units="position",
                    state="OBSERVED", hypothesis_ids=[],
                    assumptions=["official classification is canonical"],
                    limitations=["a finishing classification is not a "
                                 "per-lap performance model"],
                    supports=False, contradicts=False)
        ms_a = (official.get("driver_a") or {}).get("milliseconds")
        ms_b = (official.get("driver_b") or {}).get("milliseconds")
        if _finite(ms_a) and _finite(ms_b):
            _add(
                evidence_type="CALCULATION", source_phase="6H",
                source_tool="decompose_race_gap",
                source_reference={**base_ref, "kind": "official_ms_diff"},
                claim="official classified time difference (B - A)",
                claim_class=CLAIM_DERIVED,
                measured_value=round((int(ms_b) - int(ms_a)) / 1000.0, 3),
                units="s", state="OBSERVED", hypothesis_ids=[],
                assumptions=["canonical result milliseconds"],
                limitations=["a finishing gap is not a per-lap model"],
                supports=False, contradicts=False)
        residual = res.get("residual_accounting") or {}
        if residual.get("cumulative_comparable_gap_s") is not None:
            _add(
                evidence_type="CALCULATION", source_phase="6H",
                source_tool="decompose_race_gap",
                source_reference={**base_ref, "kind": "analytical_gap"},
                claim="analytical cumulative comparable gap",
                claim_class=CLAIM_DERIVED,
                measured_value=residual.get("cumulative_comparable_gap_s"),
                units="s", state="OBSERVED", hypothesis_ids=[],
                assumptions=["comparable-lap selection (context exclusions)"],
                limitations=["different quantity from the official gap; "
                             "no forced reconciliation"],
                supports=False, contradicts=False)
        ts = res.get("timeline_summary") or {}
        if ts.get("total_laps") is not None:
            _add(
                evidence_type="CALCULATION", source_phase="6H",
                source_tool="decompose_race_gap",
                source_reference={**base_ref, "kind": "timeline_coverage"},
                claim="timeline lap coverage (comparable / non-comparable / "
                      "unavailable)",
                claim_class=CLAIM_DERIVED,
                measured_value={"comparable": ts.get("comparable"),
                                "non_comparable": ts.get("non_comparable"),
                                "unavailable": ts.get("unavailable")},
                units="laps", state="OBSERVED", hypothesis_ids=[],
                assumptions=["deterministic lap-context classification"],
                limitations=["non-comparable intervals are itemized, "
                             "never extrapolated"],
                supports=False, contradicts=False)
        for h, ev in (res.get("hypothesis_evolution") or {}).items():
            summ, _counts = _summary_counts(ev)
            st = _map_summary(summ, {})
            _add_hyp_state(
                "6H", "decompose_race_gap", h, st,
                {**base_ref, "kind": "race_hypothesis", "hypothesis": h,
                 "summary": summ},
                ["stint-aggregated evidence-consistency, not causation"])
        return None

    def _collect_regimes() -> Optional[str]:
        from racewise.data.historical.performance_regimes import (
            analyze_performance_regimes)
        res = analyze_performance_regimes(queries, season_i, round_i, da, db)
        raw["analyze_performance_regimes"] = {"status": res.get("status")}
        if res.get("status") != "VALID":
            return str(res.get("status", "INSUFFICIENT_EVIDENCE"))
        for g in (res.get("regimes") or [])[:6]:
            g_ref = {"analysis": "analyze_performance_regimes",
                     "season": season_i, "round": round_i,
                     "regime": {"start_lap": g.get("start_lap"),
                                "end_lap": g.get("end_lap"),
                                "regime_index":
                                    (g.get("provenance") or {}).get(
                                        "regime_index")}}
            slope = (g.get("trend") or {}).get("slope_s_per_lap")
            _add(
                evidence_type="CALCULATION", source_phase="6K",
                source_tool="analyze_performance_regimes",
                source_reference={**g_ref, "kind": "trend"},
                claim=f"regime laps {g.get('start_lap')}-"
                      f"{g.get('end_lap')} delta slope ({da} vs {db})",
                claim_class=CLAIM_DERIVED,
                measured_value=slope, units="s/lap",
                state=_opt_str((g.get("trend") or {}).get("classification")),
                hypothesis_ids=[],
                assumptions=["regime-local OLS (6G semantics)"],
                limitations=["regime is an analytical structure, "
                             "not a stint"],
                supports=False, contradicts=False)
            for h, ev in (g.get("hypothesis_state_summary") or {}).items():
                summ, counts = _summary_counts(ev)
                st = _map_summary(summ, counts)
                _add_hyp_state(
                    "6K", "analyze_performance_regimes", h, st,
                    {**g_ref, "kind": "hypothesis", "hypothesis": h,
                     "summary": summ, "counts": counts},
                    ["small regime lap sets often yield "
                     "INSUFFICIENT_EVIDENCE honestly"])
        return None

    def _collect_pattern() -> Optional[str]:
        from racewise.data.historical.performance_evidence import (
            analyze_cross_race_pattern_evidence)
        from racewise.data.historical.performance_patterns import (
            analyze_cross_race_performance_patterns)
        pat = analyze_cross_race_performance_patterns(queries, da, db,
                                                      max_races=8)
        raw["analyze_cross_race_performance_patterns"] = {
            "status": pat.get("status"),
            "patterns": len(pat.get("patterns") or [])}
        if q.get("pattern_id") and pat.get("status") != "VALID":
            # a requested pattern cannot be verified against an unavailable
            # corpus scan: preserve UNAVAILABLE (no silent broadening)
            return "UNAVAILABLE"
        if pat.get("status") != "VALID" or not pat.get("patterns"):
            return "INSUFFICIENT_EVIDENCE"
        target = None
        pid = q.get("pattern_id")
        for p in pat.get("patterns", []):
            if p.get("pattern_id") == pid:
                target = p
                break
        if target is None:
            if pid:
                return "UNAVAILABLE"
            target = pat["patterns"][0]
        _add(
            evidence_type="FACT", source_phase="6L",
            source_tool="analyze_cross_race_performance_patterns",
            source_reference={
                "analysis": "analyze_cross_race_performance_patterns",
                "pattern_id": target.get("pattern_id"),
                "occurrence_count": target.get("occurrence_count"),
                "recurrence": target.get("recurrence_classification")},
            claim="recurring structural performance pattern (observed in "
                  "N independent race instances)",
            claim_class=CLAIM_OBSERVED,
            measured_value=target.get("occurrence_count"), units="races",
            state=_opt_str(target.get("recurrence_classification")),
            hypothesis_ids=[],
            assumptions=["structural signature matching "
                         "(documented thresholds)"],
            limitations=["recurrence is an observation, not a mechanism"],
            supports=False, contradicts=False)
        ev = analyze_cross_race_pattern_evidence(
            queries, da, db, target["pattern_id"], max_races=8)
        raw["analyze_cross_race_pattern_evidence"] = {
            "status": ev.get("status")}
        if ev.get("status") != "VALID":
            return str(ev.get("status", "INSUFFICIENT_EVIDENCE"))
        for prof in (ev.get("hypothesis_profiles") or []):
            h = prof.get("hypothesis_id")
            if not h:
                continue
            agg = prof.get("aggregate_state")
            supportive = agg in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED")
            _add(
                evidence_type="INFERENCE", source_phase="6M",
                source_tool="analyze_cross_race_pattern_evidence",
                source_reference={
                    "analysis": "analyze_cross_race_pattern_evidence",
                    "pattern_id": target.get("pattern_id"),
                    "hypothesis": h,
                    "aggregate_state": agg,
                    "supporting_occurrence_refs":
                        prof.get("supporting_occurrence_refs"),
                    "contradicting_occurrence_refs":
                        prof.get("contradicting_occurrence_refs")},
                claim=f"6M cross-race aggregate of {h} for the "
                      "recurring pattern",
                claim_class=CLAIM_INFERRED,
                measured_value=None, units=None, state=agg,
                hypothesis_ids=[h],
                assumptions=["documented 6M aggregation rules"],
                limitations=["consistency across races is not causation"],
                supports=supportive,
                contradicts=agg == "CONTRADICTORY")
        return None

    err: Optional[str] = None
    if qt == "LAP_PERFORMANCE":
        err = _collect_lap()
    elif qt == "STINT_PERFORMANCE":
        err = _collect_stint()
    elif qt == "RACE_GAP":
        err = _collect_race_gap()
    elif qt == "PERFORMANCE_REGIME":
        err = _collect_regimes()
    elif qt == "CROSS_RACE_PATTERN":
        err = _collect_pattern()
    elif qt == "HYPOTHESIS_EVALUATION":
        err = _collect_lap()
    elif qt == "COUNTERFACTUAL_ELIGIBILITY":
        err = None  # eligibility handled separately; ledger may stay empty
    return ledger, raw, (err or "OK")


# ---------------------------------------------------------------------------
# conflicts, synthesis, decision trace
# ---------------------------------------------------------------------------

def _evidence_conflicts(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairwise DIRECT_CONTRADICTION conflicts, preserved (never resolved
    away)."""
    conflicts: list[dict[str, Any]] = []
    n = 0
    sup = [e for e in ledger if e["supports"]]
    con = [e for e in ledger if e["contradicts"]]
    for s in sup:
        for c in con:
            overlap = sorted(set(s["hypothesis_ids"]) &
                             set(c["hypothesis_ids"]))
            if not overlap:
                continue
            n += 1
            conflicts.append({
                "conflict_id": f"conflict_{n:03d}",
                "evidence_ids": [s["evidence_id"], c["evidence_id"]],
                "hypothesis_ids": overlap,
                "conflict_type": CONFLICT_DIRECT,
                "description": (
                    f"{s['evidence_id']} ({s['source_phase']}) supports "
                    f"{','.join(overlap)} while {c['evidence_id']} "
                    f"({c['source_phase']}) contradicts it"),
                "resolution_status": CONFLICT_UNRESOLVED,
                "provenance": {"sources": [s["source_reference"],
                                           c["source_reference"]]},
            })
    return conflicts


def _decide_trace(
    trace_id: str,
    statement: str,
    basis: list[str],
    trace_type: str,
    hypotheses: list[str],
    contradictory: list[str],
    status: str,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "statement": statement,
        "basis": basis,
        "type": trace_type,
        "supporting_hypotheses": hypotheses,
        "contradictory_evidence": contradictory,
        "status": status,
    }


def _synthesize(
    base: dict[str, Any],
    ledger: list[dict[str, Any]],
    evaluations: dict[str, dict[str, Any]],
    gate: dict[str, Any],
    executed_cfs: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    collection_status: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Deterministic synthesis. Every statement carries a decision trace."""
    q = base["question"]["scope"]
    qt = base["question"]["type"]

    facts = [e for e in ledger if e["claim_class"] == CLAIM_OBSERVED]
    derived = [e for e in ledger if e["claim_class"] == CLAIM_DERIVED]

    if collection_status == "UNAVAILABLE" and not ledger:
        conclusion = CONCL_UNAVAILABLE
    elif collection_status == "INVALID":
        conclusion = CONCL_NOT_TESTABLE
    elif not ledger:
        conclusion = CONCL_INSUFFICIENT
    elif gate["any_unresolved_contradictions"]:
        conclusion = CONCL_MIXED
    elif any(v["aggregate_state"] in (AGG_SUPPORTED, AGG_PARTIAL)
             for v in evaluations.values()):
        conclusion = CONCL_SUPPORTED
    elif all(v["aggregate_state"] == AGG_NOT_REQUESTED
             for v in evaluations.values()):
        conclusion = CONCL_NOT_TESTABLE
    else:
        conclusion = CONCL_INSUFFICIENT

    trace: list[dict[str, Any]] = []
    tno = 0

    def _trace(statement: str, basis: list[str], ttype: str,
               hyps: list[str], contra: list[str], status: str) -> None:
        nonlocal tno
        tno += 1
        trace.append(_decide_trace(f"TRACE-{tno:03d}", statement, basis,
                                   ttype, hyps, contra, status))

    for f in facts:
        _trace(
            f"OBSERVED: {f['claim']}"
            + (f" = {f['measured_value']} {f['units']}"
               if f["measured_value"] is not None else ""),
            [f["evidence_id"]], "FACT", [], [], "ESTABLISHED")
    for d in derived:
        _trace(
            f"DERIVED ({d['source_phase']} {d['source_tool']}): "
            f"{d['claim']}"
            + (f" = {d['measured_value']} {d['units']}"
               if d["measured_value"] is not None else ""),
            [d["evidence_id"]], "DERIVED", d["hypothesis_ids"], [],
            "METHOD_IDENTIFIED")
    for c in conflicts:
        _trace(
            f"CONFLICT PRESERVED: {c['description']}",
            c["evidence_ids"], "CONFLICT", c["hypothesis_ids"],
            [c["evidence_ids"][1]], "UNRESOLVED")
    for h, ev in evaluations.items():
        if ev["aggregate_state"] == AGG_NOT_REQUESTED:
            _trace(
                f"{h}: not requested by this question framing "
                "(reported, never silently removed)",
                [], "HYPOTHESIS_STATUS", [h], [], AGG_NOT_REQUESTED)
            continue
        basis = ev["supporting_evidence"] + ev["contradicting_evidence"] + \
            ev["non_decisive_evidence"]
        _trace(
            f"{h}: aggregate {ev['aggregate_state']} "
            "(evidence-consistency, not causation)",
            basis, "HYPOTHESIS_STATUS", [h],
            ev["contradicting_evidence"], ev["aggregate_state"])
    for cf in executed_cfs:
        _trace(
            f"MODELLED: 6I counterfactual sensitivity {cf['delta_s']} s "
            f"under {cf['intervention']} (model property; not history, "
            "not prediction)",
            [f"evidence_cf_{cf['candidate_id'][:8]}"],
            "COUNTERFACTUAL", [], [], CLAIM_MODELLED)

    synthesis = {
        "question_restated": {"type": qt, "scope": dict(q)},
        "established_facts": [
            {"evidence_id": f["evidence_id"], "claim": f["claim"],
             "measured_value": f["measured_value"], "units": f["units"]}
            for f in facts
        ],
        "measured_findings": [
            {"evidence_id": d["evidence_id"], "claim": d["claim"],
             "measured_value": d["measured_value"], "units": d["units"],
             "method": f"{d['source_phase']} {d['source_tool']}"}
            for d in derived
        ],
        "hypothesis_findings": {
            h: {"aggregate_state": v["aggregate_state"],
                "falsification_status": v["falsification_status"],
                "supporting_evidence": v["supporting_evidence"],
                "contradicting_evidence": v["contradicting_evidence"]}
            for h, v in evaluations.items()
        },
        "contradictory_evidence": [
            {"evidence_id": e["evidence_id"], "claim": e["claim"],
             "hypothesis_ids": e["hypothesis_ids"]}
            for e in ledger if e["contradicts"]
        ],
        "unavailable_evidence": [
            {"evidence_id": e["evidence_id"], "claim": e["claim"],
             "state": e["state"]}
            for e in ledger
            if e["state"] in ("UNAVAILABLE", "NOT_TESTABLE",
                              "INSUFFICIENT_EVIDENCE")
        ],
        "counterfactual_findings": [
            {"candidate_id": cf["candidate_id"], "kind": cf["kind"],
             "delta_s": cf["delta_s"], "claim_class": CLAIM_MODELLED,
             "epistemics": cf["epistemics"]}
            for cf in executed_cfs
        ],
        "unresolved_questions": [],
        "conclusion_state": conclusion,
        "limitations": [],
        "decision_trace_refs": [t["trace_id"] for t in trace],
    }
    if conclusion == CONCL_INSUFFICIENT:
        synthesis["unresolved_questions"].append(
            "insufficient evidence to establish any hypothesis state "
            "beyond explicit insufficiency")
    if gate["any_unresolved_contradictions"]:
        synthesis["unresolved_questions"].append(
            "unresolved contradictions block an established explanation "
            "for: " + ", ".join(
                gate["hypotheses_with_unresolved_contradictions"]))
    synthesis["limitations"] = [
        "no falsification found is not confirmation",
        "model sensitivity is not historical effect",
        "residuals are reported, never assigned",
        "multiple hypotheses may remain viable simultaneously",
    ]
    return synthesis, trace


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def _invalid(base: dict[str, Any], reason: str) -> dict[str, Any]:
    base.update(status="INVALID", reason=reason)
    base["output_hash"] = _hash_obj({k: v for k, v in base.items()
                                     if k != "output_hash"})
    return base


def run_engineering_investigation(
    queries: CanonicalQueries,
    question_type: str,
    driver_a: str,
    driver_b: str,
    season: int,
    round_num: int,
    lap_number: Optional[int] = None,
    stint_number: Optional[int] = None,
    session_type: str = DEFAULT_SESSION,
    pattern_id: Optional[str] = None,
    hypotheses: Optional[list[str]] = None,
    max_evidence_items: int = MAX_EVIDENCE_ITEMS,
    max_counterfactuals: int = MAX_COUNTERFACTUALS,
) -> dict[str, Any]:
    """Deterministic engineering investigation over the 6E→6M chain.

    Derived-on-read; zero storage growth. Output is canonical apart from
    excluded runtime metadata. The conclusion is always evidence-bound;
    insufficient evidence ends INSUFFICIENT_EVIDENCE, never a fabricated
    explanation.
    """
    base_params = {
        "question_type": question_type,
        "driver_a": driver_a, "driver_b": driver_b,
        "season": season, "round": round_num,
        "lap_number": lap_number, "stint_number": stint_number,
        "session_type": session_type, "pattern_id": pattern_id,
    }
    framed = _validate_question({**base_params, "queries": queries})
    base: dict[str, Any] = dict(framed)

    if framed["status"] != "VALID":
        base["output_hash"] = _hash_obj(
            {k: v for k, v in base.items() if k != "output_hash"})
        return base

    hyp_tuple: Optional[tuple[str, ...]] = None
    if hypotheses is not None:
        bad = [h for h in hypotheses if h not in HYPOTHESIS_IDS]
        if bad:
            return _invalid(base, f"unknown hypothesis ids: {bad}")
        if not hypotheses:
            return _invalid(base, "hypotheses list is empty")
        hyp_tuple = tuple(hypotheses)

    if not (1 <= int(max_evidence_items) <= MAX_EVIDENCE_ITEMS):
        return _invalid(base, f"max_evidence_items out of bounds "
                              f"[1, {MAX_EVIDENCE_ITEMS}]")
    if not (0 <= int(max_counterfactuals) <= MAX_COUNTERFACTUALS):
        return _invalid(base, f"max_counterfactuals out of bounds "
                              f"[0, {MAX_COUNTERFACTUALS}]")

    # lifecycle trace (state-machine vocabulary reused; deterministic)
    lifecycle = [{"state": s, "status": "COMPLETED"} for s in LIFECYCLE]

    # 1-2 evidence collection
    ledger, raw, collection_status = _collect_evidence(
        queries, base, int(max_evidence_items))

    # 3-4 hypothesis evaluation + falsification gate
    evaluations, gate = _evaluate_hypotheses(ledger, hyp_tuple)

    # 5-6 counterfactual eligibility + bounded execution
    eligible, candidates = _counterfactual_eligibility(
        queries, base, int(max_counterfactuals))
    executed = _execute_counterfactuals(queries, eligible, base) \
        if eligible else []

    # integrate executed counterfactuals into the ledger as MODELLED items
    for cf in executed:
        if cf.get("delta_s") is None:
            continue
        ledger.append(_evidence_item(
            f"evidence_cf_{cf['candidate_id'][:8]}",
            evidence_type="COUNTERFACTUAL",
            source_phase="6I",
            source_tool="simulate_telemetry_counterfactual"
            if cf["kind"] == "LAP_SPEED_PROFILE"
            else "simulate_stint_counterfactual",
            source_reference={"analysis": "phase_6i_counterfactual",
                              "candidate_id": cf["candidate_id"],
                              "intervention": cf["intervention"],
                              "season": int(base["question"]["scope"]["season"]),
                              "round": int(base["question"]["scope"]["round"])},
            claim="model sensitivity to the specified speed-profile "
                  "intervention",
            claim_class=CLAIM_MODELLED,
            measured_value=cf.get("delta_s"), units="s",
            state="MODELLED",
            hypothesis_ids=["H1_corner_speed", "H2_throttle",
                            "H3_braking"],
            assumptions=["6I model gates passed"],
            limitations=["sensitivity is not historical effect"],
            supports=False, contradicts=False))

    conflicts = _evidence_conflicts(ledger)
    synthesis, trace = _synthesize(base, ledger, evaluations, gate,
                                   executed, conflicts, collection_status)

    investigation_id = _hash_obj({
        "analysis": ANALYSIS, "version": INVESTIGATION_VERSION,
        "question": base["question"],
        "pair": [driver_a, driver_b],
    })

    result: dict[str, Any] = {
        **base,
        "status": "VALID",
        "investigation_id": investigation_id,
        "investigation_version": INVESTIGATION_VERSION,
        "question_type": question_type,
        "hypotheses_in_scope": list(hyp_tuple or HYPOTHESIS_IDS),
        "evidence_plan": QUESTION_EVIDENCE_PLAN[question_type],
        "evidence_ledger": ledger,
        "collection": {
            "status": collection_status,
            "raw_layer_statuses": raw,
            "items_collected": len(ledger),
            "bounded_by": {
                "max_evidence_items": int(max_evidence_items),
                "max_counterfactuals": int(max_counterfactuals),
            },
        },
        "hypothesis_evaluations": evaluations,
        "falsification_gate": gate,
        "counterfactual_candidates": candidates,
        "executed_counterfactuals": executed,
        "evidence_conflicts": conflicts,
        "synthesis": synthesis,
        "decision_trace": trace,
        "lifecycle": lifecycle,
        "investigation_snapshot": {
            "input": base_params,
            "evidence_ids": [e["evidence_id"] for e in ledger],
            "evidence_source_hashes": {e["evidence_id"]: e["source_hash"]
                                       for e in ledger},
            "hypothesis_states": {h: v["aggregate_state"]
                                  for h, v in evaluations.items()},
            "counterfactual_ids": [c["candidate_id"] for c in executed],
        },
        "limitations": [
            "question framing is a closed vocabulary; no free-form logic",
            "counterfactuals run only when 6I-eligible; race-level "
            "extrapolation is structurally ineligible",
            "legacy LLM investigation engine is NOT invoked by this phase",
        ],
        "epistemic_boundaries": EPISTEMIC_BOUNDARIES,
        "provenance": {
            "analytical_chain": ["6E", "6F", "6G", "6H", "6I", "6J",
                                 "6K", "6L", "6M", "6N"],
            "method": "deterministic_investigation_orchestration",
            "investigation_version": INVESTIGATION_VERSION,
            "layers_executed": sorted(raw.keys()),
            "provider": "fastf1",
            "source_tables": [
                "canonical_results", "canonical_lap_times",
                "canonical_telemetry", "canonical_stints",
                "canonical_weather", "canonical_race_control",
                "canonical_pit_stops",
            ],
        },
    }
    hashable = {k: v for k, v in result.items() if k != "output_hash"}
    result["output_hash"] = _hash_obj(hashable)
    return result
