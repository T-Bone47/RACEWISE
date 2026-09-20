# Phase 6C Completion Report — Bounded Telemetry + Engineering Investigation Activation

All numbers below were measured against the live canonical store and running
code on the verification date. Nothing is projected or claimed without an
executed check.

## 0. Pre-telemetry gate (Phase 6C §2–3)

| Item | Result |
|---|---|
| Two retryable 2025 sessions | RESOLVED — Singapore RACE (43 stints) and United States SPRINT_QUALIFYING (60 stints) re-ingested SUCCESS via checkpoint resume. Modern sessions now **381** (from 379). |
| Benchmark coverage expansion | `run_benchmark_matrix` executes Q1–Q6 across 2018 R1, 2020 R1, 2021 R10, 2022 R1, 2024 R1, 2025 R1 with data-derived drivers (winner + runner-up from canonical classification, never hardcoded). Result: 4 sessions PASS, 2 PARTIAL (Q6 INSUFFICIENT_EVIDENCE where telemetry is not ingested — honest), 0 failures. |
| Baseline tests | 186 pre-existing tests remained passing throughout (final suite: 201). |

## 1. Telemetry design gate (§6)

**Consumer question** (cannot be answered from laps/stints/weather/race control/pit stops;
requires per-sample speed/throttle/brake series):

> "In which windows of a lap does driver B lose time to driver A, and is that
> loss associated with throttle lift or braking differences?"

This question is recorded in `telemetry_analysis.py` and answered by
`compare_telemetry_lap`. Telemetry stayed deferred (Phase 6A/6B) until this
consumer existed.

## 2. What was implemented

### Data model
- `canonical_telemetry` (wide format — one row per sample, six value columns;
  ~6× smaller than the long-format prototype measured at 17.5 MB/session):
  `telemetry_id, session_id, driver_id, lap_number, time_elapsed_s, lap_time_s,
  speed_kmh, throttle_pct, brake, gear, rpm, drs, source_provider, source_id,
  source_version, created_at, updated_at`.
- Signals (bounded whitelist): Speed, Throttle, Brake (boolean→0/1), nGear, RPM, DRS.
  No positional channels. No unbounded channel ingestion.
- Time model: `time_elapsed_s` = session-relative (`SessionTime`, same convention
  as FastF1 weather); `lap_time_s` = lap-relative (`SessionTime − LapStartTime`,
  documented calculation). Native resolution (~3.8 Hz), no interpolation, no
  downsampling.

### Identity & idempotency
- `telemetry_id = _stable_id("fastf1", "tel", session_id, driver_id, lap_number,
  elapsed_s)` — content-derived, deterministic, no UUIDs.
- `INSERT ... ON CONFLICT(telemetry_id) DO UPDATE` — double ingestion verified to
  produce identical counts (2023 Bahrain re-ingested twice during development;
  fixture test `test_ingest_twice_yields_identical_counts` locks it in CI).

### Bounded ingestion (policy-gated)
- `TelemetryPolicy` default **OFF**; opt-in via `--telemetry` on
  `ingest-fastf1-canonical` and `ingest-seasons` (CLI wired through
  `fastf1_canonical.ingest_session` → `ingest_telemetry`).
- Scope: top-2 classified drivers per session (deterministic from canonical
  results), 12 evenly spaced clean timed laps per driver (deterministic
  selection), hard sample cap with `truncated_to_cap` flag in stats.
- Car data loads **only** in the opt-in path (`load(laps=True, telemetry=True)`);
  the adapter default remains `telemetry=False`.

### Availability (count-derived)
- Catalog rebuild counts `canonical_telemetry` rows → `telemetry_available` /
  `telemetry_availability`. No `year >= 2018` heuristic anywhere (no-fabrication
  gate scans for it).
- `CatalogAPI._telemetry_capability` maps counts to the policy vocabulary
  (`INGESTED` / `NOT_INGESTED`); list `capability=telemetry` filter works.

