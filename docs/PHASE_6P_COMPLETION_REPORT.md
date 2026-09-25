# PHASE 6P COMPLETION REPORT

## 1. Executive Summary

Phase 6P adds the Engineering Knowledge Graph & Investigation Graph: a
deterministic, provenance-backed graph layer that connects the existing 6N
investigation outputs and 6O snapshots/memory into a navigable structure.
Nothing from 6E–6O was rebuilt and no new analytical calculation was
added — the graph CONNECTS EVIDENCE, it does not INVENT KNOWLEDGE.
Derived-on-read, zero storage growth. Final readiness:
**READY_FOR_INVESTIGATION_GRAPH**.

## 2. Baseline

6O: 626 tests, 27 historical MCP tools (42 total), 93 telemetry sessions,
787,555 telemetry rows, 405,188,608-byte canonical DB, zero storage
growth, READY_FOR_INVESTIGATION_MEMORY.

## 3. Implementation Summary

- Core `src/racewise/data/historical/investigation_graph.py`
  (`6p_graph_v1`): graph builder over 6N results (scope nodes from the
  canonical DB, evidence/counterfactual/synthesis/decision-trace/memory/
  snapshot nodes from the 6N output), closed 19-node / 26-edge
  vocabularies, deterministic identity, bounded structured traversal
  (8 kinds, depth ≤ 8, nodes ≤ 500, edges ≤ 1500 — rejected beyond caps),
  three path queries, graph snapshot/verify/replay, merge +
  6O-lineage import.
- Q18 `q18_benchmarks.py`: 4 golden graph snapshots + 8 semantics cases +
  negative controls + MCP verification.
- MCP: 4 new tools (registry 27 → 31 historical, 46 total).
- API: 4 new GET endpoints under `/api/catalog/investigation-graph`.
- Frontend: GRAPH panel in `InvestigationView.tsx` + `gp-*` CSS families.
- Tests: 45 module tests + 5 Q18 tests + 4 MCP wire tests + 5 API tests.

## 4. Node / edge counts (measured)

| scope | nodes | edges | notable families |
|---|---|---|---|
| 2023 R1 VER/PER LAP6 | 58 | 185 | 11 EVIDENCE, 1 COUNTERFACTUAL, 18 DECISION_TRACE, 7 MEMORY, 3 ANALYTICAL_SOURCE |
| 2023 R1 VER/PER STINT1 | 97 | 362 | 29 EVIDENCE, 2 STINT, 37 DECISION_TRACE |
| 2024 R14 RACE_GAP | 35 | 53 | 5 EVIDENCE, 2 MEMORY (no lap/stint scope) |
| 2022 R4 REGIME | 41 | 60 | 6 EVIDENCE, 6 REGIME (HAS_REGIME ×6) |
| cross-race pattern | 34 | 61 | 1 PATTERN with 7 MEASURED_BY |
| 1950 R1 RACE_GAP (telemetry-poor) | 22 | 24 | 0 EVIDENCE / 0 COUNTERFACTUAL / 0 MEMORY (honest) |

Largest measured payload: STINT1 graph ≈ 157 KB JSON (cap 4 MB).

## 5. Q18 results

- Golden graphs (Q18.1–4): verify VALID + replay IDENTICAL
  (replay_hash == snapshot_hash). Recorded hashes: LAP6 graph
  `b19ae7cd499446a2` / snapshot `8477e3b407c0a6b9`; STINT1 graph
  `3e32561c3df209af` / snapshot `36d9b4a7299466b6`; 2024 R14 graph
  `6a8c7d0f85945c60` / snapshot `04c44095ce32cf8c`; 2022 R4 graph
  `6ba7a5056d6f8ad6` / snapshot `fe0a51c171ce5258`.
- Q18.5 cross-race pattern graph: real 6L pattern `aa01533a485012df`
  discovered, PATTERN node present, investigation VALID.
- Q18.6 hypothesis trace: H1_corner_speed → 2 supporting / 1
  contradicting / 3 non-decisive, provenance on every entry, no ranking.
- Q18.7 contradiction path: 6 pairwise CONTRADICTS edges, all carrying
  6N conflict_ids, resolution UNRESOLVED.
