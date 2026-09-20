# PHASE 6F — Multi-Source Engineering Evidence Fusion

Status: **READY_WITH_DOCUMENTED_LIMITATIONS**

## Executive summary

Phase 6F evolves RACEWISE from *"telemetry can explain where a measured lap
delta occurs"* (6E) to *"multiple independent canonical evidence sources can be
fused to establish which explanations are supported, contradicted, not
testable, or unresolved."* The fusion layer is **derived on read**: zero
database growth, zero raw-telemetry duplication.

The engineering question answered deterministically:

> What combination of measurable factors is consistent with the observed
> performance difference, what contradicts it, what cannot be tested, and
> what remains unexplained?

Consistency is never reported as causation. The unexplained residual is a
first-class output that is never assigned to a hypothesis.

## Starting baseline (verified before implementation)

| Item | Value |
|---|---|
| Tests | 223 passing |
| Telemetry | 93 sessions / 787,555 rows (2021 pilot + 2022–2025 races) |
| MCP tools | 29 |
| Validators / FK | 14/14 / 0 violations |
| Golden hashes | stable (fresh-process replay) |
| Database | 405.2 MB on disk at 6F start (6D baseline rows unchanged) |
| Q7 | passing across 2022–2025 |

## Evidence model

Every evidence item (`evidence_fusion._evidence`) carries:

- `source_id` — deterministic, includes session/lap identity (dedup key)
- `source_type` — e.g. `canonical_sector_split`, `telemetry_speed_metric`
- `provider` + `tables` — provenance (canonical tables read)
- `evidence_type` — FACT / CALCULATION / INFERENCE (per RACEWISE semantics)
- `relationship` — SUPPORTS / CONTRADICTS / DOES_NOT_TEST (with INSUFFICIENT-quality items that cannot test)
- `hypotheses` — which candidate hypotheses the item informs
- `values` — the numerical values behind the statement
- `assumptions`, `limitations`

### Source independence

The `source_id` uniqueness invariant (asserted on every fusion, test-locked)
prevents double-counting: each canonical observation appears exactly once per
lap. Sector deltas come from canonical sector splits (measured facts);
telemetry metrics come from canonical telemetry (calculations over aligned
samples); no evidence item is a re-derivation of another item in the same
fusion.

### Quality dimensions (no single confidence score)

The output deliberately exposes **evidence states, not a score**: per-source
`quality` (VALID / VALID_WITH_CAVEATS / INSUFFICIENT), per-hypothesis formal
status, contradiction counts, and the residual classification
(EXPLAINED_BY_SPEED_TRACES / PARTIALLY_EXPLAINED / UNRESOLVED). The word
"confidence" appears nowhere in fusion output (test-enforced).

## Hypothesis set (candidate, not universal causes)

| ID | Statement |
|---|---|
| H1_corner_speed | deficit arises from lower speed through corners/fast sections |
| H2_throttle | deficit associated with later/reduced throttle application |
| H3_braking | deficit arises from braking differences |
| H4_tyre_state | a tyre-state difference (compound/age) explains part of the deficit |
| H5_race_control | race-control restriction / pit interference / conditions explain the delta |
| H6_drs | lower DRS availability contributed to the deficit |

## Formal status rules (deterministic, documented, test-covered)

Given the evidence items mapped to a hypothesis:

1. **NOT_TESTABLE** — no evidence item from a required source exists for this
   lap (fundamentally different from NOT_SUPPORTED).
2. **CONTRADICTED** — at least one valid item CONTRADICTS (and some support
   exists); **NOT_SUPPORTED** if contradictions exist but no support.
3. **SUPPORTED** — ≥1 valid SUPPORTS item and zero CONTRADICTS.
4. **PARTIALLY_SUPPORTED** — SUPPORTS present plus neutral
   (DOES_NOT_TEST/INSUFFICIENT) items — support with residual uncertainty.
5. **NOT_SUPPORTED** — evidence exists but does not support.

Invariants (test-enforced): unavailable evidence can never yield SUPPORTED;
valid contradiction forbids full support; statuses are computed from
relationships, never weighted or averaged.

### Deficit-premise gate

All six hypotheses explain *why B lost time*. When the measured delta shows B
was not slower (delta ≤ 0), the premise is vacuous: the fusion reports the
observation and marks every hypothesis NOT_TESTABLE with the delta in the
reason. It never evaluates deficit explanations against a favourable delta
(a real defect found by the Q8 matrix during 6F and fixed).

## Multi-source adapters

