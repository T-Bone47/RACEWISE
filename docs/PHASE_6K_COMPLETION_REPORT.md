# PHASE 6K COMPLETION REPORT — PERFORMANCE REGIME & CHANGE-POINT INTELLIGENCE

## 1. Executive summary

Phase 6K adds deterministic temporal regime detection over the Phase 6E comparable-lap
delta series, reusing every existing analytical layer (6E clean-lap rules, 6F evidence
fusion, 6G OLS trend semantics, 6H timeline/context queries, 6I/6J speed-profile model).
Change-point detection is deterministic top-down slope segmentation with explicit
thresholds, minimum regime length, recorded rejections and merges. Per-regime hypothesis
evolution, residual tracking, and model sensitivity keep every epistemic layer separate.
A change is reported as measured temporal structure — never as a cause.

## 2. Phase 6J baseline

| Metric | Value |
|---|---|
| Tests | 420 passing |
| Telemetry | 93 sessions / 787,555 rows |
| Database | 405,188,608 bytes (405.2 MB) |
| MCP tools | 34 |
| Status | READY_FOR_PERFORMANCE_SCENARIO_ANALYSIS |

## 3. What was built

- `src/racewise/data/historical/performance_regimes.py` — regime core: feature series,
  top-down slope segmentation (SSE-improvement gate, `MIN_REGIME_LAPS=3`,
  significance 0.03 s/lap, split threshold 0.06 s/lap), rejection/merge logs, typed
  change-point and context-transition vocabularies, per-regime hypothesis evolution /
  residual / model sensitivity, timeline synthesis, cross-race comparison.
- `performance_envelope.py` (6J): backwards-compatible `laps` parameter so regime
  sensitivity sweeps exact regime lap sets through the identical 6I model.
- MCP `analyze_historical_performance_regimes` (34 → 35 tools) with explicit bounds
  and boundary-enforced distinct drivers.
- `GET /api/catalog/performance-regimes/{season}/{round}`.
- `PerformanceRegimeView.tsx` (render-only) + timeline styles.
- Q13 benchmark suite (`q13_benchmarks.py`) + `tests/unit/test_performance_regimes.py`
  + `tests/unit/test_q13_benchmarks.py`.

## 4. Change-point method and thresholds

| Threshold | Value |
|---|---|
| Split statistic | \|right OLS slope − left OLS slope\| |
| Split acceptance | ≥ 0.06 s/lap |
| Per-side slope significance | ≥ 0.03 s/lap (Phase 6G) |
| Minimum regime length | 3 laps |
| Additional gates | SSE improvement; deterministic near-slope merging |

Rejected change points and merges are recorded, never silently discarded.

## 5. Q13 results (measured)

Matrix over 2023 R1, 2022 R4, 2024 R14, 2025 R12 — all `VALID`, 8 regimes per race,
7 transitions each. Hypothesis evolution tracked per regime per hypothesis; sequences
carry honest `INSUFFICIENT_EVIDENCE` starts and real transitions.

Negative controls (all expected):

| Control | Result |
|---|---|
| 1950 | UNAVAILABLE |
| 2018 (regimes computed, telemetry absent) | VALID, all regimes TELEMETRY_UNAVAILABLE |
| missing driver | UNAVAILABLE |
| same driver | UNAVAILABLE |
| max_regimes out of bounds | INVALID (ToolError at boundary) |
| min_regime_laps changed / start > end | INVALID |
| tiny lap window | INSUFFICIENT_EVIDENCE |
| no-telemetry pair | VALID with all regimes TELEMETRY_UNAVAILABLE |
| MCP bound violations (max_regimes=99, min=4, start>end) | REJECTED: invalid_input |

## 6. Timeline example (2023 R1, VER vs PER)

- REGIME 1: laps 1–3, NARROWING (sensitivity INVALID: lap 1 outside clean comparable set — honest refusal)
- TELEMETRY_TRANSITION lap 2; REGIME 2: laps 4–10, STABLE, sensitivity f=0.5 → −1.402 s
- GAP_TREND_CHANGE lap 11; REGIME 3: laps 11–13, WIDENING, sensitivity −2.049 s
- PIT_TRANSITION lap 14; STINT_TRANSITION lap 15 (stint 1 → 2); REGIME 4: laps 16–21, NARROWING

