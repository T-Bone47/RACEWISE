# RACEWISE

**Autonomous Evidence-Driven Race Engineering**

RACEWISE does not merely answer F1 engineering questions — it **investigates** them. Given an engineering question about a historical race, RACEWISE constructs competing hypotheses, gathers evidence through deterministic analysis tools, explicitly attempts to falsify its leading explanation, runs counterfactual strategy scenarios, and produces a traceable engineering report with full provenance.

> Ask: *"Why did VER lose pace in the second stint — and would an earlier pit stop have changed the outcome?"*
> Watch: hypotheses → evidence collection → falsification → counterfactual → report.

## What makes this different

- **AI investigates; deterministic software calculates.** The LLM (when configured) orchestrates the investigation but never invents a number. All lap times, degradation slopes, traffic fractions, pit losses and counterfactual deltas come from versioned deterministic tools with hashed provenance.
- **Falsification is mandatory.** The engine refuses to synthesize a conclusion without at least one attempted challenge to the leading hypothesis.
- **Evidence taxonomy is enforced.** Every claim is labeled `FACT` / `CALCULATION` / `INFERENCE` / `COUNTERFACTUAL` / `ASSUMPTION` — in the data model and the UI.
- **Honest degradation.** Without model credentials, investigations run on a clearly-labeled deterministic plan. Nothing pretends to be AI.

## Architecture

```text
React workstation UI  ──SSE──  FastAPI
                                 │
                        Investigation Engine (state machine)
                        hypotheses · evidence · falsification gate
                                 │
              ┌──────────────────┼──────────────────┐
        FastF1 Adapter      12 Deterministic      Counterfactual
        (canonical schemas)  Tools (allow-list)    Simulator
                                 │
                       Provenance (hash-chained executions, event log)
```

- **Domain schemas** — `src/racewise/domain/schemas.py`
- **Data adapter** — `src/racewise/data/fastf1_adapter.py` (FastF1 → canonical Lap/Stint/PitStop/Weather/RaceControl)
- **Historical canonical pipeline** — `src/racewise/data/historical/` (F1DB → canonical entities, sessions, results, qualifying, pit stops; FastF1 → tyre stints, weather, race control, per-lap rows for 2018+; data-derived availability catalog; deterministic ids; idempotent ingestion; automated quality validators)
- **Tools** — `src/racewise/tools/` (contract + 12 tools + versioned analytics)
- **Investigation engine** — `src/racewise/investigation/engine.py`
- **Provider abstraction** — `src/racewise/agent/provider.py` (`ModelProvider` protocol; `UnionAlphaProvider` for OpenRouter)
- **Counterfactual simulator** — `src/racewise/simulator/strategy.py`
- **API** — `src/racewise/api/app.py` (FastAPI + SSE)
- **UI** — `apps/web` (React/Vite investigation workstation)

## Running it

```bash
# Backend
pip install -e ".[dev]"
uvicorn racewise.api.app:app --port 8000

# Frontend (proxies /api to :8000)
cd apps/web && npm install && npm run dev
```

Optional model configuration (`.env` or environment):

```text
MODEL_PROVIDER=union_alpha
MODEL_ID=stealth/union-alpha
OPENROUTER_API_KEY=<your key>
```

Without credentials the system runs in deterministic mode and labels model-dependent phases as unavailable.

## Tests & benchmark

```bash
python -m pytest -q          # 162 tests: canonical data, analytics, simulator, engine, API, MCP
python tests/benchmark/run_benchmark.py
```

Benchmark results (measured 2026-09-17): 8/8 investigations COMPLETED, falsification and counterfactual executed in every run, 40/40 tool executions successful — see `docs/EVALUATION.md` and `benchmark_results.json`.

## Verified reference data

All analytics are pinned to hand-verified values from the 2023 Bahrain GP (VER: 57 laps, stints 1–14/15–36/37–57, pit laps 14 & 36, stint-2 clean-lap mean ≈ 97.6 s). Unit tests assert these reference values so regressions in data handling are caught.

## Limitations

- Historical data: full 1950–2026 race/qualifying/pit-stop record from F1DB (v2026.14.0); FastF1 engineering data (stints, weather, race control, per-lap rows) for 2018+ sessions actually ingested; no live timing.
- Channel telemetry (throttle/brake/RPM/traces) is deliberately deferred behind a bounded ingestion policy; availability is always data-derived, never assumed.
- One reference session in the benchmark; the PRD target of 15–20 questions is not yet met.
- No model credentials in the build environment ⇒ Union Alpha phases are implemented but unexercised; evaluation of LLM judgment dimensions is pending.
- Linear degradation model; traffic is a cumulative-time approximation, not dirty-air physics.
- Team radio is intentionally absent (availability collapsed in 2026; never a required dependency).
- Investigations are in-memory per API process; replay exists via the event log but storage is not yet persistent across restarts.

## Docs

- `docs/PHASE_6A_COMPLETION_REPORT.md` — verified modern engineering data activation
- `docs/FASTF1_MODERN_DATA.md`, `docs/MODERN_DATA_COVERAGE.md` — what FastF1 provides and what the store now holds
- `docs/PROVIDER_MERGE_POLICY.md`, `docs/MODERN_DATA_VALIDATION.md` — precedence rules and validation evidence
- `docs/PHASE_5_5B_COMPLETION_REPORT.md` — verified session-level canonicalization results
- `docs/HISTORICAL_COVERAGE.md`, `docs/F1DB_CANONICALIZATION.md` — the historical foundation
- `docs/GOLDEN_INVESTIGATIONS.md`, `docs/CROSS_PROVIDER_VALIDATION.md` — golden-race and multi-provider evidence
- `docs/IMPLEMENTATION_PLAN.md` — audit, phases, risks
- `docs/DECISIONS.md` — ADR-style decision log
- `docs/EVALUATION.md` — honest benchmark results and their boundaries
- `RACEWISE_PRD.md`, `RACEWISE_ARCHITECTURE.md`, `RACEWISE_RESEARCH_BRIEF.md` — authoritative specs
