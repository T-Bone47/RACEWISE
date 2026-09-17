# RACEWISE — Phase 2 Implementation Plan

**Date:** 18 September 2026
**Method:** every status below reflects an actually executed check in this repository, not intent.

## CURRENT STATE (verified)

| Area | Status | Evidence |
|---|---|---|
| Test suite | VERIFIED | `python -m pytest -q` → 78 passed (56 tool-contract, 8 reference analytics, 4 simulator, engine flow, API, benchmark) |
| Frontend | VERIFIED | `npm run build` (tsc + vite) and `npm run lint` (oxlint) both clean |
| Tool boundary | VERIFIED | Commit `ae1afce`: recursive typed input validation, structured `ToolError{code,field}`, request size/depth bounds, explicit output schemas for all 12 tools, output validated before hashing, strict canonical hash without silent coercion |
| 12 deterministic tools | VERIFIED | All execute against cached 2023 Bahrain data in tests and benchmark |
| Engine state machine | PARTIALLY VERIFIED | Phases exist and record events, but `_finalize()` only checks that a hypothesis is SUPPORTED; `falsification_gate_open()` is never called by the flow and `_rounds_used` is never incremented |
| Deterministic fallback plan | PARTIALLY VERIFIED | Runs end-to-end (benchmark 8/8 COMPLETED) but hard-codes hypotheses and inserts falsification evidence unconditionally in code, rather than deriving it from the active investigation |
| Model provider | VERIFIED (unexercised) | `UnionAlphaProvider` implemented behind env config; no credentials in this environment, so no live model call has occurred |
| OpenCode integration | UNVERIFIED | No `mcpServers` configured in the repository; opencode 1.18.31 supports MCP. Nothing exposed to the current session yet |
| Benchmark | PARTIALLY VERIFIED | 8 questions measured honestly, but no adversarial/counterfactual/comparative extensions and no Union Alpha execution |
| UI | PARTIALLY VERIFIED | Workstation builds and renders trace/hypotheses/evidence/counterfactual; no falsification panel, model-status label, or evidence-taxonomy highlighting for new protocol fields |
| Replay | PARTIALLY VERIFIED | Full event log stored per investigation in process memory; deterministic replay not executable |
| Learn/Challenge mode | UNVERIFIED | Not built |

## GAPS (Phase 2 scope)

1. **Host-driven investigation loop (highest priority).** OpenCode (Union Alpha, this session) must drive RACEWISE through a structured protocol: FRAME → HYPOTHESES → EVIDENCE PLAN → TOOL_EXECUTION → EVALUATION → FALSIFICATION → COUNTERFACTUAL → SYNTHESIS, with structured outputs validated at every phase and `MODEL_FAILURE`/retry on malformed output.
2. **Falsification gate enforcement.** `can_finalize()` must require hypotheses present, evidence collected, falsification attempted AND recorded for the leading hypothesis, and no unresolved mandatory gate; otherwise transition to `INSUFFICIENT_EVIDENCE` or back to `EVIDENCE_COLLECTION`.
3. **Counterfactual discipline.** Counterfactuals only via deterministic simulator tools (`simulate_pit_timing`, compound change, scenario comparison) with baseline/assumptions/delta/uncertainty/provenance; otherwise record `COUNTERFACTUAL_SKIPPED` with reason.
4. **OpenCode-native tool exposure.** Expose the existing `ToolRegistry` surface (get_session, get_laps, get_stints, get_weather, get_race_control, get_pit_stops, filter_clean_laps, compare_sectors, analyze_tyre_degradation, analyze_traffic, analyze_pit_loss, compare_driver_pace, correlate_weather, detect_pace_anomaly, simulate_pit_timing, simulate_compound_change, compare_strategy_scenarios) through an MCP server so Union Alpha can call them in-session; never allow shell/model-code execution.
5. **Investigation event log & replay.** Named events (INVESTIGATION_CREATED … INVESTIGATION_COMPLETED, MODEL_FAILURE, TOOL_FAILURE, INSUFFICIENT_EVIDENCE) with enough metadata to reconstruct the investigation; model decisions recorded separately from deterministic outputs.
6. **Evidence taxonomy in reports/UI.** FACT/CALCULATION/INFERENCE/COUNTERFACTUAL/ASSUMPTION distinguished everywhere; confidence never substitutes for evidence.
7. **Evaluation harness.** Extend the 8-question benchmark to 23+ (add ≥5 adversarial, ≥5 counterfactual, ≥5 comparative-driver) recording honest per-run telemetry; no invented gold answers.
8. **UI upgrades** (only after backend): hypothesis board, evidence timeline, falsification, counterfactual, conclusion, provenance, model status; explicit "Union Alpha" vs "Deterministic fallback" labeling.
9. **Learn Mode / Challenge Mode** grounded in the actual investigation evidence, with unsupported claims labeled as such.
10. **Security hardening.** Treat radio/metadata text as DATA (no instruction interpretation), reject oversized/malformed input, keep the allow-list closed, no path traversal or shell paths.

