# PHASE 6R — BASELINE AUDIT

Date: 2026-09-27
Baseline commit: `48f0d5d` — `feat(racewise): complete engineering product integration`
Audit performed at the start of Phase 6R, before any 6R code was written.

## 1. Test suite state (measured)

- Backend regression (`python -m pytest -q tests src --ignore=tests/integration/test_investigation_flow.py -p no:cacheprovider`): **691 passed** (latest full run).
- Legacy investigation flow (`tests/integration/test_investigation_flow.py`, run independently): **5 passed**.
- Detected test files in repository: 12 by path convention; the backend suite is the source of the 691 figure above.
- Registry-count assertions pinned at **31 historical MCP tools** in 5 test files (46 MCP tools total including live-session tools).

## 2. API surface (measured from `src/racewise/api/app.py`)

34 routes total:

- 13 core routes: `/api/health`, `/api/sessions` (+`/{session_key}/drivers`), `/api/sessions/sync` (POST), `/api/investigations` (POST/GET list), `/api/investigations/{id}` (GET), `/api/investigations/{id}/stream`, `/api/investigations/{id}/counterfactual` (POST), `/api/investigations/{id}/replay` (POST), `/api/investigations/{id}/export`, `/api/investigations/{id}/evidence-graph` (GET/POST).
- 21 catalog routes: `catalog/sessions`, `catalog/sessions/{season}/{round}/{session_type}`, `catalog/telemetry-comparison/{s}/{r}`, `catalog/attribution/{s}/{r}`, `catalog/evidence-fusion/{s}/{r}`, `catalog/stint-evidence/{s}/{r}` (`?stint=`), `catalog/counterfactual/{s}/{r}` (`?fraction=`), `catalog/performance-envelope/{s}/{r}` (`?scenario_type=`), `catalog/race-gap/{s}/{r}`, `catalog/performance-regimes/{s}/{r}`, `catalog/performance-patterns` (`?seasons=&max_races=`), `catalog/performance-pattern-evidence`, `catalog/engineering-investigation`, `catalog/engineering-investigation/replay`, `catalog/engineering-investigation/compare`, `catalog/engineering-memory`, `catalog/investigation-graph`, `catalog/investigation-graph/path`, `catalog/investigation-graph/evidence`, `catalog/investigation-graph/hypothesis`, `catalog/search`.

## 3. Frontend (measured)

- 17 TSX modules under `apps/web/src` (`App.tsx`, `CommandCenterView`, `InvestigationView`, `TelemetryView`, `AttributionView`, `EvidenceFusionView`, `StintEvidenceView`, `RaceGapView`, `CounterfactualView`, `PerformanceEnvelopeView`, `PerformanceRegimeView`, `PerformancePatternView`, `PatternEvidenceView`, `CatalogExplorer`, `panels.tsx`, `workspace.tsx`, `main.tsx`).
- Hash routing (`#/view?scope=params`); navigation groups Command center / Data / Engineering; no internal phase labels in rendered output (verified in the 48f0d5d integration commit).
- Known-good canonical contexts: telemetry comparison PASS 2023 R1 (2.084 s wall / 20 windows), attribution sector sum 0.185 s, stint 2 trend 0.1865 s/s, envelope 33.0 km/h band, CF REMOVE_DEFICIT 0.5, regimes 2022 R4 (8 regimes / 42 laps / 220-row timeline), patterns 6 patterns hash `61dbc841dd137c02`, race gap 2024 R14 official 0.895 s vs analytical −23.558 s / 42 comparable laps.

## 4. Engineering-investigation engine (measured live, this audit)

- `GET /api/catalog/engineering-investigation` accepts `question_type` from the closed 6N vocabulary: `LAP_PERFORMANCE, STINT_PERFORMANCE, RACE_GAP, PERFORMANCE_REGIME, CROSS_RACE_PATTERN, HYPOTHESIS_EVALUATION, COUNTERFACTUAL_ELIGIBILITY`.
- Drivers are **slugs** (`max-verstappen`, `sergio-perez`, `giuseppe-farina`), not 3-letter codes; unknown drivers yield status `UNAVAILABLE` with reason "driver(s) not in the canonical race result" — no broadening, no fabrication.
- Live probe `LAP_PERFORMANCE / max-verstappen / sergio-perez / 2023 R1 / lap 6`: status `VALID`, investigation id `fcc1bf694daada8e` (matches the 6N golden), output hash `e8263d8a0e191839` (this run), 12 evidence items collected, conclusion `MIXED_EVIDENCE`.
- Live probe at lap 12 (a non-fused lap): collection `INSUFFICIENT_EVIDENCE`, conclusion `INSUFFICIENT_EVIDENCE`, counterfactual candidate honestly reported `TELEMETRY_UNAVAILABLE` with `missing_data` — the engine reports rather than fabricates.
- 6N structural vocabulary observed in responses: `collection`, `hypothesis_evaluations` (H1_corner_speed…H6_drs with aggregate/falsification states), `falsification_gate`, `counterfactual_candidates`/`executed_counterfactuals`, `evidence_conflicts`, `synthesis` (established/measured/contradictory/unavailable/unresolved), `decision_trace`, `lifecycle` (11 stages), `investigation_snapshot`, `limitations`, `epistemic_boundaries`, `provenance` (analytical_chain/method/version/layers/provider/source_tables), `output_hash`.

