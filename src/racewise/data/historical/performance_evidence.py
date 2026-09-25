"""Phase 6M - cross-race hypothesis & evidence intelligence.

Consumes Phase 6L recurring performance patterns verbatim (no second
pattern matcher, no second evidence-fusion engine) and answers:

    "When a performance pattern recurs across independent races, does the
     evidence associated with competing hypotheses remain consistent,
     contradictory, variable, or unresolved?"

Design invariants (architectural, not documentation suggestions):

    OBSERVED != MODELLED            SUPPORT != PROOF
    MODEL SENSITIVITY != CAUSATION  NO_FALSIFICATION_FOUND != CONFIRMED
    SIMILARITY != CAUSALITY         TEMPORAL_ALIGNMENT != CAUSAL_ATTRIBUTION
    RECURRENCE != MECHANISM         INSUFFICIENT_EVIDENCE != NOT_SUPPORTED
    NOT_TESTABLE != CONTRADICTED    MISSING_DATA != NEGATIVE_EVIDENCE

Every statement emitted here is an association between measured evidence
states and recurring structures. Nothing is causal, ranked, scored, or
probabilistic. Residuals are reported, never assigned. Contradictions are
preserved, never averaged away.

6G -> 6F state mapping (deterministic; 6G regime summaries carry lap-level
counts so the mapping reads the underlying observations, not just the label):

    6G summary                  -> 6F state        condition
    CONSISTENTLY_SUPPORTED      -> SUPPORTED
    MOSTLY_SUPPORTED            -> SUPPORTED
    INTERMITTENTLY_SUPPORTED    -> CONTRADICTED    counts.contradicted_count > 0
                                -> PARTIALLY_SUPPORTED  otherwise
    CONTRADICTED_OVER_TIME      -> NOT_SUPPORTED   (contradiction detail kept
                                                   in the counts block)
    NOT_SUPPORTED               -> NOT_SUPPORTED
    INSUFFICIENT_EVIDENCE       -> derived from counts:
                                     support>0 and contradicted>0 -> CONTRADICTED
                                     support>0                    -> PARTIALLY_SUPPORTED
                                     otherwise (with observations) -> NOT_SUPPORTED
                                     no observations              -> INSUFFICIENT_EVIDENCE
    NOT_TESTABLE                -> NOT_TESTABLE

Aggregation rules over a pattern's occurrences (documented; S = set of
informative mapped states across occurrences):

    1. S empty                                  -> INSUFFICIENT_EVIDENCE
    2. support present and CONTRADICTED present -> CONTRADICTORY
    3. support present and NOT_SUPPORTED present-> VARIABLE
    4. S == {SUPPORTED}                         -> CONSISTENTLY_SUPPORTED
    5. S subset of support-class, has PARTIAL   -> MOSTLY_SUPPORTED
    6. only non-support states                  -> CONSISTENTLY_NOT_SUPPORTED

support-class = {SUPPORTED, PARTIALLY_SUPPORTED}; non-support-class =
{NOT_SUPPORTED, CONTRADICTED}. Percentages are never used as confidence;
hypotheses are never ranked; all six are always reported independently.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Optional

from racewise.data.historical.evidence_fusion import HYPOTHESES
from racewise.data.historical.performance_patterns import (
    MAX_RACES,
    MIN_RECURRING_RACES,
    _hash_obj,
    analyze_cross_race_performance_patterns,
)
from racewise.data.historical.stint_evidence import _ols_slope

ANALYSIS = "phase_6m_cross_race_pattern_evidence"
EVIDENCE_VERSION = "6m_evidence_v1"

MAX_OCCURRENCES = 8
MIN_OCCURRENCES = 1

# Default corpus width for the underlying Phase 6L scan. Pattern ids are
# scope-dependent in 6L (structural groups form within the analyzed corpus),
# so the caller's 6L browsing scope must be passed through unchanged -
# a pattern_id found at max_races=6 may legitimately not exist at 20.
DEFAULT_MAX_RACES = 8

# Residual-trajectory thresholds across occurrences (documented).
RESIDUAL_SPREAD_STABLE_S = 0.10        # s; same-sign residual means within
                                       # this spread -> RESIDUAL_STABLE
RESIDUAL_TREND_THRESHOLD_S = 0.01      # s per occurrence-index; OLS slope
                                       # over race-ordered occurrences beyond
                                       # this -> RESIDUAL_INCREASING/DECREASING

# Sensitivity spread below this is treated as an aligned model response
# (reuses the 6L match tolerance so no new threshold family is invented).
SENSITIVITY_SPREAD_TOLERANCE_S = 0.5

SUPPORT_CLASS = ("SUPPORTED", "PARTIALLY_SUPPORTED")
NON_SUPPORT_CLASS = ("NOT_SUPPORTED", "CONTRADICTED")

_HYPOTHESIS_IDS = sorted(HYPOTHESES.keys())

_METHOD = (
    "deterministic aggregation of Phase 6G regime-hypothesis summaries over "
    "Phase 6L recurring patterns (state mapping + explicit rules; no ML, no "
    "clustering, no confidence scores, no causality)"
)


# ---------------------------------------------------------------------------
# 6G -> 6F deterministic state mapping
# ---------------------------------------------------------------------------

def _map_hypothesis_state(summary: Optional[str],
                          counts: dict[str, Any]) -> str:
    """Map one occurrence's 6G summary (+ lap-level counts) to a 6F state."""
    if summary == "NOT_TESTABLE":
        return "NOT_TESTABLE"
    supported = int(counts.get("supported_count", 0)) + \
        int(counts.get("partially_supported_count", 0))
    contradicted = int(counts.get("contradicted_count", 0))
    observations = int(counts.get("valid_observations", 0))

    if summary in ("CONSISTENTLY_SUPPORTED", "MOSTLY_SUPPORTED"):
        return "SUPPORTED"
    if summary == "INTERMITTENTLY_SUPPORTED":
        return "CONTRADICTED" if contradicted > 0 else "PARTIALLY_SUPPORTED"
    if summary == "CONTRADICTED_OVER_TIME":
        return "NOT_SUPPORTED"
    if summary == "NOT_SUPPORTED":
        return "NOT_SUPPORTED"
    if summary == "NOT_TESTABLE":
        return "NOT_TESTABLE"
    # INSUFFICIENT_EVIDENCE (or None): derive honestly from the counts.
    if observations <= 0:
        return "INSUFFICIENT_EVIDENCE"
    if supported > 0 and contradicted > 0:
        return "CONTRADICTED"
    if supported > 0:
        return "PARTIALLY_SUPPORTED"
    return "NOT_SUPPORTED"


