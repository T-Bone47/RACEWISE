"""Phase 6O — investigation replay, comparison & engineering memory.

Consumes Phase 6N investigation outputs verbatim; it recalculates nothing
from 6E-6M. Three capabilities:

- SNAPSHOT: formalize the 6N investigation into an immutable, hash-verified
  InvestigationSnapshot (6N's built-in ``investigation_snapshot`` block is
  reused; this module wraps the full investigation with integrity fields).
- REPLAY/COMPARE: rerun the investigation from the snapshot's structured
  input, report exact structured differences (never "results differ"), and
  compare two investigations dimension-by-dimension with descriptive deltas.
- ENGINEERING MEMORY: derive scope-limited, provenance-backed memory items
  from completed investigations. Memory is derived-on-read (zero storage
  growth); it stores evidence, never opinions, and never generalizes beyond
  its declared scope.

REPRODUCE -> COMPARE -> EXPLAIN DELTAS -> TRACE -> LEARN.
No ranking, no scores, no confidence, no "best investigation".
"""
from __future__ import annotations

from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.investigation_synthesis import (
    HYPOTHESIS_IDS, INVESTIGATION_VERSION, _hash_obj,
)

ANALYSIS = "phase_6o_investigation_memory"
MEMORY_VERSION = "6o_memory_v1"
SNAPSHOT_VERSION = "6o_snapshot_v1"

# ---------------------------------------------------------------------------
# closed vocabularies
# ---------------------------------------------------------------------------

VERIFY_STATES = (
    "VALID", "HASH_MISMATCH", "INVALID_SCHEMA", "MISSING_PROVENANCE",
    "INCOMPLETE_SNAPSHOT",
)

REPLAY_STATUSES = (
    "IDENTICAL", "DIFFERENT_DATA", "DIFFERENT_TOOL_VERSION",
    "DIFFERENT_SCHEMA", "DIFFERENT_RESULT", "INVALID_SNAPSHOT",
)

DIFF_CATEGORIES = (
    "INPUT_CHANGE", "DATA_CHANGE", "TOOL_CHANGE", "PROVENANCE_CHANGE",
    "EVIDENCE_CHANGE", "HYPOTHESIS_CHANGE", "FALSIFICATION_CHANGE",
    "COUNTERFACTUAL_CHANGE", "SYNTHESIS_CHANGE", "SCHEMA_CHANGE",
)

COMPATIBILITY_STATES = ("COMPARABLE", "PARTIALLY_COMPARABLE", "NOT_COMPARABLE")

COMPARISON_DIMENSIONS = (
    "QUESTION", "SCOPE", "HYPOTHESES", "EVIDENCE_COVERAGE",
    "HYPOTHESIS_STATES", "FALSIFICATION", "COUNTERFACTUALS", "RESIDUALS",
    "SYNTHESIS", "LIMITATIONS", "PROVENANCE",
)

EVIDENCE_CHANGE_TYPES = (
    "ADDED", "REMOVED", "VALUE_CHANGED", "STATE_CHANGED", "COVERAGE_CHANGED",
    "SOURCE_CHANGED", "UNCHANGED",
)

FALSIFICATION_DELTA_TYPES = (
    "NEW_CONTRADICTION", "RESOLVED_CONTRADICTION", "PERSISTING_CONTRADICTION",
    "EVIDENCE_UNAVAILABLE", "NEW_SUPPORT", "SUPPORT_REMOVED",
    "TESTABILITY_CHANGE", "COVERAGE_CHANGE",
)

COUNTERFACTUAL_DELTA_TYPES = (
    "ADDED", "REMOVED", "RESULT_CHANGED", "MODEL_SCOPE_CHANGED",
    "VALIDITY_CHANGED", "UNCHANGED",
)

# Descriptive conclusion-transition names (no score attached).
SYNTHESIS_TRANSITIONS = (
    "SAME", "MORE_SUPPORTED", "LESS_SUPPORTED", "MIXED_TO_INSUFFICIENT",
    "INSUFFICIENT_TO_TESTABLE", "INSUFFICIENT_TO_SUPPORTED",
    "SUPPORTED_TO_MIXED", "SUPPORTED_TO_INSUFFICIENT",
    "UNAVAILABLE_TO_AVAILABLE", "AVAILABLE_TO_UNAVAILABLE",
)

TRACE_DELTA_TYPES = (
    "TRACE_ADDED", "TRACE_REMOVED", "TRACE_BASIS_CHANGED",
    "TRACE_STATUS_CHANGED", "TRACE_UNCHANGED",
)

MEMORY_STATES = ("ACTIVE", "SUPERSEDED", "INVALIDATED", "CONTEXT_LIMITED")

MEMORY_SCOPES = (
    "SESSION", "RACE", "SEASON", "CIRCUIT", "DRIVER_PAIR", "PATTERN",
    "CROSS_RACE",
)

INVALIDATION_REASONS = (
    "NEW_EVIDENCE", "SOURCE_INVALIDATED", "REPLAY_MISMATCH", "SCOPE_ERROR",
    "MODEL_VERSION_CHANGE", "HUMAN_REVIEW", "DATA_CORRECTION",
)

LINEAGE_RELATIONSHIPS = (
    "REPLAY_OF", "COMPARED_WITH", "DERIVED_MEMORY_FROM", "INVALIDATED_BY",
    "SUPERSEDES", "RELATED_TO",
)

