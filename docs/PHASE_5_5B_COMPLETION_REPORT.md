# PHASE 5.5B COMPLETION REPORT

Date: 2026-09-19. Every number below was queried from the live database or captured from actual test runs on this date. No estimates.

## DATA FOUNDATION

| Entity | Rows | Status |
|---|---|---|
| Seasons (1950–2026) | 77 | VERIFIED |
| Circuits | 78 | VERIFIED |
| Drivers | 917 | VERIFIED |
| Constructors | 187 | VERIFIED |
| Races | 1,172 | VERIFIED |
| Sessions | 5,268 | VERIFIED |
| Results | 28,189 | VERIFIED |
| Qualifying (+grids/practice) | 118,165 | VERIFIED |
| Pit stops | 22,506 | VERIFIED |
| Laps (fastest-lap facts) | 17,148 | VERIFIED |
| Stints | 0 | UNAVAILABLE (not in F1DB; correct) |
| Weather | 0 | UNAVAILABLE (not in F1DB; correct) |
| Race control | 0 | UNAVAILABLE (not in F1DB; correct) |
| Session catalog | 5,268 | VERIFIED |

Session types (12): RACE 1,172 · QUALIFYING 1,172 · FP1 721 · FP2 694 · FP3 431 · WARMING_UP 324 · QUALIFYING_2 293 · QUALIFYING_1 292 · PRE_QUALIFYING 79 · FP4 36 · SPRINT 30 · SPRINT_QUALIFYING 24.

Source: F1DB v2026.14.0, manifest with 20 SHA-256-hashed files at `data/manifests/f1db_2026.14.0_manifest.json`.

## ARCHITECTURE DELIVERED

- **Deterministic identity**: session ids = SHA-256(`f1db:<raceId>:<TYPE>`)[:16]; detail-row ids derived from source business keys. Random UUIDs eliminated.
- **Idempotency**: consecutive ingestion runs produce identical counts (verified live; also unit-tested). Upserts via `ON CONFLICT DO UPDATE`, transactional `executemany`.
- **FK integrity**: `PRAGMA foreign_key_check` → 0 violations.
- **Availability index**: `canonical_session_catalog` rebuilt from actual row counts; flags AVAILABLE/PARTIAL/UNAVAILABLE. Zero year-based heuristics (grep gate + tests enforce).
- **Tool layer / MCP**: `HistoricalSessionContext` + historical tools wired into `src/racewise/mcp/server.py`; tools/list and representative calls verified over the real server (integration tests).
- **No-fabrication gate**: grep scan for `year >= 20xx` / default-weather / synthetic-stint / hardcoded-driver patterns → clean.

## HISTORICAL COVERAGE (catalog-verified)

- **1950**: results + grid/qualifying AVAILABLE; pit stops/stints/weather/race control/telemetry UNAVAILABLE.
- **2000**: results, qualifying, pit stops (23), fastest laps AVAILABLE; compounds/telemetry UNAVAILABLE.
- **2023 Bahrain**: results (20), qualifying (20), pit stops (50), fastest laps (20) AVAILABLE; stints/weather/race-control from F1DB UNAVAILABLE (FastF1 supplies telemetry-shaped context where cached).

## INVESTIGATIONS

| Golden race | Result | Hash |
|---|---|---|
| 1950 British GP | PASS | `1487764bf78a3c38` |
| 2000 Australian GP | PASS | `43434c839bd05315` |
| 2023 Bahrain GP (incl. deterministic counterfactual `simulate_pit_timing`) | PASS | `b56bc01979f048e2` |

## REPLAY

Fresh-subprocess recomputation of all investigation payloads → all hashes identical. **REPLAY: PASS.**

## CROSS PROVIDER

F1DB vs Jolpica (cached), 1950 British GP: 94 comparisons → 41 MATCH, 51 NOT_AVAILABLE, 2 MISMATCH (both preserved; policy: F1DB is foundation of record, mismatches surfaced, never auto-merged). **PARTIAL** (coverage limited by Jolpica cache contents; validator scales to any overlapping season).

## PROVIDER BEHAVIOR

- **Jolpica**: configurable rate limit, exponential backoff with jitter, Retry-After/429/5xx/timeout handling, max retries, cache + resume. Mocked tests cover 429→429→200 and 429×3→failure.
- **FastF1**: 2023 Bahrain/Saudi/Australia sessions verified loadable from cache; older session verified to return DATA_UNAVAILABLE rather than fake support.

## TESTS

**143 passed, 0 failed** (`python -m pytest -q`, ~115 s). Baseline before phase: 101. +42 new tests: canonicalization/idempotency/FK (15), Jolpica retry, golden investigations, historical tools + MCP visibility, cross-provider, availability derivation.

## PERFORMANCE (actual)

- Full F1DB canonicalization: **~11–13 s** wall clock, 175k+ rows, ~49.6 MB DB → roughly 15k rows/s session-level throughput.
- Golden investigations (all 3 + cross-provider): a few seconds, in-memory, no repeated full-table scans.
- Session-level ingestion uses chunked transactions; peak memory stays bounded (streamed CSV iteration).

## KNOWN LIMITATIONS

1. F1DB contains no stints, weather, race control, or lap-by-lap telemetry — those tables stay empty until FastF1/OpenF1 integration; availability is declared UNAVAILABLE, never fabricated.
2. `canonical_lap_times` holds fastest-lap facts (one row per driver per race), not full lap telemetry.
3. Sprint sessions with a scheduled date but no source detail rows exist with zero capabilities (source gap, honestly flagged).
4. Cross-provider validation currently limited to races where both providers have cached data (1950 British GP today).
5. Jolpica cache coverage is thin; more seasons require network runs (rate-limited by design).

## PHASE 6 READINESS

**READY** — for the data-foundation prerequisites Phase 6 depends on: canonical identity is deterministic and idempotent, availability is data-derived, MCP/tools expose the catalog, and 143 tests guard it. PostgreSQL/Redis/queues/auth remain intentionally deferred (correctly out of scope for this phase).

## VERIFICATION COMMANDS ACTUALLY EXECUTED

- `git status`, `python -m pytest -q` → 143 passed
- canonical coverage audit (SQL counts above), session coverage audit (12 types)
- F1DB idempotency re-run → IDEMPOTENT; `PRAGMA foreign_key_check` → 0
- Jolpica retry tests (mocked 429 sequences) → pass
- FastF1 representative-session checks (3 modern + 1 old) → pass / DATA_UNAVAILABLE
- cross-provider validation → 41/51/2
- golden investigations 1950/2000/2023 → PASS ×3
- counterfactual test → deterministic output persisted
- restart/replay → REPLAY PASS (hashes identical)
- no-fabrication grep scan → clean
- secret scan: no `.env`, credentials, caches, or DBs staged for commit
