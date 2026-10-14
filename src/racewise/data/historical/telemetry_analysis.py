"""Deterministic telemetry analysis (Phase 6C).

The LLM never computes telemetry numbers: every figure here comes from SQL
over canonical_telemetry + deterministic arithmetic, with documented
assumptions. All queries are bounded (signal whitelist, sample caps).

Consumer question (design gate, Phase 6C):
    "In which windows of a lap does driver B lose time to driver A, and is
    that loss associated with throttle lift or braking differences?"
This cannot be answered from lap aggregates (lap times, stints, positions):
it requires per-sample speed/throttle/brake series. That is why telemetry
exists in RACEWISE - and why it stayed deferred until this consumer was real.

Time-loss model (documented approximation, deterministic):
    For each window w of duration dt, if B's mean speed is below A's:
        signed_w = dt * (1 - v_B/v_A)
    The SIGNED sum over all windows is the reconcilable whole-lap
    estimate (first-order consistent with the measured lap delta when
    coverage is full). The sum of POSITIVE-ONLY window losses is a
    gross slower-phase exposure figure: it localises where B is
    slower but it is NON-ADDITIVE — it must never be summed with
    sector deltas or compared directly with the lap delta, because
    windows where B is faster are zeroed instead of offsetting.
    Windows are aligned by lap-relative TIME, not by track position
    (no distance channel is ingested): at equal lap time the two
    drivers are at different points on track, so neighbouring
    windows can mix track phases (e.g. one driver on a straight,
    the other still in the preceding corner). This phase mixing is
    what inflates the gross exposure figure on laps with large
    speed variation. Both figures are reported as estimates, never
    as fact; the net figure is the one that reconciles.
"""
from __future__ import annotations

from typing import Any, Optional

from racewise.data.historical.canonical_queries import CanonicalQueries

COMPARISON_VERSION = "1.0"
DEFAULT_WINDOW_S = 5.0
MIN_SAMPLES_PER_SIGNAL = 20  # below this, evidence is too thin to compare
RECONCILE_TOLERANCE_S = 0.05  # net-estimate vs measured-delta agreement band


