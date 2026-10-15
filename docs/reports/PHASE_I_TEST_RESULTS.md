# Phase I — Test Results

Exact commands and actual outcomes. Live calls and mocked tests are
reported separately. Nothing here is projected.

## New Phase I tests

| Command | Result |
|---|---|
| `pytest tests/unit/test_alignment.py` | **8 passed** (pure math, no DB) |
| `pytest tests/unit/test_sector_loss_reconciliation.py` | **10 passed** (updated to distance-aligned values) |
| `pytest tests/unit/test_investigation_benchmark.py` | **12 passed** |

## Regression suites (post-change)

| Command | Result |
|---|---|
| Corpus `scripts/measure_corpus.py` | **228/230 (99.1%)**, same 2 known edge cases (compile-only; estimators don't affect parsing) |
| `pytest tests/unit/test_q15_benchmarks.py` | **7 passed** (residual-fed similarity stable under new estimator) |
| `pytest tests/unit/test_phase_6t_goldens.py` | **3 passed** (reproduces 15/15 + replay verdicts on the re-captured baseline) |
| `test_phase_6s_qualifying::test_race_goldens_byte_identical` | re-pinned `e208…` → `1670123dd030d4ae` with documented justification |
| Full `pytest tests/unit` | **pending re-run** (last full run: 957 passed on pre-distance tree) |

## Live NVIDIA NIM

No new live calls this phase (quota stewardship; the estimator change
is deterministic and needs no model). Standing verified state from the
committed record (`data/model_verification.json`): `openai/gpt-oss-20b`
reachable + integration-tested, structured output and tool calls True.

## Secret and configuration checks

- `git grep` for `nvapi-`, `sk-ant-`, `sk-proj-`, `xoxb-`, `ghp_`: **clean**.
- `.env` / `racewise.env` untracked + gitignored: **verified**.
- New files contain no credentials (probe scripts read `.env` at
  runtime, never embed values): **verified by inspection**.

## Pre-existing failures

None introduced. Corpus edge cases Q006/Q076 predate this work.
The pinned-hash updates (goldens + 6s race hash) are documented
re-baselines of corrected estimators, not weakened assertions:
each prior value is preserved in a code comment with its
methodological basis.
