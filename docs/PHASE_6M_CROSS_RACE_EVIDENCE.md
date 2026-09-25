# PHASE 6M — CROSS-RACE HYPOTHESIS & EVIDENCE INTELLIGENCE

Methodology reference for `analyze_cross_race_pattern_evidence` (MCP) and
`GET /api/catalog/performance-pattern-evidence`. Companion evidence document:
`PHASE_6M_COMPLETION_REPORT.md`.

## 1. Motivation

Phase 6L answers *whether* comparable regime structures recur across races.
Phase 6M answers the next engineering question: **when a pattern recurs, does
the measured evidence behind the six RACEWISE hypotheses stay consistent,
contradictory, variable, or unresolved across the independent occurrences?**

This reconnects the cross-race layer to the original investigation
architecture (QUESTION → HYPOTHESES → EVIDENCE → COMPARISON → FALSIFICATION)
without adding any analytical engine.

## 2. Relationship to prior phases

6M sits **above** 6L and consumes its recurring patterns verbatim. It creates
no second evidence-fusion engine (6F is reused through 6K/6G), no second
regime engine (6K), and no second pattern matcher (6L). Two backwards-
compatible extensions were made upstream, following the established
per-phase precedent (6L extended 6K the same way):

- `performance_patterns.py` signatures/occurrences now carry
  `hypothesis_counts` — the 6G summary's per-hypothesis lap-level counts
  (`regime_lap_statuses`, `supported_count`, `partially_supported_count`,
  `not_supported_count`, `contradicted_count`, `not_testable_count`,
  `valid_observations`). Without these, 6M could read only the summary label
  and contradictions inside `INTERMITTENTLY_SUPPORTED` regimes would be
  invisible — violating the contradiction-first requirement.

## 3. Hypothesis vocabulary

The six hypothesis IDs and statements are imported from 6F
(`evidence_fusion.HYPOTHESES`): `H1_corner_speed`, `H2_throttle`,
`H3_braking`, `H4_tyre_state`, `H5_race_control`, `H6_drs`. Underlying
occurrence states reuse the 6F vocabulary exactly: `SUPPORTED`,
`PARTIALLY_SUPPORTED`, `CONTRADICTED`, `NOT_SUPPORTED`, `NOT_TESTABLE`,
`INSUFFICIENT_EVIDENCE`.

## 4. 6G → 6F state mapping (deterministic)

Each 6K regime carries a 6G temporal summary per hypothesis. 6M maps summary
+ lap-level counts to a 6F state (`_map_hypothesis_state`):

| 6G summary | condition | 6F state |
|---|---|---|
| CONSISTENTLY_SUPPORTED, MOSTLY_SUPPORTED | — | SUPPORTED |
| INTERMITTENTLY_SUPPORTED | contradicted_count > 0 | CONTRADICTED |
| INTERMITTENTLY_SUPPORTED | otherwise | PARTIALLY_SUPPORTED |
| CONTRADICTED_OVER_TIME, NOT_SUPPORTED | — | NOT_SUPPORTED |
| NOT_TESTABLE | — | NOT_TESTABLE |
| INSUFFICIENT_EVIDENCE / None | observations ≤ 0 | INSUFFICIENT_EVIDENCE |
| INSUFFICIENT_EVIDENCE / None | support>0 and contradicted>0 | CONTRADICTED |
| INSUFFICIENT_EVIDENCE / None | support>0 | PARTIALLY_SUPPORTED |
| INSUFFICIENT_EVIDENCE / None | otherwise | NOT_SUPPORTED |

The count-derived rows mean a regime whose 6G summary is coarse still
contributes its actual observations; nothing is inferred beyond the counts.

## 5. Aggregation rules (documented, no percentages)

For one hypothesis across a pattern's occurrences, let S be the set of
informative mapped states (support-class = {SUPPORTED, PARTIALLY_SUPPORTED};
non-support-class = {NOT_SUPPORTED, CONTRADICTED}):

1. S empty → `INSUFFICIENT_EVIDENCE`
2. support present and CONTRADICTED present → `CONTRADICTORY`
3. support present and NOT_SUPPORTED present → `VARIABLE`
4. S == {SUPPORTED} → `CONSISTENTLY_SUPPORTED`
5. support-class mixture containing PARTIALLY_SUPPORTED → `MOSTLY_SUPPORTED`
6. only non-support states → `CONSISTENTLY_NOT_SUPPORTED`

`CONTRADICTORY` is deliberately a support-vs-contradiction *conflict* state
(Section 5 Case D of the spec). All-negative evidence (CONTRADICTED and/or
NOT_SUPPORTED, no support) is `CONSISTENTLY_NOT_SUPPORTED`; the underlying
contradiction remains visible per-occurrence in the profile's
`contradicting_occurrences` and the falsification block — it is preserved,
never averaged away, never converted into a score.

Evidence consistency per hypothesis: `CONSISTENT` /
`CONSISTENTLY_NOT_SUPPORTED→CONSISTENT`, `VARIABLE` (incl. MOSTLY_SUPPORTED),
`CONTRADICTORY`, `UNRESOLVED` (insufficient).

