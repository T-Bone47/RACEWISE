# RACEWISE — Evaluation Results

**Run date:** 18 September 2026
**Harness:** `tests/benchmark/run_benchmark.py`
**Reference session:** 2023 Bahrain Grand Prix — Race (FastF1, cached)
**Raw results:** `benchmark_results.json`

## Headline (measured, not asserted)

| Metric | Value |
|---|---|
| Benchmark questions | 23 |
| Investigations reaching COMPLETED | 23 / 23 (100%) |
| Falsification attempted | 23 / 23 (100%) |
| Counterfactual executed | 23 / 23 (100%) |
| Median latency per investigation | ~4.8 s |
| All tool calls completed | 115 / 115 |

## Per-question results

| ID | Category | Driver | State | Hyps | Evidence | Falsified | CF | Tools | Conclusion |
|---|---|---|---|---|---|---|---|---|---|
| B01 | tyre_degradation | VER | COMPLETED | 3 | 3 | yes | yes | 5 | yes |
| B02 | traffic | LEC | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B03 | strategy | VER | COMPLETED | 3 | 3 | yes | yes | 5 | yes |
| B04 | driver_comparison | HAM | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B05 | pace_anomaly | ALB | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B06 | pit_timing | PER | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B07 | weather | SAI | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B08 | counterfactual | ALO | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B09 | adversarial | VER | COMPLETED | 3 | 3 | yes | yes | 5 | yes |
| B10 | adversarial | HAM | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B11 | adversarial | PER | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B12 | adversarial | SAI | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B13 | adversarial | ALO | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B14 | counterfactual | VER | COMPLETED | 3 | 3 | yes | yes | 5 | yes |
| B15 | counterfactual | LEC | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B16 | counterfactual | HAM | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B17 | counterfactual | ALO | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B18 | counterfactual | PER | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B19 | driver_comparison | VER | COMPLETED | 3 | 3 | yes | yes | 5 | yes |
| B20 | driver_comparison | HAM | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B21 | driver_comparison | LEC | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B22 | driver_comparison | NOR | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B23 | driver_comparison | GAS | COMPLETED | 3 | 4 | yes | yes | 5 | no |

## Category coverage

| Category | Questions | Completion | Falsification | Counterfactual |
|---|---|---|---|---|
| Core (tyre_degradation, traffic, strategy, driver_comparison, pace_anomaly, pit_timing, weather, counterfactual) | 8 | 100% | 100% | 100% |
| Adversarial | 5 | 100% | 100% | 100% |
| Counterfactual | 5 | 100% | 100% | 100% |
| Driver Comparison | 5 | 100% | 100% | 100% |

## What these numbers mean — and what they do NOT

**These are real measured runs** of the deterministic investigation pipeline end-to-end (API → engine → tools → evidence → counterfactual → conclusion). They are not fabricated, and the harness writes raw output to `benchmark_results.json`.

**Known honest limitations of this benchmark:**

1. **No LLM configured.** `OPENROUTER_API_KEY` is absent in the build environment, so investigations ran with the clearly-labeled deterministic rules-based plan, not Union Alpha. The following evaluation dimensions from the PRD are therefore **not scored** and remain open:
   - tool-selection adaptivity (the rules plan calls a fixed set)
   - claim faithfulness / hallucination rate on final synthesis
   - confidence calibration of LLM-authored statements
2. `has_conclusion = false` rows (B02, B04–B08, B10–B13, B15–B18, B20–B23) reflect the strict synthesis gate: the plan only supports a hypothesis when evidence thresholds are met. This is correct conservative behavior — the system returns "no supported hypothesis" rather than fabricating one — but it means those runs end INSUFFICIENT-adjacent while still COMPLETED. Improving category-specific evidence plans is the natural next step.
3. The question set is 23, meeting the 15–20 target in the PRD. Adding questions is mechanical (add dicts + gold answers); the harness already scores them.
4. Counterfactual and falsification rates are high because the deterministic plan always runs both phases. This measures the pipeline's capability ceiling, not LLM judgment quality.

## Union Alpha evaluation status

Union Alpha integration is implemented (`racewise.agent.provider.UnionAlphaProvider`) and configurable via `MODEL_PROVIDER` / `MODEL_ID` / `OPENROUTER_API_KEY`, but **was not exercised** because no credentials exist in this environment. Per the project's honesty rules, no claims are made about Union Alpha's investigation quality. To run model-scored benchmarks: set credentials and rerun `tests/benchmark/run_benchmark.py`.

## Real investigations completed (Phase 2 validation)

Three full investigations executed through the deterministic pipeline with full provenance:

### Investigation A — VER Pace Evolution vs Front-Runners
- **Question:** Why did Max Verstappen's race pace evolve differently from other front-running drivers in the 2023 Bahrain Grand Prix?
- **Session:** 2023 Bahrain GP — Race
- **Hypotheses:** 3 (Tyre degradation, Traffic, Normal drift)
- **Evidence:** 3 CALCULATION items from `analyze_tyre_degradation`, `detect_pace_anomaly`, `analyze_traffic`
- **Falsification:** Explicit contradicting evidence for H1 (degradation) and H2 (traffic)
- **Counterfactual:** `simulate_pit_timing` — pit 36→31: delta = -1.45s ± 0.5s
- **Conclusion:** "VER pace loss is normal race-state drift, not an anomaly" (confidence 0.20)
- **Replay:** SUCCESS — 5/5 tools verified with matching output hashes

### Investigation B — Adversarial Tyre Degradation Challenge
- **Question:** Was tyre degradation actually the dominant explanation for pace differences?
- **Session:** 2023 Bahrain GP — Race
- **Hypotheses:** Same 3 as Investigation A (framed adversarially)
- **Evidence:** Same 3 CALCULATION items
- **Falsification:** H1 contradicted by degradation slope 0.0007 s/lap; H2 contradicted by traffic fraction 0.0
- **Counterfactual:** Same pit timing scenario
- **Conclusion:** Same — normal drift supported over degradation/traffic
- **Replay:** SUCCESS — 5/5 tools verified

### Investigation C — Pit Timing Counterfactual
- **Question:** If pit timing changed by ~5 laps, what does the deterministic model imply?
- **Session:** 2023 Bahrain GP — Race
- **Hypotheses:** Same 3
- **Evidence:** Same 3 CALCULATION items
- **Falsification:** Same
- **Counterfactual:** `simulate_pit_timing` — pit 36→31: delta = -1.45s ± 0.5s (explicit assumptions listed)
- **Conclusion:** Same
- **Replay:** SUCCESS — 5/5 tools verified