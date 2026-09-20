# PHASE 6H — Race-Level Gap Decomposition & Evidence Synthesis

Status: **READY_WITH_DOCUMENTED_LIMITATIONS**

## Executive summary

Phase 6H completes the 6E→6F→6G→6H evidence chain: lap attribution → lap
evidence fusion → stint evolution → **race-level gap decomposition**. The
output is a deterministic, evidence-bounded race timeline that shows where
the observed performance relationship was created, recovered or changed —
with the official classified gap and the analytical comparable-lap gap
preserved as **distinct, never-reconciled quantities**, non-comparable
intervals itemized, telemetry gaps preserved, pit mechanisms honestly
unproven, and residuals never assigned. Fully derived on read: zero storage
growth.

## Starting baseline (verified)

| Item | Value |
|---|---|
| Tests | 308 passing (full suite re-run at phase start) |
| Telemetry | 93 sessions / 787,555 rows |
| MCP tools | 31 |
| Database | 405.2 MB |
| Q9 | passing, stint evidence deterministic |

## Race definition and driver comparison

Race/session identity resolved through the canonical catalog; both drivers
validated against canonical race-result participation (missing driver →
UNAVAILABLE). No winner/runner-up assumption: driver A/B are explicit
parameters (API defaults to the session's canonical telemetry pair only as a
view convenience).

## Official final gap (authoritative)

From canonical `canonical_results.milliseconds` with equal laps-completed and
equal classification-status family required; otherwise `gap_s = None` with
the reason. Measured: 2023 R1 VER/PER → **11.987 s** (matches the classified
finishing gap); 2024 R1 → 22.457 s; 2022 R4 → 16.527 s; 2024 R14 → 0.647 s;
2025 R1 → 0.895 s. Never reconstructed from lap sums.

## Analytical comparable gap (different quantity)

Cumulative observed delta across comparable laps only. Measured 2023 R1:
**14.066 s** across 47 comparable laps vs official 11.987 s — reported side
by side with "no equality is implied". The most instructive case: 2025 R1
official +0.895 s vs analytical −23.558 s across 42 comparable laps and 15
non-comparable laps (red-flag restarts) — proof that the comparable-lap
sample is not the race, and the system says so instead of reconciling.

## Timeline

Chronological, total = comparable + non_comparable + unavailable
(test-enforced). 2023 R1: 57 laps → 47 comparable / 10 non-comparable
(4 pit-in, 4 pit-out, 2 race-control restriction) / 0 unavailable, reasons
tallied. Race-control matching uses exact lap fields (windows < 5 laps,
test-enforced), never session-level classification.

## Stint decomposition and gap events

Segments follow driver A's canonical stint identity. Descriptive per-segment
patterns (OLS, |slope| ≤ 0.02 s/lap = STABLE, ≥3 laps required):
2023 R1 → [NARROWING, STABLE, STABLE]; 2022 R4 → [NARROWING, STABLE,
WIDENING] (reversal); 2024 R1 → [NARROWING, NARROWING, WIDENING] (reversal);
2025 R1 → [INSUFFICIENT ×3, WIDENING ×3]. Gap events: 3-lap window slope
changes (2023 R1: 24 events) + STINT_CHANGE + TELEMETRY_EVIDENCE_CHANGE —
deterministic labels only.

## Pit windows

Observed comparable-gap transition around each pit lap (before/after),
duration and compounds recorded; **mechanism INSUFFICIENT_EVIDENCE by
design** (stop duration, transit, undercut/overcut, traffic and tyre state
are not isolated by this observation — stated in every row). Measured: 4
windows per typical race, 10 for 2025 R1 (6 pit-stop events in a
red-flag-fragmented race).

## Race-control and weather windows

2023 R1: 1 window (VSC laps); 2025 R1: 6 restriction windows; 2022 R4: 2.
Weather remains per-lap-window (6E semantics); unknown preserved.

## Telemetry evidence and stint chaining

Bounded 6G stint-evidence chaining ranked by telemetry coverage
(`max_segments` 2–24, explicitly enforced). 2023 R1: stints 1–3 chained,
trends VALID on stints 2–3; 2025 R1: stints 1–3 have no comparable telemetry
laps and are preserved INSUFFICIENT — no extrapolation. Hypothesis evolution
per race: e.g. 2022 R4 H1 corner-speed INTERMITTENTLY_SUPPORTED with
H3/H4/H5 CONTRADICTED_OVER_TIME; contradictions and support co-exist across
stints and are never averaged away.

## Residual accounting

Comparable / non-comparable / unavailable counts travel with every result;
the analytical gap's semantics state explicitly that it is NOT the official
race gap and the two MUST NOT be forced to reconcile. Cumulative residuals
remain unassigned (6E/6G invariants preserved upstream).

## Surfaces

