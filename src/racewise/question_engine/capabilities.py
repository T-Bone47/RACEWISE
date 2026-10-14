"""Machine-readable capability registry.

Every entry describes a capability RACEWISE *actually has*. Nothing here is
aspirational: each capability names the real deterministic tool that performs
it (``mcp_tool`` must exist in the ToolRegistry) and the real HTTP route that
exposes it (``api_route`` must be mounted in the API app). The test suite
enforces both, so the registry cannot drift into documenting capabilities the
product does not have — which is the failure mode a "capability registry" is
most prone to.

The question engine discovers capabilities from this registry rather than
hardcoding names, so adding a deterministic tool and one registry row is the
whole cost of extending what the engine can be asked to do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

REGISTRY_VERSION = "question_engine_capabilities_v1"

# Canonical data facets. These are the columns the canonical store actually
# reports availability for — inventing facets here would let the planner
# promise evidence that no provider can supply.
DATA_FACETS = (
    "results", "qualifying", "laps", "stints", "telemetry",
    "weather", "race_control", "pit_stops",
)

# Cost classes. The planner uses these to respect the analysis budget
# (cheap direct questions first; cross-race scans last).
COST_CLASSES = ("TRIVIAL", "LOW", "MODERATE", "EXPENSIVE")

# Hypothesis vocabulary — the six canonical engine hypotheses.
HYPOTHESIS_IDS = (
    "H1_corner_speed", "H2_throttle", "H3_braking",
    "H4_tyre_state", "H5_race_control", "H6_drs",
)

# Claim classes. Evidence is never silently promoted: a modelled number stays
# MODELLED and never becomes OBSERVED.
CLAIM_CLASSES = ("OBSERVED", "DERIVED", "INFERRED", "MODELLED")


@dataclass(frozen=True)
class Capability:
    """One deterministic engineering capability RACEWISE genuinely provides."""

    capability_id: str
    name: str
    description: str
    mcp_tool: str
    api_route: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    required_data: tuple[str, ...] = ()
    optional_data: tuple[str, ...] = ()
    supported_session_types: tuple[str, ...] = ("RACE",)
    supported_time_scopes: tuple[str, ...] = ("lap", "stint", "race")
    driver_relationships: tuple[str, ...] = ("driver_vs_driver",)
    prerequisites: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    computational_cost: str = "LOW"
    provenance_requirements: tuple[str, ...] = ()
    deterministic_version: str = "1.0.0"
    evidence_types_produced: tuple[str, ...] = ()
    hypothesis_types_supported: tuple[str, ...] = ()
    intents: tuple[str, ...] = ()
    analysis_levels: tuple[int, ...] = (2,)
    produces_corroboration: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "mcp_tool": self.mcp_tool,
            "api_route": self.api_route,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "required_data": list(self.required_data),
            "optional_data": list(self.optional_data),
            "supported_session_types": list(self.supported_session_types),
            "supported_time_scopes": list(self.supported_time_scopes),
            "driver_relationships": list(self.driver_relationships),
            "prerequisites": list(self.prerequisites),
            "limitations": list(self.limitations),
            "computational_cost": self.computational_cost,
            "provenance_requirements": list(self.provenance_requirements),
            "deterministic_version": self.deterministic_version,
            "evidence_types_produced": list(self.evidence_types_produced),
            "hypothesis_types_supported": list(self.hypothesis_types_supported),
            "intents": list(self.intents),
            "analysis_levels": list(self.analysis_levels),
            "produces_corroboration": self.produces_corroboration,
            "registry_version": REGISTRY_VERSION,
        }


# ---------------------------------------------------------------------------
# The registry.
#
# Ordered by analysis depth: context (0) -> comparison (1) -> attribution (2)
# -> hypotheses (3) -> temporal/regime (4) -> cross-race (5) -> counterfactual (6).
# ---------------------------------------------------------------------------
REGISTRY: tuple[Capability, ...] = (
    Capability(
        capability_id="resolve_session_context",
        name="Session context",
        description=(
            "Resolve a race session: circuit, weather, availability of every "
            "data facet, and the measured context both drivers carried into it."
        ),
        mcp_tool="get_historical_session",
        api_route="/api/catalog/session-context/{season}/{round}",
        inputs=("season", "round", "session_type"),
        outputs=("circuit", "weather", "availability", "grid", "driver_context"),
        optional_data=("results", "weather"),
        computational_cost="TRIVIAL",
        provenance_requirements=("source_provider", "session_id"),
        deterministic_version="1.0.0",
        intents=("DESCRIBE", "PROVENANCE"),
        analysis_levels=(0,),
    ),
    Capability(
        capability_id="compare_laps",
        name="Lap comparison",
        description=(
            "Compare two drivers' lap timing, sectors and context for a scope. "
            "The observed delta everything else explains."
        ),
        mcp_tool="compare_driver_pace",
        api_route="/api/catalog/telemetry-comparison/{season}/{round}",
        inputs=("season", "round", "driver_a", "driver_b", "lap_number"),
        outputs=("lap_time_s", "sector_times", "delta_s", "top_windows"),
        required_data=("laps",),
        optional_data=("telemetry",),
        supported_session_types=("RACE", "QUALIFYING"),
        computational_cost="LOW",
        provenance_requirements=("tool_execution", "output_hash"),
        evidence_types_produced=("OBSERVED",),
        intents=("COMPARE", "DESCRIBE", "QUANTIFY", "COMPARE_LAPS"),
        analysis_levels=(1,),
        produces_corroboration=True,
    ),
    Capability(
        capability_id="attribute_lap_loss",
        name="Lap loss attribution",
        description=(
            "Decompose an observed lap deficit into corner speed, braking and "
            "throttle contributions, and report what remains unexplained."
        ),
        mcp_tool="attribute_historical_lap_loss",
        api_route="/api/catalog/attribution/{season}/{round}",
        inputs=("season", "round", "driver_a", "driver_b", "lap_number"),
        outputs=(
            "observed_delta_s", "corner_speed_s", "braking_s", "throttle_s",
            "residual_s", "quality",
        ),
        required_data=("laps", "telemetry"),
        optional_data=("race_control", "weather"),
        computational_cost="MODERATE",
        limitations=(
            "Requires channel telemetry for the scope; absent channels degrade "
            "attribution honestly rather than estimating them.",
        ),
        provenance_requirements=("tool_execution", "output_hash", "quality"),
        evidence_types_produced=("OBSERVED", "DERIVED"),
        hypothesis_types_supported=("H1_corner_speed", "H2_throttle", "H3_braking"),
        intents=("ATTRIBUTE", "EXPLAIN", "QUANTIFY", "DECOMPOSE", "TRACE"),
        analysis_levels=(2,),
        produces_corroboration=True,
    ),
    Capability(
        capability_id="fuse_lap_evidence",
        name="Evidence fusion",
        description=(
            "Fuse the evidence ledger for a scope and evaluate every requested "
            "hypothesis against it, preserving contradictions and residuals."
        ),
        mcp_tool="fuse_historical_lap_evidence",
        api_route="/api/catalog/evidence-fusion/{season}/{round}",
        inputs=("season", "round", "driver_a", "driver_b", "lap_number", "hypotheses"),
        outputs=(
            "evidence_ledger", "hypothesis_evaluations", "aggregate_state",
            "residual", "contradictions",
        ),
        required_data=("laps",),
        optional_data=("telemetry", "race_control", "weather"),
        computational_cost="MODERATE",
        prerequisites=("compare_laps",),
        provenance_requirements=("evidence_ids", "output_hash"),
        evidence_types_produced=("INFERRED",),
        hypothesis_types_supported=HYPOTHESIS_IDS,
        intents=("EXPLAIN", "TEST_HYPOTHESIS", "FALSIFY", "RECONCILE"),
        analysis_levels=(3,),
    ),
    Capability(
        capability_id="analyze_stint",
        name="Stint evidence",
        description=(
            "Analyse stint structure and measured degradation trend across a "
            "driver's stints, with the residual left open."
        ),
        mcp_tool="get_historical_stints",
        api_route="/api/catalog/stint-evidence/{season}/{round}",
        inputs=("season", "round", "driver_a", "driver_b"),
        outputs=("stint_metadata", "trend", "mean_delta_s", "residuals"),
        required_data=("stints", "laps"),
        optional_data=("telemetry", "pit_stops"),
        computational_cost="LOW",
        provenance_requirements=("tool_execution", "output_hash"),
        evidence_types_produced=("OBSERVED", "DERIVED"),
        hypothesis_types_supported=("H4_tyre_state",),
        intents=("TREND", "EXPLAIN", "EVALUATE_TYRE_BEHAVIOR", "COMPARE_STINTS"),
        analysis_levels=(2, 4),
    ),
    Capability(
        capability_id="attribute_stint_loss",
        name="Stint loss attribution",
        description="Decompose stint-level deficit with the stint evidence path.",
        mcp_tool="attribute_historical_stint_loss",
        api_route="/api/catalog/stint-evidence/{season}/{round}",
        inputs=("season", "round", "driver_a", "driver_b", "stint_number"),
        outputs=("observed_delta_s", "contributions", "residual_s"),
        required_data=("laps", "stints"),
        optional_data=("telemetry",),
        computational_cost="MODERATE",
        prerequisites=("analyze_stint",),
        evidence_types_produced=("OBSERVED", "DERIVED"),
        hypothesis_types_supported=("H4_tyre_state",),
        intents=("ATTRIBUTE", "EXPLAIN", "QUANTIFY"),
        analysis_levels=(3,),
    ),
    Capability(
        capability_id="decompose_race_gap",
        name="Race gap decomposition",
        description=(
            "Decompose a race-level gap over official classification, by "
            "segment and by pit phase, preserving what it cannot explain."
        ),
        mcp_tool="decompose_historical_race_gap",
        api_route="/api/catalog/race-gap/{season}/{round}",
        inputs=("season", "round", "driver_a", "driver_b"),
        outputs=("final_gap_s", "segments", "pit_phase", "residual_s"),
        required_data=("results", "laps"),
        optional_data=("pit_stops", "weather", "race_control"),
        computational_cost="MODERATE",
        limitations=(
            "Race-scoped only; qualifying sessions have no official race gap.",
        ),
        provenance_requirements=("tool_execution", "output_hash"),
        evidence_types_produced=("OBSERVED", "DERIVED"),
        intents=("COMPARE", "DECOMPOSE", "LOCATE", "QUANTIFY"),
        analysis_levels=(2,),
        produces_corroboration=True,
    ),
    Capability(
        capability_id="analyze_performance_regimes",
        name="Performance regimes",
        description=(
            "Segment a session into deterministic performance regimes from lap "
            "behaviour, so a change of pace becomes a locateable boundary."
        ),
        mcp_tool="analyze_historical_performance_regimes",
        api_route="/api/catalog/performance-regimes/{season}/{round}",
        inputs=("season", "round", "driver", "lap_range"),
        outputs=("regimes", "boundaries", "slope"),
        required_data=("laps",),
        optional_data=("telemetry",),
        computational_cost="MODERATE",
        limitations=("Race sessions only; regime segmentation needs a full race distance.",),
        provenance_requirements=("tool_execution", "output_hash"),
        evidence_types_produced=("DERIVED",),
        intents=("FIND_REGIME", "FIND_TURNING_POINT", "TREND", "LOCATE"),
        analysis_levels=(4,),
    ),
    Capability(
        capability_id="analyze_performance_envelope",
        name="Performance envelope",
        description=(
            "Compare a driver's achievable performance envelope against a "
            "reference across speed, throttle and brake demand."
        ),
        mcp_tool="analyze_historical_performance_envelope",
        api_route="/api/catalog/performance-envelope/{season}/{round}",
        inputs=("season", "round", "driver_a", "driver_b", "lap_number"),
        outputs=("envelope", "limits", "delivered_vs_envelope"),
        required_data=("laps", "telemetry"),
        computational_cost="MODERATE",
        provenance_requirements=("tool_execution", "output_hash"),
        evidence_types_produced=("OBSERVED", "DERIVED"),
        intents=("COMPARE", "EVALUATE_DRIVER", "EVALUATE_CAR", "QUANTIFY"),
        analysis_levels=(3,),
    ),
    Capability(
        capability_id="simulate_telemetry_counterfactual",
        name="Bounded telemetry counterfactual",
        description=(
            "Model the lap-time effect of a bounded, explicitly-stated "
            "intervention on measured telemetry. Output is MODELLED, never "
            "historical truth."
        ),
        mcp_tool="simulate_historical_telemetry_counterfactual",
        api_route="/api/catalog/counterfactual/{season}/{round}",
        inputs=("season", "round", "driver_a", "driver_b", "lap_number", "intervention"),
        outputs=("delta_lap_time_s", "assumptions", "validity", "profile"),
        required_data=("laps", "telemetry"),
        computational_cost="EXPENSIVE",
        limitations=(
            "Race sessions only. Models one bounded intervention; it is not a "
            "forecast and never becomes an observation.",
        ),
        prerequisites=("attribute_lap_loss",),
        provenance_requirements=("tool_execution", "assumptions", "output_hash"),
        evidence_types_produced=("MODELLED",),
        intents=("COUNTERFACTUAL", "WHAT_IF", "QUANTIFY"),
        analysis_levels=(6,),
    ),
    Capability(
        capability_id="analyze_cross_race_pattern",
        name="Cross-race pattern analysis",
        description=(
            "Search a bounded season span for structurally similar performance "
            "patterns, returning recurrence rather than resemblance claims."
        ),
        mcp_tool="analyze_cross_race_performance_patterns",
        api_route="/api/catalog/performance-patterns",
        inputs=("seasons", "pattern_id"),
        outputs=("patterns", "recurrences", "structural_similarity"),
        required_data=("laps", "results"),
        optional_data=("telemetry",),
        computational_cost="EXPENSIVE",
        limitations=(
            "Bounded season span; similarity is structural, never causal.",
        ),
        prerequisites=("analyze_performance_regimes",),
        provenance_requirements=("tool_execution", "pattern_id"),
        evidence_types_produced=("DERIVED", "INFERRED"),
        intents=("FIND_PATTERN", "COMPARE_RACES", "CORRELATE"),
        analysis_levels=(5,),
    ),
    Capability(
        capability_id="evaluate_cross_race_hypotheses",
        name="Cross-race hypothesis evidence",
        description=(
            "Evaluate the evidence backing a recurring pattern across the races "
            "where it appears, including contradicting instances."
        ),
        mcp_tool="analyze_cross_race_pattern_evidence",
        api_route="/api/catalog/performance-pattern-evidence",
        inputs=("pattern_id", "seasons"),
        outputs=("evidence", "supporting", "contradicting", "recurrence"),
        required_data=("laps", "results"),
        optional_data=("telemetry",),
        computational_cost="EXPENSIVE",
        prerequisites=("analyze_cross_race_pattern",),
        provenance_requirements=("evidence_ids", "output_hash"),
        evidence_types_produced=("INFERRED",),
        hypothesis_types_supported=HYPOTHESIS_IDS,
        intents=("FIND_PATTERN", "TEST_HYPOTHESIS", "RECONCILE"),
        analysis_levels=(5,),
    ),
    Capability(
        capability_id="run_engineering_investigation",
        name="Deterministic engineering investigation",
        description=(
            "Run the full deterministic investigation lifecycle for a scope: "
            "frame, hypothesize, collect, falsify, synthesise, verify."
        ),
        mcp_tool="run_engineering_investigation",
        api_route="/api/catalog/engineering-investigation",
        inputs=("question_type", "scope", "hypotheses"),
        outputs=(
            "evidence_ledger", "hypothesis_evaluations", "decision_trace",
            "residual", "synthesis", "output_hash",
        ),
        required_data=("laps", "results"),
        optional_data=("telemetry", "stints", "race_control", "weather", "pit_stops"),
        computational_cost="EXPENSIVE",
        provenance_requirements=("output_hash", "decision_trace", "evidence_ids"),
        evidence_types_produced=("OBSERVED", "DERIVED", "INFERRED"),
        hypothesis_types_supported=HYPOTHESIS_IDS,
        intents=("INVESTIGATE", "EXPLAIN", "SYNCHRONIZE", "SUMMARIZE"),
        analysis_levels=(3, 4),
    ),
    Capability(
        capability_id="synthesize_investigation",
        name="Investigation synthesis",
        description=(
            "Compose the engineering conclusion from a completed investigation, "
            "grounded strictly in its evidence, contradictions and residual."
        ),
        mcp_tool="verify_engineering_snapshot",
        api_route="/api/catalog/engineering-investigation",
        inputs=("investigation_id",),
        outputs=("conclusion", "limitations", "counterfactual_eligibility"),
        required_data=("laps",),
        computational_cost="LOW",
        prerequisites=("run_engineering_investigation",),
        provenance_requirements=("evidence_ids", "output_hash"),
        evidence_types_produced=("INFERRED",),
        hypothesis_types_supported=HYPOTHESIS_IDS,
        intents=("SUMMARIZE", "EXPLAIN"),
        analysis_levels=(3,),
    ),
    Capability(
        capability_id="build_investigation_graph",
        name="Investigation graph",
        description=(
            "Build the question -> observation -> evidence -> hypothesis -> "
            "falsification -> conclusion graph, and walk its paths."
        ),
        mcp_tool="build_investigation_graph",
        api_route="/api/catalog/investigation-graph",
        inputs=("investigation_id",),
        outputs=("nodes", "edges", "paths"),
        required_data=("laps",),
        computational_cost="LOW",
        prerequisites=("run_engineering_investigation",),
        provenance_requirements=("evidence_ids",),
        intents=("TRACE", "PROVENANCE", "RECONCILE"),
        analysis_levels=(3,),
    ),
    Capability(
        capability_id="trace_evidence_source",
        name="Evidence source trace",
        description=(
            "Trace one evidence item back to its source provider, table, method "
            "and version — the provenance primitive every claim rests on."
        ),
        mcp_tool="trace_evidence_source",
        api_route="/api/catalog/investigation-graph/evidence",
        inputs=("investigation_id", "evidence_id"),
        outputs=("source", "provider", "method", "version", "input_scope"),
        required_data=("laps",),
        computational_cost="TRIVIAL",
        intents=("PROVENANCE", "TRACE"),
        analysis_levels=(0,),
    ),
    Capability(
        capability_id="retrieve_memory",
        name="Engineering memory",
        description=(
            "Retrieve structurally related prior investigations as precedent, "
            "with their similarities and limitations."
        ),
        mcp_tool="retrieve_engineering_memory",
        api_route="/api/catalog/engineering-memory",
        inputs=("investigation_id",),
        outputs=("neighbors", "similarity", "limitations"),
        required_data=("laps",),
        computational_cost="LOW",
        limitations=("Similarity is structural; precedent is not proof of recurrence.",),
        provenance_requirements=("evidence_ids",),
        intents=("MEMORY", "FIND_PATTERN", "COMPARE_RACES"),
        analysis_levels=(5,),
    ),
    Capability(
        capability_id="compare_investigations",
        name="Investigation comparison",
        description="Compare two investigations structurally and replay them.",
        mcp_tool="compare_engineering_investigations",
        api_route="/api/catalog/engineering-investigation/compare",
        inputs=("investigation_a", "investigation_b"),
        outputs=("differences", "shared_findings", "divergence"),
        required_data=("laps",),
        computational_cost="LOW",
        intents=("COMPARE", "COMPARE_RACES", "RECONCILE"),
        analysis_levels=(5,),
    ),
    Capability(
        capability_id="replay_investigation",
        name="Investigation replay",
        description=(
            "Re-execute a recorded investigation and verify deterministic "
            "consistency against recorded output hashes."
        ),
        mcp_tool="replay_engineering_investigation",
        api_route="/api/catalog/engineering-investigation/replay",
        inputs=("investigation_id",),
        outputs=("verified_tools", "failed_tools", "success"),
        required_data=("laps",),
        computational_cost="MODERATE",
        prerequisites=("run_engineering_investigation",),
        provenance_requirements=("output_hash",),
        intents=("PROVENANCE", "REPLAY"),
        analysis_levels=(0,),
    ),
    Capability(
        capability_id="inspect_race_control",
        name="Race control inspection",
        description=(
            "Retrieve session race-control events so safety-car, yellow and "
            "penalty context can be tested rather than assumed."
        ),
        mcp_tool="get_historical_race_control",
        api_route="/api/catalog/session-context/{season}/{round}",
        inputs=("season", "round"),
        outputs=("events", "transitions"),
        required_data=("race_control",),
        computational_cost="TRIVIAL",
        limitations=("Unavailable in eras before race control was recorded.",),
        provenance_requirements=("source_provider",),
        intents=("EVALUATE_RACE_CONTROL", "DESCRIBE", "FIND_TURNING_POINT"),
        analysis_levels=(1,),
        produces_corroboration=True,
    ),
    Capability(
        capability_id="inspect_weather",
        name="Weather context",
        description="Retrieve session weather to qualify pace claims that may depend on conditions.",
        mcp_tool="get_historical_weather",
        api_route="/api/catalog/session-context/{season}/{round}",
        inputs=("season", "round"),
        outputs=("conditions", "transitions"),
        required_data=("weather",),
        computational_cost="TRIVIAL",
        limitations=("Unavailable in most historic eras; absence is reported, never imputed.",),
        provenance_requirements=("source_provider",),
        intents=("DESCRIBE", "CORRELATE"),
        analysis_levels=(0,),
        produces_corroboration=True,
    ),
)

_BY_ID: dict[str, Capability] = {c.capability_id: c for c in REGISTRY}


def all_capabilities() -> tuple[Capability, ...]:
    """Every registered capability.

    Named ``all_capabilities`` rather than ``capabilities`` so it cannot shadow
    this module when the package re-exports it — ``question_engine.capabilities``
    must stay importable as the module.
    """
    return REGISTRY


def capability(capability_id: str) -> Optional[Capability]:
    """One capability by id, or None. Never raises on an unknown id."""
    return _BY_ID.get(capability_id)


def registry_version() -> str:
    return REGISTRY_VERSION


def by_intent(intent: str) -> tuple[Capability, ...]:
    """Capabilities that can serve a semantic intent, cheapest first."""
    return tuple(sorted(
        (c for c in REGISTRY if intent in c.intents),
        key=lambda c: (COST_CLASSES.index(c.computational_cost), c.capability_id),
    ))


def within_budget(
    max_level: int,
    session_type: str,
    max_cost: str = "EXPENSIVE",
) -> tuple[Capability, ...]:
    """Capabilities admissible under an analysis level, session and cost ceiling."""
    ceiling = COST_CLASSES.index(max_cost)
    return tuple(
        c for c in REGISTRY
        if max_level in c.analysis_levels
        and session_type in c.supported_session_types
        and COST_CLASSES.index(c.computational_cost) <= ceiling
    )


def dependency_closure(capability_id: str) -> tuple[str, ...]:
    """A capability plus its prerequisites, in dependency-first order.

    Composition is the point: "where did the time go" needs a comparison AND an
    attribution, not either one alone.
    """
    order: list[str] = []
    stack = [capability_id]
    guard: set[str] = set()
    while stack:
        current = stack.pop(0)
        if current in guard:
            continue
        guard.add(current)
        cap = _BY_ID.get(current)
        if cap is None:
            continue
        order.append(current)
        stack.extend(cap.prerequisites)
    return tuple(reversed(order))


def capability_matrix() -> dict[str, Any]:
    """Machine-readable coverage matrix: intent -> capability -> support limits.

    This is the planner's source of truth. It states, for every intent, the
    finest resolution available and what each capability cannot do — so the
    planner can promise only what is deliverable.
    """
    intents: dict[str, dict[str, Any]] = {}
    for cap in REGISTRY:
        for intent in cap.intents:
            entry = intents.setdefault(intent, {
                "intent": intent,
                "capabilities": [],
                "required_data": set(),
                "supported_session_types": set(),
                "max_analysis_level": 0,
                "limitations": set(),
            })
            entry["capabilities"].append(cap.capability_id)
            entry["required_data"].update(cap.required_data)
            entry["supported_session_types"].update(cap.supported_session_types)
            entry["max_analysis_level"] = max(entry["max_analysis_level"],
                                              max(cap.analysis_levels))
            entry["limitations"].update(cap.limitations)
    matrix: dict[str, Any] = {
        "registry_version": REGISTRY_VERSION,
        "data_facets": list(DATA_FACETS),
        "hypotheses": list(HYPOTHESIS_IDS),
        "claim_classes": list(CLAIM_CLASSES),
        "intents": {},
    }
    for intent, entry in sorted(intents.items()):
        matrix["intents"][intent] = {
            "intent": intent,
            "capabilities": sorted(entry["capabilities"]),
            "required_data": sorted(entry["required_data"]),
            "supported_session_types": sorted(entry["supported_session_types"]),
            "max_analysis_level": entry["max_analysis_level"],
            "limitations": sorted(entry["limitations"]),
        }
    return matrix