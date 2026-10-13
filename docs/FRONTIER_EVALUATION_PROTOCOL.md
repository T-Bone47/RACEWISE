# RACEWISE Frontier Evaluation Protocol

**Date:** 2026-10-14
**Version:** 1.0

---

## 1. Purpose

This protocol defines how RaceWise intelligence improvements are measured, compared, and verified. It ensures that every claimed improvement is backed by reproducible evidence and that no regression is concealed.

## 2. Evaluation Dimensions

Each dimension is measured separately. No composite "AI intelligence score" exists.

| Dimension | Measurement Method | Current Baseline |
|---|---|---|
| Context accuracy | Per-case season, round, driver pair resolution | Measured per case |
| Intent accuracy | Intent family matching | 143/230 (62.2%) |
| Decomposition | Sub-question count and ordering | Mean 1.59 sub-questions |
| Capability selection | Asserted against registry | 16 distinct capabilities |
| Data availability | Record-count derived | Asserted from counts |
| Hypothesis selection | Planned vs unavailable recorded | Measured |
| Evidence coverage | Ledger size + support/contradict per hypothesis | Measured |
| Unsupported-claim rate | Enforced by verification | 0 (enforced) |
| Provenance coverage | Enforced by verification | 0 gaps (enforced) |
| Falsification correctness | Engine verdicts passed through | 23/23 (100%) |
| Deterministic consistency | Hashes stable across processes | Verified |
| Adversarial handling | Reject/clarify/unavailable | 7/7 (100%) |
| Numerical correctness | Deterministic tool outputs | 115/115 tools completed |
| Latency | End-to-end investigation time | ~4.8s median |
| Completion rate | Investigations reaching COMPLETED | 23/23 (100%) |

## 3. Benchmark Corpus

### 3.1 Current Corpus

- **230 questions** across 25+ categories
- Two types: self-contained and continuation (follow-up)
- Intent matching is family-based (not exact token matching)
- No expected numerical values in corpus (deterministic engine owns those)

### 3.2 Holdout Strategy

- 15% of corpus reserved as holdout (approximately 35 questions)
- Grouped by race/session to prevent leakage
- Holdout set is never used for training or tuning
- Near-duplicate questions are grouped together

### 3.3 Failure Categories

Current failing cases (87 total) are categorized as:

| Category | Count | Root Cause |
|---|---|---|
| Cross-race | 8 | Planner selects capabilities but compile doesn't reach PLANNED |
| Qualifying | 5 | Separate code path not wired to planner |
| Compound | 11 | Decomposition DAG not reached by compound phrasing |
| Stint | 1 | Single case, category not fully implemented |
| Degradation | 13 | Various — needs analysis |
| Falsification | 7 | Various — needs analysis |
| Evaluation | 8 | Various — needs analysis |
| Ambiguous | 4 | Some parse when they should not |
| Comparison | 5 | Capability selection doesn't prefer compare_laps |
| Historical | 7 | Various — needs analysis |
| Provenance | 5 | Various — needs analysis |
| Hypothesis | 7 | Various — needs analysis |
| Residual | 3 | Various — needs analysis |

## 4. Scoring Procedure

### 4.1 Deterministic Scoring

For each benchmark case:
1. Run the question through the compiler
2. Compare detected intents against expected intent families
3. Verify capability selection against registry
4. Check data availability correctness
5. Verify decomposition produces required sub-questions
6. Check for unsupported claims (must be zero)
7. Verify provenance completeness

### 4.2 Model-Dependent Scoring (when model is available)

For each benchmark case:
1. Run full investigation with model
2. Score tool-call correctness
3. Score claim faithfulness against evidence
4. Score confidence calibration
5. Score abstention behavior
6. Score hallucination rate

### 4.3 Regression Detection

Before any change:
1. Run full benchmark, record results as "before"
2. Make one change at a time
3. Run full benchmark, record results as "after"
4. Compare per-category results
5. Investigate any regression — do not weaken assertions

## 5. Evaluation Report Format

Each evaluation run produces:

```
Evaluation Report
Date: YYYY-MM-DD
Commit: <hash>
Corpus: N questions (M holdout)
Model: <provider/model or "deterministic"

Overall: X/Y (Z%)
Per-category:
  category1: a/b (c%)
  category2: d/e (f%)

Regressions: <list or "none">
Improvements: <list>
Failure analysis: <top 3 categories with counts>
```

## 6. Evaluation Commands

```bash
# Full benchmark
python tests/benchmark/run_benchmark.py

# Question engine benchmark
python -m pytest tests/benchmark/ -q

# Backend tests
python -m pytest tests/ -q

# Frontend tests
cd apps/web && npx vitest run

# Specific test suites
python -m pytest tests/unit/test_question_engine.py -q
python -m pytest tests/unit/test_decision_twin.py -q
```

## 7. Leakage Prevention

- Training and validation sets are separated by race/session
- Near-duplicate questions are grouped
- Holdout set is never used for tuning
- Derived versions of the same answer are grouped
- The corpus declares no expected numerical values (deterministic engine owns those)

## 8. Versioning

- Benchmark corpus version: 1.0 (230 questions)
- Evaluation protocol version: 1.0
- Each evaluation run records: commit hash, corpus version, protocol version, model configuration