## 6. Cross-race evidence matrix

`evidence_matrix` has one row per independent occurrence (race, round,
regime index, lap range, telemetry status) and one column per hypothesis.
Every cell preserves the mapped state **and** the underlying 6G summary +
lap-level counts. Nothing is collapsed into prose.

## 7. Falsification

Per hypothesis: `FALSIFICATION_PRESENT` (≥1 contradicting occurrence),
`NO_FALSIFICATION_FOUND` (informative evidence, none contradicting —
explicitly *not* confirmation), `FALSIFICATION_NOT_TESTABLE`, or
`INSUFFICIENT_EVIDENCE`. Supporting/contradicting/not-testable/unavailable
refs are listed. The pattern-level `cross_race_falsification_check` compares
aggregate states across occurrences: `CONSISTENT_SUPPORT`, `MIXED_SUPPORT`,
`CONTRADICTED_BY_OCCURRENCE`, `NOT_TESTABLE`, `INSUFFICIENT_EVIDENCE` — a
comparison of evidence states, never a statistical test.

## 8. Context conditioning

Descriptive facets (dry / wet-or-intermediate compounds, pit overlap, race
control overlap, telemetry availability) recompute aggregate states within
each facet. Facets are associations; no facet is causal.

## 9. Residual handling

Race-ordered residual means across occurrences are classified:
`RESIDUAL_INCREASING`/`RESIDUAL_DECREASING` (OLS slope vs occurrence order,
|slope| > 0.01 s/occurrence), `RESIDUAL_REVERSAL` (mixed signs with spread >
0.10 s), `RESIDUAL_STABLE` (same sign, spread ≤ 0.10 s), `RESIDUAL_UNRESOLVED`
(measured but not characterizable), `INSUFFICIENT_EVIDENCE` (no measured
values). Residual is an unresolved component — never assigned to any
hypothesis, mechanism, or cause.

## 10. Model-sensitivity handling

Reuses the 6I/6J intervention (DEFICIT_REDUCTION, f=0.5) as recorded per
occurrence by 6L. Status `VALID` requires ≥ 2 telemetry-supported
occurrences; otherwise `INSUFFICIENT_EVIDENCE` or `TELEMETRY_UNAVAILABLE`.
`evidence_vs_sensitivity` aligns evidence states with model response per
hypothesis (`CONSISTENT_EVIDENCE_AND_MODEL_RESPONSE`,
`CONSISTENT_EVIDENCE_DIVERGENT_MODEL_RESPONSE`,
`VARIABLE_EVIDENCE_AND_MODEL_RESPONSE`, `EVIDENCE_ONLY`, `BOTH_UNAVAILABLE`).
Sensitivity is a model property, never a historical effect.

## 11. Contract and bounds

- Inputs: `driver_a`, `driver_b` (distinct), `pattern_id`, optional
  `seasons`/`rounds`/`circuit`, `max_occurrences` ∈ [1, 8] (default 8),
  `max_races` ∈ [1, 20] (default 8).
- `max_races` must match the 6L browsing scope: pattern ids are
  corpus-scope-dependent in 6L (structural groups form within the analyzed
  corpus), so 6M passes the caller's scope through instead of rescanning at a
  different width.
- `max_hypotheses` is deliberately not offered: bounding the hypothesis set
  could only hide evidence.
- Unknown parameters, malformed enums/lists and bound violations are rejected
  at the module boundary and again at the MCP tool boundary (closed schemas).

## 12. Determinism

`output_hash` = 16-hex sha256 over canonical JSON (sorted keys, compact
separators, `default=str`) of the entire result minus `output_hash` itself.
The payload contains no timestamps (`generated_at: null`), no durations, no
process metadata. Verified: in-process repeat, fresh-subprocess replay under
different `PYTHONHASHSEED` values, MCP repeated call, API byte-identical
repeat (all measured; see completion report).

## 13. Provenance

Every investigation carries the full analytical chain
`6E → 6F → 6G → 6H → 6I → 6J → 6K → 6L → 6M`, the 6L pattern provenance
(source regime refs per occurrence, source tables, provider), the state-
mapping version and the aggregation-rule reference. Occurrence refs preserve
`pair_inverted_vs_canonical` so inverted-pair sign conventions remain
auditable.

## 14. Epistemic boundaries (architectural invariants)

OBSERVED ≠ MODELLED · SUPPORT ≠ PROOF · MODEL SENSITIVITY ≠ HISTORICAL
CAUSATION · NO_FALSIFICATION_FOUND ≠ CONFIRMED · SIMILARITY ≠ CAUSALITY ·
RECURRENCE ≠ MECHANISM · TEMPORAL_ALIGNMENT ≠ CAUSAL_ATTRIBUTION ·
INSUFFICIENT_EVIDENCE ≠ NOT_SUPPORTED · NOT_TESTABLE ≠ CONTRADICTED ·
MISSING_DATA ≠ NEGATIVE_EVIDENCE

These are emitted verbatim in every `VALID` result (`epistemic_boundaries`)
and enforced in code: residuals carry `never assigned` notes, falsification
carries `not confirmation` notes, sensitivity carries `not a historical
effect` notes.
