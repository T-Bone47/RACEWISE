"""Race-state primitives shared by tools and the counterfactual simulator.

Pure functions over canonical Lap lists; no I/O.
"""
from __future__ import annotations

import statistics
from typing import Optional

from racewise.domain.schemas import Lap

RACE_STATE_VERSION = "1.0.0"


def drivers(laps: list[Lap]) -> list[str]:
    return sorted({lap.driver for lap in laps})


def laps_for_driver(laps: list[Lap], driver: str) -> list[Lap]:
    return sorted((lap for lap in laps if lap.driver == driver), key=lambda lap: lap.lap_number)


def stint_of_lap(laps: list[Lap], driver: str, lap_number: int) -> Optional[int]:
    for lap in laps_for_driver(laps, driver):
        if lap.lap_number == lap_number:
            return lap.stint
    return None


def compound_of_lap(laps: list[Lap], driver: str, lap_number: int) -> Optional[str]:
    for lap in laps_for_driver(laps, driver):
        if lap.lap_number == lap_number:
            return lap.compound
    return None


def mean_pace(laps: list[Lap]) -> Optional[float]:
    times = [lap.lap_time_s for lap in laps if lap.lap_time_s is not None]
    if not times:
        return None
    return round(statistics.fmean(times), 4)


def stint_boundary_laps(laps: list[Lap], driver: str) -> dict[int, tuple[int, int]]:
    bounds: dict[int, tuple[int, int]] = {}
    for lap in laps_for_driver(laps, driver):
        if lap.stint is None:
            continue
        lo, hi = bounds.get(lap.stint, (lap.lap_number, lap.lap_number))
        bounds[lap.stint] = (min(lo, lap.lap_number), max(hi, lap.lap_number))
    return bounds


def laps_in_window(laps: list[Lap], driver: str, start: int, end: int) -> list[Lap]:
    return [lap for lap in laps_for_driver(laps, driver) if start <= lap.lap_number <= end]


def position_at_lap(laps: list[Lap], driver: str, lap_number: int) -> Optional[int]:
    for lap in laps_for_driver(laps, driver):
        if lap.lap_number == lap_number:
            return lap.position
    return None


def cars_ahead_at_lap(laps: list[Lap], lap_number: int, driver: str, count: int = 1) -> list[str]:
    """Return the N drivers directly ahead of `driver` at a given lap."""
    target_pos = position_at_lap(laps, driver, lap_number)
    if target_pos is None:
        return []
    ahead: list[tuple[int, str]] = []
    for lap in laps:
        if lap.lap_number == lap_number and lap.position is not None and lap.position < target_pos:
            ahead.append((lap.position, lap.driver))
    ahead.sort()
    return [driver_name for _, driver_name in ahead[:count]]


def time_gap_at_lap(laps: list[Lap], lap_number: int, driver_a: str, driver_b: str) -> Optional[float]:
    """Approximate time gap between two drivers at a lap from cumulative lap times.

    Sums clean timed laps from lap 1 up to `lap_number` for each driver and
    returns (a - b) in seconds. Positive means a is behind b.
    """
    def cumulative(driver: str) -> Optional[float]:
        total = 0.0
        for lap in laps_for_driver(laps, driver):
            if lap.lap_number > lap_number:
                break
            if lap.lap_time_s is None:
                continue
            total += lap.lap_time_s
        return total if total > 0 else None

    cum_a = cumulative(driver_a)
    cum_b = cumulative(driver_b)
    if cum_a is None or cum_b is None:
        return None
    return round(cum_a - cum_b, 4)
