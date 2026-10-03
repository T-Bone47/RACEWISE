"""Investigation planner: capabilities, availability, composition, budget.

This is where a question becomes a *bounded plan against real capabilities*.
Three jobs, in order:

1. **Availability before analysis.** Every planned capability declares the data
   facets it requires. The planner checks the canonical store first and marks
   each capability testable, limited or unavailable *before* anything runs. A
   missing facet narrows the investigation instead of ending it.

2. **Composition.** No single capability answers "where exactly did he lose
   the time" — that is a comparison, then an attribution, then a hypothesis
   test, then a residual. The planner walks the registry's prerequisite graph
   and returns the dependency closure, which is what makes composition real
   rather than aspirational.

3. **Budget.** Minimum sufficient computation. Level 0-1 direct questions cost
   almost nothing; level 6 counterfactuals and level 5 cross-race scans are
   expensive and must be earned by the question. The budget is reported, never
   silently applied — if it truncates a plan, the plan says so and names what
   it dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.question_engine.capabilities import (
    COST_CLASSES,
    HYPOTHESIS_IDS,
    Capability,
    capability,
    dependency_closure,
    by_intent,
)
from racewise.question_engine.compiler import CompiledQuestion
from racewise.question_engine.decomposer import SubQuestion, decompose

PLANNER_VERSION = "question_engine_planner_v1"


def plan_version() -> str:
    return PLANNER_VERSION

# Testability verdicts, per capability, from the availability check.
TESTABLE = "TESTABLE"
LIMITED = "LIMITED"
UNAVAILABLE = "UNAVAILABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"

DEFAULT_BUDGET = {
    "max_capabilities": 12,
    "max_analysis_level": 6,
    "max_cross_race_scans": 1,
    "max_counterfactuals": 1,
}

# Facet -> availability column in the canonical store. Availability is always
# data-derived record counts, never inferred from a season year.
_FACET_COLUMN = {
    "results": "results_availability",
    "qualifying": "qualifying_availability",
    "laps": "laps_availability",
    "stints": "stints_availability",
    "telemetry": "telemetry_availability",
    "weather": "weather_availability",
    "race_control": "race_control_availability",
    "pit_stops": "pit_stops_availability",
}


@dataclass
class AvailabilityReport:
    """What data exists for the resolved scope, and what it costs."""

    season: Optional[int]
    round: Optional[int]
    session_type: str
    available: tuple[str, ...]
    unavailable: tuple[str, ...]
    counts: dict[str, Any]
    source_provider: Optional[str] = None
    resolvable: bool = True
    reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "round": self.round,
            "session_type": self.session_type,
            "available": list(self.available),
            "unavailable": list(self.unavailable),
            "counts": self.counts,
            "source_provider": self.source_provider,
            "resolvable": self.resolvable,
            "reason": self.reason,
        }


@dataclass
class PlannedStep:
    """One capability invocation in the plan, with why it is (not) eligible."""

    capability_id: str
    sub_id: str
    intents: tuple[str, ...]
    analysis_level: int
    testability: str
    cost: str
    rationale: str
    missing_data: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "sub_id": self.sub_id,
            "intents": list(self.intents),
            "analysis_level": self.analysis_level,
            "testability": self.testability,
            "cost": self.cost,
            "rationale": self.rationale,
            "missing_data": list(self.missing_data),
            "blocked_by": list(self.blocked_by),
            "depends_on": list(self.depends_on),
        }


@dataclass
class InvestigationPlan:
    """A bounded, ordered, honest plan."""

    status: str
    compiled: CompiledQuestion
    sub_questions: tuple[SubQuestion, ...]
    availability: AvailabilityReport
    steps: tuple[PlannedStep, ...] = ()
    deferred: tuple[PlannedStep, ...] = ()
    hypotheses_planned: tuple[str, ...] = ()
    hypotheses_unavailable: dict[str, str] = field(default_factory=dict)
    requested_output_depth: str = "STANDARD"
    analysis_level: int = 1
    reason: Optional[str] = None
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def runnable(self) -> tuple[PlannedStep, ...]:
        return tuple(s for s in self.steps if s.testability in (TESTABLE, LIMITED))

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "compiled": self.compiled.as_dict(),
            "sub_questions": [s.as_dict() for s in self.sub_questions],
            "availability": self.availability.as_dict(),
            "steps": [s.as_dict() for s in self.steps],
            "deferred": [s.as_dict() for s in self.deferred],
            "hypotheses_planned": list(self.hypotheses_planned),
            "hypotheses_unavailable": self.hypotheses_unavailable,
            "requested_output_depth": self.requested_output_depth,
            "analysis_level": self.analysis_level,
            "planner_version": PLANNER_VERSION,
            "provenance": self.provenance,
        }


def check_availability(queries: CanonicalQueries, compiled: CompiledQuestion
                       ) -> AvailabilityReport:
    """Data availability for the resolved scope — always record-count derived."""
    if compiled.season is None or compiled.round is None:
        return AvailabilityReport(
            season=compiled.season, round=compiled.round,
            session_type=compiled.session_type, available=(), unavailable=(),
            counts={}, resolvable=False,
            reason="no race resolved",
        )
    try:
        raw = queries.get_availability(int(compiled.season),
                                       int(compiled.round),
                                       compiled.session_type)
    except Exception as exc:  # noqa: BLE001 — availability must never crash a plan
        return AvailabilityReport(
            season=compiled.season, round=compiled.round,
            session_type=compiled.session_type, available=(), unavailable=(),
            counts={}, resolvable=False,
            reason=f"availability lookup failed: {exc}",
        )
    if not raw or not raw.get("session_id"):
        return AvailabilityReport(
            season=compiled.season, round=compiled.round,
            session_type=compiled.session_type, available=(), unavailable=(),
            counts={}, resolvable=False,
            reason="canonical store has no row for this session",
        )

    available: list[str] = []
    unavailable: list[str] = []
    counts: dict[str, Any] = {}
    for facet, column in _FACET_COLUMN.items():
        state = str(raw.get(column) or "UNAVAILABLE")
        count_key = f"{facet}_count"
        counts[facet] = {
            "availability": state,
            "count": raw.get(count_key),
        }
        (available if state == "AVAILABLE" else unavailable).append(facet)
    return AvailabilityReport(
        season=int(compiled.season),
        round=int(compiled.round),
        session_type=compiled.session_type,
        available=tuple(sorted(available)),
        unavailable=tuple(sorted(unavailable)),
        counts=counts,
        source_provider=raw.get("source_provider"),
    )


def _testability(cap: Capability, availability: AvailabilityReport) -> tuple[str, tuple[str, ...]]:
    """TESTABLE / LIMITED / UNAVAILABLE for one capability.

    A capability needing only facets that are optional for it and missing at
    runtime is LIMITED, not unavailable: e.g. attribution without telemetry can
    still report the observed delta, honestly degraded.
    """
    if cap.supported_session_types and \
            availability.session_type not in cap.supported_session_types:
        return NOT_APPLICABLE, ()

    have = set(availability.available)
    missing = [f for f in cap.required_data if f not in have]
    if not missing:
        return TESTABLE, ()
    degraded_optional = [f for f in missing if f in cap.optional_data]
    hard_missing = [f for f in missing if f not in cap.optional_data]
    if hard_missing:
        return UNAVAILABLE, tuple(sorted(missing))
    if degraded_optional:
        return LIMITED, tuple(sorted(missing))
    return TESTABLE, ()


def _select_for_intents(intents: tuple[str, ...], level: int) -> list[Capability]:
    """Capabilities that can serve any detected intent within the level budget."""
    seen: dict[str, Capability] = {}
    for intent in intents:
        for cap in by_intent(intent):
            if level in cap.analysis_levels and cap.capability_id not in seen:
                seen[cap.capability_id] = cap
    return sorted(seen.values(), key=lambda c: (COST_CLASSES.index(c.computational_cost),
                                                c.capability_id))


def _output_depth(text_intents: tuple[str, ...],
                  negations: tuple[str, ...]) -> str:
    """Requested answer depth (§32). Forensic only on explicit request."""
    joined = " ".join(text_intents)
    if "FORENSIC" in joined or any(
            n in ("contradiction_seek", "exclusion") for n in negations):
        return "FORENSIC"
    return "STANDARD"


def _hypotheses_for(sub_questions: tuple[SubQuestion, ...],
                    compiled: CompiledQuestion,
                    availability: AvailabilityReport,
                    ) -> tuple[tuple[str, ...], dict[str, str]]:
    """Which hypotheses this question can actually test, and which it cannot.

    A hypothesis the data cannot reach is recorded UNAVAILABLE with the reason.
    That is the honest move: silently omitting it would let the absence read as
    "nothing to say about DRS" rather than "no evidence about DRS".
    """
    named = list(compiled.requested_hypotheses)
    for sub in sub_questions:
        for hid in sub.required_hypotheses:
            if hid not in named:
                named.append(hid)

    # Explicit request wins; otherwise test the whole canonical set when the
    # question is an explanation rather than a narrow lookup.
    asks_explanation = bool(
        {i for sub in sub_questions for i in sub.intents}
        & {"EXPLAIN", "TEST_HYPOTHESIS", "FALSIFY", "INVESTIGATE", "ATTRIBUTE"}
    )
    if not named and asks_explanation:
        named = list(HYPOTHESIS_IDS)

    if not named:
        return (), {}

    have = set(availability.available)
    # The facet each hypothesis actually depends on. This is a *testability*
    # statement about reachability, not a claim that the hypothesis is true.
    _HYPOTHESIS_FACETS = {
        "H1_corner_speed": "telemetry",
        "H2_throttle": "telemetry",
        "H3_braking": "telemetry",
        "H4_tyre_state": "stints",
        "H5_race_control": "race_control",
        "H6_drs": "telemetry",
    }
    planned: list[str] = []
    unavailable: dict[str, str] = {}
    for hid in named:
        facet = _HYPOTHESIS_FACETS.get(hid)
        if facet and facet not in have:
            unavailable[hid] = f"requires {facet} data, unavailable for this session"
        else:
            planned.append(hid)
    return tuple(planned), unavailable


def build_plan(
    queries: CanonicalQueries,
    compiled: CompiledQuestion,
    budget: Optional[dict[str, int]] = None,
) -> InvestigationPlan:
    """Turn a compiled question into a bounded plan against real capabilities."""
    limits = dict(DEFAULT_BUDGET)
    for key, value in (budget or {}).items():
        if key in limits and isinstance(value, int):
            limits[key] = value

    if compiled.status != "PARSED":
        return InvestigationPlan(
            status=compiled.status, compiled=compiled, sub_questions=(),
            availability=AvailabilityReport(compiled.season, compiled.round,
                                            compiled.session_type, (), (), {},
                                            resolvable=False,
                                            reason=compiled.reason or "not parsed"),
            reason=compiled.reason,
            provenance={"planner_version": PLANNER_VERSION},
        )

    sub_questions = decompose(compiled)
    availability = check_availability(queries, compiled)

    max_level = limits["max_analysis_level"]
    analysis_level = min([s.analysis_level for s in sub_questions], default=1)

    steps: list[PlannedStep] = []
    deferred: list[PlannedStep] = []
    added: dict[str, PlannedStep] = {}

    for sub in sub_questions:
        if sub.analysis_level > max_level:
            continue
        candidates = _select_for_intents(sub.intents, sub.analysis_level)
        for cap in candidates:
            if cap.capability_id in added:
                continue
            state, missing = _testability(cap, availability)
            # Compose: a capability is only planned once its prerequisites are.
            closure = dependency_closure(cap.capability_id)
            blocked = tuple(
                c for c in closure[:-1]
                if (p := capability(c)) is not None
                and p.supported_session_types
                and availability.session_type not in p.supported_session_types
            )
            if blocked:
                state = NOT_APPLICABLE
                missing = tuple(sorted(set(missing) | set(blocked)))
            step = PlannedStep(
                capability_id=cap.capability_id,
                sub_id=sub.sub_id,
                intents=cap.intents,
                analysis_level=sub.analysis_level,
                testability=state,
                cost=cap.computational_cost,
                rationale=f"serves {'/'.join(sub.intents)} at level {sub.analysis_level}",
                missing_data=missing,
                blocked_by=blocked,
                depends_on=tuple(
                    c for c in closure[:-1] if c not in added
                ),
            )
            added[cap.capability_id] = step

    ordered = sorted(added.values(),
                     key=lambda s: (COST_CLASSES.index(s.cost), s.analysis_level,
                                    s.capability_id))

    # --- budget: spend on the strongest evidence, report what was dropped ---
    runnable = [s for s in ordered if s.testability in (TESTABLE, LIMITED)]
    cross_race = [s for s in runnable if s.analysis_level >= 5]
    if len(cross_race) > limits["max_cross_race_scans"]:
        keep = {s.capability_id for s in cross_race[:limits["max_cross_race_scans"]]}
        for s in cross_race:
            if s.capability_id not in keep:
                s.testability = UNAVAILABLE
                s.rationale += " (deferred: cross-race scan budget exhausted)"
                deferred.append(s)
    runnable = [s for s in ordered if s.testability in (TESTABLE, LIMITED)]
    if len(runnable) > limits["max_capabilities"]:
        for s in runnable[limits["max_capabilities"]:]:
            s.testability = UNAVAILABLE
            s.rationale += " (deferred: capability budget exhausted)"
            deferred.append(s)
    steps = [s for s in ordered if s not in deferred]
    deferred_ids = {s.capability_id for s in deferred}
    deferred = [s for s in ordered if s.capability_id in deferred_ids]

    planned_hyps, unavailable_hyps = _hypotheses_for(sub_questions, compiled,
                                                     availability)

    if not [s for s in steps if s.testability in (TESTABLE, LIMITED)]:
        return InvestigationPlan(
            status="DATA_UNAVAILABLE", compiled=compiled,
            sub_questions=sub_questions, availability=availability,
            steps=steps, deferred=deferred,
            hypotheses_planned=planned_hyps,
            hypotheses_unavailable=unavailable_hyps,
            requested_output_depth=_output_depth(compiled.detected_intents,
                                                compiled.negations),
            analysis_level=analysis_level,
            reason=("no registered capability can serve this question with the "
                    "data available for this session"),
            provenance={"planner_version": PLANNER_VERSION},
        )

    return InvestigationPlan(
        status="PLANNED", compiled=compiled, sub_questions=sub_questions,
        availability=availability, steps=steps, deferred=deferred,
        hypotheses_planned=planned_hyps,
        hypotheses_unavailable=unavailable_hyps,
        requested_output_depth=_output_depth(compiled.detected_intents,
                                            compiled.negations),
        analysis_level=analysis_level,
        reason=None,
        provenance={
            "planner_version": PLANNER_VERSION,
            "budget": limits,
            "capabilities_selected": [s.capability_id for s in steps],
            "capabilities_deferred": [s.capability_id for s in deferred],
            "composition": "capabilities are selected with their prerequisite closure",
        },
    )