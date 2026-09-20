# PHASE 6G — Stint-Level Evidence Fusion & Performance Divergence

Status: **READY_WITH_DOCUMENTED_LIMITATIONS**

## Executive summary

Phase 6G extends RACEWISE from lap-level explanations (6F) to **stint-level
temporal divergence analysis**: how the performance gap between two drivers
evolved across a canonical stint, which explanations stayed consistent, which
appeared/disappeared/were contradicted over time, and what remains
unresolved. Fully derived on read — zero storage growth. The 6E/6F
architecture is consumed, never rewritten.

## Starting baseline (verified)

| Item | Value |
|---|---|
| Tests | 258 passing (full suite re-run at phase start) |
| Telemetry | 93 sessions / 787,555 rows |
| MCP tools | 30 |
| Database | 405.2 MB |
| Stints | 26,135 canonical rows |
| Q8 | passing, fusion deterministic |

## Architecture

`stint_evidence.py` (new, ~600 lines) composes:

- `_resolve_stint` — canonical stint identity only (UNAVAILABLE if missing)
- `_select_common_laps` — 6E clean-lap rules **plus telemetry coverage for
  both drivers** (a spec §7 candidate criterion, implemented because the 6D
  telemetry policy samples 12 laps across the race, so per-stint coverage is
  the binding constraint); every exclusion reason reported
- per-lap `fuse_lap_evidence` (6F) as an ordered temporal sequence
- `_trend_block` — OLS slope with `MIN_TREND_OBS = 3`, outliers retained
- `_hypothesis_summary` — deterministic temporal rules (no scores)
- `_change_point` — thresholded first/second-half slope comparison
- cumulative residual conservation identity

## Common-lap selection (measured effect)

Moving telemetry coverage into the candidate rules (from post-selection
filtering) converted thin fusions into real trajectories — e.g. 2022 R4
stint 2 went from 3 to 5 valid laps; 2022 R2 stint 2 from 2 to 6 with
`CHANGE_DETECTED`. Coverage scan of all 93 telemetry sessions: 108 stint
pairs with ≥4 telemetry-covered clean common laps; the rest are reported
honestly as thin/INSUFFICIENT.

## Temporal model & performance trend

Trajectory preserves lap order with `stint_lap_index`; stats are mean,
median, min, max, first, last; trend is the OLS slope (s per stint lap) with
the minimum-observation rule; cumulative gap semantics state "across the
SELECTED comparable laps — not total race time lost".

Representative case (2022 R4, max-verstappen vs sergio-perez, stint 2,
5 valid laps):

- trajectory: −0.574 s → +0.428 s, mean −0.019 s
- trend: **+0.0726 s/stint lap (widening)** — descriptive, not causal
- cumulative gap −0.093 s; cumulative residual −3.1433 s, conserved exactly
- hypothesis evolution: braking / tyre state / race control
  CONTRADICTED_OVER_TIME; corner speed / throttle / DRS INTERMITTENT
- determinism hash `a2fb8b694db35155` (stable across fresh subprocesses)

## Hypothesis evolution semantics (tested)

CONSISTENTLY_SUPPORTED (≥3 evaluable, zero contradictions, full support) ·
MOSTLY_SUPPORTED (≥0.7 support fraction, zero contradictions) ·
INTERMITTENTLY_SUPPORTED · CONTRADICTED_OVER_TIME · NOT_SUPPORTED ·
INSUFFICIENT_EVIDENCE (<2 evaluable; positive claims need ≥3 laps — a 2/2
support stint is *insufficient*, not "consistent"). The 6F deficit-premise
gate propagates: all-NOT_TESTABLE laps contribute no evaluable observations.

## Telemetry trends

Per-signal per-lap values extracted from 6F evidence items form series with
the same trend rule. On the Q9 matrix, all four signal families produce
VALID trend blocks on ≥3-lap stints (speed/throttle/brake/DRS), enabling
emerging/persisting/disappearing pattern statements.

## Residual trajectory & cumulative gap

Cumulative identity `observed = pace_component + residual` holds on every
matrix row (test-enforced 1e-6). Residuals trend independently; the
cumulative residual is never assigned to a hypothesis.

## Context transitions

Regime changes (restriction / rain-in-window / compound) between consecutive
valid laps are recorded with lap number and from/to regimes. Measured: 1
transition on the 2022 R9 stint 3 row; 0 elsewhere in the matrix.

## Change-point analysis

Deterministic thresholded segmented-slope comparison (thresholds 0.03 s/lap
slope delta, ≥3 observations per half, ≥6 laps total). Measured: 2022 R2
stint 2 → CHANGE_DETECTED (narrowing); three rows NOT_TESTABLE (too few
laps); no false STABLE claims.

## Surfaces

- **MCP** `fuse_historical_stint_evidence` (tool #31): bounded inputs
  (max_laps 2–16 explicitly enforced — the generic validator ignores numeric
  ranges, so the tool rejects out-of-range values itself), unknown parameters
  rejected, ~13 KB payload cap by construction, output-hashed, deterministic
  over the real server subprocess.
- **API** `GET /api/catalog/stint-evidence/{season}/{round}?stint=N` —
  drivers default to the canonical telemetry pair; stint defaults to the
  canonical stint with the most telemetry-covered common clean laps.
- **Frontend** `StintEvidenceView.tsx` — renders the server-computed
  trajectory with context annotations, trend, hypothesis-evolution facts,
  context transitions, change-point and residual conservation. No client-side
  engineering calculation.

## Q9 benchmark results (real data, 7-row matrix, 2021–2025, multiple circuits)

| Row | Laps | Pattern | Slope (s/lap) | Change-point | Tyre consistency |
|---|---|---|---|---|---|
| 2022 R4 s2 | 5 | WIDENING | +0.0726 | NOT_TESTABLE | NOT_CONSISTENT (tyre evidence contradicted) |
| 2022 R9 s3 | 3 | NARROWING | −0.5090 | NOT_TESTABLE | NOT_TESTABLE (no valid trend rule for narrowing) |
| 2022 R2 s2 | 6 | NARROWING | −0.1896 | CHANGE_DETECTED | NOT_TESTABLE |
| 2021 R10 s2 | 5 | WIDENING | +0.0210 | NOT_TESTABLE | NOT_CONSISTENT |
| 2023 R1 s1 | 2 | INSUFFICIENT | — | NOT_TESTABLE | NOT_TESTABLE |
| 2022 R5 s1 | 1 | INSUFFICIENT | — | — | — |
| 2022 R12 s2 | 6 | NARROWING | −0.0418 | NOT_TESTABLE | NOT_TESTABLE |

- Q9.1 stable gap: no verified stable stint exists in the coverage; the rule
  is unit-tested pure (STABLE threshold 0.02 s/lap) and the matrix honestly
  reports the nearest case (−0.0418). No fabricated stable case.
- Q9.2/Q9.3 widening/narrowing: verified on real slopes.
- Q9.4 telemetry trend persistence: VALID metric trends on all ≥3-lap rows.
- Q9.5 tyre consistency: widening gap + tyre evidence CONTRADICTED_OVER_TIME
  ⇒ assessment `NOT_CONSISTENT` — the system refuses tyre attribution.
- Q9.6 context transitions: structured, counted per row.
- Q9.7 contradictions: present on 3 rows.
- Q9.8 insufficient laps: 3 rows honest INSUFFICIENT.
- Q9.9 residual conservation: identity holds on every row.
- Q9.10 full investigation: MCP tool registered and verified live.
- Q9.11 replay determinism: full-matrix JSON byte-identical across runs.

## Negative controls (all executed)

1950 → UNAVAILABLE · absent stint (99) → UNAVAILABLE · same driver →
UNAVAILABLE · 2023 R9 stint 2 (0 comparable laps) → INSUFFICIENT_EVIDENCE ·
1-valid-lap stint → trend INSUFFICIENT_EVIDENCE · deficit premise absent →
all hypotheses NOT_TESTABLE (propagated from 6F) · counterfactual gate →
UNSUPPORTED preserved · unbounded `max_laps=99` → ToolError.

## Determinism

In-process repeat: identical (test-enforced sha256). Fresh subprocess ×2:
`a2fb8b694db35155` — matches in-process. MCP output hash identical across
calls. Q9 full-matrix replay byte-identical. No timestamps or random IDs in
analytical output.

## Idempotency & storage

Derived on read; size+mtime of the canonical DB proven unchanged during
fusion; no derived tables; no telemetry duplication; **zero growth**.

## Performance (405 MB DB, 787,555 telemetry rows)

| Path | p50 | max |
|---|---|---|
| fuse_stint_evidence (≤10 lap fusions per stint) | 955 ms | 1286 ms |
| MCP execute (validate + fuse + hash) | 894 ms | — |

vs 6F lap fusion p50 87 ms — a stint is ≤10 lap fusions plus temporal
aggregation, so ~10× is expected arithmetic, not a regression; still well
inside interactive bounds. No new indexes added (none needed).

## Tests

`tests/unit/test_stint_evidence.py` (36): pure trend math (7), hypothesis
summary rules (9), change-point (2), live shape/trajectory/evolution/
conservation/gate/determinism (10), negative controls (5), MCP + API (2),
investigation integration (1). `tests/unit/test_q9_benchmarks.py` (14).
Full suite: **308 passing** (258 baseline + 50 new). No existing test
weakened.

## Security

Bounded MCP with explicit numeric-range enforcement; unknown parameters
rejected; read-only; no raw telemetry dumps (max_laps cap bounds all
downstream extraction); secret scan of committed tree clean.

## Known limitations

1. Per-stint telemetry coverage is bounded by the 6D policy (12 laps/race);
   many stints are honestly INSUFFICIENT. Widening coverage is a data-activation
   decision, not a code change.
2. No verified STABLE-pattern stint exists in current coverage; the rule is
   unit-tested, the matrix reports the observation.
3. Change-point analysis is a bounded first/second-half comparison — adequate
   for one transition, not multiple.
4. Traffic/dirty-air, tyre grip/temperature, telemetry-profile
   counterfactuals: unchanged 6E/6F limitations (UNSUPPORTED/DOES_NOT_TEST).
5. Cumulative gap covers selected laps only (semantics stated in output).

## Files changed

- `src/racewise/data/historical/stint_evidence.py` (new)
- `src/racewise/data/historical/q9_benchmarks.py` (new)
- `src/racewise/tools/historical.py` (FuseStintEvidenceTool, registration)
- `src/racewise/api/app.py` (stint-evidence endpoint)
- `apps/web/src/StintEvidenceView.tsx` (new), `App.tsx`
- `tests/unit/test_stint_evidence.py`, `tests/unit/test_q9_benchmarks.py` (new)
- `docs/PHASE_6G_STINT_EVIDENCE.md`, `docs/PHASE_6G_COMPLETION_REPORT.md`

## Verification commands

```bash
python -m pytest -q                                                    # 308 passed
python -m pytest tests/unit/test_stint_evidence.py tests/unit/test_q9_benchmarks.py -q
cd apps/web && npm run build                                           # passes
# MCP over real server: 31 tools; fuse_historical_stint_evidence live; 1950 → UNAVAILABLE
# determinism: fresh subprocess sha256 a2fb8b694db35155 (2022 R4 stint 2)
# storage: DB size+mtime unchanged during fusion (zero-write proof)
```

## Final readiness

**PHASE 6G STATUS: READY_WITH_DOCUMENTED_LIMITATIONS**

All DoD items verified; bounded limitations are data-coverage constraints and
preserved honesty gates, each explicitly represented in outputs.
