# PHASE 6N COMPLETION REPORT

## 1. Executive Summary

Phase 6N adds the first full engineering-investigation orchestration layer
above the verified 6E→6M analytical chain: deterministic question framing
(closed vocabulary), a planned evidence ledger, six-hypothesis evaluation
with a falsification gate that blocks unresolved contradictions, bounded
6I-eligible counterfactuals, an evidence-bound synthesis and a complete
decision trace. No analytical engine was rebuilt; the legacy LLM
investigation engine was neither invoked nor modified. Full regression:
**591 passed**. Final readiness: **READY_FOR_ENGINEERING_INVESTIGATION**.

## 2. Baseline

- Tests at 6M baseline: 554 passing; MCP tools: 37 (22 historical)
- Telemetry: 93 sessions, 787,555 rows; canonical DB ~405.2 MB
- Zero storage growth through 6M; 6M commits `60d9fdf`, `8c8b19a`

## 3. Investigation Architecture

`src/racewise/data/historical/investigation_synthesis.py`
(`6n_investigation_v1`): question framing → evidence plan → collection →
ledger → hypothesis evaluation → falsification gate → counterfactual
eligibility/execution → synthesis → decision trace → snapshot/provenance/
hash. Consumes 6E/6F/6G/6H/6I/6K/6L/6M verbatim; duplicates no calculation.

## 4. Question Framing

Closed 7-type vocabulary; structural validation (bounds, distinct drivers,
required params) plus data-derived validation (race result exists, drivers
in result, requested lap exists in canonical lap times, requested stint
exists in canonical stints). States VALID / INVALID / UNAVAILABLE. No
silent broadening (unknown pattern → collection UNAVAILABLE, conclusion
UNAVAILABLE, empty ledger).

## 5. Evidence Planning

`QUESTION_EVIDENCE_PLAN` maps each question type only to existing
registered tools (6E `attribute_lap_loss`, 6F `fuse_lap_evidence`, 6G
`fuse_stint_evidence`, 6H `decompose_race_gap`, 6I extraction/simulators,
6K `analyze_performance_regimes`, 6L/6M pattern layers).

## 6. Evidence Ledger

Items carry evidence_id, type (FACT/CALCULATION/INFERENCE/COUNTERFACTUAL),
source_phase, source_tool, source_reference, source_hash (sha256[:16]),
claim, claim_class (OBSERVED/DERIVED/INFERRED/MODELLED — never merged),
measured_value, units, state, hypothesis_ids, assumptions, limitations,
supports/contradicts. Bounded at 40 items. (Fixed this phase: null states
serialize as null, never the string "None".)

## 7. Hypothesis Evaluation

Per hypothesis: supporting/contradicting/non-decisive evidence lists,
coverage counts, one aggregate state from the closed 8-state vocabulary
(+NOT_REQUESTED), falsification_status, unresolved_contradictions.
No scores, no ranking.

## 8. Falsification Gate

Direct conflict pairs → MIXED_EVIDENCE + gate-blocked
(`hypotheses_with_unresolved_contradictions` disjoint from
`establishable_hypotheses`). 19 conflicts preserved (UNRESOLVED) on the
reference stint investigation. Regression-tested: SUPPORTED +
CONTRADICTED can never synthesize as established.

## 9. Counterfactual Eligibility

Probe via the exact 6I `extract_speed_profile` path (stint probes on 6G
`selected_laps`, 3 probe / 2 collect). States: ELIGIBLE / INELIGIBLE
(race-level structurally ineligible) / UNSUPPORTED_MODEL (non-speed) /
TELEMETRY_UNAVAILABLE / INSUFFICIENT_EVIDENCE.

## 10. Counterfactual Execution

Only ELIGIBLE candidates, through untouched 6I simulators, ≤ 2 executed.
Reference values reproduced: lap CF −1.019427 s; stint CF −1.650507 s
(MODELLED, "not history, not prediction").

## 11. Investigation Synthesis

Closed conclusion vocabulary: SUPPORTED_BY_AVAILABLE_EVIDENCE /
MIXED_EVIDENCE / INSUFFICIENT_EVIDENCE / NOT_TESTABLE / UNAVAILABLE.
Honest insufficiency preserved where evidence is sparse (Q16 goldens 03,
04, 06, 07, 08).

## 12. Decision Trace

Every synthesis statement = TRACE-nnn with basis ⊆ ledger evidence IDs
(asserted by test), type, hypotheses, contradictory evidence, status.
Frontend entries expand to phase/tool/source-hash/measured value/limits.

## 13. Replay / Determinism

In-process repeat byte-identical; subprocess replays identical under
PYTHONHASHSEED=3 and 29; MCP wire repeat identical (duration_ms excluded);
API repeat byte-identical. No timestamps/PIDs/random IDs; investigation_id
derived from scope.

## 14. Q16 Results

`q16_benchmarks.py`, 8 goldens over real canonical data (replay identical
for all):

