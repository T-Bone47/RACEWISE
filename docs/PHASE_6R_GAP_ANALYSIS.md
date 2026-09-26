# PHASE 6R — GAP ANALYSIS

Date: 2026-09-27 · Baseline `48f0d5d` · Benchmark corpus: 54 cases (`tests/benchmarks/engineering_questions.json`)

## Triage groups

### A. Already supported (verified, no action)

- Complete investigation chain (question → hypotheses → evidence → falsification → counterfactual → synthesis → provenance → graph → memory → replay → compare) executes end-to-end on real canonical data (44/54 cases STRUCTURAL_PASS; all 8 evidence-rich matrix rows executed with 12 items collected and the full lifecycle COMPLETED).
- Determinism: same-process (3×) and cross-process (PYTHONHASHSEED=3 vs 29) outputs byte-identical on all replay cases; replay verdict IDENTICAL on 11 of 11 replay executions.
- Provenance: every VALID investigation carries provider/source_tables/method/analytical_chain/investigation_version; every synthesis number resolves to a ledger evidence id; decision-trace refs all resolvable.
- Graph: closed vocabularies hold, zero dangling edges, graph snapshots verify and replay IDENTICAL.
- Honest limitation reporting: unknown driver → UNAVAILABLE with reason; non-fused lap → INSUFFICIENT_EVIDENCE with zero fabricated evidence; counterfactual candidates on data-poor scopes report TELEMETRY_UNAVAILABLE with missing_data; 1950/2000 eras degrade honestly.
- Contradiction preservation: 6 direct contradictions preserved UNRESOLVED in the LAP6 golden; support+contradiction never collapses to SUPPORTED.
- Storage: derived-on-read confirmed — zero row growth across 54 investigations, replays, graph builds, memory derivations.
- Security: no eval/exec/shell/unsafe-HTML; all dynamic SQL parameterized or identifier-allowlisted; no frontend API-key exposure; MCP boundaries untouched.
- Official vs analytical race gap remain separate quantities with explicit semantics text.

### B. Broken existing capability → FIXED in 6R

| Defect | Evidence | Fix |
| --- | --- | --- |
| `GET /api/catalog/performance-pattern-evidence` returned **500** whenever `driver_a`/`driver_b` were omitted | Browser E2E: Pattern Evidence view error state; curl confirmed 500 without drivers, 200 with. Root cause: default-pair branch referenced `get_catalog_api()` without a local import (NameError) — the same defect class previously fixed on the search and patterns endpoints. | One-line local import added in `src/racewise/api/app.py`. Post-fix: 200 with honest `UNAVAILABLE` + reason when the pattern is outside the default corpus. |

### C. Integration defect → FIXED in 6R

| Defect | Evidence | Fix |
| --- | --- | --- |
| Cross-Race Patterns → Pattern Evidence workflow was dead: the patterns view displayed only an 8-character id prefix (`slice(0,8)`) with no link, and Pattern Evidence accepted only a full id with **no scope binding**, so the server's default pair (newest telemetry season) could never contain the requested pattern — the workflow could never succeed from the UI. | Browser E2E: no link present; evidence request with default pair returned `UNAVAILABLE` for a pattern that exists for VER/PER. | `PatternEvidenceView` now accepts deep-link scope (`#/patternevidence?pattern_id=…&driver_a=…&driver_b=…&seasons=…`) and binds driver pair + seasons into the request; `PerformancePatternView` renders a full-fidelity "Investigate evidence →" link carrying the pattern id, the resolved corpus pair, and the season scope. tsc clean; build clean; E2E verified 200 with a real evidence matrix. |

### D. Data limitations (honest, documented — no action)

- Fused lap evidence exists only on 6D probe laps; other laps correctly yield INSUFFICIENT_EVIDENCE (EQ-A03/A04).
- 1950/2000 eras cannot support telemetry-derived capabilities (stints, regimes, counterfactuals); the system reports rather than fabricates (EQ-B04, C04, C05, D04, D05, G02).
- 1950 cross-race pattern discovery returns UNAVAILABLE "no telemetry-capable race sessions" (EQ-E04) — honest.
- Pattern ids are corpus-scope-dependent (documented in the endpoint contract); a pattern found in one seasons/max_races scope may not exist in another. The system reports `UNAVAILABLE` with `available_pattern_count` rather than approximating.
- Canonical data was re-ingested since the pre-6R memory notes: race-gap 2024 R14 NOR/VER now measures official −0.624 s / analytical +2.49 s over 35 comparable laps (previously 0.895 / −23.558 / 42), and regimes 2022 R4 now measures 8 regimes / 54 comparable laps / 49-row timeline (previously 42 laps / 220 rows). Determinism proofs bind to the current data state; 6R goldens record today's measured values.

### E. Genuine missing capability (documented, NOT built — see NEXT_CAPABILITY_GAPS.md)

- Investigation-id-addressed graph endpoint (catalog graph is scope-based only).
- Non-RACE session support in the 6N engine (QUALIFYING/FP are catalog-visible but not investigable).
- Broader fused-lap coverage (only probe laps carry fused evidence today).
- Semantic/related memory retrieval (intentionally absent; exact-scope only by design).

### F. Performance limitations (measured, not optimized)

- Cross-race patterns is the slowest operation: 14–16 s at 4-season scope; pattern-evidence up to ~16 s when re-discovering patterns at default scope. Assessed EXPECTED_ANALYTICAL_COST: bounded corpus enumeration × per-race regime segmentation × pairwise structural matching; no regression signature (single-season 2022+2023 scans are proportionally faster).
- Investigation benchmark latency p50 1.14 s / p95 17.7 s / max 59.1 s (max = EQ-E01 re-discovery + investigation); API probe p50 0.58 s / p95 6.3 s / max 16.0 s.

### G. UX limitations (observed, not blocking)

- Deep-linked Pattern Evidence prefills but does not auto-run the request (user presses Investigate evidence) — intentional single-submit semantics; documented here, no change made.
- The evidence-ledger region-label wording `derived region loss (None)` surfaces an upstream region-name None in claim text; cosmetic, values and provenance are correct.

## Failure taxonomy (final state)

No unexpected benchmark failures remain (54/54 pass; 7 executed as honest EXECUTED_LIMITATION outcomes, 47 STRUCTURAL_PASS). During development, 18 initial failures were triaged: 16 were corpus/runner vocabulary mismatches (fixed in the benchmark, not the system), 1 was the pattern-evidence 500 (fixed, group B), 1 was the dead cross-view workflow (fixed, group C).

| Category | Count | Disposition |
| --- | --- | --- |
| API_GAP | 1 (pattern-evidence 500) | FIXED |
| FRONTEND_GAP | 1 (cross-view wiring) | FIXED |
| DATA_GAP | 19 limitation cases | honest outcomes preserved |
| DETERMINISM_GAP / PROVENANCE_GAP / ORCHESTRATION_GAP / SECURITY_GAP / MODEL_GAP / TOOL_GAP | 0 | — |
