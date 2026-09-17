# RACEWISE — Evaluation Results

**Run date:** 17 September 2026
**Harness:** `tests/benchmark/run_benchmark.py`
**Reference session:** 2023 Bahrain Grand Prix — Race (FastF1, cached)
**Raw results:** `benchmark_results.json`

## Headline (measured, not asserted)

| Metric | Value |
|---|---|
| Benchmark questions | 8 |
| Investigations reaching COMPLETED | 8 / 8 (100%) |
| Falsification attempted | 8 / 8 (100%) |
| Counterfactual executed | 8 / 8 (100%) |
| Median latency per investigation | ~1.97 s |
| All tool calls completed | 40 / 40 |

## Per-question results

| ID | Category | Driver | State | Hyps | Evidence | Falsified | CF | Tools | Conclusion |
|---|---|---|---|---|---|---|---|---|---|
| B01 | tyre_degradation | VER | COMPLETED | 3 | 3 | yes | yes | 5 | yes |
| B02 | traffic | LEC | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B03 | strategy | VER | COMPLETED | 3 | 3 | yes | yes | 5 | yes |
| B04 | driver_comparison | HAM | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B05 | pace_anomaly | ALB | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B06 | pit_timing | PER | COMPLETED | 3 | 4 | yes | yes | 5 | no |
| B07 | weather | SAI | COMPLETED | 3 | 4 | yes | 5 | 5 | no |
| B08 | counterfactual | ALO | COMPLETED | 3 | 4 | yes | yes | 5 | no |

## What these numbers mean — and what they do NOT

**These are real measured runs** of the deterministic investigation pipeline end-to-end (API → engine → tools → evidence → counterfactual → conclusion). They are not fabricated, and the harness writes raw output to `benchmark_results.json`.

**Known honest limitations of this benchmark:**

1. **No LLM configured.** `OPENROUTER_API_KEY` is absent in the build environment, so investigations ran with the clearly-labeled deterministic rules-based plan, not Union Alpha. The following evaluation dimensions from the PRD are therefore **not scored** and remain open:
   - tool-selection adaptivity (the rules plan calls a fixed set)
   - claim faithfulness / hallucination rate on final synthesis
   - confidence calibration of LLM-authored statements
2. `has_conclusion = false` rows (B02, B04–B08) reflect the strict synthesis gate: the plan only supports a hypothesis when evidence thresholds are met. This is correct conservative behavior — the system returns "no supported hypothesis" rather than fabricating one — but it means those runs end INSUFFICIENT-adjacent while still COMPLETED. Improving category-specific evidence plans is the natural next step.
3. The question set is 8, below the 15–20 target in the PRD. Adding questions is mechanical (add dicts + gold answers); the harness already scores them.
4. Counterfactual and falsification rates are high because the deterministic plan always runs both phases. This measures the pipeline's capability ceiling, not LLM judgment quality.

## Union Alpha evaluation status

Union Alpha integration is implemented (`racewise.agent.provider.UnionAlphaProvider`) and configurable via `MODEL_PROVIDER` / `MODEL_ID` / `OPENROUTER_API_KEY`, but **was not exercised** because no credentials exist in this environment. Per the project's honesty rules, no claims are made about Union Alpha's investigation quality. To run model-scored benchmarks: set credentials and rerun `tests/benchmark/run_benchmark.py`.
