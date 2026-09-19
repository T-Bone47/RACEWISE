# F1DB → RACEWISE Canonicalization

Verified implementation notes for Phase 5.5B. Source: F1DB v2026.14.0.

## Pipeline

```
data/raw/f1db/f1db-<version>/f1db-*.csv     (extracted release)
        │  F1DBIngester (src/racewise/data/historical/f1db_ingest.py)
        ▼
CanonicalStore (SQLite, data/canonical/canonical.db)
        │  F1DBCanonicalizer (src/racewise/data/historical/f1db_canonical.py)
        ├── entities: seasons, circuits, drivers, constructors, races
        ├── sessions (12 types, evidence-derived existence)
        ├── results / qualifying / pit stops / fastest laps / grids / practice
        └── rebuild_catalog() → canonical_session_catalog (data-derived availability)
```

Run: `python -m racewise.data.historical.cli ingest` (see `--help`). A full run is **~11–13 s** and produces a ~49.6 MB database. Manifest with per-file SHA-256 is written to `data/manifests/f1db_<version>_manifest.json`.

## Deterministic identity

- `canonical_races`: `race_key = f1db:<raceId>` (F1DB's own stable key).
- `canonical_sessions`: `session_key = f1db:<raceId>:<SESSION_TYPE>`; `session_id` = first 16 hex chars of SHA-256 of `session_key`.
- Detail rows (`results`, `qualifying`, `pit_stops`, `lap_times`): stable IDs from SHA-256 of provider + entity + session + source business key (e.g. driverId, (raceId, lap, stop number)). Random UUIDs are gone.
- All writes are `INSERT ... ON CONFLICT(...) DO UPDATE` upserts inside transactions with `executemany` batches.

**Re-running ingestion is idempotent**: verified identical counts across consecutive runs, and `PRAGMA foreign_key_check` returns 0 violations.

## Session construction rule (no fabrication)

A session row is created for a session type **only if** F1DB represents it:

- the race row carries a scheduled date/time for that session (`sprintRaceDate`, `sprintQualifyingDate`, practice dates, etc.), or
- detail rows for that session exist in the source CSVs.

Session types preserved exactly as the source represents them, including historical formats: `RACE`, `QUALIFYING`, `QUALIFYING_1/2`, `PRE_QUALIFYING`, `FREE_PRACTICE_1..4`, `WARMING_UP`, `SPRINT`, `SPRINT_QUALIFYING`. A scheduled session with no rows is still listed in the catalog with `UNAVAILABLE` capabilities — missing data is never converted to zeros.

## Mapping decisions

| F1DB dataset | Canonical target | Notes |
|---|---|---|
| races-race-results | canonical_results | Key `(raceId, positionDisplayOrder)`; shared-car rows preserved as separate driver entries; status text verbatim |
| races-qualifying-results | canonical_qualifying | `q1/q2/q3` only when the source supplies them; historical formats untouched |
| races-starting-grid-positions | canonical_qualifying | Only fills sessions with **no** qualifying file (grid time → q1); 0 sessions currently carry both (verified) |
| races-sprint-race-results | canonical_results (session_type=SPRINT) | 590 rows |
| races-sprint-qualifying-results | canonical_qualifying (session_type=SPRINT_QUALIFYING) | 466 rows |
| races-pit-stops | canonical_pit_stops | Keyed `(raceId, lap, stop number)`; exact source duplicates deduplicated |
| races-fastest-laps | canonical_lap_times | **Fastest-lap facts only** — not lap-by-lap telemetry; sector/compound columns stay NULL |
| races-free-practice-{1..4}, warming-up, pre-qualifying, qualifying-{1,2} results | canonical_qualifying rows on their own sessions | Position + time semantics |

Fields F1DB does not provide are left NULL. Nothing is inferred from era, year, or location.

## Availability index

`canonical_session_catalog` (one row per session) is rebuilt from actual counts: `results_count`, `qualifying_count`, `grid_count`, `pit_stops_count`, `laps_count`, `stints_count`, `weather_count`, `race_control_count`, plus `*_availability` flags ∈ {AVAILABLE, PARTIAL, UNAVAILABLE}. There is no year-based logic anywhere (enforced by grep gate + tests).

## Known limitations

- F1DB has no stints/tyre compounds, weather, race control, or lap-by-lap telemetry → those canonical tables are correctly empty; modern depth must come from FastF1/OpenF1.
- 9 races have a scheduled QUALIFYING/RACE session with zero detail rows (source gap), surfaced as `UNAVAILABLE` rather than fabricated.
- Pit stops exist only from 1994 onward (source coverage).