- **MCP** `decompose_historical_race_gap` (tool #32): explicit numeric bound
  enforcement (`max_segments` 2–24 — the generic payload validator ignores
  min/max, so the tool rejects out-of-range values itself), unknown
  parameters rejected, bounded payload (~14 KB), output-hashed, deterministic
  over the real server subprocess. Registry: 31 → **32 tools**.
- **API** `GET /api/catalog/race-gap/{season}/{round}` — read-only, bounded,
  server-computed, drivers default to the canonical telemetry pair.
- **Frontend** `RaceGapView.tsx` — renders the official vs analytical gap,
  timeline segments with patterns, gap events, pit windows (mechanism
  unproven), race-control windows, hypothesis evolution with per-stint
  detail, residual accounting and conclusion. No client-side engineering
  calculation.

## Q10 results (5-race matrix, 2022–2025, multiple circuits incl. red-flag race)

| Row | Official | Analytical | Pattern | Reversal | RC windows | Stint trends VALID |
|---|---|---|---|---|---|---|
| 2023 R1 | 11.987 | 14.066 | NARROWING | no | 1 | 2, 3 |
| 2022 R4 | 16.527 | 15.418 | MIXED | yes | 2 | 2 |
| 2024 R1 | 22.457 | 24.872 | MIXED | yes | 0 | 2, 3 |
| 2024 R14 | 0.647 | 2.887 | NARROWING | no | 0 | 2, 3 |
| 2025 R1 | 0.895 | −23.558 | WIDENING | no | 6 | 4 |

Q10.1 stable: no verified stable race in the matrix; the threshold rule is
unit-tested pure and 2023 R1/2024 R14 carry STABLE segments. Q10.2/3/4:
verified (MIXED = reversal on 2 races). Q10.5: all ≥3 stint segments. Q10.6:
pit transitions observed, mechanisms unproven everywhere. Q10.7: exact-lap
windows on 3 races. Q10.8/9: telemetry-supported and telemetry-unavailable
segments both preserved. Q10.10: residual counts on every row. Q10.11:
6-hypothesis race summaries on every row, contradictions surfaced. Q10.12:
MCP verified live. Q10.13: official ≠ analytical on every row (test-enforced).
Q10.14: full-matrix JSON byte-identical across runs.

## Negative controls (all executed)

1950 → UNAVAILABLE · 2018 (no telemetry) → UNAVAILABLE via catalog capability
gate · missing driver → UNAVAILABLE · missing race (round 99) → UNAVAILABLE ·
same driver pair → UNAVAILABLE · no comparable laps → INSUFFICIENT_EVIDENCE ·
telemetry-gap segments preserved INSUFFICIENT (2025 R1 stints 1–3) ·
counterfactual → UNSUPPORTED (gate preserved) · `max_segments=99` → ToolError.

## Determinism

In-process repeat: identical (test-enforced sha256). Fresh subprocess ×2:
`5a905bfa400cfad2` — stable. MCP output hash identical across calls. Q10
full-matrix replay byte-identical. No timestamps/random IDs in analytical
output.

## Storage

Derived on read; DB size+mtime proven unchanged during decomposition; **zero
growth**; no derived tables.

## Performance (405 MB DB, 787,555 telemetry rows)

| Path | p50 | max |
|---|---|---|
| decompose_race_gap (full timeline + bounded stint chaining) | 2144 ms | 2940 ms |
| MCP execute (validate + decompose + hash) | 1845 ms | — |

vs 6G stint fusion p50 955 ms — a race decomposition chains 1–3 stint fusions
plus the full-lap timeline and event analysis, so ~2× stint cost is the
expected composition; still inside interactive bounds. No new indexes.

## Tests

`tests/unit/test_race_gap.py` (26): pure race-hypothesis rules (4), segment
patterns (3), live shape/official-gap/invariants/timeline/pit/rc/bounds/
determinism (10), negative controls (4), MCP + API (2), investigation
integration (1). `tests/unit/test_q10_benchmarks.py` (12). Full suite:
**346 passing** (308 baseline + 38 new). No existing test weakened.

## Security

Bounded MCP with explicit numeric-range enforcement; unknown parameters
rejected; read-only; no raw telemetry dumps; no arbitrary SQL/shell/
filesystem; secret scan of committed tree clean.

## Known limitations

1. Comparable-lap coverage is bounded by the 6D telemetry policy and by
   legitimate exclusions (pit laps, restrictions); non-comparable intervals
   are itemized, not filled.
2. Pit-window mechanisms remain INSUFFICIENT_EVIDENCE — isolating
   undercut/overcut/traffic requires data RACEWISE does not ingest.
3. Race-control windows are exact-lap only; timing-only events are not
   mapped to laps.
4. No verified STABLE full-race pattern in the matrix; rule unit-tested.
5. Official and analytical gaps are different quantities by design; the
   system does not produce a single "race story" number.
6. Telemetry-profile counterfactuals remain UNSUPPORTED.

## Files changed

- `src/racewise/data/historical/race_gap.py` (new)
- `src/racewise/data/historical/q10_benchmarks.py` (new)
- `src/racewise/tools/historical.py` (DecomposeRaceGapTool, registration)
- `src/racewise/api/app.py` (race-gap endpoint)
- `apps/web/src/RaceGapView.tsx` (new), `App.tsx`
- `tests/unit/test_race_gap.py`, `tests/unit/test_q10_benchmarks.py` (new)
- `docs/PHASE_6H_RACE_GAP_DECOMPOSITION.md`, `docs/PHASE_6H_COMPLETION_REPORT.md`

## Verification commands

```bash
python -m pytest -q                                                     # 346 passed
python -m pytest tests/unit/test_race_gap.py tests/unit/test_q10_benchmarks.py -q
cd apps/web && npm run build                                            # passes
# MCP over real server: 32 tools; decompose_historical_race_gap live
# determinism: fresh subprocess sha256 5a905bfa400cfad2 (2023 R1 VER/PER)
# storage: DB size+mtime unchanged during decomposition (zero-write proof)
```

## Final readiness

**PHASE 6H STATUS: READY_WITH_DOCUMENTED_LIMITATIONS**

All DoD items verified; bounded limitations are coverage constraints and
preserved honesty gates, each explicitly represented in outputs.