Model sensitivity **changed between regimes** (−1.402 s → −2.049 s at the same
intervention). This is a model property, not a historical cause.

## 7. Determinism / replay

- Fresh subprocess ×2 identical: module hash `006096419fd917db` (post-provenance).
- MCP real-server repeat: envelope hash stable (`d4da3069b1b7040b…`); full envelope
  identical except the server's `duration_ms` timing field; module-level
  `output_hash` inside `output` matches the in-process value over the wire.
- Earlier hash discrepancy (`d9b67f9bb…`) fully explained: two different hash
  expressions over identical content (script hashed `json.dumps(..., sort_keys=True)`
  default separators; module uses compact separators). Content verified identical;
  also verified seed-independent under different `PYTHONHASHSEED` values.

## 8. Performance (measured)

| Operation | Result |
|---|---|
| Regime analysis (per race) | p50 0.95 s, max 0.99 s |
| Optimization provenance | profiled: ~12.5 s of ~21 s was per-lap weather re-querying; fixed with an invocation-scoped read-through memo (verified semantically transparent by output diff + hash) |
| vs Phase 6J | envelope 237 ms; sweep p50 214 ms |

## 9. Storage

Zero growth: DB size unchanged at 405,188,608 bytes; derived-on-read; full-table row
count 1,331,081 unchanged; integrity ok.

## 10. Security

Secret scan clean; MCP allow-list preserved; enum enforcement (6I) active; explicit
numeric bounds; distinct-driver enforcement at the boundary; unknown parameters
rejected; no eval/SQL/shell/filesystem; read-only data access.

## 11. No-fabrication audit

Searches for "caused the", "proves", confidence scores, "would have won", "optimal
regime", predicted outcomes, tyre-failure/driver-error/mechanical labels return only
negated context strings (e.g. the methodology's own "no causality, no confidence
scores"). Eight association/causality disclaimers present in the module; every result
traceable to canonical tables listed in the new `provenance` block (8 tables,
provider fastf1, reuse chain 6E/6F/6G/6J documented).

## 12. Tests

Full regression: **461 passed** (420 + 41 new: 6K unit + Q13 suite), zero failures.
41 Phase 6K tests re-verified after the provenance addition and performance fix.

## 13. Known limitations

- Change-point detection is gap-trend (lap-delta) based; `SPEED_PROFILE_CHANGE`,
  `ENVELOPE_CHANGE`, `RESIDUAL_CHANGE` are typed vocabulary with residual/telemetry
  features tracked per regime, but the primary segmentation signal is the delta slope.
- Sensitivity requires paired telemetry; regimes without it report
  `TELEMETRY_UNAVAILABLE` honestly (e.g. 2018: regimes computed, sensitivity
  unavailable everywhere).
- Temporal association between performance and context transitions is reported as
  such — no causal inference exists anywhere in the phase.
- Race-level telemetry extrapolation remains UNSUPPORTED (Phase 6I boundary intact).

## 14. Files changed

- `src/racewise/data/historical/performance_regimes.py` (new)
- `src/racewise/data/historical/performance_envelope.py` (`laps` parameter)
- `src/racewise/data/historical/q13_benchmarks.py` (new)
- `src/racewise/tools/historical.py` (35th tool)
- `src/racewise/api/app.py` (performance-regimes endpoint)
- `apps/web/src/PerformanceRegimeView.tsx` (new), `apps/web/src/App.tsx`, `apps/web/src/App.css`
- `tests/unit/test_performance_regimes.py`, `tests/unit/test_q13_benchmarks.py` (new)
- `docs/PHASE_6K_PERFORMANCE_REGIMES.md`, `docs/PHASE_6K_COMPLETION_REPORT.md` (new)

## 15. Verification commands

```
python -m pytest -q                                   # 461 passed
python -c "from racewise.data.historical.q13_benchmarks import run_q13; ..."
# MCP: src/racewise/mcp/server.py tools/list -> 35 tools
# API: GET /api/catalog/performance-regimes/2023/1
```

## 16. Final readiness

**PHASE 6K STATUS: READY_FOR_PERFORMANCE_REGIME_ANALYSIS**

All 44 checklist items verified; readiness not forced — every layer returns honest
states and the epistemic boundaries (change ≠ cause, association ≠ causation,
sensitivity ≠ history) are enforced in code, output language, and documentation.
