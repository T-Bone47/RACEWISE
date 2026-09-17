# RACEWISE — Final Audit

**Date:** 17 September 2026
**Method:** every status below reflects an actually executed check, not intent.

## Requirement status

| Requirement | Status | Evidence |
|---|---|---|
| One historical race investigated end-to-end | DONE | Live smoke test: investigation `710436cab77a` reached COMPLETED via SSE with 3 hypotheses, 5 tools, 1 counterfactual, conclusion |
| ≥8 deterministic tools | DONE (12) | `build_default_registry`: get_session, get_laps, get_stints, analyze_tyre_degradation, analyze_traffic, compare_sectors, compare_driver_pace, detect_pace_anomaly, analyze_pit_loss, get_weather, get_race_control, get_pit_stops — all executed against real cached data with verified outputs |
| ≥3 hypotheses generated & evaluated | DONE | 3 per investigation with confidence + status transitions (unit + API tested) |
| ≥1 explicit falsification step | DONE | FALSIFICATION state in engine + rules plan produces contradicting evidence; benchmark falsification_rate 1.0 |
| ≥1 deterministic counterfactual | DONE | `simulate_pit_timing` v1.0.0; live demo −1.45 s ± 0.5 for pit 36→31 |
| Provenance on conclusions | DONE | SHA-256 input/output hashes on every ToolExecution; event log records all state/evidence transitions |
| Replayable investigation | PARTIAL | Full event log stored per investigation; persistence across restart not implemented |
| Benchmark scored honestly | PARTIAL | 8 questions measured (target 15–20); LLM-dependent dimensions unscored without credentials |
| Polished web UI | DONE | React workstation: trace, hypothesis board, evidence log, counterfactual lab, report; type-checks clean |
| Model-agnostic core | DONE | `ModelProvider` protocol; Union Alpha behind config only; deterministic fallback labeled |
| Tests pass | DONE | 21/21 (8 reference analytics, 4 simulator, 4 engine flow, 5 API) |
| README w/ limitations | DONE | README.md + docs/EVALUATION.md |

## Known limitations (open work)

1. **Union Alpha not exercised** — no `OPENROUTER_API_KEY` in environment. Provider, tool-calling payload and structured investigation prompts are implemented; adaptive tool selection and LLM synthesis remain unexercised. Benchmark dimensions requiring the model (tool-selection adaptivity, claim faithfulness, calibration) are explicitly not scored.
2. **Benchmark size** — 8 fixed questions vs 15–20 target; each needs a gold reference answer for numerical-accuracy scoring (harness structure supports it).
3. **Persistence** — investigations live in process memory; SQLite/Postgres tables defined in architecture not yet wired.
4. **Learn/Challenge mode UI** — Challenge exists as the engine's falsification phase; the dedicated UI screens and Learn Mode concept explanations are not built.
5. **Evidence graph visualization** — data model supports it; UI shows evidence log instead.
6. **Single session** — benchmark/fixture depth limited to 2023 Bahrain; more sessions need reference verification before use.

## Tooling-environment caveats (documented for reproducibility)

- Write tool failures were intermittent during the build; several files were created via shell workarounds and later verified by re-read. All final artifacts were read back and verified before commit.
- FastF1 logs to stderr, which PowerShell surfaces as NativeCommandError; exit codes were checked explicitly throughout.
