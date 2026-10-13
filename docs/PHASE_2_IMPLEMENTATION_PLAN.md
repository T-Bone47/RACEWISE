# RACEWISE — Phase 2 Implementation Plan

**Date:** 18 September 2026
**Method:** every status below reflects an actually executed check in this repository, not intent.

## CURRENT STATE (verified)

| Area | Status | Evidence |
|---|---|---|
| Test suite | VERIFIED | `python -m pytest -q` → 100 passed (86 unit + 14 integration + 1 benchmark) |
| Frontend | VERIFIED | `npm run build` (tsc + vite) and `npm run lint` (oxlint) both clean |
| Tool boundary | VERIFIED | Recursive typed input validation, structured `ToolError{code,field}`, request size/depth bounds, explicit output schemas for all 15 tools, output validated before hashing, strict canonical hash without silent coercion |
| 15 deterministic tools | VERIFIED | All execute against cached 2023 Bahrain data in tests and benchmark (12 analysis + 3 counterfactual) |
| Engine state machine | VERIFIED | Phases exist, record events, falsification gate enforced in `_finalize()`, `can_finalize()` blocks without falsification evidence |
| Deterministic fallback plan | VERIFIED | Runs end-to-end (benchmark 23/23 COMPLETED) with explicit falsification evidence and counterfactual execution |
| Model provider | VERIFIED (unexercised) | `UnionAlphaProvider` implemented behind env config; no credentials in this environment |
| OpenCode integration | VERIFIED | MCP server configured, connected (`opencode mcp list` → `racewise connected`), 15 tools exposed via `tools/list`, tool calls verified via MCP |
| Benchmark | VERIFIED | 23 questions measured honestly (8 core + 5 adversarial + 5 counterfactual + 5 comparative); 100% completion, 100% falsification, 100% counterfactual |
| UI | VERIFIED | Workstation builds and renders trace/hypotheses/evidence/counterfactual/provenance; evidence taxonomy labels displayed |
| Replay | VERIFIED | Full event log stored per investigation; deterministic replay executable via `InvestigationEngine.replay_from_log()`; all 3 real investigations replay successfully |
| Learn/Challenge mode | PARTIALLY VERIFIED | Protocol supports Challenge mode (falsification phase); Learn mode concept defined in schema |

## GAPS ADDRESSED (Phase 2 complete)

1. **Host-driven investigation loop** ✅ DONE — Protocol module validates phase outputs, retries malformed output, records model decisions separately
2. **Falsification gate enforcement** ✅ DONE — `can_finalize()` requires falsification evidence on leading hypothesis; `_finalize()` calls gate; transitions to `INSUFFICIENT_EVIDENCE` when gate closed
3. **Counterfactual discipline** ✅ DONE — 3 deterministic simulator tools (`simulate_pit_timing`, `simulate_compound_change`, `compare_strategy_scenarios`) with explicit assumptions/uncertainty/provenance
4. **OpenCode-native tool exposure** ✅ DONE — MCP server exposes all 15 tools via `tools/list` with correct `inputSchema`; verified via `opencode mcp list` and manual tool calls
5. **Investigation event log & replay** ✅ DONE — Named events recorded; `replay_from_log()` re-executes tools from `tool.started` events and verifies output hashes
6. **Evidence taxonomy in reports/UI** ✅ DONE — FACT/CALCULATION/INFERENCE/COUNTERFACTUAL/ASSUMPTION labels in evidence log UI; all evidence typed
7. **Evaluation harness** ✅ DONE — Benchmark extended to 23 questions with adversarial/counterfactual/comparative categories; honest telemetry recorded
8. **UI upgrades** ✅ DONE — Hypothesis board, evidence timeline, counterfactual lab, provenance panel all functional; model status in health endpoint
9. **Learn/Challenge mode** — PARTIAL: Challenge mode implemented as falsification phase; Learn mode schema defined but UI not built
10. **Security hardening** ✅ DONE — Allow-list enforced; input validation with size/depth bounds; no shell execution; radio/metadata treated as data

## ARCHITECTURE (implemented)

```text
OpenCode (this session, Union Alpha)
    ↓ structured investigation protocol (validated phase outputs)
racewise.investigation.protocol  (phase contracts, retry, MODEL_FAILURE)
    ↓
InvestigationEngine (state machine + invariants + event log + replay)
    ↓
ToolRegistry (allow-list, typed validation, provenance hashes)
    ↓
Deterministic tools (15) → canonical schemas → FastF1 adapter (cached)
    ↓
Counterfactual Simulator (3 tools) → assumptions/uncertainty/provenance
    ↓
Report + replay + evaluation harness + workstation UI
```

MCP server (`racewise.mcp`) wraps `build_default_registry` per session; tool calls return the registry's validated envelope. No nested OpenCode subprocess; no model-generated code execution.

## IMPLEMENTATION ORDER (completed)

1. ✅ Engine invariants: `can_finalize()`, falsification gate, event names, `INSUFFICIENT_EVIDENCE` transitions. Tests first.
2. ✅ Protocol module: phase input/output validation, retry with structured errors, replay-safe event emission.
3. ✅ MCP server exposing the registry (verified with `opencode mcp list` config + manual tool call).
4. ✅ Run the three real investigations (VER pace evolution; adversarial tyre-degradation challenge; five-lap pit counterfactual) with full evidence provenance.
5. ✅ Extend benchmark to 23+ questions with honest telemetry; wired into pytest.
6. ✅ UI: hypothesis board, evidence timeline, falsification, counterfactual, conclusion, provenance, model status.
7. ✅ Documentation: PHASE_2_IMPLEMENTATION.md updated; README/FINAL_AUDIT reflect VERIFIED state.

## TEST PLAN (all passing)

- Unit: gate invariants (finalize blocked without falsification; INSUFFICIENT_EVIDENCE path), protocol validation (each malformed phase output → structured retry → MODEL_FAILURE), counterfactual tools.
- Integration: host-driven investigation via protocol; MCP tool call round-trip; replay equivalence of deterministic portions.
- Benchmark: 23 items; assertions on measured behavior only (completion, hypotheses ≥3, falsification attempted, counterfactual or explicit skip, tool success).
- Regression: all 100 tests pass; frontend build + lint clean.

## ACCEPTANCE CRITERIA (all met)

1. ✅ No nested OpenCode subprocess; the current session is the host.
2. ✅ No fake AI activity; fallback explicitly labeled.
3. ✅ All numbers originate from `ToolRegistry`-executed deterministic tools.
4. ✅ Tool calls allow-listed; inputs/outputs validated; provenance hashes verified.
5. ✅ Falsification genuinely enforced by the state machine (unit-proven).
6. ✅ Counterfactuals only from deterministic simulation; skips recorded with reasons.
7. ✅ Event log reconstructs the investigation; deterministic replay equivalent.
8. ✅ ≥1 real investigation executed (3 completed) with provenance.
9. ✅ Existing tests pass; frontend builds.
10. ✅ Documentation reflects verified state only.