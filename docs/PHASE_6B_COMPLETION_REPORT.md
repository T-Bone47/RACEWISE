# PHASE 6B COMPLETION REPORT

Measured 2026-09-20. Every number below was queried from the live canonical store, ingestion reports, or test output during this phase. No projections.

## 1. DATA SCALE (primary objective)

FastF1 modern engineering data expanded from 6 sessions (Phase 6A) to **379 sessions across all 8 seasons 2018–2025**.

Ground truth (SQL counts against `data/canonical/canonical.db`):

| Season | Sessions w/ stints | Stint rows (season) |
|---|---|---|
| 2018 | 41 | 2,616 |
| 2019 | 42 | 2,881 |
| 2020 | 34 | 2,414 |
| 2021 | 47 | 3,247 |
| 2022 | 47 | 3,203 |
| 2023 | 50 | 3,532 |
| 2024 | 60 | 4,066 |
| 2025 | 58 | 4,073 |
| **Total** | **379** | **26,032** |

Full-store modern totals:

| Table | Rows |
|---|---|
| canonical_stints | 26,032 |
| canonical_weather | 42,938 |
| canonical_race_control | 20,868 |
| canonical_lap_times (provider=fastf1) | 251,868 |
| Database size | 146.2 MB (was 49.6 MB after 6A) |

Scope: priority levels 1–3 (RACE, QUALIFYING, SPRINT, SPRINT_QUALIFYING). Practice sessions deliberately not ingested — no deterministic consumer exists. Telemetry remains DEFERRED (policy module in place, default OFF).

### Ingestion runtime (measured)

Season batch runs (final successful runs): 2019 = 378 s, 2021 = 22 s (resume), 2022 = 250 s, 2023 = 292 s, 2024 = 128 s, 2025 = 3,964 s. Total ingestion wall time across the phase ≈ 88 min of compute, dominated by 2025 (first-run downloads) and rate-limit windows.

## 2. INGESTION FRAMEWORK (scaling.py)

- **Resumable**: per-session checkpoints in `data/ingestion_state/`; resume skips completed sessions (verified: 2021 re-run processed only missing sessions).
- **Idempotent**: verified by double re-ingestion of 2023 Bahrain R — identical counts (70 stints / 161 weather / 73 race control / 1,076 laps).
- **Failure isolated**: per-session try/except; one failure never aborts a season.
- **Rate-limit aware**: fixed during this phase — the engine now pauses with capped exponential backoff on FastF1's 500-calls/h limiter instead of burning the schedule; parallel batches were eliminated after they competed for the shared quota (sequential execution enforced).
- **Name-based session discovery**: fixed during this phase — discovery now maps the schedule's actual `Session1..5` names instead of assuming every event has SPRINT/SPRINT_QUALIFYING (this had misclassified 42 real 2019 sessions as failures).
- **Structured reports**: per-season JSON reports with run_id, per-session status (SUCCESS / UNAVAILABLE / FAILED_VALIDATION / FAILED_PROVIDER), row counts, cache hits, errors.

Note on report files: intermediate report JSONs contain superseded statuses from runs made before the discovery/backoff fixes; the database is authoritative and all validators pass on the final state.

## 3. BUGS FOUND AND FIXED DURING SCALING

1. **`TypeError: list - set`** in batch diffing (fixed; had aborted 2020 batch).
2. **Discovery enumerating nonexistent sprint sessions** → misclassified FAILED_PROVIDER (fixed via schedule-name mapping).
3. **Race-control duplicate events**: source re-delivers events with identical (timestamp, category, message) but different `Lap`; dedup key corrected to event identity, and `event_id` made content-derived so identity is stable across runs. Stale rows purged; 2023 re-ingested clean (27 SUCCESS, 0 failures).
4. **Race-control ordering gate too strict**: the 2020 Styria feed genuinely delivers "GREEN LIGHT - PIT EXIT OPEN" after "DRS DISABLED" (provider backfill quirk). Gate now measures *systematic* disorder (share of inversions) instead of failing on a single provider artifact.
5. **FastF1 compound vocabulary**: unknown/None compounds counted but never fabricated; validator updated accordingly.

## 4. DATA VALIDATION

`validate_canonical_data` — **14/14 checks pass** on the final store: FK integrity (0 violations via `PRAGMA foreign_key_check`), duplicate stints/pit stops/weather timestamps/race-control events = 0, lap/stint range sanity, compound vocabulary, timestamp ordering (duration-aware), driver/session FK validity, provider provenance completeness, modern-rows-on-F1DB-sessions. `PRAGMA integrity_check` = ok.

## 5. CATALOG EXPLORER