_CONCL_ORDER = {
    "UNAVAILABLE": 0, "NOT_TESTABLE": 1, "INSUFFICIENT_EVIDENCE": 2,
    "MIXED_EVIDENCE": 3, "SUPPORTED_BY_AVAILABLE_EVIDENCE": 4,
}

MAX_MEMORY_ITEMS_PER_INVESTIGATION = 20
MAX_MEMORY_RETRIEVAL_INPUTS = 4


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

_SNAPSHOT_REQUIRED = (
    "snapshot_version", "investigation_id", "investigation_input", "question",
    "hypotheses_in_scope", "evidence_plan", "evidence_ledger",
    "hypothesis_evaluations", "evidence_conflicts", "falsification_gate",
    "counterfactual_candidates", "executed_counterfactuals", "synthesis",
    "decision_trace", "provenance", "output_hash", "snapshot_hash",
    "source_hashes",
)


def build_investigation_snapshot(investigation: dict[str, Any]) -> dict[str, Any]:
    """Formalize a 6N investigation output into an immutable snapshot.

    The snapshot is sufficient to reproduce and compare the investigation
    without hidden runtime state. Identity depends only on normalized input
    and canonical output (no timestamps, PIDs or random IDs).
    """
    snap: dict[str, Any] = {
        "snapshot_version": SNAPSHOT_VERSION,
        "investigation_id": investigation.get("investigation_id"),
        "investigation_input": dict(
            investigation.get("investigation_snapshot", {}).get("input")
            or _input_from_question(investigation)),
        "question": investigation.get("question"),
        "investigation_version": investigation.get("investigation_version"),
        "hypotheses_in_scope": investigation.get("hypotheses_in_scope"),
        "evidence_plan": investigation.get("evidence_plan"),
        "evidence_ledger": investigation.get("evidence_ledger"),
        "hypothesis_evaluations": investigation.get("hypothesis_evaluations"),
        "evidence_conflicts": investigation.get("evidence_conflicts"),
        "falsification_gate": investigation.get("falsification_gate"),
        "counterfactual_candidates": investigation.get(
            "counterfactual_candidates"),
        "executed_counterfactuals": investigation.get(
            "executed_counterfactuals"),
        "synthesis": investigation.get("synthesis"),
        "decision_trace": investigation.get("decision_trace"),
        "provenance": investigation.get("provenance"),
        "analytical_chain": (investigation.get("provenance") or {}).get(
            "analytical_chain"),
        "output_hash": investigation.get("output_hash"),
        "source_hashes": dict(
            investigation.get("investigation_snapshot", {})
            .get("evidence_source_hashes") or {
                e["evidence_id"]: e["source_hash"]
                for e in investigation.get("evidence_ledger") or []}),
    }
    snap["snapshot_hash"] = _hash_obj(
        {k: v for k, v in snap.items() if k != "snapshot_hash"})
    return snap


def _input_from_question(investigation: dict[str, Any]) -> dict[str, Any]:
    q = (investigation.get("question") or {})
    scope = dict(q.get("scope") or {})
    return {
        "question_type": q.get("type"),
        "driver_a": scope.get("driver_a"), "driver_b": scope.get("driver_b"),
        "season": scope.get("season"), "round": scope.get("round"),
        "lap_number": scope.get("lap_number"),
        "stint_number": scope.get("stint_number"),
        "session_type": scope.get("session_type"),
        "pattern_id": scope.get("pattern_id"),
    }


