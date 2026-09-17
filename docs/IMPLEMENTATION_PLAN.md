# RACEWISE — Implementation Plan

**Date:** 17 September 2026
**Status:** Foundation phase
**Source documents:** RACEWISE_RESEARCH_BRIEF.md, RACEWISE_PRD.md, RACEWISE_ARCHITECTURE.md

## 1. Repository audit (observed, not assumed)

| Item | Finding |
|---|---|
| Specification documents | All three present and read in full |
| Source code | None — greenfield build |
| Environment | Python 3.11, fastf1 3.8.3, fastapi 0.133, pandas, numpy, scipy, httpx, pydantic 2, pytest installed; Node 24 available |
| Network | Live API access confirmed |
| Git | Newly initialized; FastF1 data-pipeline verification committed first |
| Data verification | 2023 Bahrain Race loaded via FastF1: 1056 laps, 20 drivers, 31 columns; stint/compound/tyre-life/pit columns present and parsed |

## 2. Verified constraints (not assumptions)

- 2023 Bahrain Race: 57 laps. VER stints: S1 laps 1–14 (SOFT, tyre life starts at 4), S2 laps 15–36 (SOFT), S3 laps 37–57 (HARD). Pit laps are 14 and 36 (`PitInTime` non-null on those rows).
- `Stint`, `TyreLife`, `Compound`, `TrackStatus`, `PitInTime`/`PitOutTime` are populated; `Position`, `IsAccurate`, `Deleted` available per lap.
- Lap 1 of each stint shows ~1:58 (in-lap including pit entry) — clean-lap filtering must exclude in/out laps.

## 3. Implementation phases

### Phase 1 — Foundation (complete)
- Repo structure, git, FastF1 adapter, canonical Lap schema, session cache
- Provenance: every tool execution records inputs, hashes, method version

### Phase 2 — Deterministic tool layer
- Data tools: `get_session`, `get_laps`, `get_stints`, `get_pit_stops`, `get_weather`, `get_race_control`
- Analysis tools: `filter_clean_laps`, `analyze_tyre_degradation`, `analyze_traffic`, `analyze_pit_loss`, `compare_driver_pace`, `compare_sectors`, `correlate_weather`, `detect_pace_anomaly`
- Each tool: name, description, input/output schema, version, `execute()`

### Phase 3 — Investigation engine
- State machine: CREATED → FRAMING → HYPOTHESIS_GENERATION → EVIDENCE_PLANNING → EVIDENCE_COLLECTION → HYPOTHESIS_TESTING → FALSIFICATION → COUNTERFACTUAL_ANALYSIS → SYNTHESIS → VERIFICATION → COMPLETED (plus failure states)
- Hypothesis objects with id, statement, predicted_observables, required_evidence, potential_falsifiers, status, confidence
- Bounded adaptive loop (not a fixed script): the agent decides which tool to call next given current evidence; the engine enforces budget and mandates falsification
- Counterfactual simulator: pit timing and compound-change scenarios with explicit assumptions

### Phase 4 — Provider integration
- `ModelProvider` protocol; `UnionAlphaProvider` via OpenRouter using configured `MODEL_ID`/`OPENROUTER_API_KEY` (no keys in repo, no network access confirmed in this environment)
- Deterministic fallback investigation path so the product degrades honestly without a live model

### Phase 5 — API + UI
- FastAPI: create investigation, stream progress (SSE), fetch report/events
- Workstation UI: Investigation Workspace, Hypothesis Board, Evidence Graph, Counterfactual Lab, Report

### Phase 6 — Evaluation + release
- Benchmark set (15–20 fixed questions) with gold answers, run and scored honestly
- Final audit against the three specification documents; `docs/FINAL_AUDIT.md`

## 4. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| No OpenRouter credentials in this environment | Confirmed | Provider is configurable; system must run with deterministic path and clearly mark model-dependent steps as unavailable |
| Union Alpha behavior unverified (stealth model) | High | Never trust model arithmetic; all numbers from tools; verification pass cross-checks claims against evidence |
| FastF1 data quirks (in/out laps, tyre-life offsets) | Confirmed | Reference-verified filtering against known 2023 Bahrain values |
| Scope overrun | High | Vertical slice first: question → hypotheses → 3 tools → falsification → report; expand only after slice works |
| PowerShell stderr false-positives | Observed | Redirect streams to files and check exit codes explicitly |

## 5. MVP boundary (must-have)

Investigation engine, ≥3 hypotheses, deterministic tools, falsification, evidence/provenance, one counterfactual, provider abstraction, tests. Learn Mode, UI polish and benchmark dashboard follow only if the core loop is solid.

## 6. Test strategy

- Unit: each analytics function against hand-verified 2023 Bahrain reference values (e.g., VER stint-2 clean-lap set, pit laps 14/36)
- Integration: end-to-end investigation on cached session with scripted model double
- Failure paths: malformed tool args, missing driver, empty stints — expect explicit errors, never fabricated numbers
- Benchmark: fixed questions scored on evidence coverage, falsification completion, numerical correctness

## 7. Definition of done

One historical race investigated end-to-end; ≥8 deterministic tools; ≥3 hypotheses evaluated; ≥1 explicit falsification; ≥1 deterministic counterfactual; provenance on every conclusion; replay from event log; benchmark scored honestly; README with limitations.
