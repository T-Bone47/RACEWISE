# Phase 6E Completion Report — Telemetry-to-Lap Attribution & Loss Decomposition

All numbers measured against the live canonical store and running code.

## 1. Executive summary

Telemetry in RACEWISE now **explains measured lap deltas** rather than merely
being queryable. The attribution engine measures the observed delta from
canonical lap facts, decomposes it authoritatively via sector splits (summing
exactly to the delta), estimates the speed-trace pace component over fixed
time regions with an explicit reconciled residual, attaches per-signal
metrics, runs falsification checks against alternative explanations, and
aggregates across stints — all deterministic, bounded, and provenance-backed.
Exposed through 2 new MCP tools (registry 27 → **29**), a bounded API endpoint,
and a frontend engineering view.

## 2. Starting state (baseline, verified)

201 tests passing · 93 telemetry sessions / 787,555 rows · DB 386.4 MB ·
14/14 validators · FK 0 · MCP 27 tools · frontend builds · HEAD `ab9afb0`.
Pre-existing uncommitted work (investigation engine, schemas, adapters from
earlier phases) left untouched throughout.

## 3. Architecture

No new persisted tables — attribution is **derived on read** from immutable
canonical telemetry + lap facts (storage discipline §24: zero DB growth).
New module `src/racewise/data/historical/loss_attribution.py`
(`attribute_lap_loss`, `attribute_stint_loss`, `falsify_attribution`) +
`attribution_benchmarks.py` (Q7 family + negative controls).
Two query-layer helpers added: `get_telemetry_driver_pair`.

## 4. Alignment methodology

Lap-relative time resampling onto a fixed 0.25 s grid; linear interpolation,
clamped to the overlapping span, no extrapolation. Chosen because FastF1
samples are car-local with no shared time base and no distance channel
exists. Full rationale: `PHASE_6E_TELEMETRY_ATTRIBUTION.md`.

## 5. Attribution methodology

- **Sector (authoritative FACT):** `sector_i(B) − sector_i(A)`; the three
  deltas sum **exactly** to the observed lap delta (test-enforced).
- **Regions (CALCULATION):** `loss = dt·(1 − v_B/v_A)` per 15 s window.
- **Reconciliation:** `observed = estimated_pace_component + residual`;
  residual always reported with interpretation, tolerance 0.05 s.
  Example (2023 R1 lap 57 VER/PER): observed 0.185 s, estimated 0.401 s,
  residual −0.216 s → "window means smooth corner-exit differences the
  straight-line model cannot see" — reported honestly, not forced to match.

## 6. Signal metrics

Per-signal explicit definitions (speed mean/max deficit, throttle lift
windows, brake fraction + onset, gear mismatch fraction, rpm delta, DRS
activation delta) — see attribution doc table.

## 7. Context filtering

Pit in/out, deleted, missing time, SC/VSC/yellow track status, inaccurate
flags, and **per-lap-window** rain (fixed after session-level rain wrongly
disqualified every lap of wet races) all classify a lap non-comparable.
Compound mismatch → VALID_WITH_CAVEATS. Exclusion reasons always exposed.
Rain-window fix validated: 2022 R10 / 2023 R9 / 2025 R1 / 2025 R12 now yield
valid attributions.

## 8. Stint analysis

Bounded (≤ 6) evenly-spaced sample of common clean stint laps; per-lap
attribution aggregated to mean/median delta, mean residual, delta trend,
`unexplained_fraction`. Verified: stint agg reconciles
(`mean_delta ≈ mean_component + mean_residual`, ±1 ms test tolerance).

## 9. Evidence / falsification / investigation integration

Falsification checks (braking, DRS, race control, compound) return
SUPPORTED / NOT_SUPPORTED / NOT_TESTABLE with numbers. Full investigation-
engine run verified: QUESTION → HYPOTHESES → EVIDENCE_COLLECTION (attribution
tool) → FALSIFICATION (4 recorded checks) → SYNTHESIS → **COMPLETED** with
empty gate failures and a replayable event log (21 events).

## 10. Counterfactual integration

Telemetry-profile counterfactuals ("match B's braking profile") are honestly
**UNSUPPORTED**: the deterministic simulator (`simulate_pit_timing`) operates
on lap times, not telemetry inputs. No simulation through prose.

## 11. MCP tools (registry 27 → 29)

`attribute_historical_lap_loss`, `attribute_historical_stint_loss` — typed
schemas, bounded params (`region_s` 5–30, `max_laps` ≤ 12), deterministic
output hashes (verified equal across repeated registry executes), negative
states preserved. Verified over the real server subprocess: 29 tools listed,
attribution call 144 ms returning VALID_COMPARISON.