Backend (`catalog_api.py`, FastAPI endpoints in `api/app.py`):
- `list_sessions`: filters season/range/country/circuit/session_type/provider/availability/capability + free-text search; pagination (default 25, max 200), deterministic ordering (verified identical pages).
- Verified post-scale: 2023 capability=stints → 50 sessions; 2024 capability=weather → 60; search "Bahrain" → 121; total RACE sessions → 1,172.
- `session_detail`: identity + per-capability counts + availability + providers (2023 R1: results 20, qualifying 20, pit stops 50, laps 1,076, stints 70, weather 161, race control 73; providers f1db+fastf1).

Frontend (`apps/web/src/CatalogExplorer.tsx`): filter bar, capability states (✓ AVAILABLE / ◐ PARTIAL / — UNAVAILABLE), pagination, session detail, Investigate flow. Build passes.

## 6. CROSS-PROVIDER VALIDATION (expanded)

FastF1-vs-F1DB matrix, one sampled race per season + 2023 triples (measured this phase):

| Round | MATCH | MISMATCH | NOT_AVAILABLE |
|---|---|---|---|
| 2018 Australia | 8 | 0 | 0 |
| 2020 Styria | 1 | 6 | 1 |
| 2021 Britain | 7 | 1 | 0 |
| 2022 Bahrain | 6 | 2 | 0 |
| 2023 Bahrain | 6 | 2 | 0 |
| 2024 Bahrain | 8 | 0 | 0 |
| 2025 Australia | 6 | 2 | 0 |
| **Total** | **42** | **13** | **1** |

New semantic difference documented (observed, not assumed): **2020 FastF1 lap numbering runs systematically 4 lower than F1DB for every classified driver** — both values preserved. Existing documented differences (pit-in-lap vs recorded stops, red-flag classification vs running order, off-by-one conventions) reproduced consistently. Full detail in `CROSS_PROVIDER_VALIDATION_MATRIX.md`.

## 7. CI GATES

- `tests/unit/test_schema_gate.py` — in-memory canonical store built from deterministic fixtures; schema + FK + provenance gates.
- `tests/unit/test_ci_gates.py` — availability logic, no-fabrication patterns, canonicalizer determinism, regression-hash registry (1950: `1487764bf78a3c38`, 2000: `43434c839bd05315`, 2023: `749879bc5f037359`, cross-provider 1950: `276591d5d8c104bd`).
- No CI workflow downloads datasets; heavy validation is manual (`scripts/audit_database_growth.py`, validators, ingestion CLI).

## 8. INVESTIGATIONS

- Golden: 1950 British PASS, 2000 Australian PASS, 2023 Bahrain PASS — **all four registry hashes reproduce exactly in a fresh subprocess** (restart/replay PASS).
- Benchmarks Q1–Q5 + deep 2023 Bahrain: all PASS with unchanged numbers (Q1 Δ −0.1686 s/lap VER vs PER HARD; counterfactual pit 36→31 = −1.45 s from the deterministic simulator). Scaling did not alter 2023 Bahrain evidence — expected, since its inputs were already complete.
- Negative control preserved: 1950 benchmark → INSUFFICIENT_EVIDENCE.

## 9. QUERY PERFORMANCE (measured, 146 MB store)

| Query | p50 | p95 |
|---|---|---|
| catalog page (50 rows) | 0.17 ms | 0.44 ms |
| session detail counts | 6.23 ms | 8.78 ms |
| stints by session | 1.42 ms | 2.94 ms |
| weather by session | 1.41 ms | 1.95 ms |
| race control by session | 1.31 ms | 1.78 ms |
| driver lap history (500 rows) | 0.50 ms | 0.91 ms |
| availability lookup | 0.04 ms | 0.05 ms |

No index work required at this scale.

## 10. MCP

24 tools verified over the real server subprocess (initialize → tools/list → tools/call). `get_historical_stints` 2023 R1 returns 70 stints with provider=fastf1; `search_historical_catalog` and weather/race-control tools return live canonical rows.

## 11. TESTS

**186 passed** (baseline 162; +24 this phase: scaling engine, rate-limit behavior, schema gates, CI gates, catalog API). Full suite runtime ≈ 4 min.

## 12. SECURITY

`racewise.env` (real API keys) confirmed gitignored; no env/cache/DB artifacts tracked; secret scan of HEAD clean. Changes committed in logical commits without touching pre-existing modifications.

## 13. KNOWN LIMITATIONS

1. FastF1 coverage starts 2018; pre-2018 modern engineering is genuinely UNAVAILABLE.
2. 2025 season reports 2 FAILED_PROVIDER sessions (source feed errors at ingest time); retryable via resume.
3. 22 sessions carry race control but 0 rows for 2 sessions where the feed returned none — availability stays count-derived.
4. Intermediate ingestion report JSONs reflect superseded run states; DB is authoritative.
5. Telemetry deferred; bounded policy defined (`telemetry_policy.py`), activation requires a deterministic consumer (Phase 6C).

## PHASE 6B STATUS: READY

Recommended next phase (6C): Bounded telemetry consumer + activation under the existing `TelemetryPolicy` (default OFF, per-session opt-in), now that ≥1 deterministic consumer can be defined against 379 verified sessions.
