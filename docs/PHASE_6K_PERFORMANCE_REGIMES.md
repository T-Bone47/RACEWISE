# PHASE 6K — PERFORMANCE REGIME & CHANGE-POINT INTELLIGENCE

Methodology document. Companion to `PHASE_6K_COMPLETION_REPORT.md`.

## 1. What a regime is (and is not)

A **performance regime** is a contiguous interval of comparable laps during which the
deterministic segmentation rule finds no change point in the pair's lap-delta trend.
A regime carries: `start_lap`, `end_lap`, `lap_count`, per-regime features (trend
classification, slope, residual, context), hypothesis evolution, model sensitivity,
and provenance.

A regime is an **analytical structure**. A stint is a canonical race structure. They
may align; they may cross (`REGIME 2: laps 20–35` over `STINT 1: laps 1–24`,
`STINT 2: laps 25–40` is valid and preserved — regime boundaries are never forced to
stint boundaries).

## 2. Segmentation mathematics (deterministic)

Top-down recursive binary segmentation over the pair's comparable-lap delta series
(`delta = driver_a lap time − driver_b lap time`, Phase 6E comparable-lap rules):

1. Fit OLS to the segment; compute residual sum of squares (SSE).
2. For every candidate split, fit OLS to left and right halves.
3. **Split statistic** = `|right slope − left slope|`.
4. Accept the best split only if **all** of:
   - statistic ≥ `SEGMENT_STAT_THRESHOLD` (0.06 s/lap),
   - per-side slope significance ≥ `SLOPE_THRESHOLD_S_PER_LAP` (0.03 s/lap, Phase 6G
     semantics, MIN_TREND_OBS reuse),
   - SSE improvement gate passes,
   - both sides ≥ `MIN_REGIME_LAPS` (3).
5. Recurse. Near-slope segments merge deterministically (rule-based; no manual
   tuning). Rejected candidates are **recorded** in `rejected_change_points` with
   reasons; merges are recorded in `regime_merges`. Nothing is silently discarded.

No neural networks, no clustering, no LLM classification, no confidence scores.
Outputs are `DETECTED` / `NOT_DETECTED` / `INSUFFICIENT_EVIDENCE` with the method,
threshold, and measured change shown alongside.

## 3. Change-point types

Typed, closed vocabulary:

- Performance: `GAP_TREND_CHANGE`, `SPEED_PROFILE_CHANGE`, `ENVELOPE_CHANGE`,
  `RESIDUAL_CHANGE`
- Context (not performance change points): `STINT_TRANSITION`, `PIT_TRANSITION`,
  `RACE_CONTROL_TRANSITION`, `WEATHER_TRANSITION`, `TELEMETRY_TRANSITION`,
  `HYPOTHESIS_STATE_CHANGE`

Context transitions are aligned with exact lap overlaps and reported **as
associations**. The system states "the performance transition occurred near the
compound transition" — never "the compound caused the transition".

## 4. Per-regime features (reuse only)

No second engine is built. Per regime:

- **Gap trend**: Phase 6G OLS trend and classification vocabulary
  (`STABLE` / `WIDENING` / `NARROWING` / `REVERSAL` / `INSUFFICIENT_EVIDENCE`).
- **Residual**: observed delta minus Phase 6F fused pace component, tracked across
  regimes (`RESIDUAL_STABLE` / `RESIDUAL_INCREASING` / `RESIDUAL_DECREASING` /
  `RESIDUAL_CHANGE` / `INSUFFICIENT_EVIDENCE`). The residual is never assigned to a
  hypothesis.
- **Hypothesis evolution**: Phase 6F `fuse_lap_evidence` verdicts aggregated per
  regime (all six hypotheses tracked independently; never collapsed to one
  race-level label).
- **Model sensitivity**: Phase 6J scenario sweep at f = 0.5 over the regime's exact
  telemetry lap set (6J gained a backwards-compatible `laps` parameter so regime
  sweeps flow through the identical 6I lap-time model). Sensitivity outside the
  driver's clean comparable telemetry-covered set returns an explicit INVALID with
  the offending laps.
- **Context**: compounds, restricted (race-control) laps, pit laps from the Phase 6H
  timeline.

If paired telemetry is absent for a regime, the regime is still reported with
`TELEMETRY_UNAVAILABLE` sensitivity — the unavailability interval is preserved, never
inferred over.

## 5. Timeline synthesis

`race_timeline` interleaves, in lap order: `REGIME` spans, `CHANGE_POINT` events
(performance), and `CONTEXT_TRANSITION` events (stint / pit / race control /
weather / telemetry). This is machine-generated from structured facts only.

## 6. Cross-race comparison

`compare_performance_regimes` composes per-race regime results descriptively
(regime counts, durations, transition types, telemetry coverage). It does **not**
rank races and does not identify a "best" race.

## 7. Epistemics

- A change is not a cause. Detection identifies measured temporal structure.
- Temporal alignment between a performance transition and a context transition is an
  association, not causation.
- Model sensitivity is a property of the 6I/6J speed-profile model under the
  specified intervention; it is not a historical claim.
- Falsification and Phase 6F evidence vocabulary are preserved; regimes organize
  evidence, they do not manufacture it.

## 8. Bounds and safety

- MCP `analyze_historical_performance_regimes`: explicit bounds on
  `max_regimes`, `min_regime_laps` (fixed at 3), lap window
  (`start_lap` ≤ `end_lap`), distinct drivers enforced at the boundary; unknown
  parameters rejected by the registry contract; enums enforced (6I hardening).
- Read-only DB access; derived-on-read; zero storage growth; no secrets; no
  eval/SQL/shell; no user-supplied expressions.

## 9. Performance note

The initial implementation measured ~21 s per race. Profiling attributed ~12.5 s to
per-lap weather re-querying (each call re-opening a SQLite connection). The fix is a
read-through memo of immutable canonical reads scoped to one analysis invocation —
same code paths, read-only DB, semantically transparent (verified by output diff and
hash analysis). Final: **p50 0.95 s / max 0.99 s per race**.
