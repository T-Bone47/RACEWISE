# PHASE 6I COMPLETION REPORT — VALIDATED TELEMETRY COUNTERFACTUALS

## 1. Executive summary

Phase 6I closes the documented limitation left open by Phases 6E–6H —
*"telemetry-profile counterfactuals remain UNSUPPORTED"* — **only where science
allows**. The existing strategy simulator still does not consume telemetry (that
gate is preserved, verbatim as a scoped statement). What 6I adds is the smallest
defensible bridge: Phase 6E's speed-trace region model, generalized to its exact
non-linearized form (fixed-distance segment integration with exact piecewise-linear
quadrature), driven by bounded mathematical interventions with six validation gates,
exact baseline reproduction, and a hard epistemic contract: the output is a **model
sensitivity**, never history, prediction, or causality.

Non-speed signals (throttle, brake, gear, RPM, DRS) return `UNSUPPORTED` — no
physics mapping exists in the codebase and none was invented. Race-level telemetry
counterfactuals remain unavailable by design (telemetry coverage is bounded; no
extrapolation across non-comparable intervals).

## 2. Starting baseline (Phase 6H, verified)

| Metric | Value |
|---|---|
| Tests | 346 passing (suite re-run at session start: 346 passed in 5:33) |
| Telemetry | 93 sessions / 787,555 rows |
| Database | 405.2 MB |
| MCP tools | 32 |
| 6H status | READY_WITH_DOCUMENTED_LIMITATIONS |
| Pre-existing uncommitted work | preserved untouched (engine.py, schemas.py, etc.) |

## 3. Simulator audit

- `simulate_pit_timing(laps, driver, original_pit_lap, counterfactual_pit_lap, *,
  pit_loss_s, degradation_s_per_lap, laps_remaining, traffic_assumption_s_per_lap)`
  — consumes **lap times only**. Verified by source inspection
  (`src/racewise/simulator/strategy.py`).
- `simulate_compound_change`, `compare_strategy_scenarios` — same contract.
- No sector-level or telemetry-level inputs anywhere in the simulator.
- Decision (documented in `docs/PHASE_6I_TELEMETRY_COUNTERFACTUALS.md` §1–2): do NOT
  fake an adapter; build the bridge on 6E's validated speed-trace lap-time model,
  generalized to exact form.

## 4. Architecture changes

New module `src/racewise/data/historical/counterfactual.py` (derived on read,
zero storage growth):

- `extract_speed_profile` — deterministic speed profile on the 6E 0.25 s
  lap-relative grid (reuses `_resample_lap` / `_interp_series` unchanged).
- `transform_speed_profile` — pure intervention mathematics (REMOVE_DEFICIT,
  BLEND_WITH_REFERENCE, SCALE_SIGNAL) with explicit bounds; NaN/inf rejected.
- `_integral_plinear` / `_segmentize` — exact quadrature of the piecewise-linear
  profile (trapezoids on clipped sub-intervals; no sampling error).
- `simulate_telemetry_counterfactual` — lap-level entry with six validation gates.
- `simulate_stint_counterfactual` — bounded stint aggregation over the Phase 6G
  common-lap selector (MIN_STINT_LAPS = 3, monotonicity check, explicit cumulative
  semantics).

## 5. Validation gates (all enforced, test-covered)

1. telemetry (≥ 20 raw samples, target + reference as required)
2. alignment (shared 0.25 s grid, ≥ 50 points)
3. intervention (known type, finite parameter, explicit bounds)
4. simulator_mapping (speed only; others → UNSUPPORTED)
5. baseline_reproduction (model baseline == measured grid duration, error ≤ 1e-6 s;
   identity-parameter delta exactly 0.0)
6. sanity_bounds (finite, speeds ≥ 0, |delta| < lap duration)

The baseline-reproduction gate earned its keep during development: the first
implementation (rectangle-rule segment means on rounded values) failed it with an
8.4e-06 s error — root cause was quadrature + rounded inputs, fixed by exact
piecewise-linear integration on unrounded values. The gate now passes with error
exactly 0.0 on the full matrix.

## 6. Baseline reproduction & identity

| Check | Result (full matrix, 4 sessions) |
|---|---|
| Model baseline vs measured grid duration | error **0.0 s** everywhere |
| Identity-parameter delta | **exactly 0.0** everywhere |

## 7. Lap counterfactual — measured examples (all VALID, all gates PASS)

| Case | Intervention | Baseline (modeled) | Counterfactual | Delta |
|---|---|---|---|---|
| 2023 R1, lap 1, PER (ref VER) | REMOVE_DEFICIT f=0.5 | 99.000000 s | 93.864999 s | **−5.135001 s** |
| 2022 R4, lap 1, PER (ref VER) | REMOVE_DEFICIT f=0.5 | — | — | −4.403444 s |
| 2024 R14, lap 1, PIA (ref HAM) | REMOVE_DEFICIT f=0.5 | — | — | −2.757208 s |
| 2025 R12, lap 1, PIA (ref NOR) | REMOVE_DEFICIT f=0.5 | — | — | −2.048394 s |
| 2023 R1, lap 1, PER | SCALE_SIGNAL f=−0.05 | — | — | +5.315789 s |