- Q18.8 counterfactual path: 1 COUNTERFACTUAL node (MODELLED),
  MODELS edge to its lap, intervention REMOVE_DEFICIT 0.5, delta −1.019427 s.
- Q18.9 memory lineage: 7 memory nodes, 7 GENERATED_MEMORY + 13
  memory→evidence DERIVED_FROM edges, no orphan memory.
- Q18.10 replay/compare lineage: merged graph 84 nodes / 308 edges after
  importing 6O COMPARED_WITH; provenance path between investigations OK.
- Q18.11 evidence-unavailable: 1950 scope → 0 evidence/counterfactual/
  memory nodes (absence never fabricated).
- Q18.12 negative controls: depth/nodes/edges over cap → INVALID; unknown
  node/evidence/hypothesis → NOT_FOUND; unknown investigation →
  UNAVAILABLE; bad kind/direction → INVALID; vocabulary closed
  (19 node / 26 edge types).
- Additional negatives: tampered snapshot → HASH_MISMATCH, invalid schema
  → INVALID_SCHEMA, replay of invalid → INVALID_SNAPSHOT, invalid
  investigation → INVALID with no partial graph, lap-beyond-race →
  UNAVAILABLE with zero fabricated LAP nodes.

## 6. MCP

Registry: **31 historical tools** (46 total): added
`build_investigation_graph`, `trace_investigation_path`,
`trace_evidence_source`, `trace_hypothesis_evidence`. All specs typed,
closed, bounded; unknown parameters rejected (`invalid_input`);
`max_depth: 99` rejected; unknown evidence/hypothesis rejected. Wire
tests over the real server subprocess: tools listed, graph build
deterministic repeat identical (duration_ms excluded), path/traces OK,
negative controls enforced. Registry-count assertions updated 27 → 31 in
5 test files.

## 7. API verification

`GET /api/catalog/investigation-graph` (200; byte-identical repeat),
`.../graph/path`, `.../graph/evidence`, `.../graph/hypothesis`.
Violation classes 422: max_depth=99, max_nodes=9999, max_edges=9999,
unknown question_type, unknown hypothesis, unknown target_node_type,
missing target_key, evidence not in the investigation. Unavailable scope
(season 2050) returns 200 with explicit status UNAVAILABLE.

## 8. Frontend verification

`npm run build` passes (324.39 kB JS, gzip 89.42 kB; no errors). GRAPH
panel: focus-type filter, path-depth control, node table, click-to-inspect
detail with typed relationships and ordered provenance path; distinct
visual families (evidence / hypothesis / MODELLED dashed counterfactual /
lineage / memory / context); no stronger/weaker/better/worse semantics.

## 9. Determinism

- In-process repeat: graph output_hash identical.
- Graph snapshot: verify VALID; replay IDENTICAL (hash equality).
- Subprocess: identical graph hash/counts under PYTHONHASHSEED=3 and =29
  (env-inherited; test-enforced).
- MCP wire repeat: identical (duration_ms excluded).
- API repeat: byte-identical response body.

## 10. Storage

Zero growth: DB size 405,188,608 bytes, mtime and row counts unchanged
across a full build → snapshot → verify → replay → traverse → paths
pipeline. No persistence added; the graph is derived-on-read and the 6P
module contains no SQL at all.

## 11. Performance (measured)

| operation | p50 | p95 | max |
|---|---|---|---|
| graph build (6N result in hand) | 18.4 ms | 21.5 ms | 21.5 ms |
| full investigation + graph (LAP6) | 702.9 ms | 723.4 ms | 723.4 ms |
| traversal NEIGHBORS d4 / d8 | 4.6 / 4.4 ms | 5.4 / 4.7 ms | 5.4 / 4.7 ms |
| investigation path | 0.1 ms | 0.1 ms | 0.1 ms |
| evidence source trace | 0.05 ms | 0.1 ms | 0.1 ms |
| hypothesis trace | 0.1 ms | 0.1 ms | 0.1 ms |
| snapshot build / verify | 1.6 / 1.5 ms | 2.4 / 2.0 ms | 2.4 / 2.0 ms |
| graph replay (incl. 6N re-run) | 629.8 ms | 647.6 ms | 647.6 ms |

