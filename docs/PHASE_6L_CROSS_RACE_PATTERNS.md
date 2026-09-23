# PHASE 6L — CROSS-RACE PERFORMANCE PATTERN INTELLIGENCE

Methodology reference for `analyze_cross_race_performance_patterns` (MCP) and
`GET /api/catalog/performance-patterns`. Companion evidence document:
`PHASE_6L_COMPLETION_REPORT.md`.

## 1. Motivation

Phase 6K answers *when* measured performance regimes changed within a race.
Phase 6L answers the natural follow-up: **do comparable regime structures
recur across independent races, and what evidence accompanies those recurring
patterns?** It is a comparative-organization layer over the verified
6E → 6K chain — not a clustering system, not a ranking system, not a
predictive model, and not a causal-inference engine.

## 2. Relationship to 6K (and the rest of the chain)

`performance_patterns.py` consumes `analyze_performance_regimes` output
**verbatim** — no second resampler, no second segmenter, no second evidence
model. The full reuse chain:

| Layer | Reused from | Role in 6L |
|---|---|---|
| Comparable-lap selection, context exclusions | 6E | regime laps are 6E-clean by construction |
| Hypothesis states (six hypotheses, 6F vocabulary) | 6F | per-regime evolution, aggregated per pattern |
| OLS trend / minimum observations | 6G | slope semantics and thresholds inherited |
| Race/pair validation | 6H | entry semantics mirrored |
| Exact quadrature lap-time model | 6I | sensitivity flows through the validated model |
| Scenario sweep (typed, bounded) | 6J | DEFICIT_REDUCTION f=0.5 per regime lap set |
| Regime segmentation + per-regime features | 6K | the substrate of every signature |

Two backwards-compatible 6K extensions were added (both additive):
`delta_series` per regime (the comparable-lap `(lap, delta)` series) and
`band_width_mean_kmh` inside the regime sensitivity block.

## 3. RegimeSignature

Every eligible 6K regime becomes a signature containing **only measured or
derived features**: race identity (season/round/race_id/circuit), the query's
ordered driver pair (plus `canonical_pair` and an explicit
`pair_inverted_vs_canonical` flag), `start_lap`/`end_lap`/`lap_count`,
`trend_classification`, `slope_s_per_lap`, `residual_state`
(6E `PRESERVED` → 6L `RESIDUAL_UNRESOLVED`), `residual_mean_s`,
`envelope_width_mean_kmh`, model sensitivity (status/delta/fraction),
`telemetry_status` + lap count, `compound_summary`, stint/pit/race-control
overlap, the raw `delta_series`, a normalized shape, the six-hypothesis state
summary and evidence coverage.

**Normalization.** The normalized shape maps the regime's measured laps onto
regime-relative progress `x = (lap − first)/(last − first)` with values =
observed deltas, resampled by linear interpolation onto an 8-point grid —
strictly inside the measured lap span (endpoints clamp to *measured* values,
never fabricated). Absolute lap numbers are preserved alongside.

**Driver-pair semantics.** `delta = driver_a − driver_b`. 6K always runs the
canonical (sorted) pair; when the query's order is inverted relative to
canonical, 6L deterministically negates signed quantities (slope, residual
mean, sensitivity delta, delta series, trajectory) and flags
`pair_inverted_vs_canonical = true` in the signature and provenance. Pairs are
never silently reordered.

## 4. Comparability contract

Six dimensions, each with an explicit state (`COMPARABLE`,
`PARTIALLY_COMPARABLE`, `NOT_COMPARABLE`, `INSUFFICIENT_EVIDENCE`) and reason:
DRIVER_PAIR (identical canonical pair required), SESSION_TYPE (6K race
sessions), LAP_DATA (both carry measured deltas),
TELEMETRY (both available / both missing / one missing →
`PARTIALLY_COMPARABLE`), CONTEXT (compound-set equality → else
`PARTIALLY_COMPARABLE`), EVIDENCE (both carry hypothesis summaries). Overall =
weakest dimension. Failed dimensions are never silently dropped.