Sensitivity curve (2023 R1 lap 1, REMOVE_DEFICIT; measured, deterministic,
non-increasing): f = 0.0 → 0.0; 0.25 → −2.694406; 0.5 → −5.135001; 0.75 →
−7.363623; 1.0 → −9.412666 s. Non-linear by measurement, not assumption.

## 8. Stint counterfactual (verified on the matrix)

- 2023 R1 stint 1: 3/3 laps valid, mean delta −2.877617 s, monotonicity PASS.
- 2025 R12 stint 2: 6/6 laps valid, mean delta −0.922525 s, monotonicity PASS.
- Exclusions preserved with reasons; cumulative semantics stated in-output:
  *"sum over the SAMPLED comparable laps only; not race time, not a season or
  race claim."*

## 9. Race-level counterfactual

**Not implemented — deliberate.** Telemetry coverage (12 clean laps/driver under
the 6D policy) cannot support race-wide counterfactuals without extrapolating
across non-comparable intervals, which 6H explicitly forbids. The stint and race
surfaces state the boundary honestly (updated `counterfactual_gate` text in
`stint_evidence.py` / `race_gap.py`: strategy-simulator counterfactuals remain
UNSUPPORTED; bounded speed-profile lap/stint sensitivity is available via 6I).

## 10. Evidence integration / falsification / counterfactual gate

