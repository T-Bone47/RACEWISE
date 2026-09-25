"""Phase 6O Q17 benchmark: investigation replay, comparison & memory.

Every case uses real canonical investigations from the 6N engine - none are
invented. Expected structural states derive from actual canonical outputs.
Deterministic: every case records replay/comparison/memory identity.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.investigation_memory import (
    MAX_MEMORY_ITEMS_PER_INVESTIGATION, build_investigation_snapshot,
    compare_engineering_investigations, derive_memory_items,
    invalidate_memory_item, replay_engineering_investigation,
    retrieve_engineering_memory, verify_investigation_snapshot,
)
from racewise.data.historical.performance_patterns import _hash_obj

Q17_VERSION = "q17_investigation_memory_v1"

LAP6 = {"question_type": "LAP_PERFORMANCE",
        "driver_a": "max-verstappen", "driver_b": "sergio-perez",
        "season": 2023, "round": 1, "lap_number": 6}
LAP11 = {**LAP6, "lap_number": 11}
STINT1 = {"question_type": "STINT_PERFORMANCE",
          "driver_a": "max-verstappen", "driver_b": "sergio-perez",
          "season": 2023, "round": 1, "stint_number": 1}
RACEGAP24 = {"question_type": "RACE_GAP",
             "driver_a": "max-verstappen", "driver_b": "sergio-perez",
             "season": 2024, "round": 14}
REGIME22 = {"question_type": "PERFORMANCE_REGIME",
            "driver_a": "max-verstappen", "driver_b": "sergio-perez",
            "season": 2022, "round": 4}
TELEMETRY_POOR = {"question_type": "RACE_GAP",
                  "driver_a": "nino-farina", "driver_b": "juan-manuel-fangio",
                  "season": 1950, "round": 1}
HYP_SUBSET = {**LAP6, "hypotheses": ["H1_corner_speed", "H6_drs"]}


def _params(case: dict[str, Any]) -> dict[str, Any]:
    """Structured input -> run_engineering_investigation kwargs."""
    kw = {k: v for k, v in case.items()
          if k in ("question_type", "driver_a", "driver_b", "season",
                   "round", "lap_number", "stint_number", "pattern_id")}
    kw["round_num"] = kw.pop("round")
    if "hypotheses" in case:
        kw["hypotheses"] = case["hypotheses"]
    return kw


def _run(queries: CanonicalQueries, case: dict[str, Any]) -> dict[str, Any]:
    from racewise.data.historical.investigation_synthesis import (
        run_engineering_investigation,
    )

    return run_engineering_investigation(queries, **_params(case))


def _golden(label: str, case: dict[str, Any], queries: CanonicalQueries,
            t0: float) -> dict[str, Any]:
    """Q17 golden: snapshot -> verify -> replay -> identity."""
    inv = _run(queries, case)
    snap = build_investigation_snapshot(inv)
    verdict = verify_investigation_snapshot(snap)
    replay = replay_engineering_investigation(queries, snap)
    return {
        "case": label,
        "kind": "golden_snapshot",
        "status": inv.get("status"),
        "conclusion_state": (inv.get("synthesis") or {}).get("conclusion_state"),
        "snapshot_hash": snap.get("snapshot_hash"),
        "investigation_hash": snap.get("output_hash"),
        "source_hash_count": len(snap.get("source_hashes") or {}),
        "verify_status": verdict.get("status"),
        "replay_status": replay.get("status"),
        "replay_hash": replay.get("replay_hash"),
        "replay_identity_holds": (
            replay.get("replay_hash") == snap.get("snapshot_hash")),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
    }


def run_q17(
    queries: CanonicalQueries,
    include_mcp: bool = True,
) -> dict[str, Any]:
    """Run the Q17 investigation-memory matrix."""
    cases: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    # --- golden snapshots (39) -------------------------------------------
    inv_lap6 = _run(queries, LAP6)
    snap_lap6 = build_investigation_snapshot(inv_lap6)
    inv_stint = _run(queries, STINT1)
    snap_stint = build_investigation_snapshot(inv_stint)
    inv_gap24 = _run(queries, RACEGAP24)
    inv_regime = _run(queries, REGIME22)

    for label, inv in (("2023R1_VER_PER_LAP6", inv_lap6),
                       ("2023R1_VER_PER_STINT1", inv_stint),
                       ("2024R14_RACE_GAP", inv_gap24),
                       ("2022R4_PERFORMANCE_REGIME", inv_regime)):
        t_g = time.perf_counter()
        snap = build_investigation_snapshot(inv)
        verdict = verify_investigation_snapshot(snap)
        replay = replay_engineering_investigation(queries, snap)
        cases.append({
            "case": f"golden_{label}", "kind": "golden_snapshot",
            "verify_status": verdict["status"],
            "replay_status": replay["status"],
            "replay_identity_holds": (replay["replay_hash"]
                                      == snap["snapshot_hash"]),
            "snapshot_hash": snap["snapshot_hash"],
            "investigation_hash": snap["output_hash"],
            "elapsed_ms": round((time.perf_counter() - t_g) * 1000.0, 1),
        })

    # --- Q17.1 replay identical ------------------------------------------
    rep1 = replay_engineering_investigation(queries, snap_lap6)
    cases.append({"case": "Q17.1_replay_identical",
                  "status": rep1["status"],
                  "identical": rep1["identical"],
                  "difference_count": rep1["difference_count"]})

    # --- Q17.2 replay with changed tool version ---------------------------
    snap_tampered = dict(snap_lap6)
    tampered_ledger = [dict(e, source_tool="attribute_lap_loss_v999")
                       for e in snap_lap6["evidence_ledger"]]
    snap_tampered["evidence_ledger"] = tampered_ledger
    snap_tampered["source_hashes"] = {
        e["evidence_id"]: e["source_hash"] for e in tampered_ledger}
    snap_tampered["snapshot_hash"] = _hash_obj(
        {k: v for k, v in snap_tampered.items() if k != "snapshot_hash"})
    rep2 = replay_engineering_investigation(queries, snap_tampered)
    cases.append({"case": "Q17.2_replay_changed_tool_version",
                  "status": rep2["status"],
                  "changed_tools": rep2.get("changed_tools"),
                  "difference_count": rep2["difference_count"],
                  "first_difference_category":
                      (rep2["differences"][0]["category"]
                       if rep2["differences"] else None)})

    # --- Q17.3 same race, different lap -----------------------------------
    inv_lap11 = _run(queries, LAP11)
    cmp_lap = compare_engineering_investigations(inv_lap6, inv_lap11)
    cases.append({"case": "Q17.3_same_race_different_lap",
                  "compatibility": cmp_lap["compatibility"],
                  "synthesis_transition": cmp_lap["synthesis_delta"]["transition"],
                  "hypothesis_state_changes":
                      sum(1 for d in cmp_lap["hypothesis_deltas"]
                          if d["state_changed"]),
                  "comparison_identical_repeat": (
                      compare_engineering_investigations(inv_lap6, inv_lap11)
                      == cmp_lap)})

    # --- Q17.4 same pair, different race ----------------------------------
    inv_gap23 = _run(queries, {**RACEGAP24, "season": 2023, "round": 1})
    cmp_race = compare_engineering_investigations(inv_gap23, inv_gap24)
    cases.append({"case": "Q17.4_same_pair_different_race",
                  "compatibility": cmp_race["compatibility"],
                  "synthesis_transition":
                      cmp_race["synthesis_delta"]["transition"]})

    # --- Q17.5 same pattern across investigations --------------------------
    # the same investigation compared with itself is COMPARABLE with
    # SAME synthesis transition and zero deltas
    cmp_self = compare_engineering_investigations(inv_lap6, inv_lap6)
    cases.append({"case": "Q17.5_same_pattern_self_comparison",
                  "compatibility": cmp_self["compatibility"]["state"],
                  "synthesis_transition":
                      cmp_self["synthesis_delta"]["transition"],
                  "evidence_delta_count": len(cmp_self["evidence_deltas"]),
                  "trace_changed_count":
                      cmp_self["decision_trace_delta"]["changed"] and
                      len(cmp_self["decision_trace_delta"]["changed"]) or 0})

    # --- Q17.6 changed hypothesis subset -----------------------------------
    inv_subset = _run(queries, HYP_SUBSET)
    cmp_hyp = compare_engineering_investigations(inv_lap6, inv_subset)
    cases.append({"case": "Q17.6_changed_hypothesis_subset",
                  "compatibility": cmp_hyp["compatibility"],
                  "hypotheses_dimension":
                      cmp_hyp["dimensions"]["HYPOTHESES"]["state"],
                  "not_requested_in_b":
                      sum(1 for d in cmp_hyp["hypothesis_deltas"]
                          if d["new_state"] == "NOT_REQUESTED")})

    # --- Q17.7 contradiction introduced/preserved ---------------------------
    fc = cmp_lap["falsification_deltas"]
    ftypes: dict[str, int] = {}
    for d in fc:
        ftypes[d["change_type"]] = ftypes.get(d["change_type"], 0) + 1
    cases.append({"case": "Q17.7_contradiction_deltas",
                  "falsification_delta_types": ftypes,
                  "vanished_evidence_never_resolved": all(
                      d["change_type"] != "RESOLVED_CONTRADICTION"
                      or all(e in {x["evidence_id"]
                                   for x in inv_lap11.get("evidence_ledger") or []}
                             for e in d.get("evidence_ids") or [])
                      for d in fc)})

    # --- Q17.8 counterfactual result comparison -----------------------------
    cf_cmp = compare_engineering_investigations(inv_lap6, inv_stint)
    cases.append({"case": "Q17.8_counterfactual_result_comparison",
                  "counterfactual_delta_count":
                      len(cf_cmp["counterfactual_deltas"]),
                  "counterfactual_delta_types": sorted({
                      d["change_type"]
                      for d in cf_cmp["counterfactual_deltas"]}),
                  "claim_classes": sorted({
                      d.get("claim_class") or "MODELLED"
                      for d in cf_cmp["counterfactual_deltas"]})})

    # --- Q17.9 evidence-poor investigation ----------------------------------
    # memory items must never be derived from empty evidence lists: the
    # derived count only covers traceable facts and modelled results
    inv_poor = _run(queries, TELEMETRY_POOR)
    poor_items = derive_memory_items(inv_poor)
    cases.append({"case": "Q17.9_evidence_poor",
                  "status": inv_poor.get("status"),
                  "conclusion_state": (inv_poor.get("synthesis") or {})
                  .get("conclusion_state"),
                  "evidence_count": len(inv_poor.get("evidence_ledger") or []),
                  "memory_items_derived": len(poor_items),
                  "memory_items_have_evidence": all(
                      it["evidence_ids"] for it in poor_items)})

    # --- Q17.10 telemetry-unavailable (lap beyond race) ----------------------
    inv_unavail = _run(queries, {**LAP6, "lap_number": 999})
    cases.append({"case": "Q17.10_telemetry_unavailable",
                  "status": inv_unavail.get("status"),
                  "reason": inv_unavail.get("reason"),
                  "memory_items_derived":
                      len(derive_memory_items(inv_unavail))})

    # --- Q17.11 memory retrieval by exact scope ------------------------------
    mem_items = (derive_memory_items(inv_lap6)
                 + derive_memory_items(inv_stint))
    mem_hit = retrieve_engineering_memory(
        mem_items, season=2023, round_num=1, driver="max-verstappen")
    mem_miss = retrieve_engineering_memory(
        mem_items, season=1999)
    mem_hyp = retrieve_engineering_memory(
        mem_items, season=2023, hypothesis="H1_corner_speed")
    cases.append({
        "case": "Q17.11_memory_retrieval_exact_scope",
        "items_derived": len(mem_items),
        "scope_match_count": mem_hit["match_count"],
        "scope_mismatch_count": mem_miss["match_count"],
        "hypothesis_match_count": mem_hyp["match_count"],
        "repeat_identical": retrieve_engineering_memory(
            mem_items, season=2023, round_num=1, driver="max-verstappen")
        == mem_hit,
        "bound_respected":
            len(derive_memory_items(inv_stint))
            <= MAX_MEMORY_ITEMS_PER_INVESTIGATION,
    })

    # --- Q17.12 invalidated memory item --------------------------------------
    if mem_items:
        invalidated = invalidate_memory_item(
            mem_items[0], "REPLAY_MISMATCH", "q17_benchmark")
        mem_after = retrieve_engineering_memory(
            [invalidated] + mem_items[1:], season=2023, round_num=1)
        mem_with_invalid = retrieve_engineering_memory(
            [invalidated] + mem_items[1:], season=2023, round_num=1,
            include_invalidated=True)
        cases.append({
            "case": "Q17.12_invalidated_memory_item",
            "validity_status": invalidated["validity_status"],
            "invalidation_reason": invalidated["invalidation"]["reason"],
            "excluded_by_default":
                invalidated["memory_id"] not in
                {m["memory_id"] for m in mem_after["matching_memory_items"]},
            "included_when_requested":
                invalidated["memory_id"] in
                {m["memory_id"] for m in
                 mem_with_invalid["matching_memory_items"]},
            "history_preserved": invalidated["invalidation"]["prior_status"]
            == "ACTIVE",
        })

    timings = sorted(c.get("elapsed_ms") for c in cases
                     if c.get("elapsed_ms") is not None)
    report: dict[str, Any] = {
        "benchmark": "Q17_investigation_memory",
        "version": Q17_VERSION,
        "matrix": cases,
        "performance": {
            "p50_ms": timings[len(timings) // 2] if timings else None,
            "p95_ms": timings[min(len(timings) - 1,
                                  int(len(timings) * 0.95))] if timings else None,
            "max_ms": max(timings) if timings else None,
        },
        "negative_controls": _negative_controls(queries),
    }
    if include_mcp:
        report["mcp"] = _mcp_verification(queries)
    return report


def _negative_controls(queries: CanonicalQueries) -> dict[str, Any]:
    """Q17 negative controls. No silent repair, no silent fallback."""
    inv_lap6 = _run(queries, LAP6)
    snap = build_investigation_snapshot(inv_lap6)
    nc: dict[str, Any] = {}

    # corrupt snapshot -> HASH_MISMATCH
    corrupt = dict(snap)
    corrupt["output_hash"] = "0" * 16
    nc["corrupt_snapshot"] = verify_investigation_snapshot(corrupt)["status"]

    # tampered ledger -> HASH_MISMATCH
    tampered = dict(snap)
    tampered["evidence_ledger"] = snap["evidence_ledger"][:-1]
    nc["tampered_snapshot"] = verify_investigation_snapshot(tampered)["status"]

    # missing provenance -> MISSING_PROVENANCE
    no_prov = {k: v for k, v in snap.items() if k != "provenance"}
    nc["missing_provenance"] = verify_investigation_snapshot(no_prov)["status"]

    # invalid schema -> INVALID_SCHEMA
    nc["invalid_schema"] = verify_investigation_snapshot({"foo": 1})["status"]

    # incomplete -> INCOMPLETE_SNAPSHOT
    incomplete = {k: v for k, v in snap.items()
                  if k not in ("decision_trace", "synthesis")}
    incomplete["snapshot_hash"] = _hash_obj(
        {k: v for k, v in incomplete.items() if k != "snapshot_hash"})
    nc["incomplete_snapshot"] = \
        verify_investigation_snapshot(incomplete)["status"]

    # replay of an invalid snapshot -> INVALID_SNAPSHOT (never rerun blindly)
    nc["replay_invalid_snapshot"] = replay_engineering_investigation(
        queries, corrupt)["status"]

    # incompatible comparison -> NOT_COMPARABLE
    cmp_bad = compare_engineering_investigations(
        inv_lap6, _run(queries, RACEGAP24))
    nc["incompatible_question_types"] = cmp_bad["compatibility"]["state"]

    # memory scope mismatch -> not returned
    items = derive_memory_items(inv_lap6)
    nc["memory_scope_mismatch_count"] = retrieve_engineering_memory(
        items, season=1999)["match_count"]

    # invalid memory item state vocabulary is closed
    nc["memory_states_closed"] = sorted(
        {it["validity_status"] for it in items}) == ["ACTIVE"]
    return nc


def _mcp_verification(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.tools.contract import ToolError
    from racewise.tools.historical import build_historical_registry

    reg = build_historical_registry(queries)
    out: dict[str, Any] = {
        "historical_tool_count": len(reg._tools),
        "tools_registered": all(
            n in reg._tools for n in (
                "replay_engineering_investigation",
                "verify_engineering_snapshot",
                "compare_engineering_investigations",
                "retrieve_engineering_memory")),
    }
    lap6 = {"question_type": "LAP_PERFORMANCE",
            "driver_a": "max-verstappen", "driver_b": "sergio-perez",
            "season": 2023, "round": 1, "lap_number": 6}
    rep = reg.execute("replay_engineering_investigation", lap6)["output"]
    out["replay_status"] = rep["status"]
    cmp1 = reg.execute(
        "compare_engineering_investigations",
        {"investigation_a": lap6,
         "investigation_b": {**lap6, "lap_number": 11}})["output"]
    out["compare_compatibility"] = cmp1["compatibility"]["state"]
    mem = reg.execute("retrieve_engineering_memory",
                      {"investigations": [lap6], "season": 2023})["output"]
    out["memory_match_count"] = mem["match_count"]
    try:
        reg.execute("replay_engineering_investigation",
                    {**lap6, "driver_b": "max-verstappen"})
        out["same_driver_rejected"] = False
    except ToolError as e:
        out["same_driver_rejected"] = e.code == "invalid_input"
    try:
        reg.execute("retrieve_engineering_memory",
                    {"investigations": [lap6] * 5})
        out["oversized_rejected"] = False
    except ToolError as e:
        out["oversized_rejected"] = e.code == "invalid_input"
    return out


if __name__ == "__main__":  # pragma: no cover - documentation measurement
    from racewise.data.historical.canonical_queries import (
        get_canonical_queries,
    )

    print(run_q17(get_canonical_queries(), include_mcp=True))