### Queries (hard bounds)
- `get_lap_telemetry`: signal whitelist (ValueError otherwise), per-query cap
  (default 2,000, defensive clamp), cap bounds **output** rows after signal
  expansion. Empty list for missing telemetry (UNAVAILABLE, never zeros).
- `telemetry_summary`: count-derived availability + drivers + ingested laps.
- MCP tools (3 new, registry 24 → **27**): `get_historical_telemetry_summary`,
  `get_historical_lap_telemetry`, `compare_historical_telemetry_lap` — all typed,
  provenance-stamped, output-hashed, bounded.

### Deterministic consumer
- `compare_telemetry_lap` (analysis version 1.0): fixed 5 s windows over the
  overlapping lap-time span; per-window mean speed/throttle/brake deltas;
  time-loss estimate `dt·(1 − v_B/v_A)` (documented straight-line approximation);
  throttle/brake association reported for the worst window. The LLM never
  computes these numbers.

## 3. Measured data (live store)

| Season | Round | Drivers | Laps sampled | Samples |
|---|---|---|---|---|
| 2021 | 10 (British) | 2 | 12 | 9,504 |
| 2022 | 1 (Bahrain) | 2 | 16 | 8,933 |
| 2023 | 1 (Bahrain) | 2 | 12 | 8,881 |
| 2024 | 1 (Bahrain) | 2 | 12 | 8,698 |
| 2025 | 1 (Australian) | 2 | 12 | 8,994 |
| **Total** | 5 sessions | 2 each | — | **45,010** |

- Database: 146.2 MB → **156.3 MB** (+10.1 MB for 45,010 telemetry rows ≈ 235 B/row,
  wide format). Five-session cost validated before any further scaling (§15).
- Ingestion runtime: ~40–60 s per session (car-data fetch + canonicalize),
  measured during the bounded runs.
- Telemetry ingestion remains **opt-in and OFF by default**; no other sessions
  ingested (§37 respected).

## 4. Performance (measured, n=40 unless noted)

| Path | p50 | p95 |
|---|---|---|
| `get_lap_telemetry` (3 signals, cap 2000) | 10.9 ms | 24.8 ms |
| `telemetry_summary` | 11.8 ms | 14.2 ms |
| `compare_telemetry_lap` (full analysis, n=20) | 64.1 ms | 84.6 ms |
| MCP `get_historical_lap_telemetry` (single call) | 35 ms | — |
| MCP `compare_historical_telemetry_lap` (single call) | 96.9 ms | — |

- Largest observed MCP payload: 2,000 samples ≈ 126 KB JSON (cap enforced,
  `truncated: true` surfaced to the caller). Full analysis payload ≈ 1.5 KB.
- No query-plan work needed at this scale.

## 5. Investigations & benchmarks

### Q6 telemetry pace explanation
Runs across all 5 telemetry sessions (session-scoped drivers):

| Session | Drivers | Verdict | Est. loss (per sampled lap) |
|---|---|---|---|
| 2021 R10 | LEC vs HAM | PASS | 2.365 s |
| 2022 R1 | LEC vs SAI | PASS | 0.361 s |
| 2023 R1 | VER vs PER | PASS | 2.084 s |
| 2024 R1 | VER vs PER | PASS | 3.544 s |
| 2025 R1 | VER vs NOR | PASS | 0.503 s |

Determinism: identical JSON hash across repeated runs in-process **and** in a
fresh subprocess (`fdf98e15bd5c7dfc` for the 2023 comparison; telemetry
investigation `365ddccc4393e4a7`).

### Telemetry investigation (2023 Bahrain)
Full QUESTION → EVIDENCE → FALSIFICATION → CONCLUSION structure in
`EngineeringBenchmarks.telemetry_investigation_2023_bahrain()`:
- Locates the loss: lap 57, 20 windows, worst window at 40.2 s
  (−11.76 km/h mean-speed delta, PER lifted 7.2 % more throttle).
- Falsification outcome is reported honestly as **MIXED**: throttle association
  present, but brake evidence and window distribution (loss spread across 20
  windows, not one corner) must be reported alongside — no single-cause claim.
