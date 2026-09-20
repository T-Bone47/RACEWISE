# Telemetry-to-Lap Loss Attribution (Phase 6E)

How RACEWISE answers *"why did Driver A lose time to Driver B on this lap?"*
deterministically, without fabricating causality.

## Causal direction (enforced)

```
measured lap delta (FACT, canonical lap times)
    → context/validity classification
    → telemetry alignment (CALCULATION)
    → sector + region decomposition (FACT + CALCULATION)
    → residual reconciliation
    → falsification of alternative explanations
    → conclusion with typed evidence
```

Telemetry never defines the delta; it only explains a delta that was already
measured. Every output field is typed FACT / CALCULATION / INFERENCE in
`evidence_typing`.

## Alignment decision

**Lap-relative time resampling onto a fixed 0.25 s grid** (linear, clamped,
no extrapolation). Rationale:

- FastF1 samples are car-local (`SessionTime` per car) — there is no shared
  time base between two cars, so direct sample pairing is impossible.
- `canonical_telemetry.lap_time_s` (lap-relative seconds) is already canonical
  and verified (6C): `SessionTime − LapStartTime`.
- Distance normalization is unavailable: no distance channel is ingested
  (positional channels deferred in 6C, no consumer).
- The grid spans the *overlap* of both drivers' traces; boundary points
  outside either span are dropped, never extrapolated.

Original telemetry is immutable; resampling happens in-memory per query.

## Attribution mathematics

### Sector attribution (authoritative, FACT)
When canonical sector splits (`sector1_s/2/3`) exist for both laps:

    delta_sector_i = sector_i(B) − sector_i(A)

These are measured facts. **The three sector deltas sum exactly to the
observed lap delta** (verified in tests to 4 decimal places). This is the
authoritative decomposition of the measured delta — no model, no residual.

### Region attribution (CALCULATION, model)
The overlapping lap-relative span is divided into fixed time regions
(default 15 s). Per region:

    loss_r = dt · (1 − v_B/v_A)     when v_B < v_A, else 0

This is a straight-line estimate of the pace deficit embedded in the speed
traces. It is **not** claimed causal and **not** expected to equal the
measured delta: window means smooth corner-exit differences, ignore racing
line/tyre state/fuel, and pit-path or standing-start effects live outside
speed traces entirely.

### Reconciliation (explicit residual)

    observed_delta ≈ estimated_pace_component + residual

The residual is always reported with an interpretation:
- `|residual| ≤ 0.05 s` → speed traces account for the delta within tolerance
- large positive → measured delta exceeds what speed traces explain
  (pit path, track position, measurement)
- negative → B's speed trace alone doesn't explain their faster lap
  (window-mean smoothing)

Residuals are never discarded and never silently zeroed.

## Per-signal metrics (explicit definitions)

| Signal | Metric | Definition |
|---|---|---|
| speed | mean/max delta | mean and max of (B − A) km/h over the shared grid; timestamp of largest deficit |
| throttle | mean delta + lift windows | mean (B − A) %; count of windows where B < 50% while A ≥ 90% |
| brake | fraction + onset | delta in share of grid samples braking; first braking point delta (s) |
| gear | mismatch fraction | share of grid points with different selected gear |
| rpm | mean delta | mean (B − A) rpm |
| drs | activation delta | delta in share of samples with DRS enabled (codes ≥ 8) |

## Context filtering

A comparison is classified before any telemetry is used:
- pit-in / pit-out / deleted laps → not comparable
- laps with no measured time → not comparable
- `track_status` containing SC/VSC/yellow codes (2/4/5/6/7) → not comparable
- `is_accurate = false` → not comparable
- rain **in the lap's own time window** → not comparable (per-lap window,
  not session-level — a wet first lap doesn't disqualify a dry lap 40)
- compound mismatch → VALID_WITH_CAVEATS

Outcomes: `VALID_COMPARISON`, `VALID_WITH_CAVEATS`, `INSUFFICIENT_EVIDENCE`,
`UNAVAILABLE` — exclusion reasons are always exposed in `context`.

## Falsification

Each attribution ships with checks against alternative explanations:
extra/earlier braking, DRS availability, race-control restriction, compound
mismatch. Each check returns `SUPPORTED` / `NOT_SUPPORTED` / `NOT_TESTABLE`
with the numbers used. SUPPORTED means *consistent with*, never *caused by*.

## Stint-level analysis

`attribute_stint_loss` samples (evenly, bounded ≤ 6) common clean laps of a
stint, attributes each, and aggregates: mean/median observed delta, mean pace
component, mean residual, delta trend, and `unexplained_fraction =
|mean residual| / |mean observed delta|`. It consumes canonical stints and
lap facts; it does not duplicate the Q1 degradation model.

## MCP surface (bounded)

- `attribute_historical_lap_loss` — one lap, fixed region grid, no raw dumps;
  `region_s` bounded 5–30 s; deterministic output hash.
- `attribute_historical_stint_loss` — bounded lap sample (`max_laps` ≤ 12).

## Determinism

Same canonical data + same methodology version ⇒ byte-identical JSON and
identical tool output hashes — verified in-process and across fresh
subprocesses.

## Known limitations

1. Region losses are speed-trace estimates; the residual quantifies what they
   do not explain.
2. No distance-based alignment (no distance channel ingested).
3. Attribution requires both laps to be clean and comparable — pit laps, flag
   laps and rain laps are refused rather than caveated into numbers.
4. Counterfactuals ("what if B had matched A's braking profile") remain
   UNSUPPORTED — the deterministic simulator has no telemetry-input model
   (`simulate_pit_timing` operates on lap times only). The gate returns
   honestly rather than simulating through prose.
