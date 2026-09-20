# Phase 6D Completion Report — Bounded Telemetry Scaling (2022–2025 Races)

Executes the Phase 6D recommendation from `PHASE_6C_COMPLETION_REPORT.md`:
extend bounded telemetry from the 5-session pilot to **every ingested RACE
session of 2022–2025**, using the existing policy-gated pipeline unchanged.
All numbers measured against the live store after the run.

## 1. What ran

- Command: `racewise.data.historical.cli ingest-seasons --start-year 2022
  --end-year 2025 --levels 1 --force --telemetry`
- Scope: priority level 1 only (RACE sessions); `TelemetryPolicy(enabled=True)`
  with unchanged 6C bounds — top-2 classified finishers, 12 evenly spaced clean
  laps each, 6 signals, per-session sample cap.
- Pilot first: 2022 rounds 1–3 measured at +25,446 rows / +2.4 MB / ~20 s per
  session before the full run was launched (storage budget respected).
- Execution mode: single background process (FastF1's shared 500-calls/h quota
  makes parallel runs counterproductive — established in Phase 6B).

## 2. Result

| Metric | Before (6C) | After (6D) |
|---|---|---|
| Telemetry sessions | 5 | **93** (1× 2021 pilot + 92 races 2022–2025) |
| Telemetry rows | 45,010 | **787,555** (+742,545) |
| Distinct telemetry drivers | 10 | **30** (top-2 per race; overlaps across seasons) |
| Database size | 156.3 MB | **386.4 MB** (+230.1 MB) |
| Cost | — | ~325 B/row, ~8,468 samples/session, ~2.4 MB/session |

Per-season coverage (sessions with telemetry / RACE sessions ingested):

| Season | Sessions | Rows |
|---|---|---|
| 2021 | 1 / 1 (pilot) | 9,504 |
| 2022 | 22 / 22 | 186,068 |
| 2023 | 22 / 22 | 181,800 |
| 2024 | 24 / 24 | 215,521 |
| 2025 | 24 / 24 | 194,662 |

Ingestion outcome: **92 SUCCESS / 0 FAILED_VALIDATION / 0 FAILED_PROVIDER /
0 UNAVAILABLE** for the 2022–2025 run (2021 pilot session already present).
Runtime ≈ 63 minutes wall-clock including rate-limit backoffs.

## 3. Verification (all executed)

| Check | Result |
|---|---|
| Validators | 14/14 pass |
| FK check / integrity | 0 violations / ok |
| Idempotency | 2024 R1 re-ingested → identical counts (8,698 before = after; global 787,555 unchanged) |
| Catalog | rebuilt; **93 sessions** show telemetry AVAILABLE of 5,268 (count-derived) |
| Golden hashes (fresh subprocess) | 1950 / 2000 / 2023 / cross-provider all **STABLE** |
| Full test suite | **201 pass** (1 scope test updated: 5 → 93 sessions, documented in the test) |
| Frontend build | Vite build passes (~1.1 s) |
| MCP over real server | 27 tools; summary (9,705 samples, 15 ms), lap telemetry (2,000 samples, 75 ms, truncated flag), compare PASS 1.659 s (2024 R14 PIA vs HAM) |

## 4. Performance at 386 MB

| Path | p50 | p95 |
|---|---|---|
| `get_lap_telemetry` 2023 R1 (3 signals) | 6.8 ms | 21.2 ms |
| `get_lap_telemetry` 2024 R14 (2 signals) | 3.7 ms | 9.6 ms |

No index changes needed — the `(session_id, driver_id, lap_number)` index from
6C keeps per-lap lookups flat as the table grows ~17×. MCP compare remains
sub-100 ms end-to-end.

## 5. Investigation refresh

- Q6 now passes on sessions across **all four scaled seasons** (verified:
  2022 R10 SAI vs PER 0.857 s; 2023 R1 VER vs PER 2.084 s; 2023 R14 VER vs PER
  0.941 s; 2024 R1 VER vs PER 3.544 s; 2024 R14 PIA vs HAM 1.659 s; 2025 R1 VER
  vs NOR 0.503 s; 2025 R12 PIA vs NOR 2.936 s).
- Q6 2023 determinism: hash `fdf98e15bd5c7dfc` unchanged — scaling added no rows
  for already-ingested sessions (idempotent overwrite).
- Full benchmark suite: Q1–Q6 + telemetry investigation + deep 2023 all PASS.
- Matrix unchanged: 2018/2020 PARTIAL (no telemetry — correct), 2021/2022/2024/
  2025 PASS.
- Note: Q6 callers must use the *ingested* top-2 drivers (canonical
  classification at ingestion time), not assume the race winner is driver one
  of the telemetry pair — e.g. 2024 R14 telemetry covers PIA/HAM.

## 6. Scope discipline

- Only RACE sessions (level 1). No practice, no qualifying, no sprint telemetry.
- Only top-2 classified finishers per race. No all-driver ingestion.
- `TelemetryPolicy` remains default OFF; `--telemetry` stays explicit opt-in.
- The 6D scope is asserted by test (`test_bounded_session_set_and_availability`:
  exactly 93 sessions, all RACE, 2021–2025).

## 7. Known limitations

1. QUALIFYING/SPRINT sessions have no telemetry (policy `session_codes=("R",)`);
   extend only with a demonstrated consumer question.
2. 30 distinct drivers across 4 seasons reflects the top-2 rule, not fleet
   coverage.
3. ~2.4 MB/session growth: a full-grid, all-laps activation would cost roughly
   20× more (~45 MB/session) and is deliberately not done.
4. Two Q6 spot-checks initially returned INSUFFICIENT_EVIDENCE when queried with
   drivers outside the ingested pair — correct behaviour (UNAVAILABLE ≠ error),
   documented in §5.

## 8. Next (not started)

- QUALIFYING telemetry if a qualifying-specific consumer question emerges.
- Per-lap telemetry-to-lap-facts joins for stint-level loss attribution.
- Storage: WAL checkpointing and eventual VACUUM policy if the DB exceeds ~1 GB.

## PHASE 6D STATUS: READY