- The 6I tool runs inside the `InvestigationEngine` state machine to **COMPLETED**
  with an empty gate: the counterfactual is recorded as `EvidenceType.COUNTERFACTUAL`
  with supporting evidence (the measured sensitivity) *and* honest contradicting
  evidence ("sensitivity is not causality; the 6E residual applies at full
  removal"). `unsupported_claims() == []`.
- Q11.8 integration fuses Phase 6F hypothesis verdicts and 6I model sensitivity
  **side by side, never merged**: e.g. 2022 R4 lap 7 → H1 corner-speed SUPPORTED by
  evidence, model sensitivity −1.844926 s; 2023 R1 lap 6 → H1 CONTRADICTED,
  sensitivity −1.852868 s. Different epistemic objects; the output says so.
- The 6G/6H `counterfactual_gate` text was corrected to be precise: the *strategy
  simulator* gate is preserved; the 6I bridge is a model-sensitivity analysis,
  not history or causality. All 60 6G/6H tests still pass unchanged.

## 11. MCP / API / Frontend

- **MCP**: registry 32 → **33 tools** (`simulate_historical_telemetry_counterfactual`,
  18 in the historical registry). Verified over the real server subprocess:
  initialize → tools/list → tools/call; output hash over the wire equals the
  in-process/fresh-subprocess hash. Explicit numeric bound enforcement (the generic
  validator ignores min/max): `fraction=99` → ToolError, `segment_s=99` → ToolError.
- **Contract hardening (systemic)**: `validate_payload` now enforces `enum` —
  `signal: "telepathy"` is rejected at the boundary for every tool (56 contract
  tests pass unchanged).
- **API**: `GET /api/catalog/counterfactual/{season}/{round}` — bounded read-only;
  drivers default to the canonical telemetry pair, lap defaults to the first
  telemetry lap with a VALID result (never fabricated); out-of-bounds fraction →
  HTTP 422; byte-identical repeat verified via TestClient.
- **Frontend**: `CounterfactualView` renders intervention, baseline/counterfactual/
  delta, validation gates, profile summary, 6E cross-check, interpretation and
  output hash. Renders only — no client-side engineering calculations. Build clean.

## 12. Q11 benchmark matrix (all verified on real data)

| Category | Result |
|---|---|
| Q11.1 speed REMOVE_DEFICIT | VALID on 4/4 matrix sessions (2022/2023/2024/2025) |
| Q11.2 speed SCALE_SIGNAL | VALID, deterministic deltas |
| Q11.3 non-speed interventions | UNSUPPORTED by contract (brake representative) |
| Q11.4 bounded parameters | out-of-bounds → INVALID (module) / ToolError (MCP) |
| Q11.5 baseline reproduction | error 0.0 + identity delta 0.0 on 4/4 |
| Q11.6 deterministic replay | hash-identical on 4/4 |
| Q11.7 stint-level | VALID with monotonicity PASS (or honest INSUFFICIENT) |
| Q11.8 hypothesis + counterfactual | verdicts and sensitivity recorded side by side |
| Q11.9 unavailable telemetry | 1950/2018/missing driver/absent lap → UNAVAILABLE |
| Q11.10 invalid parameters | fraction 1.5 / NaN → INVALID |
| Q11.11 unsupported mapping | gear / unknown intervention type → UNSUPPORTED |
| Q11.12 full MCP verification | registry VALID; fraction/segment/signal/unknown-param all REJECTED |

Negative controls: `all_expected = true` (machine-checked in the report).

## 13. Determinism & replay

| Context | Result |
|---|---|
| In-process repeat | identical |
| Fresh subprocess ×2 | identical (`eccdd347ba1e2b20` lap, `4b2cb45c04c7b0e8` stint) |
| MCP over real server | identical, hash matches subprocess hash |
| API repeat | byte-identical |
| Q11 full-matrix replay | `replay_identical` true on every row |

No timestamps, random IDs, or unordered structures in analytical output;
`output_hash` excludes itself.

## 14. Performance (measured, 20-run sample + stint)

| Operation | p50 | p95 | max |
|---|---|---|---|
| Lap counterfactual (incl. telemetry read) | **328 ms** | 398 ms | 398 ms |
| Stint counterfactual (3–6 laps) | — | — | 1,674 ms |
| MCP call (lap) | — | — | 249 ms |
| Lap payload | 3.3 KB | — | — |

Slower per-call than 6F lap fusion (~87 ms) because the counterfactual loads and
integrates full speed traces for up to two drivers; well within bounds, no
optimization needed.

## 15. Storage

**Zero growth, proven**: DB size and mtime unchanged across repeated counterfactual
runs; row counts identical (telemetry 787,555; lap times 270,449). Derived on read;
raw telemetry immutable. `PRAGMA integrity_check` = ok, `foreign_key_check` = 0 rows.

## 16. Security

- MCP allow-list unchanged; unknown parameters rejected (registry path);
  non-finite floats rejected by the contract; enums now enforced contract-wide.
- Explicit numeric bounds re-validated inside the tool (`ToolError` on violation).
- No eval/lambda/SQL/expression inputs exist; the API accepts only enum-bound
  parameters and a bounded fraction; read-only throughout.
- Secret scan of the committed tree: clean (see verification commands).

## 17. Known limitations

1. Speed-only: no deterministic lap-time model exists for throttle/brake/gear/RPM/DRS;
   interventions on them return UNSUPPORTED rather than approximated.
2. Race-level telemetry counterfactuals are not offered (coverage-bounded data;
   no extrapolation). The stint aggregate covers only sampled comparable laps.
3. The model ignores racing line, tyre state, fuel, traffic and DRS mechanics;
   deltas are model sensitivities under that scope.
4. At full deficit removal the model adopts the reference trace over the target's
   segment distances; the limit need not equal the measured lap delta (6E residual
   applies). Documented in-output.
5. The strategy simulator remains telemetry-free (preserved gate); pit/compound
   counterfactuals are unchanged.

## 18. Files changed (this phase)

- `src/racewise/data/historical/counterfactual.py` (new — core)
- `src/racewise/data/historical/q11_benchmarks.py` (new — Q11 family)
- `src/racewise/tools/historical.py` (+ tool, + registry entry)
- `src/racewise/tools/contract.py` (+ enum enforcement)
- `src/racewise/api/app.py` (+ bounded endpoint)
- `src/racewise/data/historical/stint_evidence.py`, `race_gap.py` (gate text made precise)
- `apps/web/src/CounterfactualView.tsx` (new), `apps/web/src/App.tsx`, `apps/web/src/App.css`
- `tests/unit/test_counterfactual.py` (new, 32 tests), `tests/unit/test_q11_benchmarks.py` (new, 9 tests)
- `docs/PHASE_6I_TELEMETRY_COUNTERFACTUALS.md`, `docs/PHASE_6I_COMPLETION_REPORT.md`

## 19. Commits

1. `feat(counterfactual): telemetry counterfactual core with validated bridge, Q11 matrix and tests` — counterfactual.py, q11_benchmarks.py, both test files, stint_evidence/race_gap gate text.
2. `feat(counterfactual): MCP tool, enum contract enforcement, API endpoint, CounterfactualView and Phase 6I docs` — tools/historical.py, tools/contract.py, api/app.py, frontend, docs.

## 20. Exact verification commands

```bash
# full regression (387 pass)
python -m pytest -q

# phase 6I suites only
python -m pytest tests/unit/test_counterfactual.py tests/unit/test_q11_benchmarks.py -q

# Q11 report incl. negative controls + MCP verification (JSON)
python -c "import sys; sys.path.insert(0,'src'); \
  from racewise.data.historical.canonical_queries import CanonicalQueries; \
  from racewise.data.historical.q11_benchmarks import run_q11; \
  import json; print(json.dumps(run_q11(CanonicalQueries()), indent=2, default=str))"

# MCP over the real server: 33 tools; simulate_historical_telemetry_counterfactual live
python -m racewise.mcp.server   # JSON-RPC over stdio

# API endpoint
uvicorn racewise.api.app:app    # GET /api/catalog/counterfactual/2023/1

# frontend build
cd apps/web && npm run build

# integrity / storage
python -c "import sqlite3; c=sqlite3.connect('data/canonical/canonical.db'); \
  print(c.execute('PRAGMA integrity_check').fetchone(), len(c.execute('PRAGMA foreign_key_check').fetchall()))"
```

## 21. Final readiness

All Definition-of-Done items verified with measured numbers; bounded documented
limitations remain (speed-only interventions; no race-level telemetry
counterfactuals; strategy simulator still telemetry-free by design).

**PHASE 6I STATUS: READY_WITH_DOCUMENTED_LIMITATIONS**