## 5. Pattern matching mathematics

Per pair of signatures, `_component_scores` emits every measured distance:
`slope_delta_s_per_lap`, `trend_match` (same sign), `duration_delta_laps` /
`duration_ratio`, `residual_distance_s` (mean per-lap residual difference),
`envelope_distance_rel` (relative band-width difference),
`sensitivity_delta_s`, plus context and hypothesis overlaps.

The weighted score is the achieved fraction of achievable weight (weights:
slope 1.0, trend 2.0, duration 1.0, residual 1.0, envelope 1.0, sensitivity
1.0); a missing measurement scores 0 and still counts as achievable —
a missing measurement is not a match. **Thresholds** (documented constants):
slope-difference tolerance 0.30 s/lap (rationale: 6G's 0.03 s/lap is the
significance threshold for *one* OLS slope; comparing two independently
estimated slopes needs a wider, documented difference tolerance), duration
within ±2 laps or ratio ≥ 0.5, residual mean within 0.25 s, envelope width
within 35 %, sensitivity within 0.5 s.

Classification (`_structure_state_from_score`), deterministic: score ≥ 1.0 →
`STRONGLY_MATCHING_STRUCTURE`; ≥ 0.75 → `MATCHING_STRUCTURE`; ≥ 0.5 →
`PARTIALLY_MATCHING_STRUCTURE`; else `NON_MATCHING_STRUCTURE`; fewer than 3
scored components → `INSUFFICIENT_EVIDENCE`. These are threshold
classifications, never confidence scores.

**Trajectory comparison.** Normalized shapes are compared by mean/max absolute
deviation when both regimes have ≥ 2 measured laps (`TRAJECTORY_COMPARABLE`),
else `TRAJECTORY_UNAVAILABLE` (no shape is fabricated).

## 6. Recurrence definition

Structural grouping uses a deliberately **coarse** canonical key
(trend classification, slope *state* NEAR_ZERO/POSITIVE/NEGATIVE vs the 6G
0.03 s/lap significance threshold, duration bucket 2-3/4-6/7-10/11+,
residual state, telemetry status) hashed by
`sha256(json.dumps(key, sort_keys=True, separators=(",", ":")))[:16]`.
Continuous measurements are deliberately *excluded* from the key — grouping
on them would fragment every pattern into singletons — and are instead
compared per occurrence with the explicit matcher above.

Within a coarse group, **deterministic seed-anchored splitting**: occurrences
are processed in (season, round, start_lap) order; an occurrence joins the
first seed whose explicit match is ≥ `PARTIALLY_MATCHING_STRUCTURE`, otherwise
it seeds a new pattern of the same coarse key (logged in
`pattern_split_log` — nothing is silently discarded). A pattern is reported
as `RECURRING` only when observed in ≥ `MIN_RECURRING_RACES = 2` independent
races; single-race member sets are counted in
`non_recurring_group_count` and never reported. Repeat types: `SAME_RACE`,
`CROSS_RACE`, `CROSS_SEASON`, `CROSS_CIRCUIT`. The output states
"Observed in N independent race instances" — never a significance claim.

## 7. Context handling

Context facets are **descriptive associations only**: `dry_compound_laps`,
`wet_or_intermediate_compound_laps`, `regime_spans_multiple_compounds`,
`regime_overlaps_pit_lap`, `regime_overlaps_restricted_laps` — each with
counts and race lists. Allowed: "the structure was measured on dry-compound
laps in these races." Forbidden: "different compounds caused the structure."

## 8. Hypothesis aggregation

Per hypothesis (all six, 6F vocabulary), statuses are collected per
occurrence with explicit `race_regime_refs`. Aggregation is deterministic:
all-informative-equal → `CONSISTENT`; a mix of SUPPORTED/NOT_SUPPORTED →
`VARIABLE`; SUPPORTED + CONTRADICTED → `CONTRADICTORY`; no informative
statuses → `INSUFFICIENT_EVIDENCE`. Race-level labels are never collapsed
into "the hypothesis explains the pattern."

## 9. Falsification

