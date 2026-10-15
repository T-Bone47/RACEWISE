"""Shared alignment contract for speed-trace loss estimation (Phase I §3).

One canonical definition of how two drivers' speed traces are compared,
used by loss attribution (regions) and telemetry window comparison
alike — replacing the two divergent time-mean implementations with a
single distance-fraction method.

Definitions (normative for consumers of this module):

- **Alignment base**: derived cumulative distance per driver from their
  OWN measured speed samples (trapezoid rule). No cross-driver
  assumption enters the distance construction.
- **Common grid**: both cumulative distances are rescaled to a common
  lap distance ``D`` (mean of both totals: line and sampling differences
  are second-order and documented, not modeled). Speeds are linearly
  interpolated onto ``N`` equal spans of ``[0, D]``.
- **Signed segment loss**: ``ds * (1/v_B - 1/v_A)`` per span. The sum
  over all spans is the net pace component; it reconciles with the
  measured lap delta up to interpolation error (unlike time-window
  means, which overstate the deficit where speed varies — Jensen gap).
- **Units**: metres, seconds, km/h in / m/s internally. Deltas are
  always B minus A. Losses are positive when B is slower.
- **Rectified loss**: ``max(0, signed)`` exists ONLY for worst-window
  localisation. It is non-additive and must never be summed, compared
  with a lap delta, or presented without its scope note.

Versioned: ALIGNMENT_VERSION bumps on any method change so consumers
and goldens can pin the computation they validated.
"""
from __future__ import annotations

import bisect
from typing import Any, Optional

ALIGNMENT_VERSION = "1.0"

# Rescaling the two derived lap distances to their mean absorbs line
# and sampling differences. Laps whose derived totals disagree by more
# than this fraction are too inconsistent to compare: return None and
# let the caller report unavailable/estimated accordingly.
MAX_DISTANCE_DISAGREEMENT_FRAC = 0.05

# Speeds below this (m/s) are treated as missing: division by near-zero
# speeds produces unbounded per-span losses from noise, not driving.
MIN_SPEED_MS = 1.0


def cumulative_distance(
    times_s: list[float],
    speeds_kmh: list[float],
) -> list[float]:
    """Per-driver cumulative distance (m) by trapezoid rule on OWN samples."""
    out = [0.0]
    for (t0, v0), (t1, v1) in zip(zip(times_s[:-1], speeds_kmh[:-1]),
                                  zip(times_s[1:], speeds_kmh[1:])):
        dt = t1 - t0
        vmean = ((v0 + v1) / 2.0) * 1000.0 / 3600.0 if dt > 0 else 0.0
        out.append(out[-1] + max(vmean * dt, 0.0))
    return out


def _interp(xs: list[float], ys: list[float], x: float) -> Optional[float]:
    i = bisect.bisect_left(xs, x)
    if i <= 0:
        return ys[0] if ys else None
    if i >= len(xs):
        return ys[-1] if ys else None
    x0, x1 = xs[i - 1], xs[i]
    if x1 == x0:
        return ys[i]
    f = (x - x0) / (x1 - x0)
    return ys[i - 1] + f * (ys[i] - ys[i - 1])


def distance_aligned_losses(
    times_a: list[float],
    speeds_a_kmh: list[float],
    times_b: list[float],
    speeds_b_kmh: list[float],
    n_spans: int = 400,
) -> Optional[dict[str, Any]]:
    """Signed per-span losses on the common distance grid.

    Returns ``{"span_losses": [...], "span_edges_m": [...], "distance_m": D,
    "net_s": ...}`` where each span entry holds ``s_start_m, s_end_m,
    v_a_kmh, v_b_kmh, signed_loss_s``. ``None`` when either series is
    empty or the derived lap distances disagree beyond tolerance.
    """
    if len(times_a) < 2 or len(times_b) < 2:
        return None
    da = cumulative_distance(times_a, speeds_a_kmh)
    db = cumulative_distance(times_b, speeds_b_kmh)
    if da[-1] <= 0 or db[-1] <= 0:
        return None
    disagreement = abs(da[-1] - db[-1]) / max(da[-1], db[-1])
    if disagreement > MAX_DISTANCE_DISAGREEMENT_FRAC:
        return None
    D = (da[-1] + db[-1]) / 2.0
    sa = [d / da[-1] * D for d in da]
    sb = [d / db[-1] * D for d in db]
    va_ms = [v * 1000.0 / 3600.0 for v in speeds_a_kmh]
    vb_ms = [v * 1000.0 / 3600.0 for v in speeds_b_kmh]

    spans: list[dict[str, Any]] = []
    net = 0.0
    for i in range(n_spans):
        s0, s1 = D * i / n_spans, D * (i + 1) / n_spans
        sm = (s0 + s1) / 2.0
        a = _interp(sa, va_ms, sm)
        b = _interp(sb, vb_ms, sm)
        if a is None or b is None or a < MIN_SPEED_MS or b < MIN_SPEED_MS:
            continue
        signed = (s1 - s0) * (1.0 / b - 1.0 / a)
        net += signed
        spans.append({
            "s_start_m": round(s0, 2),
            "s_end_m": round(s1, 2),
            "v_a_kmh": round(a * 3.6, 2),
            "v_b_kmh": round(b * 3.6, 2),
            "signed_loss_s": round(signed, 5),
        })
    if not spans:
        return None
    return {
        "span_losses": spans,
        "distance_m": round(D, 1),
        "net_s": round(net, 4),
        "n_spans": len(spans),
        "alignment_version": ALIGNMENT_VERSION,
    }