| golden | question | conclusion | evidence |
|---|---|---|---|
| GOLDEN_01 | LAP_PERFORMANCE 2023 R1 lap 6 | MIXED_EVIDENCE | 12 |
| GOLDEN_02 | STINT_PERFORMANCE 2023 R1 stint 1 | MIXED_EVIDENCE | 30 |
| GOLDEN_03 | RACE_GAP 2024 R14 | INSUFFICIENT_EVIDENCE | 5 |
| GOLDEN_04 | PERFORMANCE_REGIME 2022 R4 | INSUFFICIENT_EVIDENCE | 6 |
| GOLDEN_05 | HYPOTHESIS_EVALUATION 2023 R1 lap 11 | SUPPORTED_BY_AVAILABLE_EVIDENCE | 12 |
| GOLDEN_06 | CROSS_RACE_PATTERN (discovered 6L id) | INSUFFICIENT_EVIDENCE | 7 |
| GOLDEN_07 | COUNTERFACTUAL_ELIGIBILITY | INSUFFICIENT_EVIDENCE | 1 |
| GOLDEN_08 | RACE_GAP 1950 R1 (telemetry-poor) | INSUFFICIENT_EVIDENCE | 0 |

## 15. Negative Controls

INVALID: same driver, unknown question_type, season 1949, round 100,
max_evidence_items 41, missing pattern_id (also rejected at the MCP tool
contract for unknown parameters). UNAVAILABLE: missing race, lap 999
beyond race, unknown pattern_id (collection + conclusion + zero evidence).
Counterfactual: race-level structurally INELIGIBLE; stint scope only
STINT_SPEED_PROFILE; non-speed signal refused by the untouched 6I
simulator (status UNSUPPORTED). No silent fallback anywhere.

## 16. Performance

Q16 elapsed per golden: p50 ≈ 2.1 s, p95 ≈ 58 s (GOLDEN_06, dominated by
the 6L corpus scan in discovery + collection), max ≈ 58 s. Lap/stint/race
investigations ~0.1–5.6 s. Layer results memoized within one invocation.

## 17. Storage

Zero growth: DB 405,188,608 bytes before/after a full investigation, zero
row-count deltas across all tables, mtime unchanged. Derived-on-read; no
persistence added.

## 18. Security

No eval/exec/shell/arbitrary SQL/dynamic tool invocation in the 6N module;
closed enums; mandatory bounds; unknown parameters rejected at the tool
contract; distinct-driver validation; read-only DB. Frontend renders only
(single fetch, no dangerouslySetInnerHTML/eval).

## 19. No-Fabrication Audit

6N core module CLEAN (grep of caused/causes/proves/proven/confidence/most
likely/best explanation/optimal/guarantee/would-have-won/... — only the
negation disclaimer in the module docstring). Tool/API/frontend 6N code
clean; the confidence-language hits in `app.py` belong to the legacy LLM
engine (pre-existing, out of 6N scope, untouched).

## 20. Frontend

`apps/web/src/InvestigationView.tsx` (wired in App.tsx): question-framing
form (closed vocabulary, per-type inputs), hypothesis table (states, never
ranked), evidence ledger, preserved contradictions, counterfactual
eligibility/execution (MODELLED deltas), evidence-bound synthesis, and an
expandable decision trace to source phase/tool/hash/value. `npm run build`
passes; no console errors in the build output.

## 21. Tests

39 new tests (tests/unit/test_investigation_synthesis.py,
test_q16_benchmarks.py) + 3 MCP wire tests
(tests/integration/test_historical_tools_mcp.py). Full suite: **591
passed** (554 baseline + 37 new − 0 removed), including updated
registry-count assertions (23 historical tools) in
test_performance_patterns.py, test_performance_regimes.py,
test_q14_benchmarks.py, test_q15_benchmarks.py.

## 22. Known Limitations

- GOLDEN_06's discovered pattern is non-recurring under 6M at the
  collector scope → honest INSUFFICIENT_EVIDENCE.
- RACE_GAP/PERFORMANCE_REGIME corpus evidence is sparse → honest
  INSUFFICIENT_EVIDENCE conclusions.
- Counterfactuals limited to lap/stint speed-profile (6I scope).
- Cross-race investigations cost ~58 s (6L scan) — documented, not hidden.

## 23. Files Changed

Core: `src/racewise/data/historical/investigation_synthesis.py` (new),
`src/racewise/data/historical/q16_benchmarks.py` (new).
Surface: `src/racewise/tools/historical.py` (RunEngineeringInvestigationTool,
registry 22→23), `src/racewise/api/app.py` (GET
/api/catalog/engineering-investigation), `apps/web/src/InvestigationView.tsx`
(new), `apps/web/src/App.tsx`, `apps/web/src/App.css`.
Tests: `tests/unit/test_investigation_synthesis.py` (new),
`tests/unit/test_q16_benchmarks.py` (new),
`tests/integration/test_historical_tools_mcp.py` (extended),
4 registry-count assertions updated.
Docs: `docs/PHASE_6N_INVESTIGATION_SYNTHESIS.md` (new), this report.

## 24. Verification Commands

```
python -m pytest -q tests src --ignore=tests/integration/test_investigation_flow.py
python -m src.racewise.data.historical.q16_benchmarks
cd apps/web && npm run build
PYTHONHASHSEED=3 python -c "...run_engineering_investigation..."
PYTHONHASHSEED=29 python -c "...run_engineering_investigation..."
```

(The legacy-flow integration test is excluded per master-prompt scope; it
belongs to the other thread's uncommitted changes.)

## 25. Final Readiness

PHASE 6N STATUS:
READY_FOR_ENGINEERING_INVESTIGATION