def compare_telemetry_lap(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_a: str,
    driver_b: str,
    lap_number: int,
    window_s: float = DEFAULT_WINDOW_S,
    session_type: str = "RACE",
) -> dict[str, Any]:
    """Compare two drivers over one lap: per-window speed/throttle/brake deltas.

    Deterministic output; INSUFFICIENT_EVIDENCE when either driver-lap lacks
    telemetry (never a synthetic series). The time-loss estimate and the
    throttle/brake association are computed here, not narrated.
    """
    base: dict[str, Any] = {
        "analysis": "compare_telemetry_lap",
        "version": COMPARISON_VERSION,
        "season": season,
        "round": round_num,
        "session_type": session_type,
        "lap_number": lap_number,
        "driver_a": driver_a,
        "driver_b": driver_b,
        "window_s": window_s,
    }
    sig_a = _lap_series(queries, season, round_num, driver_a, lap_number, session_type)
    sig_b = _lap_series(queries, season, round_num, driver_b, lap_number, session_type)
    if sig_a is None or sig_b is None:
        return {
            **base,
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": (
                f"telemetry rows missing for "
                f"{driver_a if sig_a is None else driver_b} on this lap; "
                "telemetry is ingested for a bounded set only"
            ),
        }

    windows = _build_windows(sig_a, sig_b, window_s)
    if not windows:
        return {**base, "verdict": "INSUFFICIENT_EVIDENCE", "reason": "no overlapping time windows"}

    loss_total = 0.0
    net_total = 0.0
    ranked = []
    for w in windows:
        # Signed first-order window estimate (negative when B is faster
        # in the window). The positive-only figure below exists for
        # worst-window localisation only.
        signed = w["dt"] * (1.0 - w["v_b"] / w["v_a"]) \
            if w["v_a"] > 0 and w["v_b"] > 0 else 0.0
        loss = signed if w["v_a"] > 0 and w["v_b"] < w["v_a"] else 0.0
        w["signed_loss_s"] = round(signed, 4)
        w["est_time_loss_s"] = round(loss, 4)
        loss_total += loss
        net_total += signed
        ranked.append(w)
    ranked.sort(key=lambda w: w["est_time_loss_s"], reverse=True)
    worst = ranked[0]
    net_total = round(net_total, 3)
    loss_total = round(loss_total, 3)

    # Self-reconciliation against the measured lap delta (canonical lap
    # facts). The net estimate is an upper bound under time alignment;
    # the residual and the phase-mixing flag say whether it reconciles.
    measured_delta_s: Optional[float] = None
    laps_a = {r["lap_number"]: r for r in queries.get_lap_times(
        season, round_num, session_type, driver_a)}
    laps_b = {r["lap_number"]: r for r in queries.get_lap_times(
        season, round_num, session_type, driver_b)}
    lap_a, lap_b = laps_a.get(lap_number), laps_b.get(lap_number)
    if lap_a is not None and lap_b is not None \
            and lap_a.get("time_s") is not None \
            and lap_b.get("time_s") is not None:
        measured_delta_s = round(lap_b["time_s"] - lap_a["time_s"], 4)
    net_residual_s = (round(measured_delta_s - net_total, 4)
                      if measured_delta_s is not None else None)
    rectification_gap_s = round(loss_total - net_total, 4)
    phase_mixing_flag = (
        measured_delta_s is not None
        and rectification_gap_s > RECONCILE_TOLERANCE_S
        and rectification_gap_s > 0.5 * abs(measured_delta_s)
    )

    throttle_assoc = None
    if worst["d_throttle"] < 0:
        throttle_assoc = (
            f"driver_b lifted {abs(worst['d_throttle']):.1f}% more throttle on average "
            f"in the highest-loss window"
        )
    brake_assoc = None
    if worst["d_brake"] > 0:
        brake_assoc = (
            f"driver_b braked {worst['d_brake'] * 100:.0f}% more of the samples "
            f"in the highest-loss window"
        )

    return {
        **base,
        "verdict": "PASS",
        "n_windows": len(ranked),
        "total_est_time_loss_s": loss_total,
        "total_scope_note": (
            "gross positive-only window exposure (windows where B is "
            "faster are zeroed, not offset); NON-ADDITIVE — do not sum "
            "with sector deltas or compare directly with the measured "
            "lap delta; use net_est_time_loss_s for reconciliation"
        ),
        "net_est_time_loss_s": net_total,
        "net_scope_note": (
            "signed sum over all windows (faster windows offset slower "
            "ones); an UPPER BOUND on the pace component under time "
            "alignment — window-mean ratios overstate the deficit where "
            "speed varies, and equal lap time is not equal track "
            "position; reconciles exactly only under distance alignment"
        ),
        "measured_delta_s": measured_delta_s,
        "measured_scope_note": (
            "measured lap-time difference B minus A from canonical lap "
            "facts (FACT); the figure every estimate reconciles against"
        ) if measured_delta_s is not None else None,
        "net_residual_s": net_residual_s,
        "reconciles_within_tolerance": (
            abs(net_residual_s) <= RECONCILE_TOLERANCE_S
            if net_residual_s is not None else None
        ),
        "rectification_gap_s": rectification_gap_s,
        "phase_mixing_flag": phase_mixing_flag,
        "phase_mixing_note": (
            "window estimates mix track phases (time-aligned, not "
            "distance-aligned): the gross positive-only exposure exceeds "
            "the signed net because faster windows were zeroed instead "
            "of offsetting. The net estimate is the reconcilable figure; "
            "the gross exposure localises slower windows but is non-additive"
        ) if phase_mixing_flag else None,
        "max_loss_window": {
            "t_start_s": worst["t_start"], "t_end_s": worst["t_end"],
            "speed_delta_kmh": round(worst["v_b"] - worst["v_a"], 2),
            "throttle_delta_pct": round(worst["d_throttle"], 2),
            "brake_delta_frac": round(worst["d_brake"], 3),
            "est_time_loss_s": worst["est_time_loss_s"],
        },
        "top_windows": [
            {
                "t_start_s": w["t_start"], "speed_delta_kmh": round(w["v_b"] - w["v_a"], 2),
                "throttle_delta_pct": round(w["d_throttle"], 2),
                "brake_delta_frac": round(w["d_brake"], 3),
                "est_time_loss_s": w["est_time_loss_s"],
                "signed_loss_s": w["signed_loss_s"],
            }
            for w in ranked[:5]
        ],
        "throttle_association": throttle_assoc,
        "brake_association": brake_assoc,
        "assumptions": [
            "speed means are window averages of native-resolution samples (~3.8 Hz)",
            "time-loss estimate is straight-line (1 - v_B/v_A) per window; ignores line/tyre interactions",
            "throttle/brake deltas describe association with the loss, not proven causation",
            "windows align by lap-relative TIME (SessionTime - LapStartTime per driver); "
            "equal lap time is not equal track position and no distance channel is "
            "ingested, so neighbouring windows can mix track phases",
        ],
        "provenance": "canonical_telemetry (provider=fastf1) via bounded SQL queries",
    }


