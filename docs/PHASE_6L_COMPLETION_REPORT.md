# PHASE 6L COMPLETION REPORT — CROSS-RACE PERFORMANCE PATTERN INTELLIGENCE

## 1. Executive Summary

Phase 6L turns independently verified Phase 6K race-level regimes into
deterministic, provenance-backed cross-race comparative intelligence. Regimes
are summarized into measured signatures, grouped by coarse canonical
structural keys, refined by an explicit component-distance matcher
(seed-anchored, threshold-based, no ML), and reported as `RECURRING` only
when observed in ≥ 2 independent race instances. Every pattern carries
occurrence facets, context associations (never causes), per-hypothesis
consistency (6F vocabulary), a falsification summary (contradictions
preserved), residual pattern states (never assigned), model-sensitivity
comparison (same intervention, model-scoped) and full provenance back to
the 6K regime hashes. Zero storage growth; byte-deterministic.

## 2. Baseline

| Metric | Value |
|---|---|
| Tests (start of 6L) | 461 passing |
| Telemetry | 93 sessions, 787,555 rows |
| Database | 405,188,608 bytes (~405.2 MB) |
| MCP tools | 35 (34 historical-domain incl. 6K + session tools) |
| Phase 6L addition | 1 new MCP tool → 36 total |

## 3. Implementation

**Added**
- `src/racewise/data/historical/performance_patterns.py` — the 6L core
  (signatures, comparability contract, matching, recurrence, aggregations,
  main analysis).
- `src/racewise/data/historical/q14_benchmarks.py` — Q14 matrix, negative
  controls, MCP verification.
- `tests/unit/test_performance_patterns.py` (33 tests),
  `tests/unit/test_q14_benchmarks.py` (9 tests).
- `docs/PHASE_6L_CROSS_RACE_PATTERNS.md`, this report.
- `apps/web/src/PerformancePatternView.tsx` — render-only frontend.

**Modified (additive / backwards-compatible)**
- `src/racewise/data/historical/performance_regimes.py` — per-regime
  `delta_series` + `band_width_mean_kmh` in sensitivity (6L consumption).
- `src/racewise/tools/historical.py` — `AnalyzeCrossRacePerformancePatternsTool`
  + registry entry (34 → 35 historical-domain tools).
- `src/racewise/api/app.py` — `GET /api/catalog/performance-patterns`.
- `apps/web/src/App.tsx` — view wiring.
- `tests/unit/test_performance_regimes.py` — registry count 20 → 21 (the 6L
  tool; same stale-assertion pattern each phase updates).

## 4. Regime Signature

Measured features only (§4 of the methodology doc). Query-order pair
semantics with deterministic, provenance-flagged inversion (signed quantities
negated). Normalized shape = regime-relative progress, 8-point linear
resample strictly inside the measured lap span; absolute laps preserved.

## 5. Comparability Engine

Six dimensions × explicit states + reasons; overall = weakest dimension.
`NOT_COMPARABLE` (different canonical pair) blocks matching entirely;
partial states (e.g. telemetry missing in one regime) degrade honestly to
`PARTIALLY_COMPARABLE` while still scoring the shared components.

## 6. Pattern Matching Method

Per-component measured distances + weighted score (weights slope 1 / trend 2 /
duration 1 / residual 1 / envelope 1 / sensitivity 1; missing measurement
scores 0 but still counts as achievable). Thresholds: slope-difference 0.30
s/lap (two-slope comparison tolerance; single-slope significance stays at 6G's
0.03), duration ±2 laps or ratio ≥ 0.5, residual mean 0.25 s, envelope width
35 %, sensitivity 0.5 s. States: STRONGLY (≥ 1.0) / MATCHING (≥ 0.75) /
PARTIALLY (≥ 0.5) / NON_MATCHING (< 0.5) / INSUFFICIENT (< 3 components).

## 7. Recurrence Detection

