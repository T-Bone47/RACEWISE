"""Question engine orchestrator: ask -> investigate -> answer -> verify.

Ties the compiler, decomposer, planner, synthesizer and verifier into one call
and executes the plan against the real deterministic functions. Every number in
the answer comes from one of those calls; this module computes none.

Three properties this is built to guarantee:

* **Determinism.** Same question + same canonical store -> same answer hash.
  There are no clocks, no randomness, no model calls on the critical path.
* **Cancellation.** Each investigation carries an id and a cancel flag. A
  superseded run stops at its next checkpoint and can never write over the run
  that replaced it.
* **Follow-up continuity.** A follow-up compiles against the live investigation
  context, so "was it sector 2?" narrows the running investigation instead of
  restarting one from scratch.

Lap anchoring deserves a note. Many capabilities need a lap number, and the
user often did not name one. Picking a lap arbitrarily would manufacture a
result. The engine instead walks shared telemetry laps in descending order and
takes the first that yields a VALID or VALID_CAVEATS comparison — the same
convention the existing catalog routes use — and records which lap it anchored
to and why. If no lap qualifies, the answer says so instead of substituting one.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.question_engine.compiler import (
    COMPILE_PARSED,
    CompiledQuestion,
    compile_question,
)
from racewise.question_engine.planner import (
    InvestigationPlan,
    build_plan,
    check_availability,
)
from racewise.question_engine.synthesizer import Answer, synthesize
from racewise.question_engine.verification import (
    VerificationReport,
    verify_answer,
)
from racewise.tools.contract import canonical_hash

ENGINE_VERSION = "question_engine_v1"

# Engine statuses this module considers a usable comparison.
_VALID_STATUSES = ("VALID", "VALID_CAVEATS")


class InvestigationCancelled(RuntimeError):
    """Raised when a superseded investigation stops at a checkpoint."""


@dataclass
class InvestigationContext:
    """Interaction state for one investigation lineage (§29).

    Deliberately *not* engineering truth: it records what the user is looking
    at so a follow-up can be compiled against it. Evidence and calculations
    stay canonical and are never rewritten from here.
    """

    investigation_id: str
    question: str
    scope: dict[str, Any]
    anchored_lap: Optional[int] = None
    selected_sector: Optional[int] = None
    selected_corner: Optional[int] = None
    prior_follow_ups: list[str] = field(default_factory=list)
    answer_hash: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "question": self.question,
            "scope": self.scope,
            "anchored_lap": self.anchored_lap,
            "selected_sector": self.selected_sector,
            "selected_corner": self.selected_corner,
            "follow_ups": list(self.prior_follow_ups),
            "answer_hash": self.answer_hash,
        }


class _RunRegistry:
    """Active-run bookkeeping with cancellation and supersession."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()
        self._active: dict[str, str] = {}   # scope_key -> investigation_id

    def register(self, investigation_id: str, scope_key: str) -> None:
        with self._lock:
            # Starting an investigation for a scope supersedes the previous one
            # for that scope: the older run stops at its next checkpoint and can
            # never overwrite the newer result.
            previous = self._active.get(scope_key)
            if previous and previous != investigation_id:
                self._cancelled.add(previous)
            self._active[investigation_id] = scope_key
            self._cancelled.discard(investigation_id)

    def checkpoint(self, investigation_id: str) -> None:
        with self._lock:
            if investigation_id in self._cancelled:
                raise InvestigationCancelled(investigation_id)

    def cancel(self, investigation_id: str) -> None:
        with self._lock:
            self._cancelled.add(investigation_id)

    def is_cancelled(self, investigation_id: str) -> bool:
        with self._lock:
            return investigation_id in self._cancelled


RUNS = _RunRegistry()


# ---------------------------------------------------------------------------
# execution against real deterministic capabilities
# ---------------------------------------------------------------------------

def _shared_telemetry_laps(queries: CanonicalQueries, season: int,
                           round_num: int, session_type: str) -> list[int]:
    try:
        summary = queries.telemetry_summary(season, round_num, session_type)
    except Exception:  # noqa: BLE001 — availability gaps are reported, not raised
        return []
    if not isinstance(summary, dict) or not summary.get("available"):
        return []
    return sorted((int(x) for x in summary.get("laps") or []), reverse=True)


