# Phase 6F — Evidence Fusion Methodology

How RACEWISE fuses independent canonical evidence sources into formal
hypothesis verdicts for a measured lap delta. Companion to
`PHASE_6F_COMPLETION_REPORT.md` (measured results) and
`PHASE_6E_TELEMETRY_ATTRIBUTION.md` (attribution internals).

## 1. Causal direction (invariant)

1. The lap delta is **measured first** from canonical lap facts (6E).
2. Telemetry/context sources only **explain** it — never define it.
3. Every output statement is typed FACT / CALCULATION / INFERENCE.
4. SUPPORTED means *evidence-consistent*, never *caused by*.

## 2. Pipeline

```
canonical lap facts (measured delta)
  → 6E attribution (sector decomposition + region model + residual)
  → source adapters (10 evidence sources, lap-window aligned)
  → relationship assignment (SUPPORTS / CONTRADICTS / DOES_NOT_TEST)
  → premise gate (deficit vs favourable delta)
  → formal hypothesis rules (no weights, no averages)
  → residual classification (preserved, unassigned)
  → evidence-bounded conclusion + provenance
```

## 3. Source set and identity

| source_type | prefix | tables |
|---|---|---|
| canonical_sector_split | `sector:{season}:{round}:{lap}:{n}` | canonical_lap_times |
| telemetry_speed_regions | `speed_region:{...}:{region}` | canonical_telemetry |
| telemetry_speed_metric | `speed_metric:{...}` | canonical_telemetry |
| telemetry_throttle_metric | `throttle_metric:{...}` | canonical_telemetry |
| telemetry_brake_metric | `brake_metric:{...}` | canonical_telemetry |
| telemetry_drs_metric | `drs_metric:{...}` | canonical_telemetry |
| canonical_stint_state | `tyre_state:{...}` | canonical_stints |
| canonical_race_control_lap_overlap | `race_control:{...}` | canonical_race_control |
| canonical_pit_stop_proximity | `pit:{...}` | canonical_pit_stops |
| canonical_weather_lap_window | `weather:{...}` | canonical_weather |

`source_id` uniqueness is asserted on every fusion: one observation, one
evidence item — no double-counting, no derived copies of the same underlying
source treated as independent confirmation.

## 4. Alignment

- **Laps**: `driver_key + lap_number` via canonical `get_lap_times` (6E).
- **Telemetry**: lap-relative time grid, linear interpolation on the shared
  grid (6E `_interp_series`); original telemetry immutable, resampling only
  in-memory.
- **Race control**: event overlap with the investigated lap window — never
  session-level classification.
- **Weather**: per-lap-window aggregation — session-level rain never
  contaminates a dry lap (defect found and fixed in 6E, preserved here).
- **Pit stops**: ±1-lap proximity window.
- **Sectors**: canonical sector splits when both laps carry them; otherwise
  `authoritative_sector_decomposition` is null (never invented).

## 5. Formal hypothesis rules

Preconditions: required source present, else **NOT_TESTABLE**.

- any CONTRADICTS + some SUPPORTS → **CONTRADICTED**
- any CONTRADICTS, no SUPPORTS → **NOT_SUPPORTED**
- SUPPORTS + zero CONTRADICTS + no neutral → **SUPPORTED**
- SUPPORTS + neutral items → **PARTIALLY_SUPPORTED**
- only neutral items → **NOT_SUPPORTED**

Neutral = DOES_NOT_TEST or INSUFFICIENT-quality items. No weighted averages,
no confidence scores. Invariant: unavailable evidence can never produce
SUPPORTED.

**Premise gate**: the six hypotheses all explain a deficit (B slower than A).
When the measured delta ≤ 0 the premise is vacuous and every hypothesis is
reported NOT_TESTABLE with the actual delta in the reason.

## 6. Residual

`observed_delta ≈ estimated_pace_component + residual` (from 6E) is preserved
verbatim. Classification:

- `|residual| ≤ 0.15·|observed|` → EXPLAINED_BY_SPEED_TRACES
- `≤ 0.75·|observed|` → PARTIALLY_EXPLAINED
- else → UNRESOLVED

The residual is never assigned to a hypothesis; the conclusion states this
explicitly.

## 7. Falsification-first

Each hypothesis is exposed to contradiction by *other* sources: braking
metrics can contradict the corner-speed hypothesis, tyre state can contradict
the throttle hypothesis, race-control and weather can contradict everything.
Fusion surfaces all contradicting items in the verdict (`contradicting` list)
and the Q8 matrix asserts contradictions actually surface on real deficit
laps.

## 8. Counterfactual gate

Telemetry-profile counterfactuals ("what if B had matched A's braking?") are
**UNSUPPORTED**: the deterministic simulator accepts lap-time scenarios only.
The gate travels in the fusion output; no prose-simulated physics.

## 9. Reproducibility

Same canonical DB + same methodology version (`evidence_fusion_v1`) ⇒
byte-identical output (verified in-process, fresh subprocess, and through the
MCP server). Output hashes are the regression anchor; a changed hash means a
methodology or data change and must be justified, never silent.