def _aggregate_state(states: list[str]) -> str:
    """Documented aggregation rule (module docstring, rules 1-6)."""
    informative = sorted({s for s in states
                          if s in SUPPORT_CLASS + NON_SUPPORT_CLASS})
    if not informative:
        return "INSUFFICIENT_EVIDENCE"
    has_support = any(s in SUPPORT_CLASS for s in informative)
    has_contra = "CONTRADICTED" in informative
    has_notsup = "NOT_SUPPORTED" in informative
    if has_support and has_contra:
        return "CONTRADICTORY"
    if has_support and has_notsup:
        return "VARIABLE"
    if informative == ["SUPPORTED"]:
        return "CONSISTENTLY_SUPPORTED"
    if has_support:
        # support-class mixture including PARTIALLY_SUPPORTED
        return "MOSTLY_SUPPORTED"
    return "CONSISTENTLY_NOT_SUPPORTED"


_CONSISTENCY_MAP = {
    "CONTRADICTORY": "CONTRADICTORY",
    "VARIABLE": "VARIABLE",
    "MOSTLY_SUPPORTED": "VARIABLE",
    "CONSISTENTLY_SUPPORTED": "CONSISTENT",
    "CONSISTENTLY_NOT_SUPPORTED": "CONSISTENT",
    "INSUFFICIENT_EVIDENCE": "UNRESOLVED",
}


# ---------------------------------------------------------------------------
# Occurrence-level evidence extraction
# ---------------------------------------------------------------------------

def _occurrence_cell(occ: dict[str, Any]) -> dict[str, Any]:
    """Per-occurrence mapped evidence for every hypothesis (matrix row)."""
    counts = occ.get("hypothesis_counts") or {}
    summaries = occ.get("hypothesis_state_summary") or {}
    cells: dict[str, Any] = {}
    for hid in _HYPOTHESIS_IDS:
        c = counts.get(hid, {})
        summary = summaries.get(hid)
        cells[hid] = {
            "mapped_state": _map_hypothesis_state(summary, c),
            "underlying_6g_summary": summary,
            "underlying_counts": {
                "valid_observations": int(c.get("valid_observations", 0)),
                "supported_count": int(c.get("supported_count", 0)),
                "partially_supported_count":
                    int(c.get("partially_supported_count", 0)),
                "not_supported_count": int(c.get("not_supported_count", 0)),
                "contradicted_count": int(c.get("contradicted_count", 0)),
                "not_testable_count": int(c.get("not_testable_count", 0)),
            },
        }
    return cells


