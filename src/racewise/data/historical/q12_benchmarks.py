"""Q12 benchmark family: measured driver performance envelope (Phase 6J).

Runs the envelope/scenario layer over a fixed representative matrix
(2022-2025, multiple circuits, real telemetry pairs) and records
deterministic semantics. Every delta is a measured model sensitivity under a
specified bounded intervention; nothing is fitted, extrapolated or fabricated.

Categories:
    Q12.1  single-lap envelope (anchor lap, measured band)
    Q12.2  multi-lap envelope (>= 3 clean laps in the band)
    Q12.3  reference-driver comparison (explicit pair)
    Q12.4  scenario sweep (bounded parameter grid)
    Q12.5  monotonic sensitivity (descriptive finite differences)
    Q12.6  non-linear response detection (second differences > 0)
    Q12.7  regional sensitivity (largest model-response regions)
    Q12.8  stint envelope (6G common-lap selection + per-lap trend)
    Q12.9  evidence + sensitivity integration (verdicts kept distinct)
    Q12.10 baseline identity (reproduction error 0, identity delta 0)
    Q12.11 deterministic replay (hash-identical)
    Q12.12 MCP verification (bounds + negative controls through the registry)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.performance_envelope import (
    build_performance_envelope,
    analyze_performance_envelope,
)

Q12_VERSION = "q12_performance_envelope_v1"

MATRIX = [
    {"season": 2023, "round": 1, "driver": "sergio-perez", "reference": "max-verstappen"},
    {"season": 2022, "round": 4, "driver": "sergio-perez", "reference": "max-verstappen"},
    {"season": 2024, "round": 14, "driver": "oscar-piastri", "reference": "lewis-hamilton"},
    {"season": 2025, "round": 12, "driver": "oscar-piastri", "reference": "lando-norris"},
]


def run_q12(queries: CanonicalQueries, include_mcp: bool = True) -> dict[str, Any]:
    """Run the Q12 envelope matrix and return the structured report."""
    results: list[dict[str, Any]] = []
    for case in MATRIX:
        entry: dict[str, Any] = {**case}

        env = build_performance_envelope(queries, case["season"], case["round"], case["driver"])
        entry["envelope_status"] = env.get("status")
        if env.get("status") == "VALID":
            entry["single_lap_anchor"] = env.get("anchor_lap")
            entry["laps_in_band"] = env.get("laps_in_band")
            entry["band_summary"] = env.get("envelope_summary")
            entry["reproduction"] = {
                "error_s": env["model_baseline"]["reproduction_error_s"],
                "exact": env["model_baseline"]["reproduction_exact"],
            }
            entry["hash_envelope"] = env.get("output_hash")
            entry["replay_envelope"] = (
                build_performance_envelope(
                    queries, case["season"], case["round"], case["driver"]
                ).get("output_hash") == env.get("output_hash")
            )

        res = analyze_performance_envelope(
            queries, case["season"], case["round"], case["driver"],
            scenario_type="DEFICIT_REDUCTION", parameter=0.5,
            reference_driver=case["reference"], max_scenarios=5)
        entry["sweep_status"] = res.get("status")
        if res.get("status") == "VALID":
            deltas = [(s.get("parameter"), s.get("delta_s"))
                      for s in res.get("scenarios", [])]
            entry["sweep_deltas"] = deltas
            entry["response_status"] = res["sensitivity"]["response"]["status"]
            entry["response_nonlinear"] = (
                res["sensitivity"]["response"].get("max_abs_second_difference_s", 0) > 0)
            entry["regional_top3"] = res.get("regional_response")
            entry["identity_delta_s"] = res["model_baseline"]["identity_delta_s"]
            entry["hash_sweep"] = res.get("output_hash")
            entry["replay_sweep"] = (
                analyze_performance_envelope(
                    queries, case["season"], case["round"], case["driver"],
                    scenario_type="DEFICIT_REDUCTION", parameter=0.5,
                    reference_driver=case["reference"], max_scenarios=5,
                ).get("output_hash") == res.get("output_hash")
            )

        # deterministic stint pick: first stint (ascending) whose envelope is VALID
        stint = {"status": "INSUFFICIENT_EVIDENCE"}
        for sn in (1, 2, 3):
            probe = analyze_performance_envelope(
                queries, case["season"], case["round"], case["driver"],
                scenario_type="DEFICIT_REDUCTION", parameter=0.5,
                reference_driver=case["reference"], stint_number=sn, max_laps=6)
            if probe.get("status") == "VALID":
                stint = probe
                stint["probed_stint_number"] = sn
                break
            if stint.get("status") != "VALID":
                stint = probe
        entry["stint_status"] = stint.get("status")
        entry["stint_number"] = stint.get("probed_stint_number")
        if stint.get("status") == "VALID":
            sr = stint.get("stint_response")
            entry["stint_scope"] = stint["envelope"]["scope"]
            entry["stint_per_lap"] = (
                [(p["lap_number"], p["delta_s"]) for p in sr["per_lap"]] if sr else None)
            entry["stint_trend_s_per_lap"] = sr["sensitivity_trend_s_per_lap"] if sr else None

        entry["h1_integration"] = _h1_integration(queries, case)
        results.append(entry)

    report: dict[str, Any] = {
        "benchmark": "Q12_performance_envelope",
        "version": Q12_VERSION,
        "matrix": results,
        "negative_controls": _negative_controls(queries),
    }
    if include_mcp:
        report["mcp"] = _mcp_verification(queries)
    return report


def _h1_integration(queries: CanonicalQueries, case: dict[str, Any]) -> dict[str, Any]:
    """Q12.9: 6F H1 evidence verdict + 6J model sensitivity, kept distinct."""
    out: dict[str, Any] = {}
    try:
        from racewise.data.historical.evidence_fusion import fuse_lap_evidence

        summary = queries.telemetry_summary(case["season"], case["round"], "RACE")
        fused: dict[str, Any] = {}
        for candidate in summary.get("laps", []):
            fused = fuse_lap_evidence(
                queries, case["season"], case["round"], case["reference"],
                case["driver"], int(candidate), "RACE")
            if fused.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS"):
                out["fusion_lap"] = int(candidate)
                break
        for h in fused.get("hypotheses", []):
            if h.get("hypothesis_id") == "H1_corner_speed":
                out["evidence_verdict"] = h.get("status")
                break
        out["fusion_status"] = fused.get("status")
    except Exception as exc:  # noqa: BLE001 - integration is informational
        out["fusion_status"] = f"ERROR: {exc}"
    res = analyze_performance_envelope(
        queries, case["season"], case["round"], case["driver"],
        scenario_type="DEFICIT_REDUCTION", parameter=0.5,
        reference_driver=case["reference"])
    out["model_sensitivity_status"] = res.get("status")
    out["model_sensitivity_full_delta_s"] = next(
        (s.get("delta_s") for s in res.get("scenarios", []) if s.get("parameter") == 1.0),
        None)
    out["epistemics"] = (
        "evidence verdict and model sensitivity are different epistemic objects; "
        "neither establishes historical causality")
    return out


def _negative_controls(queries: CanonicalQueries) -> dict[str, Any]:
    nc: dict[str, Any] = {}
    nc["1950"] = build_performance_envelope(queries, 1950, 1, "giuseppe-farina").get("status")
    nc["2018"] = build_performance_envelope(queries, 2018, 1, "lewis-hamilton").get("status")
    nc["missing_driver"] = build_performance_envelope(queries, 2023, 1, "nobody-here").get("status")
    nc["missing_reference"] = analyze_performance_envelope(
        queries, 2023, 1, "sergio-perez", scenario_type="DEFICIT_REDUCTION",
        reference_driver="nobody-here").get("status")
    nc["same_driver"] = analyze_performance_envelope(
        queries, 2023, 1, "sergio-perez", scenario_type="DEFICIT_REDUCTION",
        reference_driver="sergio-perez").get("status")
    nc["bad_scenario_type"] = analyze_performance_envelope(
        queries, 2023, 1, "sergio-perez", scenario_type="TELEPORT").get("status")
    nc["param_out_of_bounds"] = analyze_performance_envelope(
        queries, 2023, 1, "sergio-perez", scenario_type="DEFICIT_REDUCTION",
        parameter=1.5, reference_driver="max-verstappen").get("status")
    nc["observed_with_parameter"] = analyze_performance_envelope(
        queries, 2023, 1, "sergio-perez", scenario_type="OBSERVED",
        parameter=0.3).get("status")
    nc["nonexistent_stint"] = analyze_performance_envelope(
        queries, 2023, 1, "sergio-perez", scenario_type="DEFICIT_REDUCTION",
        reference_driver="max-verstappen", stint_number=99).get("status")
    return nc


def _mcp_verification(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.tools.contract import ToolError
    from racewise.tools.historical import build_historical_registry

    reg = build_historical_registry(queries)
    name = "analyze_historical_performance_envelope"
    out: dict[str, Any] = {"tool_registered": name in reg._tools}
    if not out["tool_registered"]:
        return out
    r = reg.execute(name, {
        "season": 2023, "round": 1, "driver": "sergio-perez",
        "reference_driver": "max-verstappen",
        "scenario_type": "DEFICIT_REDUCTION", "parameter": 0.5})
    out["registry_status"] = r["output"].get("status")
    out["registry_response"] = r["output"].get("sensitivity", {}).get("response", {}).get("status")
    base = {"season": 2023, "round": 1, "driver": "sergio-perez", "scenario_type": "OBSERVED"}
    for label, extra in (
        ("max_scenarios_99", {"max_scenarios": 99}),
        ("max_laps_99", {"max_laps": 99}),
        ("segment_s_99", {"segment_s": 99}),
        ("parameter_oob", {"scenario_type": "DEFICIT_REDUCTION", "parameter": 5,
                           "reference_driver": "max-verstappen"}),
        ("bad_scenario", {"scenario_type": "TELEPORT"}),
        ("unknown_param", {"bogus": 1}),
    ):
        try:
            reg.execute(name, {**base, **extra})
            out[label] = "ACCEPTED"
        except ToolError as exc:
            out[label] = f"REJECTED: {exc.code}"
    nc_1950 = reg.execute(name, {"season": 1950, "round": 1, "driver": "giuseppe-farina",
                                 "scenario_type": "OBSERVED"})
    out["1950"] = nc_1950["output"].get("status")
    return out


if __name__ == "__main__":  # pragma: no cover
    from racewise.data.historical.canonical_queries import CanonicalQueries

    import json
    print(json.dumps(run_q12(CanonicalQueries(), include_mcp=True), indent=2, default=str))