- `telemetry_value_statement`: the loss is localised in time windows and
  associated with throttle/brake behaviour that lap aggregates cannot localise —
  telemetry materially contributes; removing it would leave the investigation
  unable to locate the deficit at all.

### Negative controls (both INSUFFICIENT_EVIDENCE, verified via MCP too)
- 1950 British (no telemetry era) → INSUFFICIENT_EVIDENCE
- 2018 R1 (modern era, telemetry not ingested) → INSUFFICIENT_EVIDENCE

### Q1–Q5 regression
All pass with identical numbers to Phase 6B (2023 Bahrain canonical-side).
Matrix Q1–Q6: 4 PASS / 2 PARTIAL (PARTIAL = Q6 honest INSUFFICIENT_EVIDENCE).

## 6. Regression & verification log (executed)

| Check | Result |
|---|---|
| Full test suite | **201 passed** (186 baseline + 15 new), 0 failures |
| Golden hashes (fresh subprocess) | 1950 `1487764bf78a3c38` STABLE · 2000 `43434c839bd05315` STABLE · 2023 `749879bc5f037359` STABLE · cross-provider `276591d5d8c104bd` STABLE |
| Replay | PASS — all four hashes reproduce in a fresh process |
| Validators | 14/14 pass |
| FK check | 0 violations; `PRAGMA integrity_check` = ok |
| MCP over real server subprocess | 27 tools listed; telemetry summary, lap telemetry (≤2000 samples, truncated flag), compare (PASS + INSUFFICIENT_EVIDENCE negative) verified |
| API endpoint | `GET /api/catalog/telemetry-comparison/{season}/{round}` returns PASS (2023) and INSUFFICIENT_EVIDENCE (2018) via TestClient |
| Catalog Explorer | telemetry capability count-derived; `capability=telemetry` filter returns exactly the 5 ingested sessions |
| Frontend build | Vite build passes (~1.0 s); TelemetryView renders backend results only |

## 7. Frontend

- `TelemetryView.tsx`: bounded telemetry investigation view — session dropdown
  (populated from the catalog API, fallback list is the known ingested set),
  driver-key inputs, deterministic per-window table with loss bars, assumptions
  and provenance rendered from the API payload. The view computes nothing.
- Catalog detail rows already render telemetry with ✓ / — marks from
  `capabilities.telemetry` — now genuinely count-derived.

## 8. Security

- No secrets introduced or committed; no `.env`, caches, or DB artifacts staged.
- Telemetry endpoints bounded at three layers: SQL cap, MCP tool cap
  (`max_samples ≤ 2000`), API delegates to the same bounded analysis. No
  unbounded dump path exists.

## 9. Known limitations

1. Telemetry exists for **5 sessions only** — by design (§37). Scaling requires a
   demonstrated consumer win and a storage plan (Phase 6D).
2. Time-loss estimate is a straight-line approximation (documented in every
   output); no racing-line/tyre-state interaction.
3. `lap_time_s` (lap-relative time) derives from `SessionTime − LapStartTime`;
   laps with NaT `LapStartTime` are skipped rather than estimated.
4. Q4 weather–pace mapping still uses the cumulative-mean-lap approximation
   (documented; unchanged from Phase 6A).
5. Q6 in the season matrix returns INSUFFICIENT_EVIDENCE for 2018/2020 — correct
   behaviour, not a defect.
6. 2020 R1 and 2018 R1 remain PARTIAL in the matrix; their other questions pass.

## 10. Phase 6D recommendation (not started, per §37)

Telemetry **does** materially improve investigations (loss localisation is
impossible from lap aggregates), so a bounded Phase 6D scaling plan is
recommended: extend to all races of 2022–2025 at top-2 drivers × 12 laps
(~220 sessions ≈ +440 MB projected at 235 B/row before any compression), gated
on per-season validation and idempotency runs. Do not ingest practice sessions
without a new consumer question.

## PHASE 6C STATUS: READY