Dominated by the exact 6N engine execution; the graph layer itself is
milliseconds. Q18 matrix (documentation run): p50 ≈ 4.7 s, p95 ≈ 6.7 s
per golden (stint/regime goldens run 6G/6F/6K collection).

## 12. Security audit

Grep of 6P core, Q18, historical tools and API app: no eval/exec/shell/
os.system/subprocess/__import__/pickle; no SQL in the 6P module (no
injection surface); no filesystem access; no dynamic tool invocation;
closed node/edge vocabularies with ValueError on unknown types; bounded
traversal (caps rejected, not clamped); MCP/API inputs closed enums +
bounds + unknown-parameter rejection. Test-enforced module-source scan
(`test_no_dynamic_execution_in_module`) passes.

## 13. No-fabrication audit

Grep for caused/causes/proves/proven/confidence/most likely/best
explanation/optimal/winner/superior/inferior/guaranteed/predicted/
strongest over the 6P core, Q18, new tests, API additions and frontend:
only explicit epistemic negations hit ("not a confidence score", "no
confidence, no strongest hypothesis", "not causation", pre-existing 6N
"most likely cause" negation). Comparison/relationship language is
strictly typed-edge vocabulary; SUPPORTS provenance carries
"evidence-consistency, not causation". No BETTER/WORSE anywhere; no
ranking, no scores.

## 14. Tests

- `tests/unit/test_investigation_graph.py`: **45 passed** (vocabulary,
  construction, edge semantics, provenance, memory orphans, falsification
  states, determinism incl. subprocess PYTHONHASHSEED 3/29, traversal,
  paths, lineage, negatives, security scan).
- `tests/unit/test_q18_benchmarks.py`: **5 passed**.
- `tests/integration/test_investigation_graph_api.py`: **5 passed**.
- `tests/integration/test_historical_tools_mcp.py`: +4 wire tests
  (TestMCPInvestigationGraph), full file 25 passed.
- 5 registry-count assertions updated to 31; prior phase tests pass.
- Full regression (excl. other thread's legacy-flow file, per 6N/6O
  precedent): **686 passed** (605 pre-6P baseline in the same run scope
  + 45 + 5 + 5 + 4 + 22 prior-phase delta from updated MCP file
  counting). Legacy-flow test run independently: 5 passed; file
  untouched (other thread's diff preserved).

## 15. Full regression run record

```
nohup python -m pytest -q tests src \
  --ignore=tests/integration/test_investigation_flow.py \
  -p no:cacheprovider > regression.log 2>&1
# result: 686 passed, 3 warnings in 971.45s (0:16:11)
```

Legacy flow (independent): `pytest tests/integration/test_investigation_flow.py`
→ 5 passed in 31.62s (uncommitted external diff not staged, not modified).

## 16. Files changed

New: `src/racewise/data/historical/investigation_graph.py`,
`src/racewise/data/historical/q18_benchmarks.py`,
`tests/unit/test_investigation_graph.py`,
`tests/unit/test_q18_benchmarks.py`,
`tests/integration/test_investigation_graph_api.py`,
`docs/PHASE_6P_ENGINEERING_KNOWLEDGE_GRAPH.md`, this report.
Modified: `src/racewise/tools/historical.py` (+4 tools),
`src/racewise/api/app.py` (+4 endpoints),
`apps/web/src/InvestigationView.tsx`, `apps/web/src/App.css`,
`tests/integration/test_historical_tools_mcp.py`, 5 registry-count test
files. Nothing from the other thread's uncommitted set was touched.

## 17. Known limitations

- Per-investigation graph (+ explicit lineage merges); no persistent
  corpus-wide graph (zero-storage philosophy preserved).
- Graph nodes exist only where canonical entities exist (no placeholders).
- REGIME node identity uses lap-range (6N ledger's regime_index is null).
- MCP graph output for the largest golden scope (~157 KB) is well under
  the 4 MB cap, but corpus-wide graphs would need pagination if ever added.

## 18. Final readiness

PHASE 6P STATUS:
READY_FOR_INVESTIGATION_GRAPH