`pattern_falsification_summary` carries `supporting_refs`,
`contradicting_refs` and `not_testable_refs` with per-regime provenance.
Contradictions are preserved verbatim — a recurring structure never
rehabilitates a contradicted hypothesis.

## 10. Residual intelligence

Residuals remain first-class and never assigned to any hypothesis. Pattern
states (`RESIDUAL_STABLE`, `RESIDUAL_INCREASING`, `RESIDUAL_DECREASING`,
`RESIDUAL_REVERSAL`, `RESIDUAL_UNRESOLVED`, `INSUFFICIENT_EVIDENCE`) are
deterministic aggregations of per-occurrence residual states. Residual
recurrence is an analytical observation, not a mechanism.

## 11. Sensitivity handling

Per pattern, the same intervention (`DEFICIT_REDUCTION f=0.5` through the
6I/6J model on each regime's telemetry laps) is compared across occurrences:
values, spread, and the explicit note that this is a model property — not
historical causation, not "recoverable performance".

## 12. Determinism

- `pattern_signature_id` and `output_hash`: `sha256` over canonical JSON
  (sorted keys, compact separators, explicit float rounding); no timestamps,
  no runtime durations, no `hash()`, seed-independent.
- `provenance.generated_at` is always `null` and never enters any hash.
- Verified: in-process repeat, fresh subprocess ×2 under different
  `PYTHONHASHSEED` values, MCP repeat — **byte-identical content and hash**
  (`6fc5e3be63d8cfb9` for the 2023 VER/PER probe).

## 13. Provenance

Every pattern carries: structural key, source tables (9 canonical tables),
provider, analytical chain (6E…6K, 6L), method string, all thresholds, and
`source_regime_refs` (season, round, regime index, **the 6K race
`output_hash`**, race id) — every pattern is traceable to actual canonical
observations.

## 14. Performance

Derived-on-read with two invocation-scoped memos (6K analyses per
race+canonical-pair; the existing 6K read memo). Measured: 2-race corpus
2.44 s, 4-race 5.32 s, 6-race 9.56 s (~1.6 s/race, dominated by per-race 6K
regime analysis; the seed matcher itself is O(n) per group). No N×connection
patterns.

## 15. Security

Typed parameters only; explicit numeric bounds (max_races ≤ 20,
max_patterns ≤ 50) re-validated at the tool boundary; closed input schema
(unknown parameters rejected by the contract layer); distinct-driver
validation; read-only DB; no eval/exec/shell/SQL-from-input/filesystem; no
arbitrary expressions; bounded payload sizes enforced by the existing
contract layer.

## 16. Limitations

1. A recurring pattern is an observation of repetition across independent
   race instances — not causation, not mechanism, not significance.
2. Structural keys are coarse by design; measured differences between
   occurrences are preserved in the per-occurrence features and the
   seed-vs-member comparison matrix.
3. Occurrence laps are comparable-lap selections (6E context exclusions), not
   every race lap.
4. Sensitivity comparison requires ≥ 2 telemetry-supported regimes; missing
   telemetry stays missing (`TELEMETRY_UNAVAILABLE`).
5. Race-level telemetry extrapolation remains UNSUPPORTED (6I boundary,
   inherited).
6. No ranking, no "best/worst", no confidence scores — states are
   deterministic classifications.

## 17. Q14 benchmark

See `PHASE_6L_COMPLETION_REPORT.md` §13 for the measured matrix
(4 pair/season cases across 2022–2025, all VALID with hash-identical
replays) and §14 for the negative-control results.

## 18. Epistemic boundaries

    OBSERVED ≠ ENVELOPE ≠ OPTIMAL ≠ PREDICTION   (inherited from 6J)
    SIMILARITY ≠ CAUSALITY                        (6L)
    RECURRENCE ≠ MECHANISM                        (6L)
    TEMPORAL ALIGNMENT ≠ CAUSAL ATTRIBUTION       (6L)

Phase 6L organizes verified race-level regimes into comparative,
provenance-backed intelligence. It does not manufacture causality, does not
rank, and does not predict.