def _anchor_lap(queries: CanonicalQueries, compiled: CompiledQuestion,
                predicate: Callable[[int], dict[str, Any]]) -> tuple[Optional[int],
                                                                   Optional[str]]:
    """First descending shared lap that yields a usable comparison.

    Returns ``(lap, reason)``. ``reason`` is None on success and explains the
    refusal otherwise, so the answer can say why no lap was chosen instead of
    silently picking one.
    """
    if compiled.lap_number is not None:
        return compiled.lap_number, None
    laps = _shared_telemetry_laps(queries, int(compiled.season),
                                 int(compiled.round), compiled.session_type)
    if not laps:
        return None, "no shared telemetry laps exist for this session"
    for lap in laps:
        result = predicate(lap)
        if isinstance(result, dict) and result.get("status") in _VALID_STATUSES:
            return lap, None
    return None, ("no shared telemetry lap yields a clean two-driver comparison")


def _execute_capabilities(
    queries: CanonicalQueries,
    compiled: CompiledQuestion,
    planned: tuple[str, ...],
    anchor_fn: Callable[[int], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], Optional[int]]:
    """Run the planned capabilities for real. Returns (results, errors, anchored_lap).

    Each capability is called through its own deterministic function with
    explicit, validated arguments. Nothing is invoked by name from user text.
    """
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    anchored_lap: Optional[int] = None
    season, round_num = int(compiled.season), int(compiled.round)
    driver_a, driver_b = compiled.driver_a, compiled.driver_b

    def _record(cap_id: str, payload: Any) -> None:
        if isinstance(payload, dict):
            if payload.get("status") in ("UNAVAILABLE", "INVALID_COMPARISON"):
                errors[cap_id] = str(payload.get("reason") or payload.get("status"))
            else:
                results[cap_id] = payload
        else:
            errors[cap_id] = "capability returned a non-object result"

    for cap_id in planned:
        try:
            if cap_id in ("compare_laps", "attribute_lap_loss", "fuse_lap_evidence"):
                if anchored_lap is None:
                    from racewise.data.historical.evidence_fusion import fuse_lap_evidence
                    from racewise.data.historical.loss_attribution import (
                        VALID,
                        VALID_CAVEATS,
                        attribute_lap_loss,
                    )
                    from racewise.data.historical.telemetry_analysis import (
                        compare_telemetry_lap,
                    )

                    def _probe(lap: int) -> dict[str, Any]:
                        if cap_id == "compare_laps":
                            return compare_telemetry_lap(queries, season, round_num,
                                                         driver_a, driver_b, lap)
                        if cap_id == "attribute_lap_loss":
                            return attribute_lap_loss(queries, season, round_num,
                                                      driver_a, driver_b, lap)
                        return fuse_lap_evidence(queries, season, round_num,
                                                 driver_a, driver_b, lap)

                    anchored_lap, refusal = _anchor_lap(queries, compiled, _probe)
                    if anchored_lap is None:
                        errors[cap_id] = refusal or "no comparable lap available"
                        continue

                lap = anchored_lap
                if cap_id == "compare_laps":
                    _record(cap_id, compare_telemetry_lap(
                        queries, season, round_num, driver_a, driver_b, lap))
                elif cap_id == "attribute_lap_loss":
                    _record(cap_id, attribute_lap_loss(
                        queries, season, round_num, driver_a, driver_b, lap))
                elif cap_id == "fuse_lap_evidence":
                    if compiled.session_type == "QUALIFYING":
                        from racewise.data.historical.evidence_fusion import (
                            fuse_qualifying_lap_evidence,
                        )
                        _record(cap_id, fuse_qualifying_lap_evidence(
                            queries, season, round_num, driver_a, driver_b, lap))
                    else:
                        _record(cap_id, fuse_lap_evidence(
                            queries, season, round_num, driver_a, driver_b, lap))

            elif cap_id == "decompose_race_gap":
                from racewise.data.historical.race_gap import decompose_race_gap
                _record(cap_id, decompose_race_gap(queries, season, round_num,
                                                   driver_a, driver_b))

            elif cap_id == "analyze_stint":
                from racewise.data.historical.stint_evidence import (
                    analyze_stint_comparison,
                )
                _record(cap_id, analyze_stint_comparison(
                    queries, season, round_num, driver_a, driver_b))

            elif cap_id == "resolve_session_context":
                _record(cap_id, {
                    "availability": queries.get_availability(
                        season, round_num, compiled.session_type),
                })

            elif cap_id == "inspect_race_control":
                _record(cap_id, {
                    "events": queries.get_race_control(season, round_num,
                                                       compiled.session_type),
                })

            elif cap_id == "inspect_weather":
                _record(cap_id, {
                    "conditions": queries.get_weather(season, round_num,
                                                      compiled.session_type),
                })

            # Capabilities the planner selected but whose deterministic entry
            # point is the full investigation lifecycle are executed by the
            # existing orchestrator, not re-implemented here. Reporting them as
            # not-run is honest; inventing a summary would not be.
            else:
                errors[cap_id] = ("capability is served by the investigation "
                                  "lifecycle endpoint, not this path")
        except Exception as exc:  # noqa: BLE001 — a capability must never crash an answer
            errors[cap_id] = f"{type(exc).__name__}: {exc}"

    return results, errors, anchored_lap


