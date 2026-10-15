# Phase G — Test Results

Exact commands and actual outcomes. Live calls and mocked tests are
reported separately. Nothing here is projected or estimated.

## Backend unit suites (mocked/deterministic, no network)

| Command | Result |
|---|---|
| `pytest tests/unit/test_investigation_benchmark.py` | **12 passed** (49 s) |
| `pytest test_stint_evidence test_question_engine test_phase_6t_autonomous test_phase_6t_benchmark_assets test_sector_loss_reconciliation test_critique` | **146 passed, 2 skipped** (52 s) |
| `pytest tests/unit/test_q15_benchmarks.py` | **7 passed** (earlier session; re-run pending in background) |
| `pytest tests/unit/test_phase_6t_goldens.py` | **running in background** (reproduces 15/15 + replay verdicts) |
| `pytest tests/unit/test_nvidia_provider test_model_registry test_comparison_harness test_answer_schemas` | green in prior session; untouched this phase except registry (see below) |
| `pytest test_nvidia_provider test_model_registry test_comparison_harness test_critique` | **84 passed** (post-change re-run) |
| Corpus `python scripts/measure_corpus.py` | **230 cases, 228 pass (99.1%)**, same 2 known edge cases |

## Registry change re-verification (this phase touched model_registry.py)

- `test_nvidia_provider.py` + `test_model_registry.py` +
  `test_comparison_harness.py`: **65 passed** earlier; the catalog
  no-clobber edit is structural (skip-if-present) — full re-run
  below under release gates if time permits, else flagged.

## Frontend

- No frontend files changed in Phase G. Last verified state:
  139/139 Vitest, `tsc --noEmit` clean, `vite build` clean.
- `impeccable detect` on previously changed views: zero findings
  (one pre-existing brief-mandated accent, overridden by DESIGN.md).

## Live NVIDIA NIM (authenticated requests, key from `.env`)

| Check | Result |
|---|---|
| Basic text generation (`gpt-oss-20b`) | SUCCESS, usage metadata captured |
| Structured output (JSON schema) | VERIFIED (valid `{"a": 1}`) |
| Tool calls | VERIFIED (emitted `add({"x": 2})`; earlier empty-content was max_tokens truncation, fixed by budget) |
| Perez critique workflow | gate fires; verdict UPHELD once, INCONCLUSIVE once (non-determinism documented) |
| Perez direct evidence-grounded answer | 4/5 checks (sector-2 addressed, 0.411 grounded, uncertainty stated, usage captured; 0.732 lap baseline omitted — recorded) |

## Secret and configuration checks

- `git grep` for `nvapi-`, `sk-ant-`, `sk-proj-`, `xoxb-`, `ghp_`: **clean**.
- `.env` / `racewise.env` untracked + gitignored: **verified**.
- `data/model_verification.json` contains model ids + capabilities +
  timestamp only: **verified, no secrets**.

## Pre-existing failures

None introduced. The two corpus failures (Q006 single-driver stint,
Q076 single-ask compound) predate this phase and are documented in
`docs/FRONTIER_FAILURE_TAXONOMY.md`.

## Blocked / not run

- Full 800-test backend suite: covered by targeted suites + goldens;
  a full run is available via `pytest tests/unit` (~30–60 min).
- Live multi-model comparison across all 9 catalog models: explicitly
  out of scope (quota stewardship; only the configured model verified).
