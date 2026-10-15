# Phase I — Performance Engineering

## Gap analysis (from inspection, not assumption)

| Workflow | Status before Phase I | Evidence |
|---|---|---|
| A. Lap-time decomposition | implemented (`attribute_lap_loss`, fusion, synthesizer spatial/residuals) | Perez regression green |
| B. Driving-mechanism analysis | implemented (`compare_telemetry_lap` worst-window associations, signal metrics, H1–H3 evidence) | answer calculations green |
| C. Tyre/stint | implemented (`fuse_stint_evidence`: OLS trends, compounds, change-point) | T-G03/T-G13 goldens green |
| D. Stint pace comparison | implemented (trajectory, mean deltas) | covered above |
| E. Strategy/pit-stop | `simulate_pit_timing` + counterfactual path (lifecycle endpoint) | T-G10/T-G14 goldens green |
| F. Cross-session | 6L patterns + 6M evidence + q15 | q15 green |
| **Distance alignment** | **missing** — time-window means only; schema architects explicitly deferred the distance channel (6C bounded scope) | **implemented this phase** |

Highest-value gap: the time-grid estimator's 2–4x bias (measured on
real laps), root-caused to window-mean ratios (Jensen gap) composited
with time-alignment phase mixing. No distance channel is ingested, so a
derived-distance-fraction method was built instead of a store migration
(zero migration risk, zero content-id churn).

## Shared alignment contract (§3)

New module `data/historical/alignment.py` (`ALIGNMENT_VERSION = "1.0"`),
the single definition of comparison alignment, units, signs and scope
used by both estimators:

- per-driver cumulative distance from OWN measured speeds (trapezoid);
- common grid over mean lap distance (line/sampling differences
  second-order, documented); speeds linearly interpolated;
- signed span loss `ds * (1/v_B - 1/v_A)`; net sums reconcile;
- rectified loss exists for localisation only (non-additive by
  construction); deltas always B minus A; metres/seconds/km/h.

## Estimator replacement (workflows A/B)

`loss_attribution` regions and `telemetry_analysis` windows now compute
signed losses from the common distance grid (native samples — resampling
was measured to reintroduce bias, and the old `zip()` pairing was
systematically misaligned by the grid-origin offset):

| Case | Before (gross / net / residual) | After |
|---|---|---|
| Lap 6 VER/PER | 4.049 / 3.08 / −2.348 (telemetry); 1.391 / 1.196 / −0.464 (attribution) | 1.521 / 0.915 / −0.183 (telemetry); 0.934 / 0.909 / −0.177 (attribution) |
| Lap 57 VER/PER | — / — / — | net 0.146 vs measured 0.185, residual +0.039 **within tolerance** |
| Sector 2 (lap 6) | measured 0.411, net 0.55–1.19 (unstable across iterations) | measured 0.411, net 0.464 |

The phantom t=90 s window (−27 km/h deficit, 0.73 s "loss") is gone;
worst window is now t=35 s (0.23 s, small uniform deficit, honestly no
lift/brake event — reported as absent, never invented).

Display contracts preserved: region/window shapes, sector rows (now
assigned in distance space, no ±15 s padding heuristics), field names,
claim classes, flags, interpretations. Schema additive-only except the
corrected estimator values themselves.

## What was NOT built (with reasons)

- **Store distance-channel migration** (ALTER TABLE + backfill): renders
  the derived method unnecessary; content-id churn would force a fifth
  golden re-baseline for no measured gain (derived distance reconciles
  within tolerance already).
- **Fuel-trace/traffic-adjusted models**: no fuel data, traffic only
  approximate — documented as unavailable, not modelled.
- **New universal schema**: the alignment module is shared computation,
  not a schema; existing evidence taxonomy untouched.
- **Frontend redesign**: views render the same fields; headlines already
  prefer net + reconciliation (prior work).

## Assumptions and uncertainty

- Derived distance inherits speed-measurement noise; line differences
  absorbed by mean-D rescaling (second-order, stated).
- 0.25 s resampling bypassed for estimation (kept for display grids
  and signal metrics).
- Sector nets remain estimates (upper-bound character where speed
  varies); sector FACTS (deltas) unchanged and exact.
- Disagreement guard (5% lap-distance tolerance) reports
  INSUFFICIENT rather than comparing inconsistent laps.
