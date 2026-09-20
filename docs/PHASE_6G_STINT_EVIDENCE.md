# Phase 6G — Stint-Level Evidence Fusion Methodology

How RACEWISE determines *"how did the performance relationship between Driver
A and Driver B evolve across an entire stint — which explanations remained
consistent, which changed, and what remains unexplained?"*

Companion to `PHASE_6G_COMPLETION_REPORT.md` (measured results),
`PHASE_6F_EVIDENCE_FUSION.md` (lap fusion), `PHASE_6E_TELEMETRY_ATTRIBUTION.md`
(attribution internals).

## 1. Design position

A stint is a **temporal sequence of observations**, not an average. Phase 6G
consumes per-lap Phase 6F fusions as an ordered series and adds the temporal
layer: trajectory, trend, hypothesis evolution, residual trajectory, context
transitions and change-point analysis. Nothing in 6E/6F was rewritten; every
status, relationship and provenance semantic is reused verbatim.

SUPPORTED still means *evidence-consistent*, never causation. Consistency
*over time* is still not causation.

## 2. Pipeline

```
canonical stint identity (canonical_stints — never inferred)
  → common-lap selection (6E clean-lap rules + telemetry coverage; exclusions reported)
  → per-lap Phase 6F fusions (ordered temporal sequence)
  → performance trajectory + OLS trend (min-observation rule)
  → telemetry metric trends (speed/throttle/brake/DRS per-stint slopes)
  → hypothesis evolution (per-lap statuses → persistence properties → summary rule)
  → residual trajectory + cumulative conservation identity
  → context transitions (rain / race control / compound regimes)
  → change-point (thresholded first/second-half slope comparison)
  → evidence-bounded stint conclusion
```

## 3. Stint definition

A stint exists only when canonical stint identity exists for **both** drivers
in `canonical_stints` (same session, same stint number). Missing identity →
`UNAVAILABLE`. Stint membership is never inferred from consecutive laps.

## 4. Common-lap selection

A lap is a candidate when either driver has a lap fact in the stint. It is
selected when:

- both drivers have a canonical lap fact for that lap
- both lap times are present
- neither lap carries a 6E non-comparable flag (`is_pit_in_lap`,
  `is_pit_out_lap`, `deleted`)
- telemetry covers the lap for **both** drivers (stint fusion requires
  telemetry evidence)

Every rejected lap appears in `selection.excluded` with its reason. When more
than `max_laps` (default 10, hard cap 16) laps qualify, a deterministic
evenly spaced sample is taken and the unselected laps are excluded with
reason `"outside bounded sample (stint window)"`.

## 5. Performance trajectory and trend

- Per selected lap: `lap_number`, `stint_lap_index`, status, observed delta,
  pace component, residual, per-signal metric values, compound, restriction
  and rain flags, per-hypothesis statuses.
- Stats: mean, median, min, max, first, last.
- **Trend**: OLS slope of the observed delta against the stint-lap index.
  Fewer than `MIN_TREND_OBS = 3` valid observations → trend
  `INSUFFICIENT_EVIDENCE` (a two-point "slope" is not evidence). Outliers are
  retained and visible — never silently discarded.
- **Cumulative gap**: sum of the observed deltas over the *selected
  comparable laps*. The output states explicitly that this is a cumulative
  comparison across the selected laps, **not** total race time lost, unless
  the selection covers the stint representatively.

## 6. Telemetry metric trends

For each signal metric (speed mean delta, throttle mean delta and lift
windows, braking-fraction delta and first-brake delta, DRS activation-fraction
delta) the per-lap values from the 6F evidence items form a series; the same
`_trend_block` rule (OLS + minimum observations) produces per-field trends.
Emerging/persisting/disappearing patterns are read from these blocks — they
are never asserted when the block is `INSUFFICIENT_EVIDENCE`.

## 7. Hypothesis evolution

For each of the six 6F hypotheses, the per-lap statuses form a temporal
sequence. Descriptive properties (never scores):

- counts: valid observations, supported, partially supported, not supported,
  contradicted, not testable
- first/last supported lap
- `status_transitions`: number of status changes across the evaluable laps
- `support_fraction`

Summary rule (documented; evaluable = status ≠ NOT_TESTABLE):

| Condition | Summary |
|---|---|
| < 2 evaluable | INSUFFICIENT_EVIDENCE |
| 0 < support < 3 and evaluable < 3 | INSUFFICIENT_EVIDENCE (positive claims need ≥3 laps) |
| support = 0 and ≥2 not-supported/contradicted | CONTRADICTED_OVER_TIME |
| support = 0 (else) | NOT_SUPPORTED |
| ≥3 evaluable, 0 contradictions, support = evaluable | CONSISTENTLY_SUPPORTED |
| ≥3 evaluable, 0 contradictions, support/evaluable ≥ 0.7 | MOSTLY_SUPPORTED |
| otherwise | INTERMITTENTLY_SUPPORTED |

The 6F deficit-premise gate propagates: on laps where B was not slower all
hypotheses are NOT_TESTABLE and contribute no evaluable observations.

## 8. Residual trajectory and conservation

Per-lap residuals (6E reconciliation, preserved through 6F) form a series
with the same trend rule. Cumulative identity, reported explicitly:

```
cumulative_observed = cumulative_pace_component + cumulative_residual
```

(test-enforced to 1e-6). The cumulative residual is *unresolved evidence*;
it is never assigned to a hypothesis.

## 9. Context transitions

A transition is recorded (lap number, from-regime, to-regime) whenever
(race-control restriction, rain-in-window, compound) changes between
consecutive valid laps. Incompatible regimes are never merged into a single
explanation without the transition being visible.

## 10. Change-point analysis

Deterministic and bounded: split the valid lap sequence at the median index;
compute OLS slopes of both halves; report `CHANGE_DETECTED` only when both
halves have ≥3 observations and the slope difference exceeds
`CHANGE_POINT_DELTA_S = 0.03` s per stint lap (with a minimum-activity guard
`CHANGE_POINT_MIN_SLOPE_S = 0.02`); otherwise `STABLE` (within threshold) or
`NOT_TESTABLE` (< 6 valid laps, unbalanced halves). No ML, no black boxes.

## 11. Falsification over time

A hypothesis supported on early laps is not carried forward by inertia: the
summary rules count every contradiction across the stint, transitions are
reported, and a hypothesis whose support disappears mid-stint lands in
INTERMITTENTLY_SUPPORTED rather than staying CONSISTENTLY_SUPPORTED. The Q9
matrix asserts that contradicted hypotheses actually surface on real data.

## 12. Source independence

Per-lap 6F `source_id` uniqueness is preserved inside each lap fusion. Across
laps, each lap is one observation set; stint-level summaries aggregate the
*statuses*, not re-derive evidence, so no cross-lap double counting occurs.
Dependency chains remain explicit via the per-lap evidence items retained in
the trajectory.

## 13. Storage and reproducibility

Derived on read: no derived tables, no telemetry duplication, zero database
growth (size+mtime proven unchanged during fusion). Same canonical DB +
`stint_evidence_v1` ⇒ byte-identical output (in-process, fresh subprocess,
MCP). Output hashes anchor regressions; a changed hash means a methodology or
data change and must be justified, never silent.
