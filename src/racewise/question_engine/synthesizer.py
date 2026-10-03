"""Answer synthesis: capability results -> one structured engineering answer.

The engineering answer is built FIRST, as structure, from results the
deterministic engine actually returned. Prose is generated FROM that structure
and never the reverse. This ordering is the whole point: a system that writes
the sentence first and attaches provenance afterwards will always be able to
produce a sentence with no provenance behind it.

The partial-answer engine is the other half. When a question is only partly
answerable the output is not "cannot answer" — it is:

    what we can establish
    what we cannot establish
    why
    available evidence
    missing evidence

Refusing to answer because one component is unavailable would throw away real,
correct findings, which is its own kind of dishonesty.

Claim classes are preserved exactly as the engine produced them. A MODELLED
number stays MODELLED through synthesis. It never becomes OBSERVED, and no
arithmetic in this module converts a model into a measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from racewise.question_engine.capabilities import REGISTRY_VERSION, capability
from racewise.question_engine.compiler import CompiledQuestion
from racewise.question_engine.planner import InvestigationPlan
from racewise.tools.contract import canonical_hash

SYNTHESIZER_VERSION = "question_engine_synthesizer_v1"

# ---------------------------------------------------------------------------
# Answer status vocabulary (§2). Every answer carries exactly one.
# ---------------------------------------------------------------------------
ANSWERABLE = "ANSWERABLE"
PARTIALLY_ANSWERABLE = "PARTIALLY_ANSWERABLE"
ANALYSABLE_WITH_LIMITATIONS = "ANALYSABLE_WITH_LIMITATIONS"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
NOT_TESTABLE = "NOT_TESTABLE"
UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
CONTEXT_UNRESOLVED = "CONTEXT_UNRESOLVED"

ANSWER_STATUSES = (
    ANSWERABLE, PARTIALLY_ANSWERABLE, ANALYSABLE_WITH_LIMITATIONS,
    INSUFFICIENT_EVIDENCE, DATA_UNAVAILABLE, NOT_TESTABLE,
    UNSUPPORTED_REQUEST, CONTEXT_UNRESOLVED,
)

# Engine hypothesis evaluation states — passed through verbatim, never renamed.
SUPPORTED = "SUPPORTED"
PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
NOT_SUPPORTED = "NOT_SUPPORTED"
CONTRADICTED = "CONTRADICTED"
MIXED_EVIDENCE = "MIXED_EVIDENCE"
NOT_TESTABLE = "NOT_TESTABLE"
INSUFFICIENT_EVIDENCE_HYP = "INSUFFICIENT_EVIDENCE"


def answer_status() -> tuple[str, ...]:
    return ANSWER_STATUSES


@dataclass
class Answer:
    """A structured engineering answer. Prose is a view of this, not its source."""

    status: str
    question: str
    scope: dict[str, Any]
    short_answer: str
    established: list[dict[str, Any]] = field(default_factory=list)
    not_established: list[dict[str, Any]] = field(default_factory=list)
    why_not: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    calculations: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    supporting_evidence: list[dict[str, Any]] = field(default_factory=list)
    contradicting_evidence: list[dict[str, Any]] = field(default_factory=list)
    residuals: list[dict[str, Any]] = field(default_factory=list)
    counterfactuals: list[dict[str, Any]] = field(default_factory=list)
    spatial: list[dict[str, Any]] = field(default_factory=list)
    evidence_ledger: list[dict[str, Any]] = field(default_factory=list)
    engine_conclusion: Optional[str] = None
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    decision_trace: list[dict[str, Any]] = field(default_factory=list)
    follow_ups: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "answer_status": self.status,
            "question": self.question,
            "scope": self.scope,
            "short_answer": self.short_answer,
            "established": self.established,
            "not_established": self.not_established,
            "why_not": self.why_not,
            "observations": self.observations,
            "calculations": self.calculations,
            "hypotheses": self.hypotheses,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "residuals": self.residuals,
            "counterfactuals": self.counterfactuals,
            "spatial": self.spatial,
            "evidence_ledger": self.evidence_ledger,
            "engine_conclusion": self.engine_conclusion,
            "assumptions": self.assumptions,
            "limitations": self.limitations,
            "missing_evidence": self.missing_evidence,
            "provenance": self.provenance,
            "decision_trace": self.decision_trace,
            "follow_ups": list(self.follow_ups),
            "synthesizer_version": SYNTHESIZER_VERSION,
            "registry_version": REGISTRY_VERSION,
        }
        payload["answer_hash"] = canonical_hash(
            {k: v for k, v in payload.items() if k != "provenance"}
        )
        return payload


# ---------------------------------------------------------------------------
# extraction from real capability outputs
# ---------------------------------------------------------------------------

def _extract_observations(results: dict[str, Any]) -> list[dict[str, Any]]:
    """OBSERVED facts, read from the engine's real payload contracts.

    Field names here are the engine's, not invented: ``observed_delta_s`` and
    ``lap_times`` from fusion and attribution, ``total_est_time_loss_s`` from
    the telemetry window comparison. Every entry keeps its capability id so
    verification can prove the number came from a tool rather than this module.
    """
    out: list[dict[str, Any]] = []

    def _add(statement: str, value: Any, unit: Optional[str], cap_id: str) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.append({
                "statement": statement,
                "value": value,
                "unit": unit,
                "claim_class": "OBSERVED",
                "capability_id": cap_id,
            })

    fusion = results.get("fuse_lap_evidence")
    if isinstance(fusion, dict) and not fusion.get("error"):
        lap_times = fusion.get("lap_times") or {}
        _add("Observed lap delta (measured)",
             fusion.get("observed_delta_s"), "s", "fuse_lap_evidence")
        if isinstance(lap_times, dict):
            _add(f"Subject A lap time", lap_times.get("driver_a"), "s",
                 "fuse_lap_evidence")
            _add(f"Subject B lap time", lap_times.get("driver_b"), "s",
                 "fuse_lap_evidence")

    attribution = results.get("attribute_lap_loss")
    if isinstance(attribution, dict) and not attribution.get("error"):
        lap_times = attribution.get("lap_times") or {}
        _add("Observed lap delta (measured)",
             attribution.get("observed_delta_s"), "s", "attribute_lap_loss")
        if isinstance(lap_times, dict):
            _add("Subject A lap time", lap_times.get("driver_a"), "s",
                 "attribute_lap_loss")
            _add("Subject B lap time", lap_times.get("driver_b"), "s",
                 "attribute_lap_loss")

    compare = results.get("compare_laps")
    if isinstance(compare, dict) and not compare.get("error"):
        _add("Telemetry-window estimated time loss",
             compare.get("total_est_time_loss_s"), "s", "compare_laps")

    gap = results.get("decompose_race_gap")
    if isinstance(gap, dict) and not gap.get("error"):
        for key in ("final_gap_s", "gap_s", "observed_delta_s"):
            if isinstance(gap.get(key), (int, float)):
                _add("Official classification gap", gap[key], "s",
                     "decompose_race_gap")
                break
    # Fusion and attribution independently measure the same lap delta; report
    # the quantity once with both capabilities as corroboration rather than
    # listing the same number twice.
    seen: dict[tuple[str, Any], list[str]] = {}
    for entry in out:
        key = (entry["statement"], entry["value"])
        seen.setdefault(key, []).append(entry["capability_id"])
    deduped: list[dict[str, Any]] = []
    for entry in out:
        key = (entry["statement"], entry["value"])
        if len(seen[key]) == 1 or entry["capability_id"] == seen[key][0]:
            if len(seen[key]) > 1:
                entry["corroborated_by"] = [
                    c for c in seen[key] if c != entry["capability_id"]
                ]
            deduped.append(entry)
    return deduped


def _extract_spatial(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Where the difference occurred, at the finest resolution measured.

    Sector deltas are measured; the telemetry estimate beside them covers a
    window and is not the same quantity, so the two are never summed.
    """
    out: list[dict[str, Any]] = []
    fusion = results.get("fuse_lap_evidence")
    if isinstance(fusion, dict) and not fusion.get("error"):
        for row in fusion.get("authoritative_sector_decomposition") or []:
            if not isinstance(row, dict):
                continue
            out.append({
                "scope": f"sector {row.get('sector')}",
                "measured_delta_s": row.get("delta_s"),
                "telemetry_estimated_loss_s": row.get("telemetry_estimated_loss_s"),
                "claim_class": "OBSERVED",
                "note": row.get("note"),
                "capability_id": "fuse_lap_evidence",
            })
    attribution = results.get("attribute_lap_loss")
    if isinstance(attribution, dict) and not attribution.get("error"):
        sectors = attribution.get("sector_attribution")
        if isinstance(sectors, dict):
            for row in sectors.values() if isinstance(sectors, dict) else []:
                if isinstance(row, dict):
                    out.append({
                        "scope": str(row.get("sector", "sector")),
                        "measured_delta_s": row.get("delta_s"),
                        "telemetry_estimated_loss_s": row.get("estimated_loss_s"),
                        "claim_class": "OBSERVED",
                        "capability_id": "attribute_lap_loss",
                    })
    return out