def _occurrence_ref(occ: dict[str, Any], pattern_id: str) -> dict[str, Any]:
    """Stable reference to one occurrence (race/regime/lap-range identity)."""
    return {
        "pattern_id": pattern_id,
        "season": occ["season"],
        "round": occ["round"],
        "circuit_name": occ["circuit_name"],
        "driver_pair": occ["driver_pair"],
        "regime_index": occ["regime_index"],
        "lap_range": occ["lap_range"],
        "pair_inverted_vs_canonical": occ["pair_inverted_vs_canonical"],
    }


# ---------------------------------------------------------------------------
# Hypothesis evidence profile
# ---------------------------------------------------------------------------

def _hypothesis_profile(hid: str, rows: list[dict[str, Any]],
                        refs: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic HypothesisEvidenceProfile for one hypothesis."""
    states = [r["cells"][hid]["mapped_state"] for r in rows]
    agg = _aggregate_state(states)

    supporting, contradicting, not_supported, not_testable, insufficient = \
        [], [], [], [], []
    for r, s in zip(rows, states):
        ref = refs[r["idx"]]
        if s == "SUPPORTED" or s == "PARTIALLY_SUPPORTED":
            supporting.append(ref)
        elif s == "CONTRADICTED":
            contradicting.append(ref)
        elif s == "NOT_SUPPORTED":
            not_supported.append(ref)
        elif s == "NOT_TESTABLE":
            not_testable.append(ref)
        else:
            insufficient.append(ref)

    informative = len(supporting) + len(contradicting) + len(not_supported)
    races = {(ref["season"], ref["round"]) for ref in supporting
             + contradicting + not_supported}

    # Falsification (Section 8): contradiction-first, never confirmation.
    if contradicting:
        falsification_status = "FALSIFICATION_PRESENT"
    elif informative == 0 and not_testable:
        falsification_status = "FALSIFICATION_NOT_TESTABLE"
    elif informative > 0:
        falsification_status = "NO_FALSIFICATION_FOUND"
    else:
        falsification_status = "INSUFFICIENT_EVIDENCE"

    profile = {
        "hypothesis_id": hid,
        "hypothesis_statement": HYPOTHESES[hid]["statement"],
        "aggregate_state": agg,
        "evidence_consistency": _CONSISTENCY_MAP[agg],
        "supporting_occurrences": supporting,
        "contradicting_occurrences": contradicting,
        "not_supported_occurrences": not_supported,
        "not_testable_occurrences": not_testable,
        "insufficient_occurrences": insufficient,
        "evidence_coverage": {
            "informative_occurrences": informative,
            "supporting_occurrences": len(supporting),
            "contradicting_occurrences": len(contradicting),
            "not_supported_occurrences": len(not_supported),
            "not_testable_occurrences": len(not_testable),
            "insufficient_occurrences": len(insufficient),
            "independent_races_with_evidence": len(races),
        },
        "independent_race_count": len({(r["occ"]["season"],
                                        r["occ"]["round"]) for r in rows}),
        "independent_circuit_count": len({r["occ"]["circuit_name"]
                                          for r in rows}),
        "independent_season_count": len({r["occ"]["season"] for r in rows}),
        "first_occurrence": list(min(((r["occ"]["season"], r["occ"]["round"])
                                      for r in rows), default=())),
        "last_occurrence": list(max(((r["occ"]["season"], r["occ"]["round"])
                                     for r in rows), default=())),
        "falsification_status": falsification_status,
        "falsification_note": (
            "NO_FALSIFICATION_FOUND means no available contradictory "
            "evidence exists within the analyzed scope; it is not "
            "confirmation" if falsification_status == "NO_FALSIFICATION_FOUND"
            else None),
    }
    return {k: v for k, v in profile.items() if v is not None}


# ---------------------------------------------------------------------------
# Cross-race falsification check (Section 16)
# ---------------------------------------------------------------------------

def _cross_race_falsification_check(
        profiles: list[dict[str, Any]]) -> dict[str, Any]:
    aggs = [p["aggregate_state"] for p in profiles]
    if any(a == "CONTRADICTORY" for a in aggs):
        result = "CONTRADICTED_BY_OCCURRENCE"
    elif all(a == "INSUFFICIENT_EVIDENCE" for a in aggs):
        result = "INSUFFICIENT_EVIDENCE"
    else:
        meaningful = [a for a in aggs
                      if a != "INSUFFICIENT_EVIDENCE"]
        if all(a == "NOT_TESTABLE" for a in meaningful):
            result = "NOT_TESTABLE"
        else:
            core = [a for a in meaningful if a != "NOT_TESTABLE"]
            distinct = sorted(set(core))
            if not core:
                result = "NOT_TESTABLE" if meaningful else "INSUFFICIENT_EVIDENCE"
            elif len(distinct) == 1:
                result = "CONSISTENT_SUPPORT"
            else:
                result = "MIXED_SUPPORT"
    return {
        "result": result,
        "note": ("comparison of evidence states across independent race "
                 "occurrences; not a statistical test, no significance, "
                 "no confidence"),
    }


# ---------------------------------------------------------------------------
# Context-conditioned evidence (Section 12)
# ---------------------------------------------------------------------------

def _context_conditioned(rows: list[dict[str, Any]],
                         refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Descriptive evidence consistency within context facets (no causality)."""
    def _facet(name: str, pred, note: str) -> Optional[dict[str, Any]]:
        subset = [r for r in rows if pred(r["occ"])]
        if not subset:
            return None
        per_h: dict[str, str] = {}
        for hid in _HYPOTHESIS_IDS:
            st = [r["cells"][hid]["mapped_state"] for r in subset]
            per_h[hid] = _aggregate_state(st)
        return {
            "facet": name,
            "occurrence_count": len(subset),
            "races": [f"{r['occ']['season']} R{r['occ']['round']}"
                      for r in subset],
            "aggregate_state_per_hypothesis": per_h,
            "note": note,
        }

    facets = [
        _facet("dry_compound_laps",
               lambda o: bool(o["compound_summary"]) and all(
                   "WET" not in str(c).upper() and "INTER" not in str(c).upper()
                   for c in o["compound_summary"]),
               "the structure was measured on dry-compound laps here; no "
               "causal role is assigned"),
        _facet("wet_or_intermediate_compound_laps",
               lambda o: bool(o["compound_summary"]) and any(
                   "WET" in str(c).upper() or "INTER" in str(c).upper()
                   for c in o["compound_summary"]),
               "descriptive association only"),
        _facet("pit_overlap",
               lambda o: bool(o["pit_overlap"]),
               "pit-proximity association only"),
        _facet("race_control_overlap",
               lambda o: bool(o["race_control_overlap"]),
               "race-control association only"),
        _facet("telemetry_supported",
               lambda o: o["telemetry_status"] == "TELEMETRY_AVAILABLE",
               "telemetry availability association only"),
    ]
    return [f for f in facets if f is not None]


# ---------------------------------------------------------------------------
# Residual pattern intelligence (Section 13)
# ---------------------------------------------------------------------------

def _residual_summary(rows: list[dict[str, Any]],
                      refs: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic recurring residual structure across occurrences.

    Residual is an unresolved component of the measured gap. It is never
    assigned to any hypothesis, mechanism, or cause.

    Rule (documented; vals are race-ordered residual means):
      < 3 vals or non-finite values present -> characterizable only when all
        same-sign (RESIDUAL_STABLE / RESIDUAL_REVERSAL); else RESIDUAL_UNRESOLVED
      >= 3 vals: OLS slope vs occurrence order with |slope| >
        RESIDUAL_TREND_THRESHOLD_S -> RESIDUAL_INCREASING / RESIDUAL_DECREASING
      else mixed signs (spread > RESIDUAL_SPREAD_STABLE_S) -> RESIDUAL_REVERSAL
      else same-sign with spread <= RESIDUAL_SPREAD_STABLE_S -> RESIDUAL_STABLE
      else RESIDUAL_UNRESOLVED
    """
    vals = [(r["idx"], float(r["occ"]["residual_mean_s"])) for r in rows
            if _finite(r["occ"].get("residual_mean_s"))]
    vals.sort()
    per_occurrence = [
        {"ref": refs[r["idx"]], "residual_state": r["occ"]["residual_state"],
         "residual_mean_s": r["occ"]["residual_mean_s"]}
        for r in rows
    ]
    base = {
        "per_occurrence": per_occurrence,
        "note": "residual = unresolved component; reported, never assigned",
    }
    means = [v for _, v in vals]
    if not means:
        return {**base, "residual_pattern": "INSUFFICIENT_EVIDENCE",
                "note": "no measured residual values in scope; absence is "
                        "preserved, never converted into a pattern"}
    signs = {1 if v > 0 else -1 for v in means}
    if len(means) < 3:
        if signs and len(signs) == 1:
            pattern = "RESIDUAL_STABLE"
        elif len(signs) > 1:
            pattern = "RESIDUAL_REVERSAL"
        else:
            pattern = "RESIDUAL_UNRESOLVED"
    else:
        slope = _ols_slope([float(i) for i, _ in vals], means)
        spread = max(means) - min(means)
        if abs(slope) > RESIDUAL_TREND_THRESHOLD_S:
            pattern = ("RESIDUAL_INCREASING" if slope > 0
                       else "RESIDUAL_DECREASING")
        elif len(signs) > 1 and spread > RESIDUAL_SPREAD_STABLE_S:
            pattern = "RESIDUAL_REVERSAL"
        elif len(signs) == 1 and spread <= RESIDUAL_SPREAD_STABLE_S:
            pattern = "RESIDUAL_STABLE"
        else:
            pattern = "RESIDUAL_UNRESOLVED"
    extra: dict[str, Any] = {}
    if pattern == "RESIDUAL_STABLE":
        extra["residual_mean_range_s"] = round(max(means) - min(means), 4)
    if len(means) >= 3:
        extra["residual_ols_slope_s_per_occurrence"] = round(
            _ols_slope([float(i) for i, _ in vals], means), 4)
    return {**base, "residual_pattern": pattern, **extra}


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


# ---------------------------------------------------------------------------
# Model-sensitivity summary (Section 14) and evidence-vs-sensitivity (15)
# ---------------------------------------------------------------------------

def _sensitivity_summary(rows: list[dict[str, Any]],
                         refs: list[dict[str, Any]]) -> dict[str, Any]:
    per_occurrence = [
        {"ref": refs[r["idx"]],
         "sensitivity_status": r["occ"].get("sensitivity_status"),
         "sensitivity_delta_s": r["occ"].get("sensitivity_delta_s"),
         "sensitivity_parameter": r["occ"].get("sensitivity_parameter")}
        for r in rows
    ]
    values = [(r["idx"], float(r["occ"]["sensitivity_delta_s"]))
              for r in rows if _finite(r["occ"].get("sensitivity_delta_s"))]
    values.sort()
    telemetry_any = any(
        r["occ"].get("telemetry_status") == "TELEMETRY_AVAILABLE"
        for r in rows)
    base = {
        "intervention_definition": (
            "speed-profile deficit-reduction intervention, f=0.5 (Phase 6I/6J "
            "model, applied to each occurrence's own measured telemetry laps)"),
        "per_occurrence": per_occurrence,
        "interpretation_bound": (
            "Under the specified intervention the deterministic model "
            "produces these sensitivity values. This is a model property, "
            "not a historical effect and not recoverable performance."),
    }
    if not values and not telemetry_any:
        return {**base, "status": "TELEMETRY_UNAVAILABLE",
                "note": "no paired telemetry supports sensitivity here; "
                        "absence is preserved, never extrapolated"}
    if len(values) < 2:
        return {**base, "status": "INSUFFICIENT_EVIDENCE",
                "telemetry_supported_occurrences": len(values),
                "note": "fewer than two telemetry-supported occurrences"}
    vals = [v for _, v in values]
    stats = {
        "status": "VALID",
        "telemetry_supported_occurrences": len(values),
        "mean_s": round(sum(vals) / len(vals), 4),
        "min_s": round(min(vals), 4),
        "max_s": round(max(vals), 4),
        "spread_s": round(max(vals) - min(vals), 4),
        "sensitivity_values_s": [round(v, 4) for _, v in values],
    }
    return {**base, **stats}


def _evidence_vs_sensitivity(
        profiles: list[dict[str, Any]],
        sens: dict[str, Any]) -> dict[str, Any]:
    """Structured side-by-side: evidence states vs model response."""
    sens_available = sens.get("status") == "VALID"
    spread_small = (sens_available
                    and float(sens.get("spread_s", 0.0))
                    <= SENSITIVITY_SPREAD_TOLERANCE_S)
    per_hypothesis: dict[str, Any] = {}
    for p in profiles:
        agg = p["aggregate_state"]
        if agg == "INSUFFICIENT_EVIDENCE":
            interp = ("EVIDENCE_ONLY" if sens_available
                      else "BOTH_UNAVAILABLE")
        elif not sens_available:
            interp = "EVIDENCE_ONLY"
        elif agg in ("CONSISTENTLY_SUPPORTED", "CONSISTENTLY_NOT_SUPPORTED"):
            interp = ("CONSISTENT_EVIDENCE_AND_MODEL_RESPONSE"
                      if spread_small
                      else "CONSISTENT_EVIDENCE_DIVERGENT_MODEL_RESPONSE")
        else:
            interp = "VARIABLE_EVIDENCE_AND_MODEL_RESPONSE"
        per_hypothesis[p["hypothesis_id"]] = {
            "aggregate_state": agg,
            "model_sensitivity_status": sens.get("status"),
            "interpretation": interp,
            "note": "alignment description only; no causal reading",
        }
    return {
        "per_hypothesis": per_hypothesis,
        "sensitivity_spread_tolerance_s": SENSITIVITY_SPREAD_TOLERANCE_S,
        "purpose": ("show where evidence and model response align, diverge, "
                    "or remain unavailable; never to conclude causation"),
    }


# ---------------------------------------------------------------------------
# Pattern investigation assembly
# ---------------------------------------------------------------------------

def _evidence_matrix(rows: list[dict[str, Any]],
                     refs: list[dict[str, Any]]) -> dict[str, Any]:
    matrix_rows = []
    for r in rows:
        occ = r["occ"]
        matrix_rows.append({
            "ref": refs[r["idx"]],
            "telemetry_status": occ.get("telemetry_status"),
            "cells": {hid: {
                "mapped_state": r["cells"][hid]["mapped_state"],
                "underlying_6g_summary":
                    r["cells"][hid]["underlying_6g_summary"],
                "underlying_counts": r["cells"][hid]["underlying_counts"],
            } for hid in _HYPOTHESIS_IDS},
        })
    return {
        "columns": list(_HYPOTHESIS_IDS),
        "rows": matrix_rows,
        "note": ("rows are independent race occurrences; cells preserve the "
                 "mapped state AND the underlying 6G summary + lap-level "
                 "counts; nothing is collapsed into prose"),
    }


def _contradiction_summary(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Contradiction-first summary (Section 9): never averaged away."""
    contradicted = [p for p in profiles
                    if p["aggregate_state"] == "CONTRADICTORY"]
    ref_keys = sorted({
        json.dumps(ref, sort_keys=True)
        for p in contradicted
        for ref in p["contradicting_occurrences"]
    })
    return {
        "hypotheses_with_contradictions": [p["hypothesis_id"]
                                           for p in contradicted],
        "contradicting_occurrence_refs": [json.loads(s) for s in ref_keys],
        "policy": ("contradictions are preserved verbatim, never averaged "
                   "away, never converted into a score"),
    }


def _unavailable_evidence(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    unavailable: list[str] = []
    not_testable: list[str] = []
    for p in profiles:
        if p["aggregate_state"] == "INSUFFICIENT_EVIDENCE":
            unavailable.append(p["hypothesis_id"])
        if p["not_testable_occurrences"]:
            not_testable.append(p["hypothesis_id"])
    return {
        "hypotheses_without_informative_evidence": unavailable,
        "hypotheses_with_not_testable_occurrences": not_testable,
        "policy": ("missing data is preserved as missing; it is never "
                   "converted into negative evidence"),
    }


def analyze_cross_race_pattern_evidence(
    queries: Any,
    driver_a: str,
    driver_b: str,
    pattern_id: str,
    seasons: Optional[list[int]] = None,
    rounds: Optional[list[int]] = None,
    circuit: Optional[str] = None,
    max_occurrences: int = MAX_OCCURRENCES,
    max_races: int = DEFAULT_MAX_RACES,
) -> dict[str, Any]:
    """Bounded, deterministic cross-race evidence investigation of one
    recurring Phase 6L pattern.

    Derived-on-read (zero storage growth). Reuses 6L verbatim; adds no
    analytical engine. The six hypotheses are always reported independently;
    ``max_hypotheses`` is deliberately not offered because bounding the
    hypothesis set could only hide evidence.
    """
    base: dict[str, Any] = {
        "analysis": ANALYSIS,
        "version": EVIDENCE_VERSION,
        "question": ("When this performance pattern recurs across "
                     "independent races, does the evidence associated with "
                     "competing hypotheses remain consistent, contradictory, "
                     "variable, or unresolved?"),
        "driver_a": driver_a,
        "driver_b": driver_b,
        "requested_pattern_id": pattern_id,
        "bounds_requested": {
            "seasons": seasons, "rounds": rounds, "circuit": circuit,
            "max_occurrences": max_occurrences, "max_races": max_races,
        },
        "thresholds": {
            "min_recurring_races": MIN_RECURRING_RACES,
            "max_occurrences": MAX_OCCURRENCES,
            "default_max_races": DEFAULT_MAX_RACES,
            "residual_spread_stable_s": RESIDUAL_SPREAD_STABLE_S,
            "residual_trend_threshold_s": RESIDUAL_TREND_THRESHOLD_S,
            "sensitivity_spread_tolerance_s": SENSITIVITY_SPREAD_TOLERANCE_S,
        },
        "methodology": _METHOD,
    }
    if str(driver_a) == str(driver_b):
        return {**base, "status": "INVALID",
                "reason": "driver_a and driver_b must be distinct"}
    if not isinstance(max_occurrences, int) or not (
            MIN_OCCURRENCES <= max_occurrences <= MAX_OCCURRENCES):
        return {**base, "status": "INVALID",
                "reason": (f"max_occurrences must be an integer in "
                           f"[{MIN_OCCURRENCES}, {MAX_OCCURRENCES}]")}
    if not isinstance(max_races, int) or not 1 <= max_races <= MAX_RACES:
        return {**base, "status": "INVALID",
                "reason": f"max_races must be an integer in [1, {MAX_RACES}]"}

    # ---- Phase 6L patterns (reused verbatim, caller's scope) ---------------
    patterns_res = analyze_cross_race_performance_patterns(
        queries, driver_a, driver_b, seasons=seasons, rounds=rounds,
        circuit=circuit, max_races=max_races, max_patterns=50)
    if patterns_res.get("status") != "VALID":
        return {**base, "status": patterns_res.get("status", "UNAVAILABLE"),
                "reason": patterns_res.get(
                    "reason", "Phase 6L pattern analysis did not return a "
                              "valid result"),
                "phase_6l_status": patterns_res.get("status")}

    pattern = next((p for p in patterns_res.get("patterns", [])
                    if p.get("pattern_id") == pattern_id), None)
    if pattern is None:
        return {**base, "status": "UNAVAILABLE",
                "reason": ("pattern_id not found among the recurring "
                           "patterns for this pair/scope in the canonical "
                           "corpus"),
                "available_pattern_count": patterns_res.get("pattern_count")}
    if pattern.get("recurrence_classification") != "RECURRING":
        return {**base, "status": "INSUFFICIENT_EVIDENCE",
                "reason": "pattern is not recurring"}

    # ---- bounded, deterministic occurrence subset --------------------------
    occurrences = list(pattern.get("occurrences", []))
    occurrences.sort(key=lambda o: (o["season"], o["round"],
                                    o["regime_index"]))
    selected = occurrences[:max_occurrences]
    if (len({(o["season"], o["round"]) for o in selected})
            < MIN_RECURRING_RACES):
        return {**base, "status": "INSUFFICIENT_EVIDENCE",
                "reason": (f"filtered subset spans fewer than "
                           f"{MIN_RECURRING_RACES} independent races")}

    refs = [_occurrence_ref(o, pattern_id) for o in selected]
    rows = [{"idx": i, "occ": occ, "cells": _occurrence_cell(occ)}
            for i, occ in enumerate(selected)]

    # ---- evidence matrix + profiles ----------------------------------------
    matrix = _evidence_matrix(rows, refs)
    profiles = [_hypothesis_profile(hid, rows, refs)
                for hid in _HYPOTHESIS_IDS]
    sens = _sensitivity_summary(rows, refs)

    truncation_note = None
    if len(occurrences) > len(selected):
        truncation_note = (f"{len(occurrences) - len(selected)} additional "
                           f"occurrence(s) omitted by max_occurrences="
                           f"{max_occurrences}")

    investigation_id = _hash_obj({
        "analysis": ANALYSIS, "version": EVIDENCE_VERSION,
        "pattern_id": pattern_id,
        "pair": [driver_a, driver_b],
        "scope": {"seasons": seasons, "rounds": rounds, "circuit": circuit},
        "occurrence_refs": refs,
    })

    result: dict[str, Any] = {
        **base,
        "status": "VALID",
        "investigation_id": investigation_id,
        "pattern_id": pattern_id,
        "pattern_version": pattern.get("pattern_version"),
        "occurrence_count": len(selected),
        "independent_race_count": len({(o["season"], o["round"])
                                       for o in selected}),
        "independent_circuit_count": len({o["circuit_name"]
                                          for o in selected}),
        "independent_season_count": len({o["season"] for o in selected}),
        "cross_race_falsification_check": _cross_race_falsification_check(
            profiles),
        "hypothesis_profiles": profiles,
        "evidence_matrix": matrix,
        "contradiction_summary": _contradiction_summary(profiles),
        "falsification_summary": {
            p["hypothesis_id"]: {
                "falsification_status": p["falsification_status"],
                **({"falsification_note": p["falsification_note"]}
                   if p.get("falsification_note") else {}),
                "contradicting_refs": p["contradicting_occurrences"],
                "supporting_refs": p["supporting_occurrences"],
                "not_testable_refs": p["not_testable_occurrences"],
                "unavailable_refs": p["insufficient_occurrences"],
            } for p in profiles
        },
        "context_comparison": _context_conditioned(rows, refs),
        "residual_summary": _residual_summary(rows, refs),
        "sensitivity_summary": sens,
        "evidence_vs_sensitivity": _evidence_vs_sensitivity(profiles, sens),
        "unavailable_evidence": _unavailable_evidence(profiles),
        "occurrence_truncation_note": truncation_note,
        "epistemic_boundaries": [
            "OBSERVED != MODELLED", "SUPPORT != PROOF",
            "MODEL SENSITIVITY != HISTORICAL CAUSATION",
            "NO_FALSIFICATION_FOUND != CONFIRMED",
            "SIMILARITY != CAUSALITY", "RECURRENCE != MECHANISM",
            "TEMPORAL_ALIGNMENT != CAUSAL_ATTRIBUTION",
            "INSUFFICIENT_EVIDENCE != NOT_SUPPORTED",
            "NOT_TESTABLE != CONTRADICTED", "MISSING_DATA != NEGATIVE_EVIDENCE",
        ],
        "limitations": [
            "evidence is aggregated from 6G regime-hypothesis summaries over "
            "small regime lap sets; many cells are honestly "
            "INSUFFICIENT_EVIDENCE and that absence is preserved",
            "an occurrence's evidence describes that regime only; it does "
            "not transfer to other occurrences of the same structure",
            "model sensitivity is a property of the Phase 6I speed-profile "
            "model, not a historical effect",
            *([truncation_note] if truncation_note else []),
        ],
        "provenance": {
            "analytical_chain": ["6E", "6F", "6G", "6H", "6I", "6J", "6K",
                                 "6L", "6M"],
            "phase_6l_pattern_provenance": pattern.get("provenance"),
            "method": _METHOD,
            "state_mapping": ("6G->6F deterministic mapping, module "
                              "docstring of performance_evidence.py, "
                              "version " + EVIDENCE_VERSION),
            "aggregation_rules": ("module docstring rules 1-6; support-class "
                                  "= {SUPPORTED, PARTIALLY_SUPPORTED}; "
                                  "contradiction-first"),
            "source_tables": [
                "canonical_races", "canonical_results", "canonical_laps",
                "canonical_lap_telemetry", "canonical_pit_stops",
                "canonical_stints", "canonical_weather", "canonical_race_control",
            ],
            "provider": "fastf1",
            "generated_at": None,
            "note": "no wall-clock timestamps participate in any hash",
        },
    }
    # Canonical deterministic hash over content excluding nothing runtime
    # (there are no timestamps or durations in the payload at all).
    hashable = {k: v for k, v in result.items() if k != "output_hash"}
    result["output_hash"] = _hash_obj(hashable)
    return result
