# Modern Data Validation — Verified

## Automated validators (14 checks, all passing)

`src/racewise/data/historical/validators.py` — every check queries the live database; failures are reported, never silently repaired.

| Check | What it proves |
|---|---|
| fk_integrity | `PRAGMA foreign_key_check` → 0 violations |
| stints_unique | no duplicate (session, driver, stint_number) |
| weather_unique_timestamps | no duplicate observation per (session, timestamp) |
| race_control_unique | no duplicate event per (session, timestamp, category, message) |
| lap_numbers_non_decreasing | lap sequences per (session, driver, provider) have no duplicated lap numbers |
| stint_ranges_sane | lap_end ≥ lap_start, lap_count > 0 |
| compound_vocabulary | compounds ∈ real FastF1 vocabulary (mixed sets validated per token) |
| weather_timestamp_order | weather `elapsed_s` non-decreasing per session |
| race_control_order | events chronological per session |
| pit_stops_unique | no duplicate (session, driver, lap, stop_number) |
| driver_fk_valid | modern rows reference real canonical drivers |
| session_fk_valid | modern rows attach to real canonical sessions |
| modern_rows_on_f1db_sessions | FastF1 rows exist only on F1DB-represented sessions |
| provider_provenance_complete | provider/source_id/source_version present on 100% of modern rows |

A corruption test (inserting a stint with `lap_end < lap_start`) is included in the suite and must be caught.

## Cross-provider validation (measured results)

### F1DB vs FastF1 (2023, from the canonical store)

| Race | MATCH | MISMATCH | NOT_AVAILABLE |
|---|---|---|---|
| 2023 Bahrain | 6 | 2 | 0 |
| 2023 Saudi Arabia | 7 | 1 | 0 |
| 2023 Australia | 4 | 4 | 0 |

Driver sets resolve identically on all three rounds (season-scoped code resolution verified). Remaining mismatches are **genuine documented semantic differences**, both values preserved:

- `laps[...]` — FastF1 lap numbering counts extra/formation laps differently in some races.
- `pit_stop_counts` — FastF1 counts every pit-in lap (incl. non-timed entries); F1DB lists recorded timed stops.
- `finishing_positions` (Australia only) — red-flag classification vs final running order.

### F1DB vs Jolpica (1950 British, unchanged from Phase 5.5B)

41 MATCH / 51 NOT_AVAILABLE / 2 MISMATCH (circuit naming scheme; one driver's lap count). Policy: F1DB is the foundation of record; discrepancies surfaced, never auto-merged.

## Engineering benchmark verdicts (2023 Bahrain)

| Question | Verdict | Headline result |
|---|---|---|
| Q1 Tyre degradation VER vs PER | PASS | Matched HARD stints: −0.371 vs −0.203 s/lap slope (delta −0.169 s/lap) |
| Q2 Strategy vs pace | PASS | Same-compound matched-tyre-life windows isolate pace from strategy; stint sequences compared |
| Q3 Pit windows | PASS | All stops correlated with race-control flags within ±2 laps (deterministic, no causal claim) |
| Q4 Weather vs pace | PASS | Track temp 33.8→30.7 °C across thirds; VER mean lap 99.36→98.50 s (correlation only; fuel confounder stated) |
| Q5 Traffic vs degradation | PASS | Slow laps (>1 s) checked for position-change signature; residual slope attributed to degradation |
| Deep 2023 Bahrain | PASS | Full evidence stack + contradictions + falsification + deterministic counterfactual −1.45 s |
| Q1 on 1950 inputs | INSUFFICIENT_EVIDENCE | Correct honest verdict when FastF1 has no data |

## Replay determinism

All golden investigation payloads (timestamps excluded) hash stably across subprocess restarts. Phase 6A changes one input honestly: the 2023 fastest-lap evidence statement is now provider-aware (F1DB facts counted separately from FastF1 lap rows). New hash recorded; 1950/2000/cross-provider hashes unchanged.