| Source | Alignment | Output relationship logic |
|---|---|---|
| canonical_sector_split | same lap (measured) | SUPPORTS H1/H2 when sector delta > 0 (B slower), CONTRADICTS when negative |
| telemetry_speed_regions/metric | lap-relative time grid (6E interpolation) | SUPPORTS when B speed deficit < 0 km/h |
| telemetry_throttle_metric | shared resampled grid | SUPPORTS on B lift-windows/mean throttle deficit; CONTRADICTS when B applied more |
| telemetry_brake_metric | shared resampled grid | SUPPORTS when B brakes more/later; CONTRADICTS when B brakes less/earlier (cannot explain a loss) |
| telemetry_drs_metric | lap window | SUPPORTS when B had less DRS availability; CONTRADICTS when more |
| canonical_stint_state | same lap | compound mismatch → SUPPORTS; age gap > 4 laps → SUPPORTS; comparable → CONTRADICTS (tyre state cannot explain) |
| canonical_race_control_lap_overlap | **lap-window overlap** (never session-level) | restricted lap → SUPPORTS; clear lap → CONTRADICTS |
| canonical_pit_stop_proximity | ±1 lap window | nearby stop → SUPPORTS; none → CONTRADICTS |
| canonical_weather_lap_window | **per-lap window** (6E per-lap-window philosophy) | rain in window → SUPPORTS; dry both → CONTRADICTS |

Context fusion reuses the 6E context filtering verbatim; a 6E
INSUFFICIENT_EVIDENCE verdict propagates and is never overridden.

## Residual handling

The 6E reconciliation (`observed_delta ≈ estimated_pace_component + residual`)
survives intact. Fusion classifies the residual (never zeroes it, never
assigns it):

- |residual| ≤ 15% of observed → EXPLAINED_BY_SPEED_TRACES
- ≤ 75% → PARTIALLY_EXPLAINED
- else → UNRESOLVED

The conclusion always states the residual is "reported, not assigned to any
hypothesis."

## Counterfactual gate

Telemetry-profile counterfactuals remain **UNSUPPORTED**: the deterministic
simulator operates on lap times and does not accept telemetry-profile inputs
(6E limitation preserved, not regressed). The fusion output carries the gate
explicitly (`counterfactual_gate`).

## Surfaces

