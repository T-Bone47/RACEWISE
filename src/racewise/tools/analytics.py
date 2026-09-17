"""Deterministic analysis functions for RACEWISE.

Every function is versioned, pure, and returns plain dicts. All numerical
claims in final reports must originate here.
"""
from __future__ import annotations

import statistics
from typing import Optional

from racewise.domain.schemas import Lap
from racewise.tools.race_state import cars_ahead_at_lap, laps_for_driver, time_gap_at_lap

ANALYTICS_VERSION = "1.0.0"


def filter_clean_laps(
    laps: list[Lap],
    *,
    exclude_pit_laps: bool = True,
    require_accurate: bool = True,
    require_timed: bool = True,
    track_status_allowed: str = "1",
) -> list[Lap]:
    """Return laps suitable for pace comparison.

    Policy (v1): exclude pit in/out laps, deleted laps, optionally require
    FastF1 accuracy flag, and require green-track status.
    """
    clean: list[Lap] = []
    for lap in laps:
        if require_timed and lap.lap_time_s is None:
            continue
        if exclude_pit_laps and (lap.is_pit_in_lap or lap.is_pit_out_lap):
            continue
        if lap.deleted:
            continue
        if require_accurate and lap.is_accurate is False:
            continue
        if track_status_allowed is not None and lap.track_status not in (None, track_status_allowed):
            continue
        clean.append(lap)
    return clean


def stint_laps(laps: list[Lap], driver: str, stint_number: int) -> list[Lap]:
    return sorted(
        (lap for lap in laps if lap.driver == driver and lap.stint == stint_number),
        key=lambda lap: lap.lap_number,
    )


def linear_degradation(laps: list[Lap]) -> Optional[dict]:
    """Least-squares slope of lap time vs tyre life for a lap set."""
    points = [
        (float(lap.tyre_life), float(lap.lap_time_s))
        for lap in laps
        if lap.tyre_life is not None and lap.lap_time_s is not None
    ]
    if len(points) < 3:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    if sxx == 0:
        return None
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    residuals = [y - (intercept + slope * x) for x, y in points]
    ss_res = sum(r * r for r in residuals)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {
        "slope_s_per_lap": round(slope, 4),
        "intercept_s": round(intercept, 4),
        "r_squared": round(r2, 4),
        "n_laps": n,
    }


def compare_sectors(laps_a: list[Lap], laps_b: list[Lap]) -> Optional[dict]:
    """Mean sector times for two lap sets and the per-sector delta A-B."""

    def means(laps: list[Lap]) -> dict:
        out: dict = {}
        for sector in ("sector_1_s", "sector_2_s", "sector_3_s"):
            values = [getattr(lap, sector) for lap in laps if getattr(lap, sector) is not None]
            out[sector] = round(statistics.fmean(values), 4) if values else None
        return out

    if not laps_a or not laps_b:
        return None
    means_a = means(laps_a)
    means_b = means(laps_b)
    delta = {
        sector: (
            round(means_a[sector] - means_b[sector], 4)
            if means_a[sector] is not None and means_b[sector] is not None
            else None
        )
        for sector in means_a
    }
    return {"a_means": means_a, "b_means": means_b, "delta_a_minus_b": delta}


def pace_summary(laps: list[Lap]) -> Optional[dict]:
    clean = [lap.lap_time_s for lap in laps if lap.lap_time_s is not None]
    if not clean:
        return None
    return {
        "n_laps": len(clean),
        "mean_s": round(statistics.fmean(clean), 4),
        "fastest_s": round(min(clean), 4),
        "stdev_s": round(statistics.pstdev(clean), 4) if len(clean) > 1 else 0.0,
    }


def detect_pace_anomaly(
    laps: list[Lap],
    *,
    window: int = 5,
    threshold_factor: float = 2.0,
) -> list[dict]:
    """Detect laps slower than a rolling median by > threshold_factor * scaled MAD."""
    timed = sorted(
        (lap for lap in laps if lap.lap_time_s is not None),
        key=lambda lap: lap.lap_number,
    )
    anomalies: list[dict] = []
    for i, lap in enumerate(timed):
        lo = max(0, i - window)
        hi = min(len(timed), i + window + 1)
        neighborhood = [t for j, t in enumerate([x.lap_time_s for x in timed[lo:hi]]) if lo + j != i]
        if len(neighborhood) < 3:
            continue
        med = statistics.median(neighborhood)
        abs_devs = [abs(t - med) for t in neighborhood]
        mad = statistics.median(abs_devs) or 1e-6
        deviation = lap.lap_time_s - med
        if deviation > threshold_factor * 1.4826 * mad:
            anomalies.append(
                {
                    "lap_number": lap.lap_number,
                    "lap_time_s": round(lap.lap_time_s, 4),
                    "window_median_s": round(med, 4),
                    "deviation_s": round(deviation, 4),
                    "threshold_s": round(threshold_factor * 1.4826 * mad, 4),
                }
            )
    return anomalies


def delta_time_between_drivers(driver_laps: list[Lap], reference_laps: list[Lap]) -> Optional[dict]:
    """Mean and fastest pace delta between two clean-lap sets."""
    a = pace_summary(driver_laps)
    b = pace_summary(reference_laps)
    if a is None or b is None:
        return None
    return {
        "driver_mean_s": a["mean_s"],
        "reference_mean_s": b["mean_s"],
        "delta_s": round(a["mean_s"] - b["mean_s"], 4),
        "driver_fastest_s": a["fastest_s"],
        "reference_fastest_s": b["fastest_s"],
        "fastest_delta_s": round(a["fastest_s"] - b["fastest_s"], 4),
        "driver_n_laps": a["n_laps"],
        "reference_n_laps": b["n_laps"],
    }


def traffic_exposure(
    all_laps: list[Lap],
    driver: str,
    lap_start: int,
    lap_end: int,
    gap_threshold_s: float = 1.0,
) -> dict:
    """Estimate dirty-air/traffic exposure in a lap window.

    A lap counts as 'in traffic' when the car directly ahead on track is
    within gap_threshold_s of cumulative race time at that lap.
    """
    target_cum: dict[int, float] = {}
    for lap in laps_for_driver(all_laps, driver):
        if lap.lap_time_s is not None:
            target_cum[lap.lap_number] = target_cum.get(lap.lap_number - 1, 0.0) + lap.lap_time_s
    exposures: list[dict] = []
    for lap_number in range(lap_start, lap_end + 1):
        ahead = cars_ahead_at_lap(all_laps, lap_number, driver, count=1)
        if not ahead:
            exposures.append({"lap_number": lap_number, "in_traffic": False, "gap_s": None, "car_ahead": None})
            continue
        ahead_name = ahead[0]
        gap = time_gap_at_lap(all_laps, lap_number, ahead_name, driver)
        in_traffic = gap is not None and abs(gap) <= gap_threshold_s
        exposures.append(
            {
                "lap_number": lap_number,
                "in_traffic": in_traffic,
                "gap_s": gap,
                "car_ahead": ahead_name,
            }
        )
    traffic_laps = [e["lap_number"] for e in exposures if e["in_traffic"]]
    return {
        "window": [lap_start, lap_end],
        "laps_analyzed": len(exposures),
        "traffic_laps": traffic_laps,
        "traffic_fraction": round(len(traffic_laps) / len(exposures), 4) if exposures else 0.0,
        "exposure_detail": exposures,
    }