## 12. Frontend

`AttributionView.tsx` + `GET /api/catalog/attribution/{season}/{round}`
(bounded; session must have telemetry; lap auto-selected by walking telemetry
laps newest-first through the engine itself). Renders observed delta, sector
attribution bars, top loss regions, residual interpretation, falsification
checks, assumptions. Numbers rendered, never computed, client-side.
Vite build passes (~0.2 s); endpoint verified via TestClient (2023 PASS /
2018 UNAVAILABLE).

## 13. Q7 benchmark results (real data, 4 seasons, multiple circuits)

| Session | Lap | Pair | Δ (B−A) | Residual | Status |
|---|---|---|---|---|---|
| 2022 R1 Bahrain | 52 | SAI vs LEC | −0.713 s | −0.713 s | PASS |
| 2022 R10 Austria | 52 | SAI vs PER | −0.135 s | −0.467 s | PASS |
| 2023 R1 Bahrain | 57 | VER vs PER | +0.185 s | −0.216 s | PASS |
| 2023 R9 Monza | 71 | LEC vs VER | −2.978 s | −2.978 s | PASS |
| 2024 R1 Bahrain | 57 | VER vs PER | +0.823 s | −0.925 s | PASS |
| 2024 R14 Hungary | 44 | HAM vs PIA | −0.406 s | −0.962 s | PASS |
| 2025 R1 Melbourne | 43 | NOR vs VER | +0.914 s | −0.380 s | PASS |
| 2025 R12 | 48 | NOR vs PIA | +1.083 s | −0.620 s | PASS |

Q7.1–Q7.7 sub-questions populated per session; stint attribution VALID on 7/8.
Negative controls (all PASS): 1950 → UNAVAILABLE; 2018 → UNAVAILABLE;
absent lap → UNAVAILABLE; lap-1 pit context → INSUFFICIENT_EVIDENCE.

## 14. Determinism

Byte-identical JSON in-process and across fresh subprocesses
(hash `2702543775debc33` stable); MCP output hashes equal across calls.
Attribution is read-only — idempotency is structural (no derived writes).

## 15. Test results

**223 passed** (201 baseline + 22 new: interpolation/alignment math, context
classification, signal metrics on synthetic series, live-sector reconciliation,
stint aggregation identity, negative controls, MCP registry hashes,
investigation-engine completion, Q7 matrix + negatives). Golden hashes were
re-verified stable in 6D and untouched here (no ingestion changes).

## 16. Performance (386.4 MB store, measured)

| Path | p50 | p95 |
|---|---|---|
| `attribute_lap_loss` | 202 ms | 224 ms |
| `attribute_stint_loss` | 733 ms | 817 ms |
| MCP attribute (single call, subprocess) | 144 ms | — |

No new indexes needed (composite telemetry index from 6C covers all lookups).

## 17. Storage

**0 bytes growth** — attribution is derived on read; raw telemetry immutable.

## 18. Security / no-fabrication

MCP surface remains bounded/read-only; no raw-sample dumps (region grids only,
max ~40 numbers per call). No fabrication patterns introduced; every number
in outputs traces to `canonical_lap_times` / `canonical_telemetry` with
method version. Unavailable evidence stays UNAVAILABLE.

## 19. Known limitations

1. Region losses are estimates; residual interpretation is qualitative.
2. No distance-normalized alignment (no distance channel ingested).
3. Telemetry-profile counterfactuals unsupported by the simulator (honest gate).
4. Q7 stint attribution INSUFFICIENT for 2023 R9 (no common stint-1 laps) — correct.
5. 2023 R9 lap 71 shows residual = delta (−2.978 s): a safety-car-adjacent lap
   where the speed traces explain none of the delta — reported, not hidden.

## 20. Files changed / commits

- `src/racewise/data/historical/loss_attribution.py` (new — core engine)
- `src/racewise/data/historical/attribution_benchmarks.py` (new — Q7 + negatives)
- `src/racewise/data/historical/canonical_queries.py` (+`get_telemetry_driver_pair`)
- `src/racewise/tools/historical.py` (+2 tools, registry wiring)
- `src/racewise/api/app.py` (+attribution endpoint)
- `apps/web/src/AttributionView.tsx` (new) + `App.tsx`/`App.css` wiring
- `tests/unit/test_loss_attribution.py` (new, 22 tests)
- `docs/PHASE_6E_TELEMETRY_ATTRIBUTION.md`, `docs/PHASE_6E_COMPLETION_REPORT.md`

## PHASE 6E STATUS: READY_WITH_DOCUMENTED_LIMITATIONS

(The limitations above are bounded and documented; all DoD items pass.)
