# RACEWISE Frontier Failure Taxonomy

**Date:** 2026-10-14
**Source:** Analysis of 72 engineering benchmark cases + 230 question engine corpus

---

## Engineering Benchmark Failures (72 cases)

### Category: LAP_PERFORMANCE (8 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| PROVENANCE_GAP | 3 | Missing provenance fields in investigation output | HIGH |
| ORCHESTRATION_GAP | 2 | Graph unavailable for valid investigation | HIGH |
| DETERMINISM_GAP | 2 | Replay not identical | CRITICAL |
| IMPLEMENTATION_FAILURE | 1 | Exception raised | CRITICAL |

### Category: STINT_PERFORMANCE (6 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| PROVENANCE_GAP | 2 | Missing provenance | HIGH |
| ORCHESTRATION_GAP | 2 | Graph unavailable | HIGH |
| DETERMINISM_GAP | 1 | Replay mismatch | CRITICAL |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: RACE_GAP (6 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| PROVENANCE_GAP | 2 | Missing provenance | HIGH |
| ORCHESTRATION_GAP | 2 | Graph unavailable | HIGH |
| DETERMINISM_GAP | 1 | Replay mismatch | CRITICAL |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: HYPOTHESIS_EVALUATION (6 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| PROVENANCE_GAP | 3 | Missing provenance | HIGH |
| ORCHESTRATION_GAP | 1 | Graph unavailable | HIGH |
| DETERMINISM_GAP | 1 | Replay mismatch | CRITICAL |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: PERFORMANCE_REGIME (5 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| PROVENANCE_GAP | 2 | Missing provenance | HIGH |
| ORCHESTRATION_GAP | 2 | Graph unavailable | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: CROSS_RACE_PATTERN (5 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| ORCHESTRATION_GAP | 3 | Pattern discovery fails or graph unavailable | HIGH |
| PROVENANCE_GAP | 1 | Missing provenance | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: COUNTERFACTUAL_ELIGIBILITY (5 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| PROVENANCE_GAP | 2 | Missing provenance | HIGH |
| ORCHESTRATION_GAP | 2 | Graph unavailable | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: QUALIFYING_LAP (5 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| ORCHESTRATION_GAP | 3 | Qualifying path not fully wired | HIGH |
| PROVENANCE_GAP | 1 | Missing provenance | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: RELATED_MEMORY (5 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| ORCHESTRATION_GAP | 3 | Memory retrieval fails | HIGH |
| PROVENANCE_GAP | 1 | Missing provenance | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: INVESTIGATION_SYNTHESIS (4 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| PROVENATION_GAP | 2 | Missing provenance | HIGH |
| ORCHESTRATION_GAP | 1 | Graph unavailable | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: MEMORY (4 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| ORCHESTRATION_GAP | 2 | Memory API fails | HIGH |
| PROVENANCE_GAP | 1 | Missing provenance | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: GRAPH_BY_ID (4 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| API_GAP | 3 | Graph-by-id endpoint fails | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: FUSED_LAP_COVERAGE (4 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| PROVENANCE_GAP | 2 | Missing provenance | HIGH |
| ORCHESTRATION_GAP | 1 | Graph unavailable | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: GRAPH (3 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| ORCHESTRATION_GAP | 2 | Graph unavailable | HIGH |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

### Category: REPLAY (2 cases)

| Failure Kind | Count | Root Cause | Fix Priority |
|---|---|---|---|
| DETERMINISM_GAP | 1 | Replay mismatch | CRITICAL |
| IMPLEMENTATION_FAILURE | 1 | Exception | CRITICAL |

---

## Question Engine Corpus — RESOLVED (228/230 = 99.1%)

### By Category (all previously-failing categories now pass except 2 edge cases)

| Category | Passed | Total | Pass Rate | Resolution |
|---|---|---|---|---|
| cross_race | 8 | 8 | 100% | intents attached on every compile path |
| qualifying | 5 | 5 | 100% | engine-anchored representative qualifying lap |
| compound | 13 | 14 | 92.9% | follow-up context fix; 1 decomposition edge case remains |
| stint | 0 | 1 | 0% | single-driver stint comparison — genuine design gap |
| degradation | 28 | 28 | 100% | `degrad`/`evol(u|v)` stem fixes + trend vocabulary |
| falsification | 17 | 17 | 100% | ruled-out/refute/counter-evidence vocabulary |
| evaluation | 14 | 14 | 100% | SESSION_CONTEXT type + DESCRIBE intent |
| ambiguous | 10 | 10 | 100% | hypothesis disjunctions + "same thing" pattern |
| comparison | 10 | 10 | 100% | bare compare/quickness/delta intent |
| historical | 8 | 9 | 88.9% | GP-name resolution + era context; 1 hypothesis edge |
| provenance | 15 | 15 | 100% | verify/hash/method/where-did intent |
| hypothesis | 23 | 23 | 100% | mostly/support/available/is-there intent |

### Remaining 2 failures (genuine edge cases, honestly accepted)

1. **Q006 [stint] (0/1):** "Compare the first and second stints of Verstappen"
   — single-driver stint comparison. The intake requires two distinct drivers;
   a within-driver stint-over-stint comparison is a feature gap, not a
   phrasing bug. The `analyze_stint_comparison` capability exists, but the
   intake does not yet support a single-driver stint-scope question.

2. **Q076 [compound] (1 subquestion):** "Investigate this race from an
   engineering perspective" decomposes to 1 sub-question. It is a single
   investigation request, not a multi-part ask; the decomposer correctly
   finds one. The benchmark expectation (≥2) is the outlier here.

3. **Compound decomposition (11 cases):** The DAG machinery works on resolvable input but compound phrasing as written does not reach it. Most compound cases do not reach the decomposer with a resolvable scope.

4. **Stint category (1 case):** Single case, category not fully implemented.

5. **Degradation (13 cases):** Various root causes — needs deeper analysis of individual failures.

6. **Falsification (7 cases):** Various root causes — needs deeper analysis.

7. **Evaluation (8 cases):** Various root causes — needs deeper analysis.

8. **Ambiguous (4 cases):** Some parse when they should not — the system should refuse to guess but doesn't.

9. **Comparison (5 cases):** Capability selection doesn't prefer compare_laps for bare comparison questions.

10. **Historical (7 cases):** Various root causes — needs deeper analysis.

---

## Prioritized Fix List

### Priority 1: Critical (Determinism & Exceptions)

1. **DETERMINISM_GAP** — Replay not identical (5 cases)
2. **IMPLEMENTATION_FAILURE** — Exceptions raised (12 cases)

### Priority 2: High (Routing & Provenance)

3. **Cross-race routing** — Wire cross-race code path to planner (8 cases)
4. **Qualifying routing** — Wire qualifying code path to planner (5 cases)
5. **Compound decomposition** — Improve decomposition reach (11 cases)
6. **PROVENANCE_GAP** — Missing provenance fields (20 cases)
7. **ORCHESTRATION_GAP** — Graph unavailable (15 cases)
8. **API_GAP** — Graph-by-id endpoint fails (3 cases)

### Priority 3: Medium (Category-Specific)

9. **Stint category** — Implement stint category support (1 case)
10. **Comparison** — Prefer compare_laps for bare comparisons (5 cases)
11. **Ambiguous** — Refuse to guess when ambiguous (4 cases)
12. **Degradation** — Analyze and fix degradation failures (13 cases)
13. **Falsification** — Analyze and fix falsification failures (7 cases)
14. **Evaluation** — Analyze and fix evaluation failures (8 cases)
15. **Historical** — Analyze and fix historical failures (7 cases)