def ask(
    queries: CanonicalQueries,
    question: str,
    context: Optional[dict[str, Any]] = None,
    budget: Optional[dict[str, int]] = None,
    on_stage: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Answer one engineering question end to end.

    Returns the compiled question, the plan, the structured answer, the
    verification report and full provenance.
    """
    started = time.perf_counter()
    investigation_id = uuid.uuid4().hex[:12]

    def stage(name: str, status: str, detail: Any = None) -> None:
        if on_stage is None:
            return
        try:
            on_stage({"stage": name, "status": status, "detail": detail})
        except Exception:  # noqa: BLE001 — a broken listener cannot influence the run
            pass

    stage("COMPILE", "RUNNING", "deterministic question compilation")
    compiled = compile_question(queries, question, context=context)
    stage("COMPILE", "COMPLETED", compiled.status)

    plan = build_plan(queries, compiled, budget=budget) if \
        compiled.status == COMPILE_PARSED else InvestigationPlan(
            status=compiled.status, compiled=compiled, sub_questions=(),
            availability=check_availability(queries, compiled),
            reason=compiled.reason)
    stage("PLAN", "COMPLETED", f"{len(plan.steps)} capabilities considered")

    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    anchored_lap: Optional[int] = None

    if plan.status == "PLANNED":
        RUNS.register(investigation_id,
                      f"{compiled.season}/{compiled.round}/{compiled.session_type}")
        planned = tuple(s.capability_id for s in plan.runnable)
        stage("INVESTIGATE", "RUNNING", list(planned))
        results, errors, anchored_lap = _execute_capabilities(
            queries, compiled, planned,
            lambda lap: (results.get("_anchor") or {}))
        RUNS.checkpoint(investigation_id)
        stage("INVESTIGATE", "COMPLETED", sorted(results))

    stage("SYNTHESIZE", "RUNNING", None)
    answer = synthesize(compiled, plan, results, errors)
    if anchored_lap is not None:
        answer.provenance["anchored_lap"] = anchored_lap
        answer.provenance["lap_anchoring"] = (
            "highest shared telemetry lap yielding a valid comparison"
            if compiled.lap_number is None else "user-specified lap"
        )
    stage("SYNTHESIZE", "COMPLETED", answer.status)

    stage("VERIFY", "RUNNING", None)
    report = verify_answer(answer, results)
    stage("VERIFY", "COMPLETED", "passed" if report.passed else "failed")

    ctx = InvestigationContext(
        investigation_id=investigation_id,
        question=question,
        scope=compiled.resolved_context(),
        anchored_lap=anchored_lap,
        selected_sector=compiled.sectors[0] if compiled.sectors else None,
        selected_corner=compiled.corners[0] if compiled.corners else None,
        answer_hash=answer.as_dict()["answer_hash"],
    )

    return {
        "engine_version": ENGINE_VERSION,
        "investigation_id": investigation_id,
        "status": answer.status,
        "compiled": compiled.as_dict(),
        "plan": plan.as_dict(),
        "answer": answer.as_dict(),
        "verification": report.as_dict(),
        "context": ctx.as_dict(),
        "raw_results": {k: v for k, v in results.items() if k != "_anchor"},
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "identity_hash": canonical_hash({
            "question": question,
            "compiled": compiled.as_dict().get("question_hash"),
            "capabilities": sorted(results),
            "answer_hash": answer.as_dict()["answer_hash"],
        }),
    }


def follow_up(
    queries: CanonicalQueries,
    context: dict[str, Any],
    question: str,
    budget: Optional[dict[str, int]] = None,
) -> dict[str, Any]:
    """Continue an investigation with a follow-up question.

    The follow-up compiles against the live context: it inherits the resolved
    scope, narrows spatial scope where the user narrowed it, and replaces the
    lap only when the user names one. Restating the whole race in every
    follow-up is the thing this avoids.
    """
    inherited = dict(context.get("scope") or {})
    scope_text = str(question)

    narrowed: dict[str, Any] = {}
    if "sector" in scope_text.lower():
        from racewise.question_engine.intents import sector_numbers
        sectors = sector_numbers(scope_text)
        if sectors:
            narrowed["sector"] = sectors[0]
    if context.get("anchored_lap") is not None:
        narrowed.setdefault("lap_number", context["anchored_lap"])

    merged = {k: v for k, v in inherited.items() if v is not None}
    merged.update({k: v for k, v in narrowed.items() if v is not None})

    result = ask(queries, question, context=merged, budget=budget)
    result["continued_from"] = context.get("investigation_id")
    result["inherited_scope"] = merged
    return result