# PHASE 6M COMPLETION REPORT — CROSS-RACE HYPOTHESIS & EVIDENCE INTELLIGENCE

## 1. Executive Summary

Phase 6M aggregates the measured 6F/6G hypothesis evidence behind recurring
Phase 6L patterns into a deterministic, contradiction-preserving, provenance-
backed evidence intelligence layer. New module `performance_evidence.py`
consumes 6L patterns verbatim (no second engine), maps 6G regime-hypothesis
summaries deterministically into 6F states using the underlying lap-level
counts, aggregates across independent occurrences with documented rules,
preserves contradictions verbatim, keeps residuals unassigned and model
sensitivity model-scoped, and reports honest `INSUFFICIENT_EVIDENCE` /
`TELEMETRY_UNAVAILABLE` / `UNAVAILABLE` states everywhere evidence is absent.
Full regression: **554 passed**. MCP: **37 tools**. Zero storage growth.

## 2. Baseline

- Tests at phase start: 503 passing (6L final state)
- Telemetry: 93 sessions / 787,555 rows (unchanged)
- Database: 405,188,608 bytes (~405.2 MB, unchanged)
- MCP tools at phase start: 36 (historical registry: 21)

## 3. Implementation

Files added:
- `src/racewise/data/historical/performance_evidence.py` — 6M core
- `src/racewise/data/historical/q15_benchmarks.py` — Q15 benchmark suite
- `tests/unit/test_performance_evidence.py` — 44 tests
- `tests/unit/test_q15_benchmarks.py` — 7 tests
- `apps/web/src/PatternEvidenceView.tsx` — frontend view
- `docs/PHASE_6M_CROSS_RACE_EVIDENCE.md`, this report

Files modified:
- `src/racewise/data/historical/performance_patterns.py` — backwards-
  compatible `hypothesis_counts` on signatures/occurrences (Phase 6M
  extension, same precedent as 6L's additions to 6K)
- `src/racewise/tools/historical.py` — `AnalyzeCrossRacePatternEvidenceTool`
- `src/racewise/api/app.py` — `GET /api/catalog/performance-pattern-evidence`
- `apps/web/src/App.tsx` — view wiring
- `tests/unit/test_performance_regimes.py`,
  `tests/unit/test_performance_patterns.py`,
  `tests/unit/test_q14_benchmarks.py` — registry count 21 → 22 (as each
  prior phase did)

## 4. Hypothesis Evidence Profiles

Per pattern, per hypothesis (`H1_corner_speed`, `H2_throttle`,
`H3_braking`, `H4_tyre_state`, `H5_race_control`, `H6_drs`, always all six,
never collapsed or ranked): aggregate state, evidence consistency,
supporting/contradicting/not-supported/not-testable/insufficient occurrence
refs, explicit coverage counts, independent race/circuit/season counts,
first/last occurrence.

## 5. Cross-Race Evidence Matrix

Rows = independent occurrences (season, round, regime index, lap range,
telemetry status, pair-inversion flag); columns = six hypotheses. Every cell
preserves mapped state + underlying 6G summary + lap-level counts.

## 6. Evidence Consistency

Deterministic mapping (methodology doc §4) + aggregation rules (§5).
CONSISTENT / VARIABLE / CONTRADICTORY / UNRESOLVED derived from aggregate
states; no percentages, no scores.

## 7. Falsification

`FALSIFICATION_PRESENT` / `NO_FALSIFICATION_FOUND` (explicitly not
confirmation) / `FALSIFICATION_NOT_TESTABLE` / `INSUFFICIENT_EVIDENCE` per
hypothesis with refs; pattern-level `cross_race_falsification_check`
(CONSISTENT_SUPPORT / MIXED_SUPPORT / CONTRADICTED_BY_OCCURRENCE /
NOT_TESTABLE / INSUFFICIENT_EVIDENCE).

## 8. Context Conditioning

Facets: dry compounds, wet/intermediate compounds, pit overlap, race-control
overlap, telemetry availability — each recomputes per-hypothesis aggregates
within the facet. Associations only.

## 9. Residual Intelligence

RESIDUAL_STABLE (≤0.10 s spread, same sign), RESIDUAL_INCREASING/DECREASING
(OLS > 0.01 s/occurrence), RESIDUAL_REVERSAL (mixed signs, spread > 0.10 s),
RESIDUAL_UNRESOLVED, INSUFFICIENT_EVIDENCE. Never assigned; the note
"reported, never assigned" is emitted in every result.

## 10. Model Sensitivity

6I/6J intervention (DEFICIT_REDUCTION, f=0.5) per occurrence as recorded by
6L; VALID requires ≥2 telemetry-supported occurrences, else
INSUFFICIENT_EVIDENCE / TELEMETRY_UNAVAILABLE. Reported as a model property.

## 11. Evidence-vs-Sensitivity

Per-hypothesis alignment states: CONSISTENT_EVIDENCE_AND_MODEL_RESPONSE /
CONSISTENT_EVIDENCE_DIVERGENT_MODEL_RESPONSE /
VARIABLE_EVIDENCE_AND_MODEL_RESPONSE / EVIDENCE_ONLY / BOTH_UNAVAILABLE.

## 12. Q15 Results

Suite: `q15_benchmarks.py` (measured 2026-09-25, canonical DB 405,188,608 B).

- **ver_per_2022_2023** (11 patterns): most_informative
  `9297e804eb9753f2` — MOSTLY_SUPPORTED (H1/H3/H6), VARIABLE (H2/H4),
  CONSISTENTLY_NOT_SUPPORTED (H5), check MIXED_SUPPORT, residual STABLE,
  sens INSUFFICIENT, hash `5c67c0e3e519ae0b`; most_contradictory
  `d860774091a4e6b0` — CONTRADICTORY (H1/H2/H6), CONSISTENTLY_NOT_SUPPORTED
  (H3/H4/H5), check CONTRADICTED_BY_OCCURRENCE, residual STABLE, sens
  TELEMETRY_UNAVAILABLE, hash `6eaf2b0d40b90b29`; telemetry_poor
  `3082b650453bb3e8` — all INSUFFICIENT, hash `0efa0e441059ab68`.
- **ver_per_2023_2024** (16 patterns): most_informative `319076b6a0143dd1` —
  VARIABLE (5 hypotheses), RESIDUAL_INCREASING, sens VALID spread 1.2988 s,
  hash `22f1a0ab9a48d4b2`; most_contradictory `9d4ee02d2ed62a83` — all
  CONSISTENTLY_NOT_SUPPORTED, RESIDUAL_DECREASING, sens VALID spread 3.1522 s,
  hash `a7882928c0b76573`; telemetry_poor `451c808f794bfa82` all INSUFFICIENT,
  hash `80c1e8afe1011daf`.
- **ham_pia_2024_2025**: single evidence-poor pattern pool — all roles
  honestly resolve to all-INSUFFICIENT (`74110f8c25e1138a`,
  hash `2efb1b1edfb2e8df`); absence preserved, never manufactured.
- **nor_pia_2025** (evidence-rich): most_informative `df11eff2b3854a84` —
  MOSTLY_SUPPORTED/VARIABLE/CONSISTENTLY_NOT_SUPPORTED mix, sens VALID,
  hash `c4f76062db998f66`; most_contradictory `48baee49b1e0c336` — all
  CONSISTENTLY_NOT_SUPPORTED, RESIDUAL_INCREASING, sens VALID,
  hash `359f7010c8a04772`; telemetry_poor `83dd98d5b318a1e9` all INSUFFICIENT,
  hash `09034815fd21971b`.

All 12 investigations VALID, all replays hash-identical, provenance chains
end in `6M`.

## 13. Negative Controls

- same driver → INVALID (before any scan)
- max_occurrences 0 / 9 → INVALID (before any scan)
- max_races 0 / 21 → INVALID
- missing pattern_id → UNAVAILABLE (live test)
- non-recurring pattern → INSUFFICIENT_EVIDENCE (defensive branch, tested)
- 1950 scope → UNAVAILABLE with `phase_6l_status` propagated (live test)
- MCP boundary: same-driver, bound overflow, unknown param, malformed list,
  empty pattern_id → ToolError `invalid_input`; wire rejection delivered
  in-envelope (`ok:false, error.code:invalid_input`)
- API: missing pattern_id / bound overflow / same driver / malformed seasons
  → 422

## 14. Determinism

- Module hash stable across in-process repeat (Q15 replay_identical true for
  all 12 investigations)
- Fresh-subprocess replay under PYTHONHASHSEED=3 vs 29: identical
  (live test)
- MCP: two real-server tools/call responses byte-identical except
  `duration_ms`; module hash `6eaf2b0d40b90b29` matches over the wire
- API: repeat GET byte-identical

## 15. Performance

Measured (warm, canonical DB): 6L pattern scan at max_races=8: 8.91 s;
6M evidence investigation incl. its own 6L scan: 9.22 s → **6M aggregation
overhead ~3%** of an inherently derived-on-read 6L corpus scan (6K regime
analysis dominates). Cost is bounded by max_races/max_occurrences; the
invocation-scoped read memo from Phase 6K keeps repeated canonical reads off
the database.

## 16. Storage

Zero growth: 405,188,608 bytes before and after; derived-on-read; no new
tables; `PRAGMA integrity_check` = ok; `foreign_key_check` clean.

## 17. Security

No eval/exec/shell/arbitrary SQL/user expressions/filesystem access in any
new file; no secrets; MCP allow-list preserved (closed schemas, unknown
parameters rejected); DB opened read-only; bounded inputs
(max_occurrences ≤ 8, max_races ≤ 20) with boundary re-validation at the
tool layer.

## 18. No-Fabrication Audit

Repository-level scans over all new code and frontend for caused/proves/
confidence/optimal/prediction/etc.: only two matches, both negation
disclaimers ("no confidence", "not confidence scores"). Generated output
contains no causal, ranking, confidence, or predictive language; the
epistemic-boundaries block is emitted in every VALID result.

## 19. Tests

- New: 44 (`test_performance_evidence.py`) + 7 (`test_q15_benchmarks.py`)
- Full regression: **554 passed, 0 failed** (`pytest -q`, 10:03)
- Stale registry-count assertions updated: 21 → 22 in three prior-phase
  test files (same practice as every prior phase)

## 20. Known Limitations

- Regime-level hypothesis evidence is sparse: 6G summaries need ≥2 evaluable
  laps and regime lap sets are small, so many cells are honestly
  INSUFFICIENT_EVIDENCE (e.g. ham_pia_2024_2025 yielded an evidence-poor
  pool; that absence is reported, not filled).
- Underlying evidence is 6G regime summaries + counts, not per-lap evidence
  references; per-occurrence provenance points at the 6K regime hash for
  full traceability.
- `NO_FALSIFICATION_FOUND` is scope-limited absence of contradiction, not
  confirmation (stated in output).
- Pattern ids are 6L corpus-scope-dependent; callers must browse and
  investigate at the same `max_races`.
- Corpus bounded to telemetry-capable sessions (93); pre-2018 scopes return
  UNAVAILABLE.

## 21. Files Changed

See §3. Diff stats at commit time (see verification commands).

## 22. Verification Commands

```
python -m pytest -q                       # 554 passed
python -m pytest tests/unit/test_performance_evidence.py tests/unit/test_q15_benchmarks.py -q
python -c "import sys; sys.path.insert(0,'src'); \
  from racewise.data.historical.canonical_queries import get_canonical_queries; \
  from racewise.data.historical.q15_benchmarks import run_q15; \
  print(run_q15(get_canonical_queries())['benchmark'])"
stat -c %s data/canonical/canonical.db    # 405188608 (unchanged)
cd apps/web && npm run build
```

## 23. Final Readiness

PHASE 6M STATUS: READY_FOR_CROSS_RACE_EVIDENCE_ANALYSIS

All readiness-gate items verified: 6L integration, exact 6F vocabulary,
evidence matrix, deterministic aggregation, contradiction preservation,
falsification, context associations, residuals never assigned, model
sensitivity model-scoped, telemetry limitations preserved, explicit coverage,
complete provenance, deterministic output hash, subprocess + seed
independence, MCP contract, API, frontend, negative controls, contradiction
regression, no-fabrication audit, security audit, zero storage growth,
performance measured, Q15 complete, 554/554 tests, documentation complete.
