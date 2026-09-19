# Modern Data Coverage — Verified

All figures queried from the canonical store (2026-09-19). Availability claims are record-count-derived; no year heuristics.

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

## Canonical modern-data rows (current)

| Table | Rows | Sessions covered |
|---|---|---|
| canonical_stints | 369 | 6 |
| canonical_weather | 897 | 6 |
| canonical_race_control | 360 | 6 |
| canonical_lap_times (fastf1) | 5,138 | 6 |
| canonical_lap_times (f1db facts) | 17,148 | 1,162 |

## Availability flips (data-derived)

| Session | Stints | Weather | Race control | Per-lap rows |
|---|---|---|---|---|
| 2023 Bahrain R | AVAILABLE | AVAILABLE | AVAILABLE | AVAILABLE |
| 2023 Bahrain Q | AVAILABLE | AVAILABLE | AVAILABLE | AVAILABLE |
| 2023 Saudi R / Australia R / Azerbaijan R | AVAILABLE | AVAILABLE | AVAILABLE | AVAILABLE |
| 2018 Australia R | AVAILABLE | AVAILABLE | AVAILABLE | AVAILABLE |
| 1950–2017 sessions | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |

The `canonical_session_catalog` flags for these sessions were rebuilt from actual counts and now read AVAILABLE; every pre-2018 session remains UNAVAILABLE because the store genuinely has no rows.

## Session loading exceptions observed

None in this set. Two benign FastF1 parser warnings (drivers completing race distance marginally before recorded session end) — informational only, data unaffected.

## Known gaps

1. FastF1 provides no data before 2018 → pre-2018 modern engineering stays UNAVAILABLE.
2. Only 6 representative sessions ingested so far; scaling is a CLI run away (`python -m racewise.data.historical.cli fastf1-canonical --season 2023 --round N`).
3. Channel telemetry (throttle/brake/RPM/XY) deliberately deferred — see `FASTF1_MODERN_DATA.md`.