## 5. Graph (measured live, this audit)

- `GET /api/catalog/investigation-graph?question_type=LAP_PERFORMANCE&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1&lap_number=6` → 200 in 0.85 s, **58 nodes / 185 edges**, matching the 6P golden for `LAP6` (58 nodes / 185 edges). Graph response carries `graph_version`, `graph_id`, `source_hashes`, `provenance`, `epistemic_boundaries`.
- Note: `investigation-graph` is a scope query endpoint (rebuilds from scope); there is no `?investigation_id=` mode on the catalog graph route — a benchmark runner must pass the full scope.

## 6. Endpoint sanity checks (measured live, this audit)

All 200 with real data unless noted:

| Endpoint | Result |
| --- | --- |
| `catalog/sessions` | 200, 5,268 sessions indexed, capability matrix per session |
| `catalog/telemetry-comparison/2023/1` | 200, 0.25 s |
| `catalog/attribution/2023/1` | 200, 0.55 s |
| `catalog/evidence-fusion/2023/1` | 200, 1.10 s |
| `catalog/stint-evidence/2023/1?stint=2` | 200, 2.40 s |
| `catalog/race-gap/2023/1` | 200, 7.30 s |
| `catalog/race-gap/2024/14` | 200, 5.13 s |
| `catalog/counterfactual/2023/1?fraction=0.5` | 200, 0.22 s |
| `catalog/performance-envelope/2023/1` | 200, 0.41 s |
| `catalog/performance-regimes/2022/4` | 200, 3.13 s |
| `catalog/performance-patterns?seasons=2022,2023` | 200, 13.96 s |
| `catalog/engineering-investigation` (valid scope) | 200, 0.02–0.92 s |
| `catalog/search?q=2023 R1` | 200, deterministic exact/substring match |
| `engineering-investigation` with unknown `question_type` | 422 with closed-vocabulary message (correct) |
| `engineering-investigation` with unknown driver | 200 + `UNAVAILABLE` status with reason (correct honesty) |

## 7. Known limitations entering 6R (carried from 6N–6Q + this audit)

- Fused lap evidence exists only on 6D probe laps; lap-scoped investigations on other laps correctly report `INSUFFICIENT_EVIDENCE`.
- `engineering-investigation` supports `session_type=RACE` only.
- Cross-race patterns is the slowest analytical endpoint (≈14 s for a two-season scan).
- No semantic memory search: engineering memory is deterministic scope/exact-match.
- `investigation-graph` rebuilds from scope; an investigation-id-addressed graph route is not exposed on the catalog API.
- Catalog routes 422 (rather than empty-200) on invalid vocabulary — correct behavior, but the benchmark treats it as a structural expectation, not an error.
- Drivers are identified by slug everywhere in the deterministic chain; 3-letter codes are not accepted (documented behavior, not a defect).

## 8. Environment

- Windows; Python 3.11 (uv-managed); backend on `127.0.0.1:8000` (uvicorn); frontend dev server on `[::1]:5173` (Vite).
- Dev-server startup: `nohup python -m uvicorn racewise.api.app:app --port 8000` and `nohup npm --prefix apps/web run dev -- --port 5173 --strictPort`.
- Subprocess tests inherit `os.environ` and only override `PYTHONHASHSEED` (3 and 29 per the 6R protocol).

## 9. Golden assets already in the repository (for 6R reuse)

- Investigation `fcc1bf694daada8e` (LAP6 matrix, 12 evidence, 18 traces).
- Graph goldens: LAP6 `b19ae7cd499446a2` (58n/185e), STINT1 `3e32561c3df209af`, RACE_GAP24 `6a8c7d0f85945c60`, REGIME22 `6ba7a5056d6f8ad6`.
- Replay: IDENTICAL `a7a0446765a05e4f`. Patterns hash: `61dbc841dd137c02`. Memory: 7 items.
- Precedent benchmark modules: `q16_benchmarks.py`, `q17_benchmarks.py`, `q18_benchmarks.py`.