Coarse canonical structural key (trend, slope state, duration bucket,
residual state, telemetry status) → `sha256[:16]` `pattern_signature_id`;
seed-anchored deterministic splitting inside each group (join requires
explicit match ≥ PARTIALLY_MATCHING_STRUCTURE; new seeds logged in
`pattern_split_log`); `RECURRING` only at ≥ 2 independent races; single-race
member sets counted as non-recurring and never reported.

## 8. Context Conditioning

Facets only: dry/wet/multi-compound laps, pit overlap, race-control overlap —
counts + race lists, association language throughout. No facet is ever
labeled causal.

## 9. Hypothesis Comparison

All six hypotheses aggregated per pattern with deterministic consistency
states (CONSISTENT / VARIABLE / CONTRADICTORY / INSUFFICIENT_EVIDENCE) and
per-occurrence `race_regime_refs`. Never collapsed into a race-level label.

## 10. Falsification

`supporting_refs` / `contradicting_refs` / `not_testable_refs` with
per-regime provenance; contradictions preserved verbatim; a recurring
structure never rehabilitates a contradicted hypothesis.

## 11. Residual Intelligence

Pattern states RESIDUAL_STABLE / INCREASING / DECREASING / REVERSAL /
UNRESOLVED / INSUFFICIENT from per-occurrence 6E-conservation states.
Residual recurrence is an analytical observation, not a mechanism; never
assigned to a hypothesis.

## 12. Sensitivity Comparison

Same intervention (DEFICIT_REDUCTION f=0.5) per regime telemetry laps through
the 6I/6J model; per-occurrence deltas, spread, and an explicit note that a
sensitivity difference is a model property, not historical causation.

## 13. Q14 Results (measured)

All four matrix cases VALID, hash-identical replays:

| Case | Corpus | Signatures → groups | Patterns | Repeat types | Sensitivity states | Hash |
|---|---|---|---|---|---|---|
| VER vs PER 2022–23 | 6/6 | 48 → 16 | 6 | CROSS_CIRCUIT_REPEAT | INSUFFICIENT | `6fcf0ca9f6fd4bf3` |
| VER vs PER 2023–24 | 6/6 | 48 → 17 | 14 | CROSS_CIRCUIT_REPEAT | MEASURED + INSUFFICIENT | `1de39f937491f3d5` |
| HAM vs PIA 2024–25 | 6/6 | 43 → 7 | 6 | CROSS_CIRCUIT_REPEAT | INSUFFICIENT | `b62758217bd8536c` |
| NOR vs PIA 2025 | 6/6 | 48 → 17 | 7 | CROSS_CIRCUIT_REPEAT | MEASURED + INSUFFICIENT | `0d389ce5de163ab6` |

Worked example (VER/PER 2023, first pattern `0d47f1401e19d9be`, coarse key
WIDENING/POSITIVE/2-3/RESIDUAL_UNRESOLVED/AVAILABLE): 3 occurrences across
Bahrain R1 laps 11–13 (slope +0.044), Jeddah R2 laps 48–50 (+1.1585), Baku R4
laps 38–40 (+0.1905); measured sensitivity −2.0486 / −0.4695 / −1.526 s
(spread 1.5791 s) — reported as a model property, explicitly not historical
causation; seed-vs-member matches PARTIALLY_MATCHING (0.571, 0.714);
hypotheses INSUFFICIENT at this evidence depth; facets: dry-compound laps.

## 14. Negative Controls

| Control | Result |
|---|---|
| same driver | INVALID |
| 1950 scope (no telemetry sessions) | UNAVAILABLE |
| 2018 scope (no telemetry sessions) | UNAVAILABLE |
| pair absent from corpus | UNAVAILABLE |
| max_races 21 / 0 | INVALID |
| max_patterns 51 | INVALID |
| single-race corpus (rounds filter) | INSUFFICIENT_EVIDENCE |
| tool: seasons not a list / rounds not ints / empty circuit / unknown param | ToolError `invalid_input` |

## 15. Determinism

- In-process repeat: identical.
- Fresh subprocess ×2 under `PYTHONHASHSEED` 0 and 7: **byte-identical
  content**, hash `6fc5e3be63d8cfb9` (2023 VER/PER probe).