def _lap_series(
    queries: CanonicalQueries,
    season: int,
    round_num: int,
    driver_key: str,
    lap_number: int,
    session_type: str,
) -> Optional[dict[str, list[tuple[float, float]]]]:
    """Load bounded signal series for one driver-lap; None if unavailable."""
    out: dict[str, list[tuple[float, float]]] = {}
    for signal in ("speed", "throttle", "brake"):
        rows = queries.get_lap_telemetry(
            season, round_num, driver_key, lap_number,
            session_type=session_type, signals=[signal],
        )
        if len(rows) < MIN_SAMPLES_PER_SIGNAL:
            return None
        out[signal] = [(r["lap_time_s"], r["value"]) for r in rows]
    return out


def _build_windows(
    sig_a: dict[str, list[tuple[float, float]]],
    sig_b: dict[str, list[tuple[float, float]]],
    window_s: float,
) -> list[dict[str, float]]:
    """Deterministic fixed-width windows over the overlapping lap-time span."""
    t0 = max(sig_a["speed"][0][0], sig_b["speed"][0][0])
    t1 = min(sig_a["speed"][-1][0], sig_b["speed"][-1][0])
    if t1 <= t0:
        return []
    windows: list[dict[str, float]] = []
    t = t0
    while t < t1:
        t_end = min(t + window_s, t1)
        v_a = _mean_in(sig_a["speed"], t, t_end)
        v_b = _mean_in(sig_b["speed"], t, t_end)
        th_a = _mean_in(sig_a["throttle"], t, t_end)
        th_b = _mean_in(sig_b["throttle"], t, t_end)
        br_a = _mean_in(sig_a["brake"], t, t_end)
        br_b = _mean_in(sig_b["brake"], t, t_end)
        if v_a is not None and v_b is not None and v_a > 0 and v_b > 0:
            windows.append({
                "t_start": round(t, 3), "t_end": round(t_end, 3),
                "dt": round(t_end - t, 3),
                "v_a": round(v_a, 2), "v_b": round(v_b, 2),
                "d_throttle": (th_b - th_a) if (th_a is not None and th_b is not None) else 0.0,
                "d_brake": (br_b - br_a) if (br_a is not None and br_b is not None) else 0.0,
            })
        t = t_end
    return windows


def _mean_in(series: list[tuple[float, float]], t_start: float, t_end: float) -> Optional[float]:
    vals = [v for (tt, v) in series if t_start <= tt < t_end]
    return sum(vals) / len(vals) if vals else None
