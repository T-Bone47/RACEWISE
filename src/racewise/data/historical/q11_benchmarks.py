"""Q11 benchmark family: validated telemetry counterfactuals (Phase 6I).

Runs the Phase 6I counterfactual layer over a fixed representative lap matrix
(2022-2025, multiple circuits, real telemetry pairs) and records deterministic
semantics. Every number is a measured model sensitivity under a specified
intervention - never a fabricated outcome. Categories the simulator genuinely
does not support (e.g. braking interventions) are recorded UNSUPPORTED, not
skipped.

Categories:
    Q11.1  valid speed REMOVE_DEFICIT intervention
    Q11.2  valid speed SCALE_SIGNAL intervention
    Q11.3  braking (and all non-speed) interventions -> UNSUPPORTED by contract
    Q11.4  bounded parameters (out-of-bounds fractions rejected / flagged)
    Q11.5  baseline reproduction (exact: error 0, identity delta 0)
    Q11.6  deterministic replay (byte-identical JSON + hashes)
    Q11.7  stint-level validated counterfactual (Phase 6G common-lap selection)
    Q11.8  hypothesis + counterfactual integration (H1 evidence + sensitivity)
    Q11.9  unavailable telemetry negative control (1950 / 2018 / absent lap)
    Q11.10 invalid parameter negative control (unsupported signal, bad fraction)
    Q11.11 unsupported simulator mapping (non-speed signals)
    Q11.12 full MCP verification (registry path, bounds, negative controls)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from racewise.data.historical.canonical_queries import CanonicalQueries
from racewise.data.historical.counterfactual import VALID, simulate_telemetry_counterfactual

Q11_VERSION = "q11_telemetry_counterfactual_v1"

# Fixed representative lap matrix (verified against the canonical store):
# telemetry-covered first laps of the canonical pairs, multiple circuits/eras.
MATRIX = [
    {"season": 2023, "round": 1, "driver": "sergio-perez", "reference": "max-verstappen"},
    {"season": 2022, "round": 4, "driver": "sergio-perez", "reference": "max-verstappen"},
    {"season": 2024, "round": 14, "driver": "oscar-piastri", "reference": "lewis-hamilton"},
    {"season": 2025, "round": 12, "driver": "oscar-piastri", "reference": "lando-norris"},
]

SENSITIVITY_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)


def _first_covered_lap(queries: CanonicalQueries, season: int, round_num: int) -> int | None:
    summary = queries.telemetry_summary(season, round_num, "RACE")
    if not summary.get("available"):
        return None
    return summary["laps"][0] if summary["laps"] else None


def run_q11(queries: CanonicalQueries, include_mcp: bool = True) -> dict[str, Any]:
    """Run the Q11 counterfactual matrix and return the structured report."""
    results: list[dict[str, Any]] = []
    for case in MATRIX:
        lap = _first_covered_lap(queries, case["season"], case["round"])
        entry: dict[str, Any] = {**case, "lap_number": lap}
        if lap is None:
            entry.update({"status": "UNAVAILABLE", "reason": "no telemetry rows"})
            results.append(entry)
            continue

        # Q11.1 REMOVE_DEFICIT + monotone sensitivity curve (Q11.4-adjacent)
        curve: list[dict[str, Any]] = []
        for f in SENSITIVITY_FRACTIONS:
            r = simulate_telemetry_counterfactual(
                queries, case["season"], case["round"], case["driver"], lap,
                "speed", "REMOVE_DEFICIT", f, reference_driver=case["reference"])
            curve.append({"fraction": f, "status": r.get("status"),
                          "delta_s": r.get("counterfactual_delta_s")})
        valid_pts = [c for c in curve if c["status"] == VALID]
        # as the fraction grows the intervened profile gets faster, so the
        # delta must be non-increasing (more negative) - never less gained
        monotone = all(
            valid_pts[i]["delta_s"] >= valid_pts[i + 1]["delta_s"] - 1e-9
            for i in range(len(valid_pts) - 1)
        ) if valid_pts else False
        entry.update({
            "sensitivity_curve": curve,
            "monotone_non_increasing_delta": monotone,
            "status": curve[2]["status"],  # the f=0.5 anchor
        })

        # Q11.2 SCALE_SIGNAL
        r_scale = simulate_telemetry_counterfactual(
            queries, case["season"], case["round"], case["driver"], lap,
            "speed", "SCALE_SIGNAL", -0.05)
        entry["scale_minus5pct"] = {
            "status": r_scale.get("status"),
            "delta_s": r_scale.get("counterfactual_delta_s"),
        }

        # Q11.5 baseline reproduction gates
        r_anchor = simulate_telemetry_counterfactual(
            queries, case["season"], case["round"], case["driver"], lap,
            "speed", "REMOVE_DEFICIT", 0.5, reference_driver=case["reference"])
        gates = r_anchor.get("validation_gates", {})
        entry["baseline_reproduction"] = {
            "error_s": (r_anchor.get("model", {}).get("baseline_reproduction") or {}).get("error_s"),
            "identity_delta_s": (r_anchor.get("model", {}).get("baseline_reproduction") or {}).get("identity_intervention_delta_s"),
            "all_gates_pass": all(g.get("status") == "PASS" for g in gates.values()) if gates else None,
        }

        # Q11.6 deterministic replay
        r_repeat = simulate_telemetry_counterfactual(
            queries, case["season"], case["round"], case["driver"], lap,
            "speed", "REMOVE_DEFICIT", 0.5, reference_driver=case["reference"])
        entry["replay_identical"] = (
            r_anchor.get("output_hash") == r_repeat.get("output_hash")
            and r_anchor.get("output_hash") is not None
        )

        # Q11.3/Q11.11 unsupported mapping (brake representative of all non-speed)
        r_brake = simulate_telemetry_counterfactual(
            queries, case["season"], case["round"], case["driver"], lap,
            "brake", "REMOVE_DEFICIT", 0.5, reference_driver=case["reference"])
        entry["brake_intervention_status"] = r_brake.get("status")

        # Q11.7 stint level
        st = _stint_counterfactual(queries, case, lap)
        entry["stint"] = st

        # Q11.8 hypothesis + counterfactual integration
        entry["h1_integration"] = _h1_integration(queries, case, lap)

        results.append(entry)

    report: dict[str, Any] = {
        "benchmark": "Q11_telemetry_counterfactual",
        "version": Q11_VERSION,
        "matrix": results,
        "negative_controls": _negative_controls(queries),
    }
    if include_mcp:
        report["mcp"] = _mcp_verification(queries)
    return report


def _stint_counterfactual(
    queries: CanonicalQueries, case: dict[str, Any], lap: int | None,
) -> dict[str, Any]:
    from racewise.data.historical.counterfactual import simulate_stint_counterfactual
    from racewise.data.historical.stint_evidence import _select_common_laps

    # deterministic stint pick: first stint (ascending) with >= 3 covered laps
    stints = queries.get_stints(case["season"], case["round"], "RACE", case["driver"])
    for s in sorted(stints, key=lambda r: r["stint_number"]):
        sn = int(s["stint_number"])
        try:
            selected, _exc, _sa, _sb = _select_common_laps(
                queries, case["season"], case["round"], "RACE",
                case["driver"], case["reference"], sn, 6)
        except Exception:  # noqa: BLE001 - probing must not break the benchmark
            continue
        if len(selected) >= 3:
            res = simulate_stint_counterfactual(
                queries, case["season"], case["round"], case["driver"],
                case["reference"], sn, "speed", "REMOVE_DEFICIT", 0.5)
            return {
                "stint_number": sn, "status": res.get("status"),
                "laps_sampled": res.get("laps_sampled"),
                "laps_valid": res.get("laps_valid"),
                "mean_delta_s": (res.get("aggregate") or {}).get("mean_delta_s"),
                "monotonicity_check": (res.get("monotonicity_check") or {}).get("status"),
            }
    return {"status": "INSUFFICIENT_EVIDENCE", "reason": "no stint with >= 3 covered laps"}


def _h1_integration(
    queries: CanonicalQueries, case: dict[str, Any], lap: int | None,
) -> dict[str, Any]:
    """Q11.8: H1 (corner speed) evidence verdict + model sensitivity, kept distinct."""
    from racewise.data.historical.counterfactual import VALID
    from racewise.data.historical.evidence_fusion import fuse_lap_evidence

    out: dict[str, Any] = {}
    fusion_lap = lap
    try:
        summary = queries.telemetry_summary(case["season"], case["round"], "RACE")
        fused: dict[str, Any] = {}
        for candidate in summary.get("laps", []):
            fused = fuse_lap_evidence(
                queries, case["season"], case["round"], case["reference"],
                case["driver"], int(candidate), "RACE")
            if fused.get("status") in ("VALID_COMPARISON", "VALID_WITH_CAVEATS"):
                fusion_lap = int(candidate)
                break
        for h in fused.get("hypotheses", []):
            if h.get("hypothesis_id") == "H1_corner_speed":
                out["evidence_verdict"] = h.get("status")
                break
        out["fusion_status"] = fused.get("status")
        out["fusion_lap"] = fusion_lap
    except Exception as exc:  # noqa: BLE001 - integration is informational
        out["fusion_status"] = f"ERROR: {exc}"
    r = simulate_telemetry_counterfactual(
        queries, case["season"], case["round"], case["driver"], fusion_lap,
        "speed", "REMOVE_DEFICIT", 0.5, reference_driver=case["reference"])
    out["model_sensitivity_status"] = r.get("status")
    out["model_sensitivity_delta_s"] = r.get("counterfactual_delta_s")
    out["epistemics"] = (
        "evidence verdict and model sensitivity are different epistemic objects; "
        "neither establishes historical causality"
    )
    return out


def _negative_controls(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.data.historical.counterfactual import (
        INSUFFICIENT,
        UNAVAILABLE,
        UNSUPPORTED,
    )

    nc: dict[str, Any] = {}
    # 1950: no telemetry at all
    nc["1950"] = simulate_telemetry_counterfactual(
        queries, 1950, 1, "giuseppe-farina", 1, "speed", "SCALE_SIGNAL", 0.05
    ).get("status")
    # 2018: no telemetry under the bounded policy
    nc["2018"] = simulate_telemetry_counterfactual(
        queries, 2018, 1, "lewis-hamilton", 1, "speed", "SCALE_SIGNAL", 0.05
    ).get("status")
    # missing driver on a telemetry session
    nc["missing_driver"] = simulate_telemetry_counterfactual(
        queries, 2023, 1, "nobody-here", 1, "speed", "SCALE_SIGNAL", 0.05
    ).get("status")
    # absent lap (lap 999 has no telemetry rows)
    nc["absent_lap"] = simulate_telemetry_counterfactual(
        queries, 2023, 1, "max-verstappen", 999, "speed", "SCALE_SIGNAL", 0.05
    ).get("status")
    # insufficient telemetry: thin coverage / invalid fraction flagged by module
    nc["fraction_out_of_bounds_status"] = simulate_telemetry_counterfactual(
        queries, 2023, 1, "max-verstappen", 1, "speed", "REMOVE_DEFICIT", 1.5,
        reference_driver="sergio-perez",
    ).get("status")
    nc["nan_fraction_status"] = simulate_telemetry_counterfactual(
        queries, 2023, 1, "max-verstappen", 1, "speed", "REMOVE_DEFICIT", float("nan"),
        reference_driver="sergio-perez",
    ).get("status")
    # unsupported signal + unknown intervention type
    nc["gear_intervention_status"] = simulate_telemetry_counterfactual(
        queries, 2023, 1, "max-verstappen", 1, "gear", "REMOVE_DEFICIT", 0.5,
        reference_driver="sergio-perez",
    ).get("status")
    nc["unknown_intervention_status"] = simulate_telemetry_counterfactual(
        queries, 2023, 1, "max-verstappen", 1, "speed", "MAKE_FASTER", 0.5,
        reference_driver="sergio-perez",
    ).get("status")
    expected = {
        "1950": UNAVAILABLE, "2018": UNAVAILABLE,
        "missing_driver": UNAVAILABLE, "absent_lap": UNAVAILABLE,
        "fraction_out_of_bounds_status": "INVALID",
        "nan_fraction_status": "INVALID",
        "gear_intervention_status": UNSUPPORTED,
        "unknown_intervention_status": UNSUPPORTED,
    }
    nc["all_expected"] = all(nc[k] == v for k, v in expected.items())
    nc["insufficient_state_available"] = INSUFFICIENT  # semantics exist in the module
    return nc


def _mcp_verification(queries: CanonicalQueries) -> dict[str, Any]:
    from racewise.tools.contract import ToolError
    from racewise.tools.historical import build_historical_registry

    reg = build_historical_registry(queries)
    name = "simulate_historical_telemetry_counterfactual"
    out: dict[str, Any] = {"tool_registered": name in reg._tools}
    if not out["tool_registered"]:
        return out
    pair = queries.get_telemetry_driver_pair(2023, 1)
    lap = _first_covered_lap(queries, 2023, 1)
    if pair and lap is not None:
        r = reg.execute(name, {
            "season": 2023, "round": 1, "driver": pair[1], "reference_driver": pair[0],
            "lap_number": lap, "signal": "speed",
            "intervention_type": "REMOVE_DEFICIT", "fraction": 0.5,
        })
        out["registry_status"] = r["output"].get("status")
        out["registry_delta_s"] = r["output"].get("counterfactual_delta_s")
    # bounds through the contracted registry path
    for label, kwargs in (
        ("fraction_99", {"fraction": 99}),
        ("segment_s_99", {"fraction": 0.05, "segment_s": 99}),
        ("bad_signal", {"fraction": 0.5, "signal": "telepathy"}),
        ("unknown_param", {"fraction": 0.5, "bogus": 1}),
    ):
        base = {
            "season": 2023, "round": 1, "driver": "max-verstappen", "lap_number": 1,
            "signal": "speed", "intervention_type": "SCALE_SIGNAL",
        }
        try:
            reg.execute(name, {**base, **kwargs})
            out[label] = "ACCEPTED"
        except ToolError as exc:
            out[label] = f"REJECTED: {exc.code}"
    return out


if __name__ == "__main__":  # pragma: no cover
    q = CanonicalQueries()
    print(json.dumps(run_q11(q, include_mcp=True), indent=2, default=str))