def verify_investigation_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verify snapshot integrity. Never silently repairs."""
    missing = [k for k in _SNAPSHOT_REQUIRED if k not in snapshot]
    if missing:
        core = {"snapshot_version", "investigation_input", "snapshot_hash",
                "output_hash", "provenance"}
        if core <= set(missing):
            return {"status": "INVALID_SCHEMA", "missing_fields": missing,
                    "analysis": ANALYSIS, "version": MEMORY_VERSION}
        if "provenance" in missing:
            return {"status": "MISSING_PROVENANCE", "missing_fields": missing,
                    "analysis": ANALYSIS, "version": MEMORY_VERSION}
        return {"status": "INCOMPLETE_SNAPSHOT", "missing_fields": missing,
                "analysis": ANALYSIS, "version": MEMORY_VERSION}
    recomputed = _hash_obj(
        {k: v for k, v in snapshot.items() if k != "snapshot_hash"})
    status = "VALID" if recomputed == snapshot["snapshot_hash"] \
        else "HASH_MISMATCH"
    return {
        "status": status,
        "snapshot_hash": snapshot["snapshot_hash"],
        "recomputed_hash": recomputed,
        "evidence_count": len(snapshot.get("evidence_ledger") or []),
        "source_hash_count": len(snapshot.get("source_hashes") or {}),
        "analysis": ANALYSIS, "version": MEMORY_VERSION,
    }


def export_snapshot_canonical_json(snapshot: dict[str, Any]) -> str:
    """Deterministic canonical JSON export (stable, provenance-preserving)."""
    import json
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                      default=str, allow_nan=False)


# ---------------------------------------------------------------------------
# structural difference engine
# ---------------------------------------------------------------------------

def _diff_values(path: str, old: Any, new: Any, category: str,
                 source_reference: Any = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            out.extend(_diff_values(
                f"{path}.{k}" if path else k, old.get(k), new.get(k),
                category, source_reference))
        return out
    if isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new) or old != new:
            # list-level diff as a single entry (lists are compared wholesale
            # to keep difference reports bounded)
            if old != new:
                out.append({"path": path, "old_value": old, "new_value": new,
                            "category": category,
                            "source_reference": source_reference})
        return out
    if old != new:
        out.append({"path": path, "old_value": old, "new_value": new,
                    "category": category,
                    "source_reference": source_reference})
    return out


def _classify_differences(diffs: list[dict[str, Any]],
                          snap_a: dict[str, Any],
                          snap_b: dict[str, Any]) -> dict[str, Any]:
    """Attach replay statuses: schema / tool / data / result changes."""
    keys_a, keys_b = set(snap_a), set(snap_b)
    schema_changed = sorted(keys_a ^ keys_b)
    tools_a = {e.get("source_tool") for e in snap_a.get("evidence_ledger") or []}
    tools_b = {e.get("source_tool") for e in snap_b.get("evidence_ledger") or []}
    tools_changed = sorted(t for t in tools_a | tools_b
                           if (t in tools_a) != (t in tools_b))
    hashes_a = set(snap_a.get("source_hashes") or {})
    hashes_b = set(snap_b.get("source_hashes") or {})
    sources_changed = sorted(h for h in hashes_a | hashes_b
                             if (snap_a.get("source_hashes") or {}).get(h)
                             != (snap_b.get("source_hashes") or {}).get(h))
    return {
        "changed_schema_keys": schema_changed,
        "changed_tools": tools_changed,
        "changed_sources": sources_changed,
    }


def replay_engineering_investigation(
    queries: CanonicalQueries,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Replay a snapshot's investigation input through the exact 6N engine.

    Compares the fresh canonical output against the snapshot and reports
    structured differences (path / old / new / category), never prose.
    """
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    base: dict[str, Any] = {
        "analysis": ANALYSIS, "version": MEMORY_VERSION,
        "original_hash": snapshot.get("snapshot_hash"),
    }
    verdict = verify_investigation_snapshot(snapshot)
    base["snapshot_verification"] = verdict["status"]
    if verdict["status"] != "VALID":
        base.update({"status": "INVALID_SNAPSHOT", "identical": False,
                     "differences": [], "replay_hash": None})
        return base

    inp = dict(snapshot.get("investigation_input") or {})
    kwargs = dict(
        question_type=inp.get("question_type"),
        driver_a=inp.get("driver_a"), driver_b=inp.get("driver_b"),
        season=int(inp["season"]), round_num=int(inp["round"]),
        lap_number=inp.get("lap_number"), stint_number=inp.get("stint_number"),
        session_type=inp.get("session_type") or "RACE",
        pattern_id=inp.get("pattern_id"),
    )
    hyps = snapshot.get("hypotheses_in_scope")
    if hyps and hyps != list(HYPOTHESIS_IDS):
        kwargs["hypotheses"] = list(hyps)
    fresh = run_engineering_investigation(queries, **kwargs)
    fresh_snap = build_investigation_snapshot(fresh)

    diffs = _diff_values("", fresh_snap, snapshot, "DATA_CHANGE")
    classified = _classify_differences(diffs, fresh_snap, snapshot)

    if fresh_snap["snapshot_hash"] == snapshot["snapshot_hash"]:
        status = "IDENTICAL"
    elif classified["changed_schema_keys"]:
        status = "DIFFERENT_SCHEMA"
    elif classified["changed_tools"]:
        status = "DIFFERENT_TOOL_VERSION"
    elif classified["changed_sources"]:
        status = "DIFFERENT_DATA"
    else:
        status = "DIFFERENT_RESULT"
    base.update({
        "status": status,
        "identical": status == "IDENTICAL",
        "replay_hash": fresh_snap["snapshot_hash"],
        "replay_output_hash": fresh.get("output_hash"),
        "differences": diffs[:200],
        "difference_count": len(diffs),
        **classified,
        "provenance": {"analytical_chain": ["6E", "6F", "6G", "6H", "6I",
                                            "6J", "6K", "6L", "6M", "6N",
                                            "6O"],
                       "method": "deterministic_snapshot_replay",
                       "investigation_version": INVESTIGATION_VERSION},
    })
    return base


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------

def _scope_of(inv: dict[str, Any]) -> dict[str, Any]:
    return dict(((inv.get("question") or {}).get("scope")) or {})


def _compatibility(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    if (a.get("status") != "VALID") or (b.get("status") != "VALID"):
        return {"state": "NOT_COMPARABLE",
                "reason": "one or both investigations are not VALID"}
    if a.get("question_type") != b.get("question_type"):
        return {"state": "NOT_COMPARABLE",
                "reason": "different question types are structurally "
                          "incommensurable"}
    sa, sb = _scope_of(a), _scope_of(b)
    differing = [k for k in ("season", "round", "driver_a", "driver_b",
                             "lap_number", "stint_number", "pattern_id")
                 if sa.get(k) != sb.get(k)]
    if not differing:
        return {"state": "COMPARABLE", "differing_scope_keys": []}
    return {"state": "PARTIALLY_COMPARABLE",
            "differing_scope_keys": sorted(differing)}


def _evidence_deltas(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    led_a = {e["evidence_id"]: e for e in a.get("evidence_ledger") or []}
    led_b = {e["evidence_id"]: e for e in b.get("evidence_ledger") or []}
    deltas: list[dict[str, Any]] = []
    for eid in sorted(set(led_a) | set(led_b)):
        ea, eb = led_a.get(eid), led_b.get(eid)
        if ea is not None and eb is None:
            deltas.append({"evidence_id_a": eid, "evidence_id_b": None,
                           "change_type": "REMOVED",
                           "old_state": ea.get("state"),
                           "new_state": None,
                           "old_value": ea.get("measured_value"),
                           "new_value": None, "delta": None,
                           "units": ea.get("units"),
                           "source_a": ea.get("source_tool"),
                           "source_b": None,
                           "claim_class": ea.get("claim_class"),
                           "hypothesis_id": None,
                           "interpretation_boundary":
                               "removed evidence is evidence loss, "
                               "never resolution"})
            continue
        if ea is None and eb is not None:
            deltas.append({"evidence_id_a": None, "evidence_id_b": eid,
                           "change_type": "ADDED",
                           "old_state": None, "new_state": eb.get("state"),
                           "old_value": None,
                           "new_value": eb.get("measured_value"),
                           "delta": None, "units": eb.get("units"),
                           "source_a": None, "source_b": eb.get("source_tool"),
                           "claim_class": eb.get("claim_class"),
                           "hypothesis_id": None,
                           "interpretation_boundary":
                               "added evidence is not better evidence; "
                               "it is more evidence"})
            continue
        value_delta = None
        if isinstance(ea.get("measured_value"), (int, float)) and \
                isinstance(eb.get("measured_value"), (int, float)):
            value_delta = round(eb["measured_value"] - ea["measured_value"], 6)
        if ea == eb:
            change = "UNCHANGED"
        elif ea.get("measured_value") != eb.get("measured_value"):
            change = "VALUE_CHANGED"
        elif ea.get("state") != eb.get("state"):
            change = "STATE_CHANGED"
        elif ea.get("source_hash") != eb.get("source_hash"):
            change = "SOURCE_CHANGED"
        else:
            change = "COVERAGE_CHANGED"
        if change != "UNCHANGED":
            deltas.append({
                "evidence_id_a": eid, "evidence_id_b": eid,
                "change_type": change,
                "old_state": ea.get("state"), "new_state": eb.get("state"),
                "old_value": ea.get("measured_value"),
                "new_value": eb.get("measured_value"),
                "delta": value_delta, "units": ea.get("units"),
                "source_a": ea.get("source_tool"),
                "source_b": eb.get("source_tool"),
                "claim_class": ea.get("claim_class"),
                "hypothesis_id": None,
                "interpretation_boundary":
                    "historical evidence and MODELLED counterfactuals are "
                    "never merged; deltas are measured, not evaluative"})
    return deltas


def _hypothesis_deltas(a: dict[str, Any],
                       b: dict[str, Any]) -> list[dict[str, Any]]:
    ev_a = a.get("hypothesis_evaluations") or {}
    ev_b = b.get("hypothesis_evaluations") or {}
    out: list[dict[str, Any]] = []
    for h in HYPOTHESIS_IDS:
        ha, hb = ev_a.get(h) or {}, ev_b.get(h) or {}
        cov_a = ha.get("evidence_coverage") or {}
        cov_b = hb.get("evidence_coverage") or {}
        out.append({
            "hypothesis_id": h,
            "old_state": ha.get("aggregate_state"),
            "new_state": hb.get("aggregate_state"),
            "state_changed": ha.get("aggregate_state")
            != hb.get("aggregate_state"),
            "old_supporting": cov_a.get("supporting"),
            "new_supporting": cov_b.get("supporting"),
            "old_contradicting": cov_a.get("contradicting"),
            "new_contradicting": cov_b.get("contradicting"),
            "old_non_decisive": cov_a.get("non_decisive"),
            "new_non_decisive": cov_b.get("non_decisive"),
            "old_falsification_status": ha.get("falsification_status"),
            "new_falsification_status": hb.get("falsification_status"),
            "unresolved_contradictions_changed":
                ha.get("unresolved_contradictions")
                != hb.get("unresolved_contradictions"),
            "note": "descriptive only; no ranking, no better/worse",
        })
    return out


def _falsification_deltas(a: dict[str, Any],
                          b: dict[str, Any]) -> list[dict[str, Any]]:
    conf_a = a.get("evidence_conflicts") or []
    conf_b = b.get("evidence_conflicts") or []
    led_b_ids = {e["evidence_id"] for e in b.get("evidence_ledger") or []}
    led_a_ids = {e["evidence_id"] for e in a.get("evidence_ledger") or []}
    keys_a = {(tuple(c.get("evidence_ids") or []),
               tuple(c.get("hypothesis_ids") or [])) for c in conf_a}
    keys_b = {(tuple(c.get("evidence_ids") or []),
               tuple(c.get("hypothesis_ids") or [])) for c in conf_b}
    out: list[dict[str, Any]] = []
    for c in conf_b:
        key = (tuple(c.get("evidence_ids") or []),
               tuple(c.get("hypothesis_ids") or []))
        if key not in keys_a:
            out.append({"change_type": "NEW_CONTRADICTION",
                        "hypothesis_ids": list(c.get("hypothesis_ids") or []),
                        "evidence_ids": list(c.get("evidence_ids") or [])})
    for c in conf_a:
        key = (tuple(c.get("evidence_ids") or []),
               tuple(c.get("hypothesis_ids") or []))
        if key in keys_b:
            out.append({"change_type": "PERSISTING_CONTRADICTION",
                        "hypothesis_ids": list(c.get("hypothesis_ids") or []),
                        "evidence_ids": list(c.get("evidence_ids") or [])})
            continue
        # contradiction vanished: resolved ONLY if its evidence still exists;
        # if the evidence itself vanished, that is evidence loss, not resolve
        evidence_survived = all(e in led_b_ids
                                for e in (c.get("evidence_ids") or []))
        if evidence_survived and led_b_ids:
            out.append({"change_type": "RESOLVED_CONTRADICTION",
                        "hypothesis_ids": list(c.get("hypothesis_ids") or []),
                        "evidence_ids": list(c.get("evidence_ids") or [])})
        else:
            out.append({"change_type": "EVIDENCE_UNAVAILABLE",
                        "hypothesis_ids": list(c.get("hypothesis_ids") or []),
                        "evidence_ids": list(c.get("evidence_ids") or []),
                        "note": "contradiction disappeared because its "
                                "evidence vanished; preserved as evidence "
                                "loss, not resolution"})
    gate_a = a.get("falsification_gate") or {}
    gate_b = b.get("falsification_gate") or {}
    sup_a = set(gate_a.get("establishable_hypotheses") or [])
    sup_b = set(gate_b.get("establishable_hypotheses") or [])
    for h in sorted(sup_b - sup_a):
        out.append({"change_type": "NEW_SUPPORT", "hypothesis_ids": [h],
                    "evidence_ids": []})
    for h in sorted(sup_a - sup_b):
        out.append({"change_type": "SUPPORT_REMOVED", "hypothesis_ids": [h],
                    "evidence_ids": []})
    if (gate_a.get("any_unresolved_contradictions")
            != gate_b.get("any_unresolved_contradictions")):
        out.append({"change_type": "TESTABILITY_CHANGE", "hypothesis_ids": [],
                    "evidence_ids": []})
    return out


def _counterfactual_deltas(a: dict[str, Any],
                           b: dict[str, Any]) -> list[dict[str, Any]]:
    cfs_a = {c.get("candidate_id"): c
             for c in a.get("executed_counterfactuals") or []}
    cfs_b = {c.get("candidate_id"): c
             for c in b.get("executed_counterfactuals") or []}
    out: list[dict[str, Any]] = []
    for cid in sorted(set(cfs_a) | set(cfs_b)):
        ca, cb = cfs_a.get(cid), cfs_b.get(cid)
        if cb is None:
            out.append({"candidate_id": cid, "kind": ca.get("kind"),
                        "change_type": "REMOVED",
                        "old_delta_s": ca.get("delta_s"),
                        "new_delta_s": None, "delta_change": None,
                        "model_scope": ca.get("model"),
                        "intervention": ca.get("intervention"),
                        "claim_class": ca.get("claim_class")})
        elif ca is None:
            out.append({"candidate_id": cid, "kind": cb.get("kind"),
                        "change_type": "ADDED",
                        "old_delta_s": None, "new_delta_s": cb.get("delta_s"),
                        "delta_change": None,
                        "model_scope": cb.get("model"),
                        "intervention": cb.get("intervention"),
                        "claim_class": cb.get("claim_class")})
        elif ca == cb:
            out.append({"candidate_id": cid, "kind": ca.get("kind"),
                        "change_type": "UNCHANGED",
                        "old_delta_s": ca.get("delta_s"),
                        "new_delta_s": cb.get("delta_s"),
                        "delta_change": None,
                        "model_scope": ca.get("model"),
                        "intervention": ca.get("intervention"),
                        "claim_class": ca.get("claim_class")})
        else:
            dc = None
            if isinstance(ca.get("delta_s"), (int, float)) and \
                    isinstance(cb.get("delta_s"), (int, float)):
                dc = round(cb["delta_s"] - ca["delta_s"], 6)
            out.append({"candidate_id": cid, "kind": ca.get("kind"),
                        "change_type": "RESULT_CHANGED",
                        "old_delta_s": ca.get("delta_s"),
                        "new_delta_s": cb.get("delta_s"),
                        "delta_change": dc,
                        "model_scope": cb.get("model"),
                        "intervention": cb.get("intervention"),
                        "claim_class": cb.get("claim_class")})
    return out


def _synthesis_transition(old: Optional[str], new: Optional[str]) -> str:
    if old == new:
        return "SAME"
    key = (old, new)
    named = {
        ("MIXED_EVIDENCE", "INSUFFICIENT_EVIDENCE"): "MIXED_TO_INSUFFICIENT",
        ("INSUFFICIENT_EVIDENCE", "NOT_TESTABLE"): "INSUFFICIENT_TO_TESTABLE",
        ("INSUFFICIENT_EVIDENCE", "SUPPORTED_BY_AVAILABLE_EVIDENCE"):
            "INSUFFICIENT_TO_SUPPORTED",
        ("SUPPORTED_BY_AVAILABLE_EVIDENCE", "MIXED_EVIDENCE"):
            "SUPPORTED_TO_MIXED",
        ("SUPPORTED_BY_AVAILABLE_EVIDENCE", "INSUFFICIENT_EVIDENCE"):
            "SUPPORTED_TO_INSUFFICIENT",
        ("UNAVAILABLE", "SUPPORTED_BY_AVAILABLE_EVIDENCE"):
            "UNAVAILABLE_TO_AVAILABLE",
        ("UNAVAILABLE", "MIXED_EVIDENCE"): "UNAVAILABLE_TO_AVAILABLE",
        ("UNAVAILABLE", "INSUFFICIENT_EVIDENCE"): "UNAVAILABLE_TO_AVAILABLE",
        ("SUPPORTED_BY_AVAILABLE_EVIDENCE", "UNAVAILABLE"):
            "AVAILABLE_TO_UNAVAILABLE",
        ("MIXED_EVIDENCE", "UNAVAILABLE"): "AVAILABLE_TO_UNAVAILABLE",
        ("INSUFFICIENT_EVIDENCE", "UNAVAILABLE"): "AVAILABLE_TO_UNAVAILABLE",
    }
    if key in named:
        return named[key]
    oa, ob = _CONCL_ORDER.get(old, -1), _CONCL_ORDER.get(new, -1)
    if ob > oa:
        return "MORE_SUPPORTED"
    if oa > ob:
        return "LESS_SUPPORTED"
    return "SAME"


def _trace_deltas(a: dict[str, Any],
                  b: dict[str, Any]) -> list[dict[str, Any]]:
    tr_a = {t.get("trace_id"): t for t in a.get("decision_trace") or []}
    tr_b = {t.get("trace_id"): t for t in b.get("decision_trace") or []}
    out: list[dict[str, Any]] = []
    for tid in sorted(set(tr_a) | set(tr_b)):
        ta, tb = tr_a.get(tid), tr_b.get(tid)
        if tb is None:
            out.append({"trace_id": tid, "change_type": "TRACE_REMOVED",
                        "statement": (ta or {}).get("statement"),
                        "basis_changed": None, "status_changed": None})
        elif ta is None:
            out.append({"trace_id": tid, "change_type": "TRACE_ADDED",
                        "statement": tb.get("statement"),
                        "basis_changed": None, "status_changed": None})
        else:
            basis_changed = ta.get("basis") != tb.get("basis")
            status_changed = ta.get("status") != tb.get("status")
            if basis_changed:
                out.append({"trace_id": tid,
                            "change_type": "TRACE_BASIS_CHANGED",
                            "statement": tb.get("statement"),
                            "old_basis": ta.get("basis"),
                            "new_basis": tb.get("basis"),
                            "status_changed": status_changed})
            elif status_changed:
                out.append({"trace_id": tid,
                            "change_type": "TRACE_STATUS_CHANGED",
                            "statement": tb.get("statement"),
                            "old_status": ta.get("status"),
                            "new_status": tb.get("status"),
                            "basis_changed": False})
            else:
                out.append({"trace_id": tid, "change_type": "TRACE_UNCHANGED",
                            "statement": tb.get("statement"),
                            "basis_changed": False,
                            "status_changed": False})
    return out


def _dimension_states(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    def same_state(dim: str, same: bool, detail: Any = None) -> dict[str, Any]:
        entry: dict[str, Any] = {"state": "SAME" if same else "CHANGED"}
        if detail is not None:
            entry["detail"] = detail
        return entry

    qa = a.get("question") or {}
    qb = b.get("question") or {}
    cov_a = len(a.get("evidence_ledger") or [])
    cov_b = len(b.get("evidence_ledger") or [])
    syn_a, syn_b = a.get("synthesis") or {}, b.get("synthesis") or {}
    return {
        "QUESTION": same_state("QUESTION",
                               qa.get("type") == qb.get("type"),
                               {"a": qa.get("type"), "b": qb.get("type")}),
        "SCOPE": same_state("SCOPE", _scope_of(a) == _scope_of(b),
                            {"differing": [k for k in
                                           sorted(set(_scope_of(a))
                                                  | set(_scope_of(b)))
                                           if _scope_of(a).get(k)
                                           != _scope_of(b).get(k)]}),
        "HYPOTHESES": same_state(
            "HYPOTHESES",
            a.get("hypotheses_in_scope") == b.get("hypotheses_in_scope"),
            {"a": a.get("hypotheses_in_scope"),
             "b": b.get("hypotheses_in_scope")}),
        "EVIDENCE_COVERAGE": same_state(
            "EVIDENCE_COVERAGE", cov_a == cov_b,
            {"a_items": cov_a, "b_items": cov_b,
             "note": "more evidence is not better evidence"}),
        "HYPOTHESIS_STATES": same_state(
            "HYPOTHESIS_STATES",
            {h: v.get("aggregate_state")
             for h, v in (a.get("hypothesis_evaluations") or {}).items()}
            == {h: v.get("aggregate_state")
                for h, v in (b.get("hypothesis_evaluations") or {}).items()},
            {"a": {h: v.get("aggregate_state")
                   for h, v in (a.get("hypothesis_evaluations")
                                or {}).items()},
             "b": {h: v.get("aggregate_state")
                   for h, v in (b.get("hypothesis_evaluations")
                                or {}).items()}}),
        "FALSIFICATION": same_state(
            "FALSIFICATION",
            a.get("falsification_gate") == b.get("falsification_gate"),
            {"a_blocked": (a.get("falsification_gate") or {})
             .get("hypotheses_with_unresolved_contradictions"),
             "b_blocked": (b.get("falsification_gate") or {})
             .get("hypotheses_with_unresolved_contradictions")}),
        "COUNTERFACTUALS": same_state(
            "COUNTERFACTUALS",
            a.get("executed_counterfactuals") == b.get(
                "executed_counterfactuals"),
            {"a_count": len(a.get("executed_counterfactuals") or []),
             "b_count": len(b.get("executed_counterfactuals") or []),
             "note": "MODELLED outputs stay separate from historical "
                     "evidence"}),
        "RESIDUALS": same_state(
            "RESIDUALS",
            [e for e in a.get("evidence_ledger") or []
             if e.get("claim") and "residual" in e["claim"]]
            == [e for e in b.get("evidence_ledger") or []
                if e.get("claim") and "residual" in e["claim"]],
            {"note": "residuals are reported, never assigned"}),
        "SYNTHESIS": same_state(
            "SYNTHESIS",
            syn_a.get("conclusion_state") == syn_b.get("conclusion_state"),
            {"a": syn_a.get("conclusion_state"),
             "b": syn_b.get("conclusion_state")}),
        "LIMITATIONS": same_state(
            "LIMITATIONS", a.get("limitations") == b.get("limitations")),
        "PROVENANCE": same_state(
            "PROVENANCE",
            (a.get("provenance") or {}).get("analytical_chain")
            == (b.get("provenance") or {}).get("analytical_chain"),
            {"a_layers": (a.get("provenance") or {}).get("layers_executed"),
             "b_layers": (b.get("provenance") or {}).get("layers_executed")}),
    }


def compare_engineering_investigations(
    a: dict[str, Any], b: dict[str, Any],
) -> dict[str, Any]:
    """Compare two 6N investigations dimension-by-dimension.

    Descriptive deltas only: no overall score, no ranking, no better/worse.
    Historical evidence and MODELLED counterfactuals stay separate.
    """
    compat = _compatibility(a, b)
    syn_a = (a.get("synthesis") or {}).get("conclusion_state")
    syn_b = (b.get("synthesis") or {}).get("conclusion_state")
    trace_delta = _trace_deltas(a, b)
    result: dict[str, Any] = {
        "analysis": ANALYSIS,
        "version": MEMORY_VERSION,
        "compatibility": compat,
        "investigation_a": a.get("investigation_id"),
        "investigation_b": b.get("investigation_id"),
        "hash_a": a.get("output_hash"),
        "hash_b": b.get("output_hash"),
        "dimensions": _dimension_states(a, b),
        "evidence_deltas": _evidence_deltas(a, b),
        "hypothesis_deltas": _hypothesis_deltas(a, b),
        "falsification_deltas": _falsification_deltas(a, b),
        "counterfactual_deltas": _counterfactual_deltas(a, b),
        "synthesis_delta": {
            "old_conclusion_state": syn_a,
            "new_conclusion_state": syn_b,
            "transition": _synthesis_transition(syn_a, syn_b),
            "note": "descriptive transition name; no score, no ranking",
        },
        "decision_trace_delta": {
            "changed": [t for t in trace_delta
                        if t["change_type"] != "TRACE_UNCHANGED"],
            "unchanged_count": sum(
                1 for t in trace_delta
                if t["change_type"] == "TRACE_UNCHANGED"),
            "added_count": sum(1 for t in trace_delta
                               if t["change_type"] == "TRACE_ADDED"),
            "removed_count": sum(1 for t in trace_delta
                                 if t["change_type"] == "TRACE_REMOVED"),
        },
        "lineage": [{
            "source_investigation": a.get("investigation_id"),
            "target_investigation": b.get("investigation_id"),
            "relationship": "COMPARED_WITH",
            "provenance": {"method": "deterministic_comparison",
                           "hash_a": a.get("output_hash"),
                           "hash_b": b.get("output_hash")},
        }],
        "provenance": {"analytical_chain": ["6E", "6F", "6G", "6H", "6I",
                                            "6J", "6K", "6L", "6M", "6N",
                                            "6O"],
                       "method": "deterministic_investigation_comparison"},
    }
    return result


# ---------------------------------------------------------------------------
# engineering memory (derived-on-read; zero storage growth)
# ---------------------------------------------------------------------------

def derive_memory_items(investigation: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive scope-limited, provenance-backed memory items from a 6N result.

    Only statements with traceable evidence, explicit scope, explicit
    provenance and explicit limitations are derived. Statements never
    generalize beyond the investigation's declared scope.
    """
    if (investigation.get("status") or "VALID") != "VALID":
        return []
    scope = _scope_of(investigation)
    scope_label = (
        f"{scope.get('season')} R{scope.get('round')} "
        f"{scope.get('driver_a')}/{scope.get('driver_b')}"
        + (f" lap {scope.get('lap_number')}"
           if scope.get("lap_number") is not None else "")
        + (f" stint {scope.get('stint_number')}"
           if scope.get("stint_number") is not None else ""))
    hyp_states = {h: v.get("aggregate_state")
                  for h, v in (investigation.get("hypothesis_evaluations")
                               or {}).items()}
    src_hashes = dict((investigation.get("investigation_snapshot") or {})
                      .get("evidence_source_hashes") or {
                          e["evidence_id"]: e.get("source_hash")
                          for e in investigation.get("evidence_ledger") or []})
    items: list[dict[str, Any]] = []

    def _add(statement: str, evidence_ids: list[str], hyp_ids: list[str],
             evidence_type: str, claim_class: str, limitations: list[str],
             memory_scope: str, created_from: str) -> None:
        if len(items) >= MAX_MEMORY_ITEMS_PER_INVESTIGATION:
            return
        mid = _hash_obj({"analysis": ANALYSIS, "statement": statement,
                         "investigation": investigation.get("investigation_id"),
                         "evidence_ids": evidence_ids, "idx": len(items)})
        items.append({
            "memory_id": mid,
            "statement": statement,
            "evidence_ids": evidence_ids,
            "source_investigation_ids": [investigation.get("investigation_id")],
            "source_hashes": {e: src_hashes[e] for e in evidence_ids
                              if e in src_hashes},
            "scope": {"scope_type": memory_scope,
                      "season": scope.get("season"),
                      "round": scope.get("round"),
                      "driver_pair": sorted([scope.get("driver_a"),
                                             scope.get("driver_b")]),
                      "circuit": None,
                      "lap_number": scope.get("lap_number"),
                      "stint_number": scope.get("stint_number"),
                      "pattern_id": scope.get("pattern_id")},
            "hypothesis_ids": hyp_ids,
            "evidence_type": evidence_type,
            "claim_class": claim_class,
            "limitations": limitations,
            "created_from": created_from,
            "validity_status": "ACTIVE",
            "output_hash": investigation.get("output_hash"),
        })

    # established facts (OBSERVED, scope-bound)
    for f in (investigation.get("synthesis") or {}).get(
            "established_facts") or []:
        _add(
            f"In the {scope_label} investigation, the measured fact was: "
            f"{f.get('claim')} = {f.get('measured_value')} {f.get('units')} "
            "under the available canonical data.",
            [f.get("evidence_id")], [],
            "FACT", "OBSERVED",
            ["fact holds only within the declared scope",
             "observed value is not a mechanism"],
            "RACE", "synthesis.established_facts")

    # hypothesis evaluation outcomes (INFERRED, scope-bound). Only states
    # backed by at least one traceable evidence item are derivable: a
    # NOT_TESTABLE / INSUFFICIENT_EVIDENCE state with an empty evidence list
    # cannot justify a memory item (no fabricated knowledge from absence).
    for h, state in hyp_states.items():
        if state in ("NOT_REQUESTED",):
            continue
        h_eval = ((investigation.get("hypothesis_evaluations") or {})
                  .get(h) or {})
        ev_ids = list(h_eval.get("supporting_evidence") or []) \
            + list(h_eval.get("contradicting_evidence") or [])
        if not ev_ids:
            continue
        _add(
            f"In the {scope_label} investigation, {h} was evaluated as "
            f"{state} under the available evidence.",
            ev_ids[:6], [h], "INFERENCE", "INFERRED",
            ["evaluation is evidence-consistency, not causation",
             "no falsification found is not confirmation",
             "state holds only within the declared scope"],
            "RACE", f"hypothesis_evaluations.{h}")

    # executed counterfactuals (MODELLED — never merged with history)
    for cf in investigation.get("executed_counterfactuals") or []:
        _add(
            f"In the {scope_label} investigation, the 6I model was "
            f"sensitive to the {cf.get('kind')} intervention: "
            f"{cf.get('delta_s')} s (MODELLED; not history, not prediction).",
            [f"evidence_cf_{cf.get('candidate_id', '')[:8]}"],
            ["H1_corner_speed", "H2_throttle", "H3_braking"],
            "COUNTERFACTUAL", "MODELLED",
            ["model sensitivity is not historical effect",
             "counterfactual is not history"],
            "RACE", "executed_counterfactuals")

    return items


def invalidate_memory_item(item: dict[str, Any], reason: str,
                           source: str) -> dict[str, Any]:
    """ACTIVE -> INVALIDATED with reason and provenance (history kept)."""
    if reason not in INVALIDATION_REASONS:
        raise ValueError(f"invalidation reason must be one of "
                         f"{list(INVALIDATION_REASONS)}")
    out = dict(item)
    out["validity_status"] = "INVALIDATED"
    out["invalidation"] = {"reason": reason, "source": source,
                           "prior_status": item.get("validity_status")}
    return out


def retrieve_engineering_memory(
    items: list[dict[str, Any]],
    *,
    season: Optional[int] = None,
    round_num: Optional[int] = None,
    driver: Optional[str] = None,
    driver_pair: Optional[list[str]] = None,
    hypothesis: Optional[str] = None,
    pattern_id: Optional[str] = None,
    scope_type: Optional[str] = None,
    include_invalidated: bool = False,
) -> dict[str, Any]:
    """Deterministic, exact-scope memory retrieval.

    Only items whose declared scope matches the request are returned;
    provenance and exact matching are authoritative (no semantic
    similarity). Invalidated items are excluded unless explicitly included.
    """
    def _match(it: dict[str, Any]) -> bool:
        if not include_invalidated and \
                it.get("validity_status") != "ACTIVE":
            return False
        s = it.get("scope") or {}
        if season is not None and s.get("season") != season:
            return False
        if round_num is not None and s.get("round") != round_num:
            return False
        if driver is not None and driver not in (s.get("driver_pair") or []):
            return False
        if driver_pair is not None and \
                sorted(driver_pair) != sorted(s.get("driver_pair") or []):
            return False
        if hypothesis is not None and \
                hypothesis not in (it.get("hypothesis_ids") or []):
            return False
        if pattern_id is not None and s.get("pattern_id") != pattern_id:
            return False
        if scope_type is not None and s.get("scope_type") != scope_type:
            return False
        return True

    matched = [it for it in items if _match(it)]
    return {
        "analysis": ANALYSIS,
        "version": MEMORY_VERSION,
        "matching_memory_items": matched,
        "match_count": len(matched),
        "scope": {"season": season, "round": round_num, "driver": driver,
                  "driver_pair": driver_pair, "hypothesis": hypothesis,
                  "pattern_id": pattern_id, "scope_type": scope_type,
                  "include_invalidated": include_invalidated},
        "policy": "exact scope and provenance matching only; a related "
                  "prior investigation never transfers its conclusion to "
                  "a new investigation",
        "provenance": {"method": "deterministic_memory_retrieval",
                       "analytical_chain": ["6E", "6F", "6G", "6H", "6I",
                                            "6J", "6K", "6L", "6M", "6N",
                                            "6O"]},
        "limitations": [
            "memory is derived-on-read from the supplied investigations; "
            "nothing is persisted",
            "memory items are scope-limited and never generalize",
        ],
    }
