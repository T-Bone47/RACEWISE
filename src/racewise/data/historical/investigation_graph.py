"""Phase 6P — Engineering Knowledge Graph & Investigation Graph.

Deterministic, provenance-backed graph over the existing investigation
ecosystem. The graph CONNECTS EVIDENCE; it never INVENTS KNOWLEDGE:

    QUESTION -> HYPOTHESIS -> EVIDENCE -> ANALYSIS
        -> RACE / LAP / STINT / REGIME / PATTERN
        -> COUNTERFACTUAL -> INVESTIGATION -> MEMORY

Design invariants (reused verbatim from 6N/6O):

    * Derived-on-read: zero storage growth. No graph database, no new
      persistence layer — nodes and edges are assembled from the canonical
      DB plus the caller-supplied 6N/6O objects.
    * Closed node-type and edge-type vocabularies. A relationship is only
      created where an existing canonical analytical result states it;
      nothing is inferred from graph topology.
    * Deterministic node/edge identity (no random UUIDs, no timestamps,
      no PIDs). Canonical-JSON hashing with sha256[:16] via the shared
      ``_hash_obj`` helper (Phase 6L convention).
    * SUPPORT is not PROOF. An edge of type SUPPORTS / CONTRADICTS states
      the analytical relationship 6N/6M already recorded; the existence of
      a path is never a causal claim. Contradictions are imported from the
      6N evidence conflicts (never inferred from connectivity).
    * Historical evidence and MODELLED counterfactuals remain distinct
      node types; MEMORY stays bound to its evidence and source
      investigation (never an orphaned universal rule).

Bounded traversal: max_depth <= 8, max_nodes <= 500, max_edges <= 1500.
Values beyond the safe bounds are rejected (INVALID), never silently
clamped.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.investigation_memory import (
    derive_memory_items, verify_investigation_snapshot,
)
from racewise.data.historical.investigation_synthesis import (
    HYPOTHESIS_IDS, QUESTION_TYPES,
)
from racewise.data.historical.performance_patterns import _hash_obj

ANALYSIS = "phase_6p_investigation_graph"
GRAPH_VERSION = "6p_graph_v1"
SNAPSHOT_VERSION = "6p_graph_snapshot_v1"

# ---------------------------------------------------------------------------
# closed vocabularies
# ---------------------------------------------------------------------------

NODE_TYPES = (
    "INVESTIGATION", "QUESTION", "DRIVER", "DRIVER_PAIR", "SEASON", "RACE",
    "SESSION", "LAP", "STINT", "REGIME", "PATTERN", "HYPOTHESIS", "EVIDENCE",
    "COUNTERFACTUAL", "SYNTHESIS", "DECISION_TRACE", "MEMORY",
    "ANALYTICAL_SOURCE", "SNAPSHOT",
)

EDGE_TYPES = (
    "INVESTIGATES", "TARGETS", "COMPARES_WITH", "CONTAINS", "HAS_LAP",
    "HAS_STINT", "HAS_REGIME", "PARTICIPATES_IN", "TESTS", "SUPPORTS",
    "CONTRADICTS", "DERIVED_FROM", "MEASURED_BY", "MODELS",
    "SENSITIVITY_OF", "HAS_EVIDENCE", "HAS_COUNTERFACTUAL", "HAS_SYNTHESIS",
    "HAS_DECISION_TRACE", "GENERATED_MEMORY", "REPLAY_OF", "COMPARED_WITH",
    "RELATED_TO", "SUPERSEDES", "INVALIDATED_BY", "HAS_SOURCE",
)

# Falsification graph states (imported 6N semantics; never collapsed).
FALSIFICATION_STATES = (
    "SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED",
    "MIXED_EVIDENCE", "NOT_TESTABLE", "INSUFFICIENT_EVIDENCE",
    "NOT_REQUESTED",
)

# Traversal bounds (hard caps; rejected, not clamped, beyond the caps).
MAX_DEPTH = 8
MAX_NODES = 500
MAX_EDGES = 1500
DEFAULT_DEPTH = 4

_PHASE_TOOLS = {
    "6E": "attribute_lap_loss",
    "6F": "fuse_lap_evidence",
    "6G": "fuse_stint_evidence",
    "6H": "decompose_race_gap",
    "6I": "simulate_telemetry_counterfactual",
    "6J": "build_performance_envelope",
    "6K": "analyze_performance_regimes",
    "6L": "analyze_cross_race_performance_patterns",
    "6M": "analyze_cross_race_pattern_evidence",
    "6N": "run_engineering_investigation",
    "6O": "build_investigation_snapshot",
    "6P": "build_investigation_graph",
}

_STATE_NOTE = (
    "state is a structural analytical classification imported from the "
    "source layer; it is not a confidence score"
)


# ---------------------------------------------------------------------------
# graph container
# ---------------------------------------------------------------------------

class _Graph:
    """Accumulating node/edge builder with deterministic canonicalization."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: dict[str, dict[str, Any]] = {}

    # -- nodes ----------------------------------------------------------

    def node(self, node_id: str, node_type: str, label: str,
             canonical_reference: Optional[dict[str, Any]] = None,
             metadata: Optional[dict[str, Any]] = None,
             provenance: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if node_type not in NODE_TYPES:
            raise ValueError(f"unknown node type {node_type!r}")
        existing = self._nodes.get(node_id)
        if existing is not None:
            return existing
        node = {
            "node_id": node_id,
            "node_type": node_type,
            "label": label,
            "canonical_reference": dict(canonical_reference or {}),
            "metadata": dict(metadata or {}),
            "provenance": dict(provenance or {}),
        }
        self._nodes[node_id] = node
        return node

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    # -- edges ----------------------------------------------------------

    def edge(self, source_node: str, target_node: str, edge_type: str,
             provenance: Optional[dict[str, Any]] = None,
             source_reference: Optional[dict[str, Any]] = None) -> Optional[str]:
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"unknown edge type {edge_type!r}")
        if source_node not in self._nodes or target_node not in self._nodes:
            raise ValueError(
                f"edge endpoints must exist: {source_node} -> {target_node}")
        if len(self._edges) >= MAX_EDGES:
            return None
        edge_id = _hash_obj({
            "s": source_node, "t": target_node, "e": edge_type,
            "r": _hashable(source_reference or {}),
        })
        if edge_id in self._edges:
            return edge_id
        self._edges[edge_id] = {
            "edge_id": edge_id,
            "source_node": source_node,
            "target_node": target_node,
            "edge_type": edge_type,
            "provenance": dict(provenance or {}),
            "source_reference": dict(source_reference or {}),
        }
        return edge_id

    # -- canonicalization ------------------------------------------------

    def canonical(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        nodes = [self._nodes[k] for k in sorted(self._nodes)]
        edges = sorted(
            self._edges.values(),
            key=lambda e: (e["source_node"], e["edge_type"],
                           e["target_node"], e["edge_id"]))
        return nodes, edges


def _hashable(value: Any) -> Any:
    """Normalize a reference to hashable canonical JSON semantics."""
    if isinstance(value, dict):
        return {k: _hashable(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_hashable(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


# ---------------------------------------------------------------------------
# deterministic node identity (prompt section 7)
# ---------------------------------------------------------------------------

def _season_id(season: int) -> str:
    return f"season:{int(season)}"


def _race_id(season: int, round_num: int) -> str:
    return f"race:{int(season)}:{int(round_num)}"


def _session_id(season: int, round_num: int, session_type: str) -> str:
    return f"session:{int(season)}:{int(round_num)}:{session_type}"


def _driver_id(driver_key: str) -> str:
    return f"driver:{driver_key}"


def _driver_pair_id(a: str, b: str) -> str:
    lo, hi = sorted([str(a), str(b)])
    return f"driver_pair:{lo}:{hi}"


def _lap_id(season: int, round_num: int, driver: str, lap: int) -> str:
    return f"lap:{int(season)}:{int(round_num)}:{driver}:{int(lap)}"


def _stint_id(season: int, round_num: int, driver: str, stint: int) -> str:
    return f"stint:{int(season)}:{int(round_num)}:{driver}:{int(stint)}"


def _regime_id(season: int, round_num: int, start_lap: Any,
               end_lap: Any) -> str:
    return f"regime:{int(season)}:{int(round_num)}:{start_lap}-{end_lap}"


def _hypothesis_id(hid: str) -> str:
    return f"hypothesis:{hid}"


def _pattern_id(pattern_id: str) -> str:
    return f"pattern:{pattern_id}"


def _memory_id(memory_id: str) -> str:
    return f"memory:{memory_id}"


def _source_id(phase: str, tool: str) -> str:
    return f"analytical_source:{phase}:{tool}"


# ---------------------------------------------------------------------------
# shared scope nodes (season / race / session / drivers / pair)
# ---------------------------------------------------------------------------

def _add_scope_nodes(g: _Graph, queries: CanonicalQueries, scope: dict[str, Any],
                     season: int, round_num: int, driver_a: str,
                     driver_b: str) -> dict[str, str]:
    """Deterministic context nodes for an investigation's question scope.

    Every node is created only when the canonical store actually contains
    the referenced entity (resolve_race / resolve_session / get_driver);
    a missing entity yields no node and no edge (never a placeholder).
    """
    ids: dict[str, str] = {}

    race = queries.resolve_race(season, round_num=round_num)
    season_node = season in (r["season"] for r in
                             [race] if race is not None) if race else False
    if race is not None:
        s_id = _season_id(season)
        g.node(s_id, "SEASON", f"Season {season}",
               canonical_reference={"season": season},
               provenance={"source_table": "canonical_races"})
        ids["season"] = s_id
        r_id = _race_id(season, round_num)
        g.node(r_id, "RACE", f"{season} R{round_num} {race['grand_prix']}",
               canonical_reference={
                   "season": season, "round": round_num,
                   "grand_prix": race["grand_prix"],
                   "circuit_name": race["circuit_name"],
                   "date": race["date"], "total_laps": race["total_laps"]},
               provenance={"source_table": "canonical_races",
                           "race_id": race["race_id"]})
        ids["race"] = r_id
        g.edge(s_id, r_id, "CONTAINS",
               provenance={"source_table": "canonical_races"},
               source_reference={"season": season, "round": round_num})
        if season_node:
            pass  # season node created above; kept for clarity
    elif race is None:
        # no canonical race row: the race node cannot exist
        pass

    session = queries.resolve_session(season, round_num, "RACE")
    if session is not None and "race" in ids:
        sess_id = _session_id(season, round_num, "RACE")
        g.node(sess_id, "SESSION", f"{season} R{round_num} RACE session",
               canonical_reference={
                   "season": season, "round": round_num,
                   "session_type": "RACE",
                   "date_start": session["date_start"],
                   "laps_total": session["laps_total"]},
               provenance={"source_table": "canonical_sessions",
                           "session_id": session["session_id"]})
        ids["session"] = sess_id
        g.edge(ids["race"], sess_id, "CONTAINS",
               provenance={"source_table": "canonical_sessions"},
               source_reference={"session_type": "RACE"})

    for role, key in (("a", driver_a), ("b", driver_b)):
        d = queries.get_driver(key)
        if d is None:
            continue
        d_id = _driver_id(key)
        g.node(d_id, "DRIVER", d["full_name"],
               canonical_reference={"driver_key": key, "code": d["code"],
                                    "number": d["driver_number"]},
               provenance={"source_table": "canonical_drivers",
                           "driver_id": d["driver_id"]})
        ids[f"driver_{role}"] = d_id
        if "race" in ids:
            g.edge(d_id, ids["race"], "PARTICIPATES_IN",
                   provenance={"source_table": "canonical_results"},
                   source_reference={"driver_key": key,
                                     "season": season, "round": round_num})
        if "session" in ids:
            # lap / stint scope nodes exist only inside real sessions
            lap = scope.get("lap_number")
            if lap is not None:
                l_id = _lap_id(season, round_num, key, int(lap))
                g.node(l_id, "LAP", f"{key} lap {lap}",
                       canonical_reference={
                           "season": season, "round": round_num,
                           "session_type": "RACE", "driver_key": key,
                           "lap_number": int(lap)},
                       provenance={"source_table": "canonical_lap_times"})
                ids[f"lap_{role}"] = l_id
                g.edge(sess_id, l_id, "HAS_LAP",
                       provenance={"source_table": "canonical_lap_times"},
                       source_reference={"driver_key": key,
                                         "lap_number": int(lap)})
                g.edge(d_id, l_id, "CONTAINS",
                       provenance={"source_table": "canonical_lap_times"},
                       source_reference={"lap_number": int(lap)})
            stint = scope.get("stint_number")
            if stint is not None:
                st_rows = queries.get_stints(season, round_num, "RACE", key)
                row = next((s for s in st_rows
                            if s["stint_number"] == int(stint)), None)
                if row is not None:
                    st_id = _stint_id(season, round_num, key, int(stint))
                    g.node(st_id, "STINT", f"{key} stint {stint}",
                           canonical_reference={
                               "season": season, "round": round_num,
                               "driver_key": key,
                               "stint_number": int(stint),
                               "lap_start": row["lap_start"],
                               "lap_end": row["lap_end"],
                               "compound": row["compound"]},
                           provenance={"source_table": "canonical_stints",
                                       "stint_id": row["stint_id"]})
                    ids[f"stint_{role}"] = st_id
                    g.edge(sess_id, st_id, "HAS_STINT",
                           provenance={"source_table": "canonical_stints"},
                           source_reference={"driver_key": key,
                                             "stint_number": int(stint)})
                    g.edge(d_id, st_id, "CONTAINS",
                           provenance={"source_table": "canonical_stints"},
                           source_reference={"stint_number": int(stint)})

    if ids.get("driver_a") and ids.get("driver_b"):
        p_id = _driver_pair_id(driver_a, driver_b)
        g.node(p_id, "DRIVER_PAIR",
               f"{driver_a} vs {driver_b}",
               canonical_reference={"driver_pair": sorted([driver_a,
                                                           driver_b])},
               provenance={"method": "canonical telemetry pair identity"})
        ids["driver_pair"] = p_id
        g.edge(p_id, ids["driver_a"], "CONTAINS",
               provenance={"method": "canonical telemetry pair identity"})
        g.edge(p_id, ids["driver_b"], "CONTAINS",
               provenance={"method": "canonical telemetry pair identity"})
    return ids


# ---------------------------------------------------------------------------
# analytical source nodes (evidence -> source -> canonical data)
# ---------------------------------------------------------------------------

def _add_evidence_nodes(
    g: _Graph, inv: dict[str, Any], inv_id: str, scope_ids: dict[str, str],
    season: int, round_num: int, queries: CanonicalQueries,
) -> dict[str, str]:
    """Evidence ledger nodes with their exact analytical-source edges.

    SUPPORTS / CONTRADICTS edges are created only where the 6N evaluation
    recorded them (evidence item flags + hypothesis membership); a ledger
    item with neither flag yields only DERIVED_FROM / MEASURED_BY edges.
    """
    ledger = inv.get("evidence_ledger") or []
    evals = inv.get("hypothesis_evaluations") or {}
    conflict_eids: set[str] = set()
    for c in inv.get("evidence_conflicts") or []:
        conflict_eids.update(c.get("evidence_ids") or [])
    ref: dict[str, str] = {}

    hypothesis_requested = inv.get("hypotheses_in_scope") or list(HYPOTHESIS_IDS)

    for e in ledger:
        eid = e["evidence_id"]
        ref[eid] = eid
        # preserve the 6N claim_class as the node type discriminator inside
        # EVIDENCE nodes: historical FACT/CALCULATION/INFERENCE stay EVIDENCE,
        # MODELLED items are COUNTERFACTUAL nodes (never merged).
        if e.get("claim_class") == "MODELLED" or \
                e.get("evidence_type") == "COUNTERFACTUAL":
            node_type = "COUNTERFACTUAL"
            cf_exec = next((c for c in inv.get("executed_counterfactuals") or []
                            if f"evidence_cf_{c['candidate_id'][:8]}" == eid),
                           None)
            meta = {
                "claim_class": "MODELLED",
                "model": (cf_exec or {}).get("model"),
                "intervention": (cf_exec or {}).get("intervention"),
                "parameter": (cf_exec or {}).get("parameter"),
                "baseline": (cf_exec or {}).get("baseline"),
                "measured_delta_s": (cf_exec or {}).get("delta_s"),
                "validation_state": (cf_exec or {}).get("claim_class"),
                "epistemics": (cf_exec or {}).get("epistemics"),
                "note": "MODELLED model sensitivity; not history, not "
                        "prediction",
            }
            cand = next((c for c in inv.get("counterfactual_candidates") or []
                         if c.get("candidate_id") ==
                         ((cf_exec or {}).get("candidate_id"))), None)
            telemetry_scope = ((cand or {}).get("model_scope"))
            if telemetry_scope:
                meta["telemetry_scope"] = telemetry_scope
            g.node(f"evidence:{eid}", node_type, eid,
                   canonical_reference=dict(e.get("source_reference") or {}),
                   metadata=meta,
                   provenance={"source_phase": e.get("source_phase"),
                               "source_tool": e.get("source_tool"),
                               "source_hash": e.get("source_hash")})
            if cf_exec:
                req = (cf_exec.get("result") or {}).get("request") or {}
                target_lap = req.get("lap_number") or \
                    inv.get("question", {}).get("scope", {}).get("lap_number")
                target_stint = req.get("stint_number") or \
                    inv.get("question", {}).get("scope", {}).get("stint_number")
                driver = req.get("driver") or \
                    inv.get("question", {}).get("scope", {}).get("driver_a")
                if target_lap is not None and driver:
                    l_id = _lap_id(season, round_num, driver, int(target_lap))
                    if g.has_node(l_id):
                        g.edge(f"evidence:{eid}", l_id, "MODELS",
                               provenance={"source_phase": "6I"},
                               source_reference={
                                   "candidate_id": cf_exec["candidate_id"]})
                elif target_stint is not None and driver:
                    s_id = _stint_id(season, round_num, driver,
                                     int(target_stint))
                    if g.has_node(s_id):
                        g.edge(f"evidence:{eid}", s_id, "MODELS",
                               provenance={"source_phase": "6I"},
                               source_reference={
                                   "candidate_id": cf_exec["candidate_id"]})
        else:
            state = e.get("state")
            meta = {
                "evidence_type": e.get("evidence_type"),
                "claim_class": e.get("claim_class"),
                "state": state,
                "state_note": _STATE_NOTE if state else None,
                "measured_value": e.get("measured_value"),
                "units": e.get("units"),
                "claim": e.get("claim"),
                "limitations": e.get("limitations") or [],
                "is_conflict_record": eid in conflict_eids,
            }
            g.node(f"evidence:{eid}", "EVIDENCE", eid,
                   canonical_reference=dict(e.get("source_reference") or {}),
                   metadata=meta,
                   provenance={"source_phase": e.get("source_phase"),
                               "source_tool": e.get("source_tool"),
                               "source_hash": e.get("source_hash")})

        # investigation HAS_EVIDENCE (6N ledger membership is the fact)
        g.edge(f"investigation:{inv_id}", f"evidence:{eid}", "HAS_EVIDENCE",
               provenance={"source": "6n evidence_ledger"},
               source_reference={"evidence_id": eid})

        # analytical source node (exact phase/tool from the ledger item)
        phase, tool = e.get("source_phase"), e.get("source_tool")
        if phase and tool:
            src_id = _source_id(phase, tool)
            if not g.has_node(src_id):
                g.node(src_id, "ANALYTICAL_SOURCE", f"{phase} {tool}",
                       canonical_reference={"phase": phase, "tool": tool},
                       provenance={"analytical_chain":
                                   ["6E", "6F", "6G", "6H", "6I", "6J", "6K",
                                    "6L", "6M", "6N"]})
            g.edge(f"evidence:{eid}", src_id, "DERIVED_FROM",
                   provenance={"source_hash": e.get("source_hash")},
                   source_reference={"source_phase": phase,
                                     "source_tool": tool})

        # scope anchoring: the evidence's own source_reference names the
        # race/lap/stint/regime/pattern it is measured on
        sr = dict(e.get("source_reference") or {})
        reg = sr.get("regime") or {}
        if reg.get("start_lap") is not None:
            rg_id = _regime_id(season, round_num, reg.get("start_lap"),
                               reg.get("end_lap"))
            if not g.has_node(rg_id):
                g.node(rg_id, "REGIME",
                       f"regime laps {reg.get('start_lap')}-"
                       f"{reg.get('end_lap')}",
                       canonical_reference={
                           "season": season, "round": round_num,
                           "start_lap": reg.get("start_lap"),
                           "end_lap": reg.get("end_lap"),
                           "regime_index": reg.get("regime_index")},
                       provenance={"source_phase": "6K",
                                   "source_table": "canonical_lap_times"})
            g.edge(f"evidence:{eid}", rg_id, "MEASURED_BY",
                   provenance={"source_phase": e.get("source_phase")},
                   source_reference={"kind": sr.get("kind")})
            race_id = scope_ids.get("race")
            if race_id and g.has_node(race_id):
                g.edge(race_id, rg_id, "HAS_REGIME",
                       provenance={"source_phase": "6K"},
                       source_reference={"start_lap": reg.get("start_lap"),
                                         "end_lap": reg.get("end_lap")})
        elif sr.get("stint_number") is not None and sr.get("drivers"):
            driver = sorted(sr["drivers"])[0]
            s_id = _stint_id(season, round_num, driver,
                             int(sr["stint_number"]))
            if g.has_node(s_id):
                g.edge(f"evidence:{eid}", s_id, "MEASURED_BY",
                       provenance={"source_phase": e.get("source_phase")},
                       source_reference={"kind": sr.get("kind")})
        elif sr.get("lap_number") is not None and sr.get("drivers"):
            driver = sorted(sr["drivers"])[0]
            l_id = _lap_id(season, round_num, driver, int(sr["lap_number"]))
            if g.has_node(l_id):
                g.edge(f"evidence:{eid}", l_id, "MEASURED_BY",
                       provenance={"source_phase": e.get("source_phase")},
                       source_reference={"kind": sr.get("kind")})
        elif sr.get("pattern_id"):
            p_id = _pattern_id(sr["pattern_id"])
            if not g.has_node(p_id):
                g.node(p_id, "PATTERN", f"pattern {sr['pattern_id'][:12]}",
                       canonical_reference={"pattern_id": sr["pattern_id"]},
                       provenance={"source_phase": "6L"})
            g.edge(f"evidence:{eid}", p_id, "MEASURED_BY",
                   provenance={"source_phase": e.get("source_phase")},
                   source_reference={"kind": sr.get("kind")})
        elif "race" in scope_ids:
            g.edge(f"evidence:{eid}", scope_ids["race"], "MEASURED_BY",
                   provenance={"source_phase": e.get("source_phase")},
                   source_reference={"kind": sr.get("kind")})

        # hypothesis TESTS edges (6N ledger hypothesis_ids membership)
        for h in e.get("hypothesis_ids") or []:
            h_id = _hypothesis_id(h)
            if not g.has_node(h_id):
                g.node(h_id, "HYPOTHESIS", h,
                       canonical_reference={"hypothesis_id": h},
                       provenance={"source": "Phase 6F canonical vocabulary"})
            g.edge(h_id, f"evidence:{eid}", "TESTS",
                   provenance={"source": "6n evidence_ledger "
                                          "hypothesis_ids"},
                   source_reference={"hypothesis_id": h})

    # SUPPORTS / CONTRADICTS from the 6N per-hypothesis evaluation
    # (imported relationships; never inferred from connectivity)
    for h, ev in evals.items():
        h_id = _hypothesis_id(h)
        for eid in ev.get("supporting_evidence") or []:
            if g.has_node(f"evidence:{eid}"):
                g.edge(f"evidence:{eid}", h_id, "SUPPORTS",
                       provenance={"source": "6n hypothesis_evaluations",
                                   "relationship": "evidence-consistency, "
                                                   "not causation"},
                       source_reference={"hypothesis_id": h,
                                         "supporting": True})
        for eid in ev.get("contradicting_evidence") or []:
            if g.has_node(f"evidence:{eid}"):
                g.edge(f"evidence:{eid}", h_id, "CONTRADICTS",
                       provenance={"source": "6n hypothesis_evaluations"},
                       source_reference={"hypothesis_id": h,
                                         "contradicting": True})
    return ref


# ---------------------------------------------------------------------------
# investigation graph build
# ---------------------------------------------------------------------------

def build_investigation_graph(
    queries: CanonicalQueries,
    investigation: dict[str, Any],
) -> dict[str, Any]:
    """Build the deterministic investigation graph for one 6N result.

    Nodes: closed 19-type vocabulary; edges: closed 26-type vocabulary.
    Every edge carries provenance naming the exact source block
    (e.g. ``6n evidence_ledger``, ``6n hypothesis_evaluations``).
    Derived-on-read; zero storage growth.
    """
    status = investigation.get("status")
    if status == "INVALID":
        return {
            "analysis": ANALYSIS, "version": GRAPH_VERSION,
            "graph_version": GRAPH_VERSION,
            "status": "INVALID", "reason": investigation.get("reason"),
        }
    if status != "VALID":
        return {
            "analysis": ANALYSIS, "version": GRAPH_VERSION,
            "graph_version": GRAPH_VERSION,
            "status": status or "UNAVAILABLE",
            "reason": investigation.get("reason",
                                        "investigation is not VALID"),
        }

    q = dict((investigation.get("question") or {}).get("scope") or {})
    season = int(q["season"])
    round_num = int(q["round"])
    driver_a = str(q["driver_a"])
    driver_b = str(q["driver_b"])
    inv_id = str(investigation["investigation_id"])
    qt = investigation.get("question_type")
    output_hash = investigation.get("output_hash")

    g = _Graph()

    # --- investigation + question ------------------------------------------
    g.node(f"investigation:{inv_id}", "INVESTIGATION", inv_id[:16],
           canonical_reference={
               "investigation_id": inv_id,
               "investigation_version":
                   investigation.get("investigation_version"),
               "question_type": qt, "output_hash": output_hash},
           provenance={"source": "phase_6n_engineering_investigation"})
    q_id = f"question:{_hash_obj({'qt': qt, 'scope': _hashable(q)})}"
    g.node(q_id, "QUESTION", str(qt),
           canonical_reference={"question_type": qt, "scope": _hashable(q)},
           provenance={"source": "6n question framing (closed vocabulary)"})
    g.edge(f"investigation:{inv_id}", q_id, "INVESTIGATES",
           provenance={"source": "6n question framing"})
    g.edge(q_id, f"investigation:{inv_id}", "TARGETS",
           provenance={"source": "6n question framing"})

    # --- scope nodes (season / race / session / drivers / lap / stint) -----
    scope_ids = _add_scope_nodes(g, queries, q, season, round_num,
                                 driver_a, driver_b)
    race_id = scope_ids.get("race")
    if race_id:
        g.edge(f"investigation:{inv_id}", race_id, "INVESTIGATES",
               provenance={"source": "6n question scope"},
               source_reference={"season": season, "round": round_num})
    pair_id = scope_ids.get("driver_pair")
    if pair_id:
        g.edge(f"investigation:{inv_id}", pair_id, "COMPARES_WITH",
               provenance={"source": "6n question scope"},
               source_reference={"driver_pair": sorted([driver_a, driver_b])})

    # --- evidence + analytical sources + hypotheses -------------------------
    evidence_refs = _add_evidence_nodes(
        g, investigation, inv_id, scope_ids, season, round_num, queries)

    # --- hypothesis states (falsification graph, never collapsed) ----------
    evals = investigation.get("hypothesis_evaluations") or {}
    requested = investigation.get("hypotheses_in_scope") or list(HYPOTHESIS_IDS)
    for h in HYPOTHESIS_IDS:
        h_id = _hypothesis_id(h)
        if not g.has_node(h_id):
            g.node(h_id, "HYPOTHESIS", h,
                   canonical_reference={"hypothesis_id": h},
                   provenance={"source": "Phase 6F canonical vocabulary"})
        ev = evals.get(h) or {}
        if ev.get("requested") is False or h not in requested:
            state = ev.get("aggregate_state") or "NOT_REQUESTED"
        else:
            state = ev.get("aggregate_state") or "NOT_TESTABLE"
        g.edge(f"investigation:{inv_id}", h_id, "TESTS",
               provenance={"source": "6n hypothesis_evaluations",
                           "note": "aggregate state imported from 6N; "
                                   "never ranked, never scored"},
               source_reference={"hypothesis_id": h,
                                 "aggregate_state": state,
                                 "falsification_status":
                                     ev.get("falsification_status")})

    # --- evidence conflicts (contradiction graph; imported, not inferred) --
    for c in investigation.get("evidence_conflicts") or []:
        eids = c.get("evidence_ids") or []
        if len(eids) == 2 and all(g.has_node(f"evidence:{e}") for e in eids):
            g.edge(f"evidence:{eids[0]}", f"evidence:{eids[1]}",
                   "CONTRADICTS",
                   provenance={"source": "6n evidence_conflicts",
                               "conflict_id": c.get("conflict_id"),
                               "conflict_type": c.get("conflict_type"),
                               "resolution_status":
                                   c.get("resolution_status"),
                               "note": "contradiction imported from the "
                                       "analytical layer; never inferred "
                                       "from graph topology"},
                   source_reference={
                       "conflict_id": c.get("conflict_id"),
                       "hypothesis_ids": c.get("hypothesis_ids") or []})

    # --- synthesis + decision trace ----------------------------------------
    syn = investigation.get("synthesis") or {}
    syn_id = f"synthesis:{inv_id}"
    g.node(syn_id, "SYNTHESIS",
           str(syn.get("conclusion_state") or "UNAVAILABLE"),
           canonical_reference={
               "conclusion_state": syn.get("conclusion_state"),
               "unresolved_questions": syn.get("unresolved_questions") or [],
               "limitations": syn.get("limitations") or []},
           provenance={"source": "6n synthesis",
                       "note": "conclusion is evidence-bound; SUPPORT is "
                               "not PROOF"})
    g.edge(f"investigation:{inv_id}", syn_id, "HAS_SYNTHESIS",
           provenance={"source": "6n synthesis"})
    for t in investigation.get("decision_trace") or []:
        t_id = f"decision_trace:{inv_id}:{t['trace_id']}"
        g.node(t_id, "DECISION_TRACE", t["trace_id"],
               canonical_reference={"trace_id": t["trace_id"],
                                    "statement": t["statement"],
                                    "status": t["status"],
                                    "type": t["type"]},
               provenance={"source": "6n decision_trace"})
        g.edge(syn_id, t_id, "HAS_DECISION_TRACE",
               provenance={"source": "6n synthesis.decision_trace_refs"})
        for eid in t.get("basis") or []:
            if g.has_node(f"evidence:{eid}"):
                g.edge(t_id, f"evidence:{eid}", "HAS_EVIDENCE",
                       provenance={"source": "6n decision_trace.basis"},
                       source_reference={"trace_id": t["trace_id"]})

    # --- engineering memory (memory graph; never orphaned) ------------------
    for m in derive_memory_items(investigation):
        m_id = _memory_id(m["memory_id"])
        g.node(m_id, "MEMORY", m["memory_id"][:12],
               canonical_reference={
                   "memory_id": m["memory_id"],
                   "statement": m["statement"],
                   "scope": _hashable(m.get("scope") or {}),
                   "evidence_type": m.get("evidence_type"),
                   "claim_class": m.get("claim_class"),
                   "validity_status": m.get("validity_status"),
                   "limitations": m.get("limitations") or []},
               provenance={"source": "6o derive_memory_items",
                           "note": "scope-bound; a related prior "
                                   "investigation never transfers its "
                                   "conclusion"})
        g.edge(f"investigation:{inv_id}", m_id, "GENERATED_MEMORY",
               provenance={"source": "6o derive_memory_items"},
               source_reference={"memory_id": m["memory_id"]})
        for eid in m.get("evidence_ids") or []:
            if g.has_node(f"evidence:{eid}"):
                g.edge(m_id, f"evidence:{eid}", "DERIVED_FROM",
                       provenance={"source": "6o memory evidence_ids",
                                   "source_hash":
                                       (m.get("source_hashes") or {}).get(eid)},
                       source_reference={"evidence_id": eid})
        for h in m.get("hypothesis_ids") or []:
            h_id = _hypothesis_id(h)
            if g.has_node(h_id):
                g.edge(m_id, h_id, "RELATED_TO",
                       provenance={"source": "6o memory hypothesis_ids"},
                       source_reference={"hypothesis_id": h})

    # --- snapshot node (6O identity, replay/compare lineage lives in 6O) ---
    snap = build_snapshot_identity(investigation)
    snap_id = f"snapshot:{snap['snapshot_hash']}"
    g.node(snap_id, "SNAPSHOT", snap["snapshot_hash"][:12],
           canonical_reference={
               "snapshot_hash": snap["snapshot_hash"],
               "investigation_id": inv_id,
               "output_hash": output_hash},
           provenance={"source": "6o build_investigation_snapshot"})
    g.edge(f"investigation:{inv_id}", snap_id, "REPLAY_OF",
           provenance={"source": "6o snapshot identity",
                       "snapshot_hash": snap["snapshot_hash"],
                       "output_hash": output_hash,
                       "note": "the snapshot is the replayable identity "
                               "of this investigation"},
           source_reference={"snapshot_hash": snap["snapshot_hash"]})

    nodes, edges = g.canonical()
    body = {
        "analysis": ANALYSIS,
        "graph_version": GRAPH_VERSION,
        "investigation_id": inv_id,
        "question_type": qt,
        "question_scope": _hashable(q),
        "output_hash": output_hash,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
    graph_id = _hash_obj({"investigation_id": inv_id,
                          "graph_version": GRAPH_VERSION,
                          "question": _hashable(q)})
    body["graph_id"] = graph_id
    body["source_hashes"] = {
        e["evidence_id"]: e["source_hash"]
        for e in investigation.get("evidence_ledger") or []
        if e.get("source_hash")}
    body["output_hash"] = _hash_obj(
        {k: v for k, v in body.items() if k != "output_hash"})
    body["provenance"] = {
        "analytical_chain": ["6E", "6F", "6G", "6H", "6I", "6J", "6K", "6L",
                             "6M", "6N", "6O", "6P"],
        "method": "deterministic_graph_assembly_from_existing_outputs",
        "graph_version": GRAPH_VERSION,
        "storage": "derived-on-read; zero storage growth",
    }
    body["epistemic_boundaries"] = [
        "a graph edge is an imported analytical relationship, not causation",
        "SUPPORTS/CONTRADICTS states are imported from 6N, never inferred "
        "from graph topology",
        "MODELLED counterfactual nodes stay separate from historical "
        "evidence nodes",
        "MEMORY stays bound to its evidence and source investigation",
        "the graph ranks nothing: no confidence, no strongest hypothesis",
    ]
    return body


def build_snapshot_identity(investigation: dict[str, Any]) -> dict[str, Any]:
    """6O snapshot identity fields without duplicating snapshot content."""
    snap_block = investigation.get("investigation_snapshot") or {}
    return {
        "investigation_id": investigation.get("investigation_id"),
        "output_hash": investigation.get("output_hash"),
        "snapshot_hash": _hash_obj({
            "investigation_id": investigation.get("investigation_id"),
            "input": _hashable(snap_block.get("input") or {}),
            "output_hash": investigation.get("output_hash"),
        }),
    }


# ---------------------------------------------------------------------------
# graph snapshot (deterministic, replayable)
# ---------------------------------------------------------------------------

def build_graph_snapshot(graph: dict[str, Any]) -> dict[str, Any]:
    """Immutable graph snapshot: hash of the canonical node/edge lists."""
    snap: dict[str, Any] = {
        "snapshot_version": SNAPSHOT_VERSION,
        "graph_version": graph.get("graph_version"),
        "graph_id": graph.get("graph_id"),
        "investigation_id": graph.get("investigation_id"),
        "node_count": graph.get("node_count"),
        "edge_count": graph.get("edge_count"),
        "nodes": graph.get("nodes") or [],
        "edges": graph.get("edges") or [],
        "source_hashes": graph.get("source_hashes") or {},
    }
    snap["output_hash"] = _hash_obj(
        {k: v for k, v in snap.items() if k != "output_hash"})
    return snap


def verify_graph_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Verify graph snapshot integrity (hash recompute; never repairs)."""
    required = ("snapshot_version", "graph_id", "nodes", "edges",
                "output_hash")
    missing = [k for k in required if k not in snapshot]
    if missing:
        return {"status": "INVALID_SCHEMA", "missing_fields": missing,
                "analysis": ANALYSIS, "version": GRAPH_VERSION}
    recomputed = _hash_obj(
        {k: v for k, v in snapshot.items() if k != "output_hash"})
    status = "VALID" if recomputed == snapshot["output_hash"] \
        else "HASH_MISMATCH"
    return {"status": status,
            "stored_hash": snapshot["output_hash"],
            "recomputed_hash": recomputed,
            "node_count": len(snapshot.get("nodes") or []),
            "edge_count": len(snapshot.get("edges") or []),
            "analysis": ANALYSIS, "version": GRAPH_VERSION}


def replay_graph_snapshot(
    queries: CanonicalQueries,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild the graph from the snapshot's investigation identity.

    The snapshot stores no free text to execute: replay re-runs the exact
    6N engine from the investigation's structured question scope, rebuilds
    the graph, takes a fresh graph snapshot and compares canonical snapshot
    hashes (nodes + edges + source hashes; never prose).
    """
    verdict = verify_graph_snapshot(snapshot)
    base: dict[str, Any] = {
        "analysis": ANALYSIS, "version": GRAPH_VERSION,
        "snapshot_verification": verdict["status"],
    }
    if verdict["status"] != "VALID":
        base.update({"status": "INVALID_SNAPSHOT", "identical": False,
                     "replay_hash": None})
        return base
    inv_id = snapshot.get("investigation_id")
    node = next((n for n in snapshot.get("nodes") or []
                 if n.get("node_id") == f"investigation:{inv_id}"), None)
    qref = (node or {}).get("canonical_reference") or {}
    qnode = next((n for n in snapshot.get("nodes") or []
                  if n.get("node_type") == "QUESTION"), None)
    scope = dict((qnode or {}).get("canonical_reference", {}).get("scope")
                 or {})
    if not scope or not qref.get("question_type"):
        base.update({"status": "INVALID_SNAPSHOT", "identical": False,
                     "replay_hash": None,
                     "reason": "snapshot lacks the structured question scope"})
        return base
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )
    inv = run_engineering_investigation(
        queries,
        question_type=qref["question_type"],
        driver_a=scope["driver_a"], driver_b=scope["driver_b"],
        season=int(scope["season"]), round_num=int(scope["round"]),
        lap_number=scope.get("lap_number"),
        stint_number=scope.get("stint_number"),
        session_type=scope.get("session_type") or "RACE",
        pattern_id=scope.get("pattern_id"))
    if inv.get("status") != "VALID":
        base.update({"status": "UNAVAILABLE",
                     "reason": inv.get("reason"),
                     "identical": False, "replay_hash": None})
        return base
    fresh_graph = build_investigation_graph(queries, inv)
    fresh_snap = build_graph_snapshot(fresh_graph)
    replay_hash = fresh_snap["output_hash"]
    identical = replay_hash == snapshot["output_hash"]
    base.update({
        "status": "IDENTICAL" if identical else "DIFFERENT_RESULT",
        "identical": identical,
        "replay_hash": replay_hash,
        "stored_hash": snapshot["output_hash"],
        "replay_node_count": fresh_graph["node_count"],
        "replay_edge_count": fresh_graph["edge_count"],
        "provenance": {"method": "deterministic_graph_replay"},
    })
    return base


# ---------------------------------------------------------------------------
# bounded traversal (prompt sections 17-18)
# ---------------------------------------------------------------------------

_TRAVERSAL_KINDS = {
    "NEIGHBORS": None,
    "EVIDENCE": ("HAS_EVIDENCE", "GENERATED_MEMORY"),
    "HYPOTHESES": ("TESTS", "SUPPORTS", "CONTRADICTS"),
    "INVESTIGATIONS": ("INVESTIGATES", "TARGETS", "REPLAY_OF",
                       "COMPARED_WITH"),
    "PROVENANCE": ("DERIVED_FROM", "HAS_SOURCE"),
    "COUNTERFACTUALS": ("HAS_COUNTERFACTUAL", "MODELS"),
    "MEMORY": ("GENERATED_MEMORY",),
    "SOURCES": ("DERIVED_FROM",),
}


def traverse_graph(
    graph: dict[str, Any],
    start_node: str,
    *,
    direction: str = "BOTH",
    traversal_kind: str = "NEIGHBORS",
    max_depth: int = DEFAULT_DEPTH,
    max_nodes: int = 200,
    max_edges: int = 800,
) -> dict[str, Any]:
    """Deterministic bounded BFS from one node.

    Only structured traversal kinds are offered (NEIGHBORS / EVIDENCE /
    HYPOTHESES / INVESTIGATIONS / PROVENANCE / COUNTERFACTUALS / MEMORY /
    SOURCES) — no arbitrary query language. Bounds are rejected, never
    silently clamped.
    """
    if traversal_kind not in _TRAVERSAL_KINDS:
        return {"status": "INVALID",
                "reason": (f"traversal_kind must be one of "
                           f"{sorted(_TRAVERSAL_KINDS)}")}
    if direction not in ("OUT", "IN", "BOTH"):
        return {"status": "INVALID",
                "reason": "direction must be one of ['OUT', 'IN', 'BOTH']"}
    if not isinstance(max_depth, int) or not 1 <= max_depth <= MAX_DEPTH:
        return {"status": "INVALID",
                "reason": f"max_depth must be an integer in [1, {MAX_DEPTH}]"}
    if not isinstance(max_nodes, int) or not 1 <= max_nodes <= MAX_NODES:
        return {"status": "INVALID",
                "reason": f"max_nodes must be an integer in [1, {MAX_NODES}]"}
    if not isinstance(max_edges, int) or not 1 <= max_edges <= MAX_EDGES:
        return {"status": "INVALID",
                "reason": f"max_edges must be an integer in [1, {MAX_EDGES}]"}

    nodes = {n["node_id"]: n for n in graph.get("nodes") or []}
    edges = graph.get("edges") or []
    if start_node not in nodes:
        return {"status": "NOT_FOUND",
                "reason": f"unknown node {start_node!r}"}

    allowed = _TRAVERSAL_KINDS[traversal_kind]
    adj_out: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    adj_in: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for e in edges:
        if allowed is not None and e["edge_type"] not in allowed:
            continue
        adj_out.setdefault(e["source_node"], []).append(
            (e["target_node"], e))
        adj_in.setdefault(e["target_node"], []).append(
            (e["source_node"], e))

    visited_nodes = {start_node}
    visited_edges: list[dict[str, Any]] = []
    frontier = [(start_node, 0)]
    while frontier and len(visited_nodes) < max_nodes and \
            len(visited_edges) < max_edges:
        nid, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        nexts: list[tuple[str, dict[str, Any]]] = []
        if direction in ("OUT", "BOTH"):
            nexts.extend(adj_out.get(nid, []))
        if direction in ("IN", "BOTH"):
            nexts.extend(adj_in.get(nid, []))
        nexts.sort(key=lambda t: (t[0], t[1]["edge_id"]))
        for target, e in nexts:
            if len(visited_edges) >= max_edges:
                break
            if e["edge_id"] not in {x["edge_id"] for x in visited_edges}:
                visited_edges.append(e)
            if target not in visited_nodes and \
                    len(visited_nodes) < max_nodes:
                visited_nodes.add(target)
                frontier.append((target, depth + 1))

    sub_nodes = [nodes[nid] for nid in sorted(visited_nodes)]
    visited_edges.sort(key=lambda e: (e["source_node"], e["edge_type"],
                                      e["target_node"], e["edge_id"]))
    return {
        "status": "OK",
        "analysis": ANALYSIS, "version": GRAPH_VERSION,
        "start_node": start_node,
        "direction": direction,
        "traversal_kind": traversal_kind,
        "bounds": {"max_depth": max_depth, "max_nodes": max_nodes,
                   "max_edges": max_edges},
        "truncated": len(visited_nodes) >= max_nodes
        or len(visited_edges) >= max_edges,
        "nodes": sub_nodes,
        "edges": visited_edges,
        "node_count": len(sub_nodes),
        "edge_count": len(visited_edges),
    }


# ---------------------------------------------------------------------------
# path queries (prompt sections 19-21)
# ---------------------------------------------------------------------------

def explain_investigation_path(
    graph: dict[str, Any],
    investigation_id: str,
    target_node: str,
    *,
    max_depth: int = MAX_DEPTH,
) -> dict[str, Any]:
    """Ordered provenance path from the investigation to a target node.

    BFS shortest path (deterministic tie-break by sorted node ids) — the
    graph equivalent of the 6N decision trace: every hop names its edge
    type and provenance.
    """
    if not isinstance(max_depth, int) or not 1 <= max_depth <= MAX_DEPTH:
        return {"status": "INVALID",
                "reason": f"max_depth must be an integer in [1, {MAX_DEPTH}]"}
    nodes = {n["node_id"]: n for n in graph.get("nodes") or []}
    edges = graph.get("edges") or []
    root = f"investigation:{investigation_id}"
    if root not in nodes:
        return {"status": "UNAVAILABLE",
                "reason": f"unknown investigation {investigation_id!r}"}
    if target_node not in nodes:
        return {"status": "NOT_FOUND",
                "reason": f"unknown node {target_node!r}"}
    adj: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for e in edges:
        adj.setdefault(e["source_node"], []).append((e["target_node"], e))
    # BFS with deterministic expansion order
    prev: dict[str, tuple[str, dict[str, Any]]] = {}
    seen = {root}
    frontier = [root]
    found = root == target_node
    depth = 0
    while frontier and not found and depth < max_depth:
        nxt: list[str] = []
        for nid in sorted(frontier):
            for target, e in sorted(adj.get(nid, []),
                                    key=lambda t: t[0]):
                if target in seen:
                    continue
                seen.add(target)
                prev[target] = (nid, e)
                if target == target_node:
                    found = True
                    break
                nxt.append(target)
            if found:
                break
        frontier = nxt
        depth += 1
    if not found:
        return {"status": "NOT_FOUND",
                "reason": (f"no path from the investigation to "
                           f"{target_node!r} within max_depth={max_depth}")}
    path: list[dict[str, Any]] = []
    cur = target_node
    while cur != root:
        parent, e = prev[cur]
        path.append({"step": cur, "node_type": nodes[cur]["node_type"],
                     "via_edge_type": e["edge_type"],
                     "via_edge_id": e["edge_id"],
                     "via_provenance": e["provenance"]})
        cur = parent
    path.append({"step": root, "node_type": "INVESTIGATION",
                 "via_edge_type": None, "via_edge_id": None,
                 "via_provenance": None})
    path.reverse()
    return {
        "status": "OK", "analysis": ANALYSIS, "version": GRAPH_VERSION,
        "investigation_id": investigation_id,
        "target_node": target_node,
        "path_length": len(path),
        "path": path,
        "note": "a path is provenance navigation, not a causal chain",
    }


def trace_evidence_to_source(
    graph: dict[str, Any],
    evidence_id: str,
) -> dict[str, Any]:
    """Evidence -> analytical source -> scope, with explicit missing
    provenance (never a fabricated path)."""
    eid = evidence_id if evidence_id.startswith("evidence:") \
        else f"evidence:{evidence_id}"
    nodes = {n["node_id"]: n for n in graph.get("nodes") or []}
    if eid not in nodes:
        return {"status": "NOT_FOUND",
                "reason": f"unknown evidence {evidence_id!r}"}
    node = nodes[eid]
    edges = graph.get("edges") or []
    src_edges = [e for e in edges
                 if e["source_node"] == eid
                 and e["edge_type"] in ("DERIVED_FROM", "MEASURED_BY",
                                        "MODELS")]
    src_edges.sort(key=lambda e: (e["edge_type"], e["target_node"]))
    sources = []
    for e in src_edges:
        target = nodes.get(e["target_node"]) or {}
        sources.append({
            "edge_type": e["edge_type"],
            "node_id": e["target_node"],
            "node_type": target.get("node_type"),
            "label": target.get("label"),
            "canonical_reference": target.get("canonical_reference") or {},
            "source_phase": (node.get("provenance") or {}).get("source_phase"),
            "source_tool": (node.get("provenance") or {}).get("source_tool"),
            "source_hash": (node.get("provenance") or {}).get("source_hash"),
            "provenance": e["provenance"],
        })
    missing: list[str] = []
    prov = node.get("provenance") or {}
    for k in ("source_phase", "source_tool", "source_hash"):
        if not prov.get(k):
            missing.append(k)
    if not sources:
        missing.append("analytical_source")
    return {
        "status": "OK", "analysis": ANALYSIS, "version": GRAPH_VERSION,
        "evidence_id": eid,
        "node": node,
        "sources": sources,
        "missing_provenance": missing,
        "note": ("path is complete"
                 if not missing
                 else "path is incomplete; the missing provenance fields "
                      "are listed explicitly"),
    }


def trace_hypothesis_evidence(
    graph: dict[str, Any],
    hypothesis_id: str,
    investigation_id: Optional[str] = None,
) -> dict[str, Any]:
    """Supporting / contradicting / non-decisive evidence for one hypothesis,
    plus related counterfactuals — descriptive only, never ranked."""
    hid = hypothesis_id if hypothesis_id.startswith("hypothesis:") \
        else _hypothesis_id(hypothesis_id)
    nodes = {n["node_id"]: n for n in graph.get("nodes") or []}
    if hid not in nodes:
        return {"status": "NOT_FOUND",
                "reason": f"unknown hypothesis {hypothesis_id!r}"}
    edges = graph.get("edges") or []
    inv_prefix = (f"investigation:{investigation_id}"
                  if investigation_id else "investigation:")
    supporting, contradicting, non_decisive, counterfactuals = \
        [], [], [], []
    tested_by: list[str] = []
    for e in edges:
        if e["edge_type"] == "TESTS" and e["source_node"] == hid and \
                e["target_node"].startswith(inv_prefix):
            tested_by.append(e["target_node"])
        if e["target_node"] != hid:
            continue
        src = nodes.get(e["source_node"]) or {}
        if e["edge_type"] == "SUPPORTS":
            supporting.append(_evidence_ref(e["source_node"], src,
                                            e["provenance"]))
        elif e["edge_type"] == "CONTRADICTS":
            contradicting.append(_evidence_ref(e["source_node"], src,
                                               e["provenance"]))
    supporting.sort(key=lambda r: r["node_id"])
    contradicting.sort(key=lambda r: r["node_id"])
    # non-decisive: TESTS edges from the hypothesis onto evidence nodes
    # that carry neither a SUPPORTS nor a CONTRADICTS edge to this hyp
    supports_ids = {s["node_id"] for s in supporting}
    contradicts_ids = {c["node_id"] for c in contradicting}
    for e in edges:
        if e["edge_type"] == "TESTS" and e["source_node"] == hid and \
                e["target_node"].startswith("evidence:"):
            if e["target_node"] not in supports_ids and \
                    e["target_node"] not in contradicts_ids:
                non_decisive.append(_evidence_ref(e["target_node"],
                                                  nodes.get(e["target_node"])
                                                  or {}, e["provenance"]))
    non_decisive.sort(key=lambda r: r["node_id"])
    for e in edges:
        if e["edge_type"] == "TESTS" and e["target_node"] == hid and \
                e["source_node"].startswith("evidence:") and \
                (nodes.get(e["source_node"]) or {}).get("node_type") == \
                "COUNTERFACTUAL":
            counterfactuals.append(_evidence_ref(e["source_node"],
                                                 nodes.get(e["source_node"])
                                                 or {}, e["provenance"]))
    counterfactuals.sort(key=lambda r: r["node_id"])
    tested_by.sort()
    return {
        "status": "OK", "analysis": ANALYSIS, "version": GRAPH_VERSION,
        "hypothesis_id": hid,
        "investigations": tested_by,
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "non_decisive_evidence": non_decisive,
        "counterfactuals": counterfactuals,
        "note": ("evidence lists are descriptive; no ranking, no scoring"),
    }


def _evidence_ref(node_id: str, node: dict[str, Any],
                  provenance: dict[str, Any]) -> dict[str, Any]:
    meta = node.get("metadata") or {}
    return {
        "node_id": node_id,
        "node_type": node.get("node_type"),
        "claim_class": meta.get("claim_class"),
        "state": meta.get("state"),
        "measured_value": meta.get("measured_value"),
        "units": meta.get("units"),
        "provenance": provenance,
    }


# ---------------------------------------------------------------------------
# lineage import (6O relationships; never invented)
# ---------------------------------------------------------------------------

def merge_investigation_graphs(*graphs: dict[str, Any]) -> dict[str, Any]:
    """Union of investigation graphs (deterministic; dedupe by id).

    Used to connect two or more investigations in one navigable graph so
    that 6O lineage edges (COMPARED_WITH, REPLAY_OF, ...) can be attached
    between them. Node/edge identity is content-addressed, so shared
    context nodes (same race, same drivers, same hypotheses) merge
    naturally; nodes absent from a graph stay absent (never invented).
    """
    g = _Graph()
    for graph in graphs:
        for n in graph.get("nodes") or []:
            g._nodes[n["node_id"]] = n
        for e in graph.get("edges") or []:
            g._edges[e["edge_id"]] = e
    nodes, edges = g.canonical()
    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def add_lineage_edges(
    graph: dict[str, Any],
    relationship: str,
    source_investigation_id: str,
    target_investigation_id: str,
    provenance: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Attach a 6O lineage relationship between two investigations.

    Only 6O's own vocabulary (REPLAY_OF / COMPARED_WITH / DERIVED_MEMORY_FROM
    / INVALIDATED_BY / SUPERSEDES / RELATED_TO) is accepted; the caller must
    supply the 6O provenance that established the relationship.
    """
    from racewise.data.historical.investigation_memory import (
        LINEAGE_RELATIONSHIPS,
    )
    if relationship not in LINEAGE_RELATIONSHIPS:
        return {"status": "INVALID",
                "reason": (f"relationship must be one of "
                           f"{list(LINEAGE_RELATIONSHIPS)}")}
    nodes = {n["node_id"] for n in graph.get("nodes") or []}
    src = f"investigation:{source_investigation_id}"
    tgt = f"investigation:{target_investigation_id}"
    if src not in nodes or tgt not in nodes:
        return {"status": "NOT_FOUND",
                "reason": "both investigations must already be graph nodes"}
    g = _Graph()
    for n in graph.get("nodes") or []:
        g._nodes[n["node_id"]] = n
    for e in graph.get("edges") or []:
        g._edges[e["edge_id"]] = e
    edge_id = g.edge(src, tgt, relationship,
                     provenance=provenance
                     or {"source": "6o lineage (caller-supplied)"},
                     source_reference={"relationship": relationship})
    nodes_list, edges_list = g.canonical()
    out = dict(graph)
    out["nodes"] = nodes_list
    out["edges"] = edges_list
    out["node_count"] = len(nodes_list)
    out["edge_count"] = len(edges_list)
    out["lineage_edges_added"] = [edge_id] if edge_id else []
    out["status"] = "OK"
    return out


# ---------------------------------------------------------------------------
# closed-vocabulary helpers for surfaces (MCP / API / frontend)
# ---------------------------------------------------------------------------

def graph_vocabulary() -> dict[str, Any]:
    """The closed graph vocabulary (node types, edge types, bounds)."""
    return {
        "node_types": list(NODE_TYPES),
        "edge_types": list(EDGE_TYPES),
        "traversal_kinds": sorted(_TRAVERSAL_KINDS),
        "bounds": {"max_depth": MAX_DEPTH, "max_nodes": MAX_NODES,
                   "max_edges": MAX_EDGES},
        "question_types": list(QUESTION_TYPES),
        "hypothesis_ids": list(HYPOTHESIS_IDS),
    }
