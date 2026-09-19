# PHASE 6A COMPLETION REPORT

Date: 2026-09-19. Every number below was measured on this date against the live database, real FastF1 cache, or actual test runs. No estimates, no marketing language.

## FASTF1 SESSION LOADING

- FastF1 version: **3.8.3** (recorded as `source_version` on every modern row)
- Sessions tested: **6** → successful: **6** → DATA_UNAVAILABLE: **0**
- Set: 2023 Bahrain R + Q, 2023 Saudi R, 2023 Australia R, 2023 Azerbaijan R (cold download), 2018 Australia R (older era)
- Coverage boundary verified: FastF1 supports **2018+**; earlier seasons stay honestly UNAVAILABLE
- Cache: persistent, configurable path, Git-excluded; warm load 6.2 s vs 10.8 s cold (measured)

## CANONICAL MODERN DATA (actual rows)

| Table | Rows before | Rows after | Delta |
|---|---|---|---|
| canonical_stints | 0 | **369** | +369 |
| canonical_weather | 0 | **897** | +897 |
| canonical_race_control | 0 | **360** | +360 |
| canonical_lap_times (fastf1 per-lap) | 0 | **5,138** | +5,138 |
| canonical_lap_times (f1db fastest-lap facts) | 17,148 | 17,148 | unchanged |
| F1DB entities/results/qualifying/pit stops | 28,189 / 118,165 / 22,506 | unchanged | no regression |

Database size: 49.6 MB → **51.5 MB**. Foreign keys: `PRAGMA foreign_key_check` = **0 violations**.

## TELEMETRY

Explicitly **deferred with a documented bounded policy** (long-format signal table, per-session `--telemetry` flag, measured size, default OFF). No uncontrolled schema growth; nothing invented. See `docs/FASTF1_MODERN_DATA.md`.

## PROVIDER VALIDATION (measured)

- F1DB vs FastF1, 2023 Bahrain / Saudi / Australia: driver sets MATCH on all 3; mismatches are documented semantic differences (pit-in-lap vs recorded stops; lap-numbering; red-flag classification vs running order) with both values preserved.
- F1DB vs Jolpica, 1950 British: unchanged (41 MATCH / 51 NOT_AVAILABLE / 2 MISMATCH).
- Merge policy documented in `docs/PROVIDER_MERGE_POLICY.md`; provider provenance complete on 100% of modern rows (validator-enforced).

## GOLDEN INVESTIGATIONS

| Investigation | Status | Hash |
|---|---|---|
| 1950 British GP | PASS | `1487764bf78a3c38` — STABLE |
| 2000 Australian GP | PASS | `43434c839bd05315` — STABLE |
| 2023 Bahrain GP | PASS | `749879bc5f037359` — NEW, intentional: E5 evidence statement is now provider-aware (F1DB facts vs FastF1 per-lap rows counted separately after modern ingestion changed the underlying table content) |
| Cross-provider 1950 | PASS | `276591d5d8c104bd` — STABLE |

## ENGINEERING BENCHMARK QUESTIONS (all deterministic)

- Q1 degradation (VER vs PER, matched HARD stints): PASS — slope −0.371 vs −0.203 s/lap (Δ −0.169 s/lap)
- Q2 strategy vs pace: PASS — same-compound matched-tyre-life windows + stint-sequence comparison; falsification evidence included
- Q3 pit windows: PASS — stops correlated with race-control flags ±2 laps, no causal claim
- Q4 weather vs pace: PASS — track temp 33.8→30.7 °C across race thirds; correlation only, fuel confounder stated
- Q5 traffic vs degradation: PASS — position-change signature on slow laps vs residual degradation slope
- Deep 2023 Bahrain: PASS — QUESTION → HYPOTHESES → EVIDENCE → CONTRADICTIONS → FALSIFICATION → COUNTERFACTUAL → CONCLUSION → PROVENANCE
- Counterfactual `simulate_pit_timing` (pit 36→31): **−1.45 s** from the deterministic simulator with explicit assumptions — no invented numbers
- Negative control: same benchmark on 1950 inputs → **INSUFFICIENT_EVIDENCE** (correct honest verdict)

## TESTS

**162 passed, 0 failed** (baseline 143 → +19: FastF1 canonicalization/idempotency, validator corruption detection, availability flips, engineering benchmarks incl. INSUFFICIENT_EVIDENCE path, FastF1 cross-provider, new MCP tools). Runtime ~4 min.

## IDEMPOTENCY & REPLAY

- FastF1 ingestion re-run → identical counts (369/897/360/5,138) — verified twice, plus locked by unit test.
- Golden investigation hashes recomputed in a fresh subprocess — all stable (documented 2023 change above).

## PERFORMANCE (measured)

- Session load (cache hit): 6–12 s per session; cold download ~11 s (Azerbaijan)
- Canonicalization: ~470 rows/s per session (load excluded); full 6-session ingest ~30 s total including F1DB rebuild
- F1DB full pipeline: ~12 s (unchanged)
- Query latency: get_lap_times 1,076 rows 100 ms; get_results 23 ms; availability lookup 129 ms
- Data volume per added session: ~2,200 rows average

## NO-FABRICATION AUDIT

Grep scan for `year >=`, `default_weather`, `synthetic`, `estimated`, `fallback`, `hardcoded` patterns: **clean**. Availability is count-derived everywhere; pre-2018 stays UNAVAILABLE; the Q4 lap→time mapping is a documented approximation, not presented as source data; `INSUFFICIENT_EVIDENCE` is used when evidence is absent.

## KNOWN LIMITATIONS

1. Modern engineering data covers 6 representative sessions; scaling to full seasons is a CLI run, not new code.
2. Pre-2018: FastF1 provides nothing → UNAVAILABLE (correct, not fixable by us).
3. Channel telemetry deferred with a bounded policy; no consumer yet.
4. `FreshTyre`, trap speeds, personal-best flags mapped to no canonical column (documented, not invented).
5. Weather lap-time correlation uses cumulative-mean lap mapping (documented approximation).
6. Jolpica validation coverage still limited to cached 1950 data.

## Git

5 logical commits planned: feature (FastF1 canonical ingestion + validators + benchmarks), feature (MCP tools), test, docs, chore (pre-existing hygiene). Pre-existing unrelated modifications left uncommitted. No secrets, caches, or DBs staged (`.gitignore` hardened in Phase 5.5B; verified `racewise.env` and caches are ignored).

## PHASE 6A STATUS: READY

All Definition-of-Done items verified: sessions loaded and cached, stints/weather/race control populated from real provider data with provenance, telemetry explicitly deferred with policy, availability count-derived and flipped, modern coverage audited, deep investigation + 5 benchmark questions + falsification + counterfactual pass, cross-provider expanded, idempotency and replay verified, 162 tests pass, performance measured, documentation written, no fabricated data, no secrets committed.
