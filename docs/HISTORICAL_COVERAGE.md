# Historical Coverage — Verified

Status legend: `VERIFIED` (queried from the canonical store on 2026-09-19), `UNAVAILABLE` (provider does not supply; no fabrication).

Source of record: F1DB v2026.14.0 (manifest: `data/manifests/f1db_2026.14.0_manifest.json`, 20 files hashed).

## Canonical record counts (queried, not estimated)

| Table | Rows |
|---|---|
| canonical_seasons | 77 |
| canonical_circuits | 78 |
| canonical_drivers | 917 |
| canonical_constructors | 187 |
| canonical_races | 1,172 |
| canonical_sessions | 5,268 |
| canonical_results | 28,189 |
| canonical_qualifying | 118,165 |
| canonical_pit_stops | 22,506 |
| canonical_lap_times | 17,148 (fastest-lap facts only — see note) |
| canonical_stints | 0 |
| canonical_weather | 0 |
| canonical_race_control | 0 |
| canonical_session_catalog | 5,268 |

## Sessions by type

| Session type | Sessions |
|---|---|
| QUALIFYING | 1,172 |
| RACE | 1,172 |
| FREE_PRACTICE_1 | 721 |
| FREE_PRACTICE_2 | 694 |
| FREE_PRACTICE_3 | 431 |
| WARMING_UP | 324 |
| QUALIFYING_1 | 292 |
| QUALIFYING_2 | 293 |
| PRE_QUALIFYING | 79 |
| FREE_PRACTICE_4 | 36 |
| SPRINT | 30 |
| SPRINT_QUALIFYING | 24 |

Sessions are constructed only when F1DB represents them (scheduled date in `f1db-races.csv` **or** detail rows exist). No invented sessions.

## Era snapshots (from canonical_session_catalog, session_type=RACE)

| Race | Results | Qualifying (grid) | Pit stops | Fastest-lap facts | Stints | Weather | Race control |
|---|---|---|---|---|---|---|---|
| 1950 British GP (R1) | AVAILABLE (21) | AVAILABLE (20, grid rows) | UNAVAILABLE | AVAILABLE (1) | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| 1950 Monaco (R2) | AVAILABLE (21) | AVAILABLE (20) | UNAVAILABLE | AVAILABLE (1) | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| 2000 Australian GP | AVAILABLE (22) | AVAILABLE (22) | AVAILABLE (23) | AVAILABLE (21) | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| 2023 Bahrain GP | AVAILABLE (20) | AVAILABLE (20) | AVAILABLE (50) | AVAILABLE (20) | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |

## What F1DB does and does not contain

- **Results**: per driver, all races 1950–2026. Status text (DNF/DNS/DNQ semantics) preserved verbatim.
- **Qualifying/grids**: qualifying results files exist for most of history; grid-position files fill sessions with no qualifying file. Never double-counted (verified: 0 sessions have both).
- **Pit stops**: per-stop rows 1994 onward (22,506 rows). Earlier eras are `UNAVAILABLE`, never zero.
- **Fastest laps**: 17,148 rows stored in `canonical_lap_times` **as fastest-lap facts only** (one row per driver per race). This is NOT lap-by-lap telemetry; `is_accurate`/sector columns are NULL. F1DB has no lap-by-lap data.
- **Sprint**: 590 sprint results + 466 sprint-qualifying rows (2021–2026).
- **Practice/warm-up**: 41,268 practice + 7,683 warm-up rows (stored as qualifying-table rows per position/time semantics).
- **Stints, weather, race control**: not present in F1DB v2026.14.0 → tables exist with 0 rows and availability is `UNAVAILABLE`. Modern depth comes only from FastF1/OpenF1 integration.
- **Pre-qualifying / Q1/Q2 eras**: preserved as their own session types (`PRE_QUALIFYING`, `QUALIFYING_1/2`), not forced into modern Q1/Q2/Q3 semantics.

## Availability is data-derived

Availability flags are computed by querying actual canonical record counts (`rebuild_catalog`); no season-year heuristics anywhere in the codebase (verified by the no-fabrication grep gate).
