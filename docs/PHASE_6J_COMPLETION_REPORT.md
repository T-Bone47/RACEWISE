# PHASE 6J COMPLETION REPORT — MEASURED PERFORMANCE ENVELOPE & SCENARIO ANALYSIS

## 1. Executive summary

Phase 6J turns the validated Phase 6I counterfactual machinery into a *measured*
performance-envelope layer: per grid point, the min/max/median of a driver's own
clean comparable laps — a measured band, never an ideal lap or theoretical maximum
— swept with bounded typed scenarios through the exact 6I lap-time model. All
scenarios flow through one simulator (6I), baseline reproduction remains exact
(error 0.0, identity delta exactly 0.0), the response is measured (MONOTONIC and
measurably non-linear on the full matrix, never fitted), and the epistemic
boundary is preserved: every delta is model sensitivity, not history, not
prediction, not causality. Derived on read; zero storage growth.

## 2. Starting baseline (Phase 6I, verified at session start)

| Metric | Value |
|---|---|
| Tests | 388 passing (suite re-run; floor moved 346 → 388 during 6I's window) |
| Telemetry | 93 sessions / 787,555 rows |
| Database | 405.2 MB |
| MCP tools | 33 |
| 6I status | READY_WITH_DOCUMENTED_LIMITATIONS |
| Pre-existing uncommitted work | preserved untouched |

## 3. Architecture changes

New module `src/racewise/data/historical/performance_envelope.py` (derived on
read, zero storage growth). Reuse discipline held — **no second implementation of
anything**: profile extraction = 6I `extract_speed_profile`; lap-time model = 6I
`_segmentize`/`_model_lap_time` (exact piecewise-linear quadrature); clean-lap
context = 6E `_classify_lap` + per-lap-window rain; stint lap selection = 6G
`_select_common_laps`; reference interpolation = 6E `_interp_series`.

- `build_performance_envelope` — measured band (single anchor + multi-lap),
  segment-level band summary, exact model baseline, `profile_id`.
- `analyze_performance_envelope` — one entry point for session and stint scope:
  typed scenario sweep, response classification, regional sensitivity,
  per-lap stint trend.
- `_classify_response` — descriptive finite differences
  (MONOTONIC / NON_MONOTONIC / FLAT / INSUFFICIENT_DATA).

## 4. Envelope definition

Per grid point t over the driver's clean comparable laps:
`lower = min v_i(t)`, `upper = max v_i(t)`, `centre = median v_i(t)`. Normalization
is lap-relative time only; raw values never modified. Measured example (2023 R1,
PER, 6-lap band): overall range 45.6–330.6 km/h, mean band width 33.0 km/h, max
band width 142.7 km/h — the driver's actual measured variability, stated as such.

## 5. Scenario model & bounds

Five typed scenarios (`OBSERVED`, `DEFICIT_REDUCTION`, `REFERENCE_BLEND`,
`ENVELOPE_LOWER_BOUND`, `ENVELOPE_UPPER_BOUND`); closed enum enforced contract-wide
(unknown types rejected at the registry). Explicit bounds re-enforced in the tool:
`max_scenarios ≤ 11`, `max_laps ≤ 12`, `segment_s ∈ [2, 30]`, finite |parameter| ≤ 1;
`OBSERVED` with a non-zero parameter is INVALID; reference scenarios require an
explicit distinct reference driver. Reference profiles use the reference driver's
telemetry on the anchor lap (6I semantics).

## 6. Sensitivity analysis (measured, 2023 R1 PER vs VER example)

| f | Δ modeled lap time |
|---|---|
| 0.0 | 0.000000 s (identity, exact) |
| 0.25 | −0.356358 s |
| 0.50 | −0.705146 s |
| 0.75 | −1.046681 s |
| 1.00 | −1.381261 s |

Response: MONOTONIC, max |2nd difference| 0.007570 s → measurably **non-linear**.
Full matrix: 4/4 sessions VALID, MONOTONIC, non-linear; identity delta exactly 0.0
on all rows.

## 7. Regional response (model sensitivity by region, not sector causality)

Largest model responses, 2023 R1: 36.3–42.3 s window −0.224 s; 48.3–54.3 s −0.113 s;
84.3–90.3 s −0.114 s. Output explicitly labels these "model sensitivity by region".

## 8. Stint analysis

Stint envelopes built via 6G selection; mid-parameter scenario applied per measured
stint lap (reference interpolated onto each lap/reference common span; insufficient
overlap skipped and counted — never extrapolated). Measured trends: 2022 R4 stint 2
sensitivity *increases* through the stint (+0.350 s/lap; per-lap −1.93 → −0.42 s);
2023 R1 stint 2 −0.008 s/lap; 2024 R14 stint 2 −0.061 s/lap. Interpretation is fixed
in-output: "interpret alongside canonical degradation evidence — no new tyre model
is built here."

## 9. Evidence integration

Q12.9 fuses 6F verdicts and 6J sensitivity side by side, never merged — all four
verdict variants exercised across the matrix: 2022 R4 H1 SUPPORTED (sensitivity
−8.505 s at f=1.0), 2023 R1 / 2024 R14 H1 CONTRADICTED (−1.381 / −4.840 s),
2025 R12 H1 NOT_TESTABLE (−1.971 s). The investigation-engine integration runs the
envelope tool through the full state machine to COMPLETED with an empty
falsification gate (`unsupported_claims() == []`).

## 10. Q12 benchmark matrix

| Category | Result |
|---|---|
| Q12.1 single-lap envelope | VALID, data-derived anchor, 4/4 sessions |
| Q12.2 multi-lap envelope | 5–6 laps in band on 4/4 |
| Q12.3 reference comparison | explicit pairs, all VALID |
| Q12.4 scenario sweep | 5-point bounded grids, 4/4 |
| Q12.5 monotonic sensitivity | MONOTONIC 4/4 |
| Q12.6 non-linear response | measured 2nd differences > 0 on 4/4 |
| Q12.7 regional sensitivity | top-3 regions reported 4/4 |
| Q12.8 stint envelope | VALID on 4/4 (stints 1–2; 2025 R12 stint 1 has band but < 3 ref-overlap laps for the per-lap trend) |
| Q12.9 evidence + sensitivity | verdicts and sensitivity recorded side by side |
| Q12.10 baseline identity | reproduction error 0.0 + identity delta 0.0 on 4/4 |
| Q12.11 deterministic replay | envelope + sweep hashes identical on 4/4 |
| Q12.12 MCP verification | registry VALID; 6 bound violations REJECTED; 1950 UNAVAILABLE |

## 11. Negative controls

`1950` → UNAVAILABLE · `2018` → UNAVAILABLE · missing driver → UNAVAILABLE ·
missing reference → UNAVAILABLE · same driver A=B → INVALID · bad scenario type →
UNSUPPORTED · parameter 1.5 → INVALID · OBSERVED with parameter 0.3 → INVALID ·
nonexistent stint → INSUFFICIENT_EVIDENCE. All machine-checked in the report.

## 12. Determinism & replay

| Context | Result |
|---|---|
| In-process repeat | identical |
| Fresh subprocess ×2 | identical (`0633419e5d81f347` envelope, `36b5fd19e6bb2fea` sweep) |
| MCP over real server | identical; hash matches all contexts |
| API repeat | byte-identical |
| Q12 replay | envelope + sweep hash-identical on every matrix row |

## 13. Performance (measured)

| Operation | Time |
|---|---|
| Envelope build (6-lap band) | 237 ms |
| Scenario sweep (5 points, 6 laps) | p50 214 ms / max 247 ms |
| Stint sweep | 148 ms |
| MCP call | 225 ms |
| Sweep payload | 6.6 KB |

Comparable to 6I (lap counterfactual p50 328 ms); the sweep amortizes profile
extraction across scenario points. No optimization needed.

## 14. Storage

**Zero growth, proven**: DB size and mtime unchanged across repeated runs;
telemetry rows still 787,555. `PRAGMA integrity_check` = ok, FK violations 0.
Derived on read; envelopes/scenario matrices never persisted.

## 15. Security

MCP allow-list unchanged; typed scenario enums enforced contract-wide; explicit
numeric bounds re-validated in the tool (all six bound violations → ToolError);
unknown parameters rejected by the registry; finite-number enforcement preserved;
no eval/SQL/filesystem/shell; read-only throughout; secret scan of the committed
tree clean.

## 16. Known limitations

1. Speed-only: non-speed signals remain UNSUPPORTED (no deterministic lap-time model).
2. Race-level telemetry counterfactuals remain UNSUPPORTED; scenario results cover
   only the sampled measured laps and are never summed into an alternate race result.
3. The envelope pools laps across the session — stint age and tyre state vary inside
   the band (stated in-output; stint scope provides the finer view).
4. The per-lap stint sensitivity trend requires sufficient reference-profile overlap;
   laps without it are skipped and counted, never extrapolated.
5. The 6I model scope applies (no racing line, tyre, fuel, traffic, DRS mechanics);
   envelope upper bound is fastest *measured* form, not a capability claim.

## 17. Files changed (this phase)

- `src/racewise/data/historical/performance_envelope.py` (new — core)
- `src/racewise/data/historical/q12_benchmarks.py` (new — Q12 family)
- `src/racewise/tools/historical.py` (+ tool, + registry entry → 34 MCP tools)
- `src/racewise/api/app.py` (+ bounded endpoint)
- `apps/web/src/PerformanceEnvelopeView.tsx` (new), `apps/web/src/App.tsx`
- `tests/unit/test_performance_envelope.py` (new, 23 tests), `tests/unit/test_q12_benchmarks.py` (new, 9 tests)
- `docs/PHASE_6J_PERFORMANCE_ENVELOPE.md`, `docs/PHASE_6J_COMPLETION_REPORT.md`

## 18. Commits

1. `feat(envelope): measured performance envelope core, scenario sweeps, Q12 matrix and tests` — performance_envelope.py, q12_benchmarks.py, both test files.
2. `feat(envelope): MCP envelope tool, API endpoint, PerformanceEnvelopeView and Phase 6J docs` — tools/historical.py, api/app.py, frontend, docs.

## 19. Exact verification commands

```bash
# full regression (420 pass)
python -m pytest -q

# phase 6J suites only
python -m pytest tests/unit/test_performance_envelope.py tests/unit/test_q12_benchmarks.py -q

# Q12 report incl. negative controls + MCP verification (JSON)
python -c "import sys; sys.path.insert(0,'src'); \
  from racewise.data.historical.canonical_queries import CanonicalQueries; \
  from racewise.data.historical.q12_benchmarks import run_q12; \
  import json; print(json.dumps(run_q12(CanonicalQueries()), indent=2, default=str))"

# MCP over the real server: 34 tools; analyze_historical_performance_envelope live
python -m racewise.mcp.server   # JSON-RPC over stdio

# API endpoint
uvicorn racewise.api.app:app    # GET /api/catalog/performance-envelope/2023/1

# frontend build
cd apps/web && npm run build

# integrity / storage
python -c "import sqlite3; c=sqlite3.connect('data/canonical/canonical.db'); \
  print(c.execute('PRAGMA integrity_check').fetchone(), len(c.execute('PRAGMA foreign_key_check').fetchall()))"
```

## 20. Final readiness

All Definition-of-Done items verified with measured numbers; bounded documented
limitations remain (speed-only scenarios; no race-level extrapolation; pooled
session band).

**PHASE 6J STATUS: READY_FOR_PERFORMANCE_SCENARIO_ANALYSIS**
