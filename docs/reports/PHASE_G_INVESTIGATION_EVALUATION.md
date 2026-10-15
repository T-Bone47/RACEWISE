# Phase G — Investigation Evaluation Report

## Initial repository state and baseline

- Branch `master`, clean tree at `e0a67f1`, synced with `origin/master`.
- Phases C–F complete and verified: `AnswerSchema` + `PromptRegistry` wired
  into `synthesize()` / `provider.generate_with_template()` / engine LLM
  path; model registry + router + comparison harness; NVIDIA NIM adapter
  live-verified (`openai/gpt-oss-20b`: text, structured output, tool calls);
  selective critique with deterministic gate.
- Question-engine corpus: 230 cases, 228 pass (99.1%), 2 known edge cases
  (single-driver stint comparison; single-ask compound expectation).
- Mandatory Perez case status at entry: telemetry gross 4.049 s labeled
  non-additive, net 3.08 s, residual −2.348 s / −0.464 s, sector 2 measured
  +0.411 s with mechanism evidence — all from the prior fix, all green.

## Implementation changes (this phase)

1. **Dead `analyze_stint` capability restored** (`engine.py`): the branch
   imported a non-existent `analyze_stint_comparison`. It now calls the real
   `fuse_stint_evidence` with the compiled stint number or the deterministic
   default. New shared helper `default_common_stint()` in
   `stint_evidence.py`, reused by the catalog route (identical behavior,
   verified by existing route tests).
2. **Planner scope-driven completion** (`planner.py`): sector-scoped loss
   questions always plan sector-resolving capabilities; any two-driver lap
   comparison always plans the measured-baseline capabilities. Same
   testability / session-type / budget gates; no duplication of existing steps.
3. **Corner resolution guard** (`synthesizer.py` + `intents.py`): bare
   "corner" now records corner scope (excluding the "corner speed"
   hypothesis phrase); corner questions carry a `corner-level attribution`
   limitation because no evidence layer indexes by corner.
4. **Benchmark module** (`tests/unit/test_investigation_benchmark.py`):
   12 end-to-end cases over real data with per-case metric recording
   (§8 of the mission): evidence completeness, reference validity,
   numerical correctness, baseline preservation, claim correctness,
   contradiction handling, uncertainty calibration, schema validity.

## Architecture and data-flow implications

- No new layers. The planner rule reuses the existing selection gates;
  the synthesizer guard reuses the existing `not_established` channel;
  the stint fix reuses the existing default-resolution logic via extraction.
- `spatial_scopes` gained bare-corner detection; its only consumers are
  compiler provenance and the new guard (verified by grep).
- Planner additions flow through the existing budget trim, so plan sizes
  stay bounded (observed: 1→3 and 5→7 capabilities on affected phrasings).

## Benchmark cases and evidence sources

All cases run `ask()` in-process against the canonical DB (no network,
no mocks, deterministic). Tool-level cases call capabilities directly.

| Case | Categories | Result |
|---|---|---|
| PEREZ_SECTOR2 | 1,2,3 | measured 0.732 OBSERVED; S2 0.411; gross DERIVED non-additive; net closer than gross; residual present; H1/H2/H3 mechanism evidence; verification clean |
| LAP_COMPARE | 1,3 | measured baseline present (fixed this phase — was telemetry-only) |
| STINT_ASK | 4 | analyze_stint executes; trend DERIVED; compounds OBSERVED |
| GAP_TOOL | 6 | official gap 11.987 s with documented semantics |
| FALSIFY | 7 | hypothesis states in bucket vocabulary with evidence ids |
| MISSING_LAP44 | 8 | INSUFFICIENT_EVIDENCE, missing data named, no telemetry figures |
| CORNER | 9 | corner-level limitation carried (fixed this phase) |
| HISTORIC_1950 | 8,9 | honest non-answerable status, zero telemetry claims |
| FOLLOWUP | 10 | continued_from linkage, sector-2 scope inherited, spatial rows present |
| COUNTERFACTUAL | 5 | INSUFFICIENT with named reason (served by lifecycle endpoint) |
| STINT_TOOL / GAP_TOOL | 4,6 | tool-level invariants |

## Numerical validation results

- Sector facts sum to the observed delta exactly (re-asserted).
- Residual identity holds: `residual_s == observed − estimated_pace_component_s`.
- Gross > net > measured ordering holds on the Perez case.
- Net strictly closer to measured than gross.
- **Residual definitions differ legitimately** (established by measurement):
  −2.348 = measured minus the 5 s-window signed net (20 windows,
  `compare_telemetry_lap`); −0.4644 = measured minus the 15 s-region
  signed net on the 0.25 s grid (`attribute_lap_loss`, 7 regions).
  Different estimators, different grids, same sign (model overestimates
  in both resolutions). Both documented in scope notes; no defect found,
  no code changed for this item.

## Live versus mocked provider results

- Deterministic benchmark: 12/12 pass, zero model calls.
- Live NVIDIA (`openai/gpt-oss-20b`): critique gate fires on the Perez
  answer; verdicts varied UPHELD/INCONCLUSIVE across runs (advisory-only
  design confirmed correct); direct evidence-grounded answer addressed
  sector 2, grounded 0.411, stated uncertainty (4/5 checks — omits the
  0.732 lap baseline; recorded limitation).
- No live calls in the committed test suite (all mocked/stubbed).

## Remaining limitations and blockers

- Elliptical follow-up fragments ("was it sector 2?", "was the loss in
  sector 2?") do not compile; full-sentence follow-ups work. Documented,
  not fixed (intake surgery out of scope for this milestone).
- `ask()`-path counterfactuals report INSUFFICIENT (served by the
  lifecycle endpoint); counterfactual rigor covered at tool level +
  goldens T-G10/T-G14.
- Time-aligned window estimates remain upper bounds (no distance
  channel ingested) — disclosed in assumptions, scope notes, and flags.

## Regression risks

- Planner additions: bounded by existing budget trim; corpus steady 99.1%.
- Bare-corner spatial rule: could only affect `spatial_scopes`
  consumers (provenance display + new guard); corpus confirms no shift.
- Stint helper extraction: route behavior verified identical by existing
  route tests (146-suite green).