- **MCP** `fuse_historical_lap_evidence` (tool #30): strict input schema
  (season/round/session_type/driver_a/driver_b/lap_number), unknown parameters
  rejected, bounded output (~0.5 KB), output-hashed, deterministic.
  Registry: 29 → **30 tools**, verified over the real server subprocess.
- **API** `GET /api/catalog/evidence-fusion/{season}/{round}` — bounded,
  read-only, lap defaults to the highest shared telemetry lap with a valid
  fusion (never fabricated).
- **Frontend** `EvidenceFusionView.tsx` — renders server-computed results
  only: observed delta, authoritative sector decomposition, hypothesis
  verdicts with supporting/contradicting/not-tested chains, residual,
  source-dependency audit, assumptions, methodology version. No client-side
  engineering calculation.

## Q8 benchmark family (9 categories)

Matrix: 2022 R1, 2022 R10, 2023 R1, 2023 R9, 2024 R1, 2024 R14, 2025 R1,
2025 R12 (multiple circuits, four seasons, wet- and dry-affected rounds).

- Q8.1 sector evidence fused — all valid rows
- Q8.2 tyre/stint evidence fused — all valid rows
- Q8.3 race-control evidence fused — all valid rows
- Q8.4 weather evidence fused — all valid rows
- Q8.5 DRS evidence fused — all valid rows
- Q8.6 contradictions recorded — falsification-first verified (every deficit
  row carries contradicting items; verdicts include CONTRADICTED/NOT_SUPPORTED)
- Q8.7 insufficient-evidence / premise gate — deficit rows with favourable
  delta are all NOT_TESTABLE (test-enforced)
- Q8.8 multi-source investigation — ≥4 sources, all 6 hypotheses formally
  evaluated, residual class present on every valid row
- Q8.9 replay determinism — full-matrix canonical JSON byte-identical across
  runs

Representative results (real data):

| Session | Lap | Observed Δ (B−A) | H1 | H2 | H3 | Residual | Class |
|---|---|---|---|---|---|---|---|
| 2023 R1 (VER/PER) | 57 | +0.185 s | SUPPORTED | CONTRADICTED | CONTRADICTED | −0.2157 s | UNRESOLVED |
| 2025 R12 | 48 | +1.083 s | SUPPORTED | SUPPORTED | CONTRADICTED | −0.6195 s | PARTIALLY_EXPLAINED |
| 2025 R1 | 43 | +0.914 s | SUPPORTED | SUPPORTED | SUPPORTED | −0.3804 s | PARTIALLY_EXPLAINED |
| 2022 R1 | 52 | −0.713 s | NOT_TESTABLE | NOT_TESTABLE | NOT_TESTABLE | −0.7130 s | UNRESOLVED |

## Negative controls (all executed)

- 1950 → UNAVAILABLE (no canonical telemetry)
- 2018 → UNAVAILABLE (no telemetry ingested)
- missing driver → UNAVAILABLE
- absent lap (999) → UNAVAILABLE
- favourable-delta premise → all hypotheses NOT_TESTABLE
- SC/VSC-affected laps → carry restriction evidence / 6E context verdicts propagate
- rain outside lap window → does not contaminate (per-lap-window weather)
- telemetry counterfactual → UNSUPPORTED (gate preserved)

## Determinism

- In-process repeat: identical canonical JSON (test-enforced, sha256).
- Fresh subprocess ×2: `e6ca5d2e5f730aac` (2023 R1 lap 57) — stable.
- MCP output hash: identical across repeated calls over the real server.
- Q8 full-matrix replay: byte-identical (test-enforced).
- No timestamps, UUIDs or other nondeterministic fields in analytical output.

## Idempotency & storage

Fusion is derived on read. Verified: size + mtime of the canonical DB are
**unchanged** by fusion and Q8 execution; integrity check ok; telemetry rows
787,555 and sessions 5,268 unchanged. No derived tables were created.

## Performance (405 MB DB, 787,555 telemetry rows)

| Path | p50 | p95 |
|---|---|---|
| fuse_lap_evidence (full fusion, 10 sources) | 87 ms | 101 ms |
| MCP execute (validate + execute + hash) | 56 ms | — |

No new indexes required; existing `(session_id, driver_id, lap_number)`
telemetry index covers all paths.

## Tests

- `tests/unit/test_evidence_fusion.py` — 21 tests: formal rules (7),
  live fusion shape/provenance/no-confidence-score/residual/consistency (6),
  negative controls (4), MCP + API surfaces (2), investigation integration (2).
- `tests/unit/test_q8_benchmarks.py` — 14 tests: matrix coverage (9) +
  negative controls (4) + determinism.
- Full suite: **258 passing** (223 baseline + 35 new). No existing test
  weakened.

## Investigation engine integration

`fuse_historical_lap_evidence` executes inside the
`InvestigationEngine.run(plan)` state machine with full provenance
(tool_executions, observations, evidence with supports/contradicts wiring).
The deterministic plan reaches COMPLETED with an empty falsification gate and
zero unsupported claims; telemetry counterfactuals stay gated
(`counterfactuals == []` asserted). The engine file itself was **not
modified** (carries unrelated uncommitted work from another thread).

## Security

- MCP allow-list: fusion tool registered through the standard registry;
  unknown parameters and non-allow-listed tools rejected (ToolError, tested).
- Read-only: no derived writes, no shell/filesystem/SQL exposure.
- Bounded output (~0.5 KB/call); no raw telemetry dumps at any layer.
- Secret scan of committed tree: clean (see verification commands).

## Known limitations

1. Speed-region losses are straight-line `dt·(1 − v_B/v_A)` estimates — the
   residual vs the measured delta remains reported, sometimes UNRESOLVED.
2. Traffic/dirty-air is not measurable with current signals (DOES_NOT_TEST).
3. Tyre grip/temperature not modeled — compound and age only.
4. Telemetry-profile counterfactuals remain UNSUPPORTED by the simulator.
5. Sector decomposition requires canonical sector splits for both laps;
   otherwise region attribution only.
6. The investigation-engine plan in tests is deterministic; LLM orchestration
   of fusion is unchanged from the existing architecture.

## Files changed (Phase 6F)

- `src/racewise/data/historical/evidence_fusion.py` (core, +methodology_version, +premise gate)
- `src/racewise/data/historical/q8_benchmarks.py` (new)
- `src/racewise/tools/historical.py` (FuseLapEvidenceTool, registration)
- `src/racewise/api/app.py` (evidence-fusion endpoint)
- `apps/web/src/EvidenceFusionView.tsx` (new), `App.tsx`, `App.css`
- `tests/unit/test_evidence_fusion.py`, `tests/unit/test_q8_benchmarks.py` (new)
- `docs/PHASE_6F_EVIDENCE_FUSION.md`, `docs/PHASE_6F_COMPLETION_REPORT.md`

## Verification commands

```bash
python -m pytest -q                                  # 258 passed
python -m pytest tests/unit/test_evidence_fusion.py tests/unit/test_q8_benchmarks.py -q
cd apps/web && npm run build                         # passes
# MCP over real server: tools/list → 30 tools; tools/call fuse_historical_lap_evidence
# determinism: fresh subprocess sha256 e6ca5d2e5f730aac (2023 R1, lap 57)
```

## Final readiness

**PHASE 6F STATUS: READY_WITH_DOCUMENTED_LIMITATIONS**

All DoD items verified except capabilities deliberately bounded by the
limitations above (traffic evidence, tyre-grip modeling, telemetry-profile
counterfactuals) — each preserved as an explicit honest state, never
fabricated.
