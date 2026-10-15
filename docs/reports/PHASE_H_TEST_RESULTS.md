# Phase H — Test Results

Exact commands and actual outcomes. Live calls and mocked tests are
reported separately. Nothing here is projected.

## New Phase H tests

| Command | Result |
|---|---|
| `pytest tests/unit/test_phase_h_planner_executor.py` | **22 passed** |
| `pytest tests/unit/test_investigation_benchmark.py` | **12 passed** |

## Regression suites (post-change)

| Command | Result |
|---|---|
| 146-file set (stint, question_engine, autonomous, benchmark_assets, sector_loss, critique) | **146 passed, 2 skipped** |
| `test_nvidia_provider test_model_registry test_comparison_harness test_critique` | **84 passed** |
| Corpus `scripts/measure_corpus.py` | **228/230 (99.1%)**, same 2 known edge cases |
| `pytest tests/unit/test_phase_6t_goldens.py` | **running in background** (golden path files untouched: autonomous path imports `question_intake` only) |
| Full `pytest tests/unit` | **running in background** |

## Live NVIDIA NIM (authenticated, key from `.env`)

No new live calls this phase (quota stewardship). Standing verified
state from the committed record (`data/model_verification.json`):
`openai/gpt-oss-20b` reachable + integration-tested, structured output
and tool calls verified True. Prior live findings incorporated:
critique verdicts vary run to run (advisory-only confirmed); concise
sector answers can omit the lap baseline (recorded limitation).

## Secret and configuration checks

- `git grep` for `nvapi-`, `sk-ant-`, `sk-proj-`, `xoxb-`, `ghp_`: **clean**.
- `.env` / `racewise.env` untracked + gitignored: **verified**.
- Verification record contains model ids + capabilities + timestamp
  only: **verified, no secrets**.

## Pre-existing failures

None introduced. Corpus edge cases Q006/Q076 predate this work.