## ARCHITECTURE (target)

```text
OpenCode (this session, Union Alpha)
    ↓ structured investigation protocol (validated phase outputs)
racewise.investigation.protocol  (phase contracts, retry, MODEL_FAILURE)
    ↓
InvestigationEngine (state machine + invariants + event log)
    ↓
ToolRegistry (allow-list, typed validation, provenance hashes)
    ↓
Deterministic tools → canonical schemas → FastF1 adapter (cached)
    ↓
Report + replay + evaluation harness + workstation UI
```

MCP server (`racewise.mcp`) wraps `build_default_registry` per session; tool calls return the registry's validated envelope. No nested OpenCode subprocess; no model-generated code execution.

## IMPLEMENTATION ORDER

1. Engine invariants: `can_finalize()`, falsification gate, event names, `INSUFFICIENT_EVIDENCE` transitions. Tests first.
2. Protocol module: phase input/output validation, retry with structured errors, replay-safe event emission.
3. MCP server exposing the registry (verify with `opencode mcp list` config + manual tool call).
4. Run the three real investigations in this session (VER pace evolution; adversarial tyre-degradation challenge; five-lap pit counterfactual) and store reports + event logs.
5. Extend benchmark to 23+ questions with honest telemetry; wire into pytest.
6. UI: falsification panel, model status, taxonomy badges; Learn/Challenge endpoints and panels.
7. Documentation: PHASE_2_IMPLEMENTATION.md, OPENCode_RACEWISE_INTEGRATION.md, INVESTIGATION_PROTOCOL.md, FALSIFICATION_PROTOCOL.md, EVIDENCE_MODEL.md, EVALUATION_PROTOCOL.md; update README/FINAL_AUDIT with VERIFIED/PARTIALLY VERIFIED/UNVERIFIED labels.

## TEST PLAN

- Unit: gate invariants (finalize blocked without falsification; INSUFFICIENT_EVIDENCE path), protocol validation (each malformed phase output → structured retry → MODEL_FAILURE), counterfactual skip records.
- Integration: host-driven investigation via protocol with scripted model doubles (success, malformed, falsification-refuses); MCP tool call round-trip; replay equivalence of deterministic portions.
- Benchmark: 23+ items; assertions on measured behavior only (completion, hypotheses ≥3, falsification attempted, counterfactual or explicit skip, tool success).
- Regression: existing 78 tests keep passing; frontend build + lint clean.

## ACCEPTANCE CRITERIA

1. No nested OpenCode subprocess; the current session is the host.
2. No fake AI activity; fallback explicitly labeled.
3. All numbers originate from `ToolRegistry`-executed deterministic tools.
4. Tool calls allow-listed; inputs/outputs validated; provenance hashes verified.
5. Falsification genuinely enforced by the state machine (unit-proven).
6. Counterfactuals only from deterministic simulation; skips recorded with reasons.
7. Event log reconstructs the investigation; deterministic replay equivalent.
8. ≥1 real Union Alpha investigation executed in this session and stored with provenance.
9. Existing tests pass; frontend builds.
10. Documentation reflects verified state only.
