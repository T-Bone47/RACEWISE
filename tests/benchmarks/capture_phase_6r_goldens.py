"""Capture the Phase 6R golden set (one-off, run manually).

Executes 12 canonical investigations through the real chain, recording for
each: canonical input, investigation id, output hash, snapshot hash,
replay verdict, provenance hash, graph node/edge counts + graph hash where
applicable. Results land in tests/benchmarks/phase_6r_goldens.json.

Usage: python tests/benchmarks/capture_phase_6r_goldens.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.data.historical.canonical_queries import CanonicalQueries  # noqa: E402
from racewise.data.historical.investigation_graph import (  # noqa: E402
    build_graph_snapshot, build_investigation_graph, replay_graph_snapshot,
    verify_graph_snapshot,
)
from racewise.data.historical.investigation_memory import (  # noqa: E402
    build_investigation_snapshot, compare_engineering_investigations,
    replay_engineering_investigation,
)
from racewise.data.historical.investigation_synthesis import (  # noqa: E402
    run_engineering_investigation,
)

GOLDENS: list[dict[str, Any]] = [
    {"golden_id": "G01_LAP", "label": "lap investigation (mixed evidence, graph golden)",
     "input": {"question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2023, "round": 1,
               "lap_number": 6},
     "graph": True, "replay": True, "prior_id": "fcc1bf694daada8e"},
    {"golden_id": "G02_STINT", "label": "stint investigation (graph golden)",
     "input": {"question_type": "STINT_PERFORMANCE", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2023, "round": 1,
               "stint_number": 1},
     "graph": True, "replay": True},
    {"golden_id": "G03_RACE_GAP", "label": "race gap investigation (2024 R14)",
     "input": {"question_type": "RACE_GAP", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2024, "round": 14},
     "graph": True, "replay": True},
    {"golden_id": "G04_REGIME", "label": "performance-regime investigation (2022 R4)",
     "input": {"question_type": "PERFORMANCE_REGIME", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2022, "round": 4},
     "graph": True, "replay": True},
    {"golden_id": "G05_PATTERN", "label": "cross-race pattern investigation",
     "input": {"question_type": "CROSS_RACE_PATTERN", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2023, "round": 1,
               "pattern_id": "3082b650453bb3e8"},
     "graph": False, "replay": True},
    {"golden_id": "G06_HYPOTHESIS", "label": "hypothesis-subset investigation",
     "input": {"question_type": "HYPOTHESIS_EVALUATION",
               "driver_a": "max-verstappen", "driver_b": "sergio-perez",
               "season": 2023, "round": 1, "lap_number": 6,
               "hypotheses": ["H1_corner_speed", "H6_drs"]},
     "graph": False, "replay": True},
    {"golden_id": "G07_COUNTERFACTUAL", "label": "counterfactual-eligibility investigation",
     "input": {"question_type": "COUNTERFACTUAL_ELIGIBILITY",
               "driver_a": "max-verstappen", "driver_b": "sergio-perez",
               "season": 2023, "round": 1, "lap_number": 6},
     "graph": False, "replay": True},
    {"golden_id": "G08_INSUFFICIENT_LAP", "label": "insufficient-telemetry lap (honest limitation)",
     "input": {"question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2023, "round": 1,
               "lap_number": 12},
     "graph": False, "replay": False},
    {"golden_id": "G09_HISTORICAL", "label": "1950 historical limitation",
     "input": {"question_type": "RACE_GAP", "driver_a": "nino-farina",
               "driver_b": "juan-manuel-fangio", "season": 1950, "round": 1},
     "graph": False, "replay": True},
    {"golden_id": "G10_UNKNOWN_DRIVER", "label": "unknown driver (UNAVAILABLE)",
     "input": {"question_type": "RACE_GAP", "driver_a": "max-verstappen",
               "driver_b": "kimi-antonelli", "season": 2023, "round": 1},
     "graph": False, "replay": False},
    {"golden_id": "G11_COMPARE", "label": "investigation comparison LAP6 vs LAP11",
     "input": {"question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2023, "round": 1,
               "lap_number": 6},
     "compare_with": {"question_type": "LAP_PERFORMANCE",
                      "driver_a": "max-verstappen", "driver_b": "sergio-perez",
                      "season": 2023, "round": 1, "lap_number": 11},
     "graph": False, "replay": False},
    {"golden_id": "G12_MEMORY", "label": "memory derivation from LAP6",
     "input": {"question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2023, "round": 1,
               "lap_number": 6},
     "memory": True, "graph": False, "replay": False},
    {"golden_id": "G13_GRAPH_BY_ID", "label": "graph addressed by investigation id",
     "input": {"question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2023, "round": 1,
               "lap_number": 6},
     "graph": True, "replay": True, "addressed_graph": True},
    {"golden_id": "G14_QUALIFYING_LAP", "label": "qualifying single-lap investigation (honest telemetry limits)",
     "input": {"question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2022, "round": 4,
               "lap_number": 2, "session_type": "QUALIFYING"},
     "graph": True, "replay": True},
    {"golden_id": "G15_RELATED_MEMORY", "label": "structural related-memory retrieval from LAP6",
     "input": {"question_type": "LAP_PERFORMANCE", "driver_a": "max-verstappen",
               "driver_b": "sergio-perez", "season": 2023, "round": 1,
               "lap_number": 6},
     "related_memory": True, "graph": False, "replay": False},
]


def main() -> int:
    queries = CanonicalQueries()
    out: list[dict[str, Any]] = []
    for g in GOLDENS:
        entry: dict[str, Any] = {"golden_id": g["golden_id"],
                                 "label": g["label"],
                                 "canonical_input": g["input"]}
        kw = dict(g["input"])
        kw["round_num"] = kw.pop("round")
        try:
            inv = run_engineering_investigation(queries, **kw)
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)[:200]
            out.append(entry)
            continue
        entry["status"] = inv.get("status")
        entry["investigation_id"] = inv.get("investigation_id")
        entry["output_hash"] = inv.get("output_hash")
        entry["prior_id_match"] = (g.get("prior_id") in (None, entry["investigation_id"]))
        syn = inv.get("synthesis") or {}
        entry["conclusion_state"] = syn.get("conclusion_state")
        entry["evidence_items"] = (inv.get("collection") or {}).get("items_collected")

        prov = inv.get("provenance") or {}
        prov_hash_src = {
            "analytical_chain": prov.get("analytical_chain"),
            "method": prov.get("method"),
            "investigation_version": prov.get("investigation_version"),
            "provider": prov.get("provider"),
            "source_tables": prov.get("source_tables"),
        }
        entry["provenance_hash"] = format(
            hash(json.dumps(prov_hash_src, sort_keys=True)) & 0xFFFFFFFFFFFFFFFF,
            "016x")

        if inv.get("status") == "VALID" and g.get("replay"):
            snap = build_investigation_snapshot(inv)
            entry["snapshot_hash"] = snap.get("snapshot_hash")
            rp = replay_engineering_investigation(queries, snap)
            entry["replay_status"] = rp.get("status")
            entry["replay_identical"] = rp.get("identical")
            entry["replay_hash"] = rp.get("replay_hash")

        if g.get("graph") and inv.get("status") == "VALID":
            graph = build_investigation_graph(queries, inv)
            if graph.get("status") in ("INVALID", "UNAVAILABLE"):
                entry["graph"] = {"status": graph.get("status"),
                                  "reason": graph.get("reason")}
            else:
                snap = build_graph_snapshot(graph)
                entry["graph"] = {
                    "nodes": graph.get("node_count") or len(graph.get("nodes") or []),
                    "edges": graph.get("edge_count") or len(graph.get("edges") or []),
                    "graph_id": graph.get("graph_id"),
                    "graph_version": graph.get("graph_version"),
                    "snapshot_hash": snap.get("snapshot_hash"),
                    "verify_status": verify_graph_snapshot(snap).get("status"),
                }
                rp = replay_graph_snapshot(queries, snap)
                entry["graph"]["replay_status"] = rp.get("status")

        if g.get("compare_with"):
            kw2 = dict(g["compare_with"])
            kw2["round_num"] = kw2.pop("round")
            inv2 = run_engineering_investigation(queries, **kw2)
            cmp_res = compare_engineering_investigations(inv, inv2)
            entry["comparison"] = {
                "compatibility": (cmp_res.get("compatibility") or {}).get("status")
                or cmp_res.get("compatibility"),
                "synthesis_transition": (cmp_res.get("synthesis_transition")
                                         or {}).get("transition")
                or cmp_res.get("synthesis_transition"),
                "b_investigation_id": inv2.get("investigation_id"),
                "b_output_hash": inv2.get("output_hash"),
            }

        if g.get("memory") and inv.get("status") == "VALID":
            from racewise.data.historical.investigation_memory import (
                derive_memory_items, retrieve_engineering_memory,
            )
            items = derive_memory_items(inv)
            res = retrieve_engineering_memory(items, season=2023, round_num=1)
            entry["memory"] = {"derived_items": len(items),
                               "exact_scope_matches": res.get("match_count")}

        if g.get("related_memory") and inv.get("status") == "VALID":
            # Phase 6S GAP 4: ±1-season neighbor pool + structural
            # retrieval (mirrors the API's bounded neighborhood)
            from racewise.data.historical.investigation_memory import (
                derive_memory_items, retrieve_related_engineering_memory,
            )
            items = derive_memory_items(inv)
            neighbor_runs = []
            for nb_season in (int(kw["season"]) - 1, int(kw["season"]) + 1):
                nb_kw = dict(kw)
                nb_kw["season"] = nb_season
                nb_inv = run_engineering_investigation(queries, **nb_kw)
                nb_items = 0
                if nb_inv.get("status") == "VALID":
                    nb_items = len(derive_memory_items(nb_inv))
                    items += derive_memory_items(nb_inv)
                neighbor_runs.append({
                    "season": nb_season,
                    "status": nb_inv.get("status"),
                    "items_derived": nb_items})
            rel = retrieve_related_engineering_memory(
                items, season=2023, round_num=1,
                driver_pair=["max-verstappen", "sergio-perez"])
            entry["related_memory"] = {
                "neighbor_runs": neighbor_runs,
                "related_match_count": rel.get("related_match_count"),
                "match_reasons": sorted({r for item in
                                         rel.get("related_memory_items") or []
                                         for r in item.get("match_reasons")}),
                "policy": rel.get("policy"),
            }

        if g.get("addressed_graph") and inv.get("status") == "VALID":
            # Phase 6S GAP 1: the id-addressed graph must equal the
            # scope-addressed graph of the same investigation
            graph_by_id = build_investigation_graph(queries, inv)
            entry["addressed_by"] = {
                "investigation_id": inv.get("investigation_id"),
                "graph_id_matches_scope_graph": (
                    graph_by_id.get("graph_id") ==
                    (entry.get("graph") or {}).get("graph_id")),
            }

        out.append(entry)
        print(f"{g['golden_id']}: status={entry.get('status')} "
              f"hash={entry.get('output_hash')} replay={entry.get('replay_status')}")

    dest = ROOT / "tests" / "benchmarks" / "phase_6r_goldens.json"
    # (file name kept for continuity; the set itself is v2 with 15 goldens)
    payload = {
        "golden_set": "phase_6r_goldens_v2",
        "captured": "2026-09-29",
        "note": ("canonical inputs and measured hashes; conclusions are "
                 "structural states, never invented numbers; hashes bind to "
                 "the canonical data state at capture time. v2 adds the "
                 "Phase 6S gap-closure goldens G13 (id-addressed graph), "
                 "G14 (qualifying lap) and G15 (structural related "
                 "memory). Hash-classified deltas vs 6R: G02_STINT output "
                 "hash changed = EXPECTED_CAPABILITY_EXTENSION (the 6S "
                 "telemetry probe expansion 12->24 laps measures more laps "
                 "of the same stint-1 scope); all other G01-G12 hashes are "
                 "unchanged including the honest limitation G08"),
        "goldens": out,
    }
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"written: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