def _extract_calculations(results: dict[str, Any]) -> list[dict[str, Any]]:
    """DERIVED decompositions — estimated pace components and channel signals.

    These are the modelled/derived estimates and they are labelled as such.
    The signal metrics are the direct measured telemetry deltas for each
    hypothesis' channel, which is what the hypothesis evidence rests on.
    """
    out: list[dict[str, Any]] = []

    def _add(statement: str, value: Any, unit: Optional[str], cap_id: str,
             claim_class: str = "DERIVED", **extra: Any) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            entry = {
                "statement": statement,
                "value": value,
                "unit": unit,
                "claim_class": claim_class,
                "capability_id": cap_id,
            }
            entry.update(extra)
            out.append(entry)

    attribution = results.get("attribute_lap_loss")
    if isinstance(attribution, dict) and not attribution.get("error"):
        _add("Estimated pace component from the speed-trace model",
             attribution.get("estimated_pace_component_s"), "s",
             "attribute_lap_loss")
        metrics = attribution.get("signal_metrics")
        if isinstance(metrics, dict):
            speed = metrics.get("speed") or {}
            _add("Mean speed delta across the measured window",
                 speed.get("mean_delta_kmh"), "km/h", "attribute_lap_loss",
                 hypothesis_id="H1_corner_speed")
            _add("Maximum speed deficit observed",
                 speed.get("max_deficit_kmh"), "km/h", "attribute_lap_loss",
                 hypothesis_id="H1_corner_speed")
            throttle = metrics.get("throttle") or {}
            _add("Mean throttle delta across the measured window",
                 throttle.get("mean_delta_pct"), "%", "attribute_lap_loss",
                 hypothesis_id="H2_throttle")
            _add("Throttle lift windows where B lifted and A did not",
                 throttle.get("b_lift_windows_vs_a"), "count",
                 "attribute_lap_loss", claim_class="OBSERVED",
                 hypothesis_id="H2_throttle")
            brake = metrics.get("brake") or {}
            _add("Braking-fraction delta across the measured window",
                 brake.get("braking_fraction_delta"), "fraction",
                 "attribute_lap_loss", hypothesis_id="H3_braking")
            _add("Earliest braking point delta",
                 brake.get("first_brake_delta_s"), "s", "attribute_lap_loss",
                 hypothesis_id="H3_braking")

    stint = results.get("analyze_stint")
    if isinstance(stint, dict) and not stint.get("error"):
        trend = stint.get("trend") if isinstance(stint.get("trend"), dict) else {}
        _add("Measured degradation slope per stint-lap",
             trend.get("slope_per_stint_lap"), "s", "analyze_stint")
    return out