- MCP `tools/call` repeat over the real server: `output` identical, module
  hash matches over the wire, envelope hash stable.
- API repeat: byte-identical response body.
- No timestamps in any hash; `provenance.generated_at` is always null.

## 16. Performance

| Corpus | Elapsed | Patterns |
|---|---|---|
| 2 races | 2.44 s | 3 |
| 4 races | 5.32 s | 5 |
| 6 races | 9.56 s | 6 |

~1.6 s/race, dominated by per-race 6K regime analysis (memoized per
race+canonical-pair within an invocation). MCP wire round-trip for a 4-race
corpus: 13.5 s including server startup. No N×connection patterns; the
existing 6K read memo does the heavy lifting.

## 17. Storage

Derived-on-read; **zero growth**: DB size, mtime and row counts unchanged;
`PRAGMA integrity_check` = ok; `PRAGMA foreign_key_check` = 0 violations;
405,188,608 bytes before and after.

## 18. Security

Typed parameters; explicit numeric bounds re-validated at the tool boundary
(schema `minimum`/`maximum` are not trusted alone); closed input schema with
unknown-parameter rejection (verified through the contract layer); distinct-
driver enforcement; read-only DB; no eval/exec/shell/SQL-from-input/
filesystem/secrets (scans clean); payload size limits enforced by the
existing contract layer.

## 19. No-Fabrication Audit

Repository-level scans over all new code, docs and frontend for "caused the",
"would have won", "likely winner", "best/worst race", "optimal",
"guaranteed", "confidence score": **clean** — the only matches anywhere are
negated disclaimers ("no confidence scores, no rankings, no causality").
Frontend renders states and associations only; no ranking visuals.

## 20. Tests

| Suite | Count | Result |
|---|---|---|
| Phase 6L unit (`test_performance_patterns.py`) | 33 | pass |
| Phase 6L Q14 (`test_q14_benchmarks.py`) | 9 | pass |
| Full regression | **503** | pass (461 + 42 new) |

The one pre-existing failure during development was 6K's stale registry-count
assertion (20 → 21 after the 6L tool), updated with a phase note as in prior
phases. No existing test was weakened.

## 21. Known Limitations

1. Recurrence is repetition, not significance: two occurrences is an
   observation, never a statistical claim (stated in every output).
2. Coarse structural keys intentionally ignore continuous differences; the
   seed-vs-member matrix preserves them, but a pattern's occurrences can
   span PARTIALLY_MATCHING structures.
3. Sensitivity comparison needs ≥ 2 telemetry-supported regimes; 2022-era
   VER/PER races without paired telemetry produce honestly INSUFFICIENT
   sensitivity summaries.
4. Corpus bounded to telemetry-capable race sessions (catalog `capability`
   filter) and `max_races ≤ 20`; unbounded cross-history scans are refused.
5. Race-level telemetry extrapolation remains UNSUPPORTED (6I boundary).

## 22. Files Changed

See §3. New: 5 files. Modified: 5 files. Zero storage schema changes.

## 23. Verification Commands

```
python -m pytest tests/unit/test_performance_patterns.py tests/unit/test_q14_benchmarks.py -q
python -m pytest -q                       # full regression (503)
python -m racewise.data.historical.q14_benchmarks   # full Q14 matrix (docs measurement)
```

MCP wire probes (tools/list count, tools/call repeat, bound violations) were
executed against the real server subprocess exactly as
`tests/integration/test_historical_tools_mcp.py` does.

## 24. Final Readiness

All §35 gates verified: 6K integration, deterministic signatures,
comparability contract, deterministic matching, recurrence detection, context
associations, hypothesis evolution, falsification, unassigned residuals,
model-scoped sensitivity, telemetry limitations, provenance, output-hash +
subprocess + seed determinism, MCP/API/frontend contracts, negative controls,
no-fabrication audit, security audit, zero storage growth, performance
benchmark, Q14, full regression, documentation.

**PHASE 6L STATUS: READY_FOR_CROSS_RACE_PATTERN_ANALYSIS**
