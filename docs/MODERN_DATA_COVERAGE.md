# Modern Data Coverage — Verified

All figures queried from the canonical store (updated 2026-09-20, Phase 6B scale-up). Availability claims are record-count-derived; no year heuristics.

## FastF1 session loading verification (measured, FastF1 3.8.3)

| Session | Load result | Laps | Weather obs | RC events | Stint rows | Load time |
|---|---|---|---|---|---|---|
| 2023 Bahrain R | OK (cache hit) | 1,056 | 161 | 73 | 70 | 4.7 s first / 6.2 s warm |
| 2023 Bahrain Q | OK (cache hit) | 254 | 95 | 21 | 89 | 7.0 s |
| 2023 Saudi Arabia R | OK (cache hit) | 943 | 148 | 56 | 44 | 11.8 s first |
| 2023 Australia R | OK (cache hit) | 1,003 | 222 | 103 | 85 | 11.8 s first |
| 2023 Azerbaijan R | OK (**downloaded** — proves cold load works) | 962 | 160 | 52 | 43 | 11.3 s |
| 2018 Australia R | OK (older era) | 940 | 111 | 55 | 38 | 12.0 s |

- 6/6 sessions loaded successfully; **0 DATA_UNAVAILABLE** in this set.
- FastF1's real coverage boundary: **2018+**. Seasons before 2018 cannot provide lap/telemetry data through FastF1 — the ingest path would mark them unavailable rather than fabricate.
- Cache: persistent, deterministic path (`.fastf1-cache/`, configurable via `FastF1Adapter(cache_dir=...)`), excluded from Git. Second load parses from cache only (6.2 s vs 10.8 s cold, measured).

## Canonical modern-data rows (current, after Phase 6B scaling)

| Table | Rows | Sessions covered |
|---|---|---|
| canonical_stints | 26,032 | 379 (2018–2025) |
| canonical_weather | 42,938 | 379 (2018–2025) |
| canonical_race_control | 20,868 | 357 (2018–2025) |
| canonical_lap_times (fastf1) | 251,868 | 379 (2018–2025) |
| canonical_lap_times (f1db facts) | 17,148 | historical |
| **DB size** | **146.2 MB** | 5,268 sessions total |

Per-season session coverage (stint-bearing sessions, actual counts):

| Season | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|
| Sessions | 41 | 42 | 34 | 47 | 47 | 50 | 60 | 58 |

Scope: RACE, QUALIFYING, SPRINT, SPRINT_QUALIFYING (priority levels 1–3). Practice sessions not ingested — no deterministic consumer yet.

## Availability flips (data-derived)

| Sessions | Stints | Weather | Race control | Per-lap rows |
|---|---|---|---|---|
| 379 modern sessions (2018–2025 R/Q/S/SQ) | AVAILABLE | AVAILABLE | AVAILABLE (357/379) | AVAILABLE |
| 4,889 sessions pre-2018 + practice | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |

The `canonical_session_catalog` was rebuilt from actual counts after scaling. Every pre-2018 session remains UNAVAILABLE because the store genuinely has no rows.

## Session loading exceptions observed

None in this set. Two benign FastF1 parser warnings (drivers completing race distance marginally before recorded session end) — informational only, data unaffected.

## Known gaps

1. FastF1 provides no data before 2018 → pre-2018 modern engineering stays UNAVAILABLE.
2. 2020 season lap numbering runs systematically lower in FastF1 than F1DB (measured −4 for all classified drivers at 2020 Styria) — both values preserved, see CROSS_PROVIDER_VALIDATION_MATRIX.md.
3. Two 2025 Australia sessions are FAILED_PROVIDER (source feed errors, documented in ingestion reports).
4. Channel telemetry (throttle/brake/RPM/XY) deliberately deferred — see `FASTF1_MODERN_DATA.md` and `telemetry_policy.py`.
