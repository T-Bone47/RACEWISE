"""Reference-verified unit tests against 2023 Bahrain Race data."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from racewise.data.fastf1_adapter import FastF1Adapter
from racewise.domain.schemas import Lap
from racewise.tools.analytics import (
    delta_time_between_drivers,
    detect_pace_anomaly,
    filter_clean_laps,
    linear_degradation,
    pace_summary,
    stint_laps,
)


@pytest.fixture(scope="module")
def bahrain_laps() -> list:
    adapter = FastF1Adapter(cache_dir=os.path.join(os.path.dirname(__file__), "..", ".fastf1-cache"))
    session = adapter.load_session(2023, "Bahrain", "R")
    return adapter.laps(session)


def test_race_has_57_laps_for_ver(bahrain_laps):
    ver = [lap for lap in bahrain_laps if lap.driver == "VER"]
    assert len(ver) == 57
    assert max(lap.lap_number for lap in ver) == 57


def test_ver_pit_laps_are_14_and_36(bahrain_laps):
    ver = [lap for lap in bahrain_laps if lap.driver == "VER"]
    pit_laps = [lap.lap_number for lap in ver if lap.is_pit_in_lap]
    assert pit_laps == [14, 36]


def test_stint_bounds_match_reference(bahrain_laps):
    ver = [lap for lap in bahrain_laps if lap.driver == "VER"]
    s1 = stint_laps(ver, "VER", 1)
    s2 = stint_laps(ver, "VER", 2)
    s3 = stint_laps(ver, "VER", 3)
    assert (s1[0].lap_number, s1[-1].lap_number) == (1, 14)
    assert (s2[0].lap_number, s2[-1].lap_number) == (15, 36)
    assert (s3[0].lap_number, s3[-1].lap_number) == (37, 57)
    assert {lap.compound for lap in s1} == {"SOFT"}
    assert {lap.compound for lap in s2} == {"SOFT"}
    assert {lap.compound for lap in s3} == {"HARD"}


def test_clean_lap_filter_excludes_in_out_laps(bahrain_laps):
    ver = [lap for lap in bahrain_laps if lap.driver == "VER"]
    s2 = stint_laps(ver, "VER", 2)
    clean = filter_clean_laps(s2)
    numbers = [lap.lap_number for lap in clean]
    assert 15 not in numbers  # pit in-lap (1:58.378)
    assert 36 not in numbers  # pit in-lap (1:40.964)
    assert all(lap.lap_time_s is not None for lap in clean)


def test_clean_lap_pace_matches_reference(bahrain_laps):
    ver = [lap for lap in bahrain_laps if lap.driver == "VER"]
    s2_clean = filter_clean_laps(stint_laps(ver, "VER", 2))
    summary = pace_summary(s2_clean)
    assert summary["n_laps"] == 20
    # Hand-verified: mean of laps 16-35 is ~97.60s, fastest 97.372 (lap 25)
    assert 97.3 < summary["mean_s"] < 97.9
    assert summary["fastest_s"] == 97.372


def test_degradation_slope_is_small_when_tyres_settled(bahrain_laps):
    ver = [lap for lap in bahrain_laps if lap.driver == "VER"]
    s2_clean = filter_clean_laps(stint_laps(ver, "VER", 2))
    deg = linear_degradation(s2_clean)
    assert deg is not None
    assert deg["n_laps"] == 20
    assert abs(deg["slope_s_per_lap"]) < 0.2  # settled stint, near-flat


def test_anomaly_detector_flags_in_lap_when_included(bahrain_laps):
    ver = [lap for lap in bahrain_laps if lap.driver == "VER"]
    s2 = stint_laps(ver, "VER", 2)
    anomalies = detect_pace_anomaly(s2)
    flagged = {a["lap_number"] for a in anomalies}
    assert 36 in flagged  # 1:40.964 vs ~97.5s median


def test_driver_delta_non_negative_for_ver_vs_ham_s3(bahrain_laps):
    ver = [lap for lap in bahrain_laps if lap.driver == "VER"]
    ham = [lap for lap in bahrain_laps if lap.driver == "HAM"]
    ver_s3 = filter_clean_laps(stint_laps(ver, "VER", 3))
    ham_s3 = filter_clean_laps(stint_laps(ham, "HAM", 3))
    delta = delta_time_between_drivers(ver_s3, ham_s3)
    assert delta is not None
    assert -1.0 < delta["delta_s"] < 3.0  # VER led HAM by ~5s per stint pace delta
