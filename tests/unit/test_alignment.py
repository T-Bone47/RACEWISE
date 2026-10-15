"""Alignment contract tests (Phase I §3): pure math, no DB, no network."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from racewise.data.historical.alignment import (
    ALIGNMENT_VERSION,
    MAX_DISTANCE_DISAGREEMENT_FRAC,
    cumulative_distance,
    distance_aligned_losses,
)


def test_cumulative_distance_constant_speed():
    # 100 m/s for 10 s -> 1000 m
    times = [float(t) for t in range(11)]
    speeds = [360.0] * 11  # 360 km/h = 100 m/s
    out = cumulative_distance(times, speeds)
    assert out[0] == 0.0
    assert out[-1] == pytest.approx(1000.0, abs=1e-6)
    assert all(b >= a for a, b in zip(out[:-1], out[1:]))


def test_cumulative_distance_empty_or_single():
    assert cumulative_distance([], []) == [0.0]
    assert cumulative_distance([0.0], [100.0]) == [0.0]


def test_identical_series_net_zero():
    times = [float(t) * 0.25 for t in range(40)]
    speeds = [200.0 + 50.0 * (t % 5) for t in times]
    out = distance_aligned_losses(times, speeds, times, speeds)
    assert out is not None
    assert out["net_s"] == pytest.approx(0.0, abs=1e-9)


def test_slower_driver_positive_net():
    times = [float(t) * 0.25 for t in range(40)]
    va = [300.0] * 40
    vb = [290.0] * 40  # uniformly ~3.3% slower
    out = distance_aligned_losses(times, va, times, vb)
    assert out is not None
    assert out["net_s"] > 0
    # Plausible magnitude band: the time-window formula gives
    # T*(1-vb/va) = 0.325 while the mean-distance form gives 0.331
    # (rescale factor (va+vb)/2vb). Both are first-order consistent;
    # the test pins the band, not either closed form.
    assert 0.30 < out["net_s"] < 0.36


def test_faster_windows_offset():
    # B slower in first half, faster in second half by the same ratio:
    # net must be ~0 while gross-style positive sum is not.
    times = [float(t) * 0.5 for t in range(20)]
    va = [200.0] * 20
    vb = [180.0] * 10 + [222.222] * 10
    out = distance_aligned_losses(times, va, times, vb, n_spans=20)
    assert out is not None
    signed = [s["signed_loss_s"] for s in out["span_losses"]]
    assert any(v > 0 for v in signed) and any(v < 0 for v in signed)
    assert out["net_s"] == pytest.approx(0.0, abs=0.05)


def test_disagreement_guard():
    times = [float(t) for t in range(10)]
    va = [300.0] * 10  # ~3000 m
    vb = [100.0] * 10  # ~1000 m -> >5% disagreement
    assert distance_aligned_losses(times, va, times, vb) is None


def test_empty_series_returns_none():
    assert distance_aligned_losses([], [], [0.0], [100.0]) is None
    assert distance_aligned_losses([0.0], [100.0], [], []) is None


def test_span_fields_and_version():
    times = [float(t) * 0.25 for t in range(8)]
    out = distance_aligned_losses(times, [200.0] * 8, times, [190.0] * 8,
                                  n_spans=4)
    assert out is not None
    assert out["alignment_version"] == ALIGNMENT_VERSION
    assert len(out["span_losses"]) == 4
    for sp in out["span_losses"]:
        assert {"s_start_m", "s_end_m", "v_a_kmh", "v_b_kmh",
                "signed_loss_s"} <= set(sp)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