def _extract_residuals(results: dict[str, Any], compiled: CompiledQuestion
                       ) -> list[dict[str, Any]]:
    """What the tested mechanisms could NOT explain (§22).

    This is the single most important field in the answer. An explanation that
    hides its own remainder is worse than no explanation.
    """
    out: list[dict[str, Any]] = []
    for cap_id in ("attribute_lap_loss", "decompose_race_gap",
                   "attribute_stint_loss"):
        payload = results.get(cap_id)
        if not isinstance(payload, dict) or payload.get("error"):
            continue
        for key in ("residual_s", "unexplained_s", "residual"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                out.append({
                    "statement": (
                        f"{abs(value):.3f} s remains unexplained by the mechanisms "
                        f"actually tested"
                    ),
                    "value": value,
                    "unit": "s",
                    "claim_class": "DERIVED",
                    "never_assigned_to": "no mechanism — reported, not inferred",
                    "capability_id": cap_id,
                })
                break
    return out


def _extract_hypotheses(results: dict[str, Any]) -> tuple[list[dict[str, Any]],
                                                           list[dict[str, Any]],
                                                           list[dict[str, Any]]]:
    """Hypothesis states and their evidence, read from the engine's own buckets.

    ``fuse_lap_evidence`` reports three disjoint buckets — ``supported``,
    ``contradicted_or_not_supported``, ``untestable`` — plus a per-hypothesis
    breakdown of which evidence source ids bear on it. Those are the engine's
    verdicts and they are passed through unchanged. The engine deliberately
    keeps "contradicted" and "not supported" in one bucket and keeps
    "untestable" separate; the synthesizer does not merge them, because
    "we could not test this" and "we tested it and it did not hold" are
    different engineering facts.
    """
    hypotheses: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    contradicting: list[dict[str, Any]] = []

    fusion = results.get("fuse_lap_evidence")
    if not isinstance(fusion, dict) or fusion.get("error"):
        return hypotheses, supporting, contradicting

    buckets = {
        "SUPPORTED": list(fusion.get("supported") or []),
        "CONTRADICTED_OR_NOT_SUPPORTED":
            list(fusion.get("contradicted_or_not_supported") or []),
        "UNTESTABLE": list(fusion.get("untestable") or []),
    }
    state_of: dict[str, str] = {}
    for state, ids in buckets.items():
        for hid in ids:
            state_of[hid] = state

    detail = fusion.get("hypotheses")
    if not isinstance(detail, list):
        detail = []
    seen: set[str] = set()

    for entry in detail:
        if not isinstance(entry, dict):
            continue
        hid = entry.get("hypothesis_id")
        if not hid:
            continue
        seen.add(hid)
        state = state_of.get(hid, "UNTESTABLE")
        entry_out = {
            "hypothesis_id": hid,
            "state": state,
            "statement": entry.get("statement"),
            "supporting_evidence_ids": list(entry.get("supporting") or []),
            "contradicting_evidence_ids": list(entry.get("contradicting") or []),
            "untestable_evidence_ids": list(entry.get("untestable") or []),
            "capability_id": "fuse_lap_evidence",
        }
        hypotheses.append(entry_out)
        for eid in entry_out["supporting_evidence_ids"]:
            supporting.append({"evidence_id": eid, "hypothesis_id": hid,
                               "state": state})
        for eid in entry_out["contradicting_evidence_ids"]:
            contradicting.append({"evidence_id": eid, "hypothesis_id": hid,
                                  "state": state})

    # Any bucketed hypothesis without a detail row still has a real state and
    # must not disappear from the answer.
    for hid, state in sorted(state_of.items()):
        if hid not in seen:
            hypotheses.append({
                "hypothesis_id": hid,
                "state": state,
                "statement": None,
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "untestable_evidence_ids": [],
                "capability_id": "fuse_lap_evidence",
            })
    return hypotheses, supporting, contradicting


def _extract_evidence_ledger(results: dict[str, Any]) -> list[dict[str, Any]]:
    """The evidence ledger itself, with each item's provider and tables.

    This is what "show me every piece of evidence supporting this" resolves to.
    """
    out: list[dict[str, Any]] = []
    fusion = results.get("fuse_lap_evidence")
    if not isinstance(fusion, dict) or fusion.get("error"):
        return out
    for item in fusion.get("evidence_items") or []:
        if not isinstance(item, dict):
            continue
        out.append({
            "evidence_id": item.get("source_id"),
            "statement": item.get("statement"),
            "evidence_type": item.get("evidence_type"),
            "relationship": item.get("relationship"),
            "hypotheses": list(item.get("hypotheses") or []),
            "provider": item.get("provider"),
            "tables": list(item.get("tables") or []),
            "assumptions": list(item.get("assumptions") or []),
            "limitations": list(item.get("limitations") or []),
            "capability_id": "fuse_lap_evidence",
        })
    return out


def _extract_counterfactuals(results: dict[str, Any]) -> list[dict[str, Any]]:
    """MODELLED results, labelled so they can never be read as measurements."""
    out: list[dict[str, Any]] = []
    payload = results.get("simulate_telemetry_counterfactual")
    if isinstance(payload, dict) and not payload.get("error"):
        delta = payload.get("delta_lap_time_s", payload.get("predicted_delta_s"))
        if isinstance(delta, (int, float)):
            out.append({
                "statement": "Modelled lap-time change under a bounded intervention",
                "value": delta,
                "unit": "s",
                "claim_class": "MODELLED",
                "is_historical_truth": False,
                "assumptions": payload.get("assumptions") or [],
                "validity": payload.get("validity"),
                "capability_id": "simulate_telemetry_counterfactual",
            })
    return out


def _short_answer(status: str, observations: list[dict[str, Any]],
                  residuals: list[dict[str, Any]],
                  hypotheses: list[dict[str, Any]]) -> str:
    """One honest sentence. Never a confidence score, never a causal claim."""
    if status == DATA_UNAVAILABLE:
        return "The data required to investigate this question is not available."
    if status == CONTEXT_UNRESOLVED:
        return "The question cannot be investigated until its context is resolved."
    if status == UNSUPPORTED_REQUEST:
        return "This request does not map to a supported engineering capability."

    delta = next((o for o in observations
                  if "delta" in o["statement"].lower()), None)
    leading = f"{delta['value']:+.3f} s" if delta and isinstance(
        delta.get("value"), (int, float)) else None

    if residuals:
        residual = residuals[0]
        text = (f"{abs(residual['value']):.3f} s remains unexplained by the "
                f"mechanisms tested")
    elif hypotheses:
        supported = sum(1 for h in hypotheses if h.get("state") == "SUPPORTED")
        text = (f"{len(hypotheses)} hypotheses evaluated against evidence, "
                f"{supported} supported")
    else:
        text = "no numerical finding was established"
    return f"{leading + ' observed; ' if leading else ''}{text}."


def _follow_ups(plan: InvestigationPlan) -> tuple[dict[str, Any], ...]:
    """Suggestions drawn ONLY from capabilities that actually ran or can run.

    Offering an action the engine cannot take is a small lie with a button on
    it, so every suggestion here is derived from the plan's own capabilities.
    """
    out: list[dict[str, Any]] = []
    ran = {s.capability_id for s in plan.runnable}
    avail = set(plan.availability.available)

    def _offer(label: str, cap_id: str) -> None:
        cap = capability(cap_id)
        if cap is None:
            return
        out.append({
            "label": label,
            "capability_id": cap_id,
            "api_route": cap.api_route,
            "available": cap_id in ran or not cap.required_data,
        })

    if "fuse_lap_evidence" in ran:
        _offer("Show evidence against the leading hypothesis", "fuse_lap_evidence")
    if "attribute_lap_loss" in ran:
        _offer("Open residual analysis", "attribute_lap_loss")
    if "telemetry" in avail:
        _offer("Run the eligible counterfactual",
               "simulate_telemetry_counterfactual")
    if compiled_cross := (plan.compiled.pattern_seasons or
                          "cross_race" in plan.compiled.temporal_scopes):
        _offer("Find another race with this pattern", "analyze_cross_race_pattern")
    if "analyze_stint" in ran:
        _offer("Compare the next stint", "analyze_stint")
    _offer("Inspect the evidence provenance", "trace_evidence_source")
    return tuple(out)


def synthesize(
    compiled: CompiledQuestion,
    plan: InvestigationPlan,
    results: dict[str, Any],
    capability_errors: Optional[dict[str, str]] = None,
) -> Answer:
    """Compose the structured answer from real capability results."""
    errors = dict(capability_errors or {})
    provenance = {
        "compiler_version": compiled.provenance.get("compiler_version"),
        "planner_version": plan.provenance.get("planner_version"),
        "registry_version": REGISTRY_VERSION,
        "capabilities_executed": sorted(results),
        "capability_errors": errors,
        "availability": plan.availability.as_dict(),
    }

    if compiled.status == CONTEXT_UNRESOLVED:
        return Answer(
            status=CONTEXT_UNRESOLVED, question=compiled.raw_question,
            scope=compiled.resolved_context(),
            short_answer=_short_answer(CONTEXT_UNRESOLVED, [], [], []),
            not_established=[{"statement": "any finding",
                              "reason": "context unresolved"}],
            provenance=provenance,
        )
    if compiled.status == UNSUPPORTED_REQUEST:
        return Answer(
            status=UNSUPPORTED_REQUEST, question=compiled.raw_question,
            scope=compiled.resolved_context(),
            short_answer=_short_answer(UNSUPPORTED_REQUEST, [], [], []),
            not_established=[{"statement": "any finding",
                              "reason": "no supported capability maps to this request"}],
            provenance=provenance,
        )
    if plan.status == "DATA_UNAVAILABLE":
        return Answer(
            status=DATA_UNAVAILABLE, question=compiled.raw_question,
            scope=compiled.resolved_context(),
            short_answer=_short_answer(DATA_UNAVAILABLE, [], [], []),
            not_established=[{"statement": "any finding",
                              "reason": plan.reason or "no capability is testable"}],
            missing_evidence=list(plan.availability.unavailable),
            provenance=provenance,
        )

    observations = _extract_observations(results)
    calculations = _extract_calculations(results)
    spatial = _extract_spatial(results)
    residuals = _extract_residuals(results, compiled)
    hypotheses, supporting, contradicting = _extract_hypotheses(results)
    ledger = _extract_evidence_ledger(results)
    counterfactuals = _extract_counterfactuals(results)

    engine_conclusion: Optional[str] = None
    assumptions: list[str] = []
    engine_limitations: list[str] = []
    for cap_id in ("fuse_lap_evidence", "attribute_lap_loss",
                   "decompose_race_gap", "analyze_stint"):
        payload = results.get(cap_id)
        if not isinstance(payload, dict) or payload.get("error"):
            continue
        if isinstance(payload.get("conclusion"), str) and engine_conclusion is None:
            engine_conclusion = payload["conclusion"]
        assumptions.extend(str(a) for a in (payload.get("assumptions") or []))
        engine_limitations.extend(str(x) for x in (payload.get("limitations") or []))

    # --- what could not be established, and why (§12) ---------------------
    not_established: list[dict[str, Any]] = []
    for step in plan.deferred:
        not_established.append({
            "statement": step.capability_id,
            "reason": step.rationale,
            "missing_data": list(step.missing_data),
        })
    for hid, reason in plan.hypotheses_unavailable.items():
        not_established.append({
            "statement": f"hypothesis {hid}",
            "reason": reason,
            "state": "NOT_TESTABLE",
        })
    for cap_id, message in errors.items():
        not_established.append({"statement": cap_id, "reason": message})
    for term in compiled.unsupported_terms:
        not_established.append({
            "statement": f"'{term}'",
            "reason": "no deterministic capability measures this quantity",
        })
    if compiled.spatial_scopes and "corner" in compiled.spatial_scopes and \
            "telemetry" not in plan.availability.available:
        not_established.append({
            "statement": "corner-level attribution",
            "reason": "telemetry unavailable; finest valid resolution is lap/sector",
        })

    # --- status: the honest verdict, never the optimistic one --------------
    # ANSWERABLE requires a measured finding AND no untested asked-for part.
    # A question that got a clean measurement but also hit an unavailable
    # hypothesis is PARTIALLY_ANSWERABLE, and the difference is the whole point
    # of the partial-answer engine.
    measured = bool(observations or calculations)
    any_untestable = any(h["state"] == "UNTESTABLE" for h in hypotheses)
    none_supported = bool(hypotheses) and not any(
        h["state"] == "SUPPORTED" for h in hypotheses)

    if not results:
        # Nothing ran. Whatever the plan looked like, no capability produced a
        # result, so there is nothing established. Reporting ANSWERABLE here
        # would be the single worst failure this system can make: a confident
        # status attached to zero evidence.
        status = INSUFFICIENT_EVIDENCE if plan.status != "DATA_UNAVAILABLE" \
            else DATA_UNAVAILABLE
    elif not (measured or hypotheses or residuals) and not_established:
        status = INSUFFICIENT_EVIDENCE
    elif not_established or any_untestable:
        status = PARTIALLY_ANSWERABLE if measured else ANALYSABLE_WITH_LIMITATIONS
    elif none_supported:
        # Measured and fully investigated, but nothing held up: that is a real
        # answer with a limitation, not a failure.
        status = ANALYSABLE_WITH_LIMITATIONS
    else:
        status = ANSWERABLE

    limitations = list(plan.availability.unavailable)
    for cap in REGISTRY_LIMITATIONS(plan):
        limitations.extend(cap)
    limitations.extend(engine_limitations)

    established = []
    if observations:
        established.append({
            "statement": "measured difference",
            "detail": observations,
        })
    if spatial:
        established.append({"statement": "where it occurred", "detail": spatial})
    if hypotheses:
        established.append({
            "statement": "hypothesis evaluation",
            "detail": hypotheses,
        })
    if residuals:
        established.append({"statement": "what remains unexplained",
                            "detail": residuals})

    return Answer(
        status=status,
        question=compiled.raw_question,
        scope=compiled.resolved_context(),
        short_answer=_short_answer(status, observations, residuals, hypotheses),
        established=established,
        not_established=not_established,
        why_not=[{"statement": n["statement"], "reason": n["reason"]}
                 for n in not_established],
        observations=observations,
        calculations=calculations,
        hypotheses=hypotheses,
        supporting_evidence=supporting,
        contradicting_evidence=contradicting,
        residuals=residuals,
        counterfactuals=counterfactuals,
        spatial=spatial,
        evidence_ledger=ledger,
        engine_conclusion=engine_conclusion,
        assumptions=sorted(set(assumptions)),
        limitations=sorted(set(limitations)),
        missing_evidence=sorted(set(plan.availability.unavailable)),
        provenance=provenance,
        decision_trace=[s.as_dict() for s in plan.steps],
        follow_ups=_follow_ups(plan),
    )


def REGISTRY_LIMITATIONS(plan: InvestigationPlan) -> list[str]:
    """Honest limits declared by the capabilities actually in play."""
    out: list[str] = []
    for step in plan.steps:
        cap = capability(step.capability_id)
        if cap is not None:
            out.extend(cap.limitations)
    return out