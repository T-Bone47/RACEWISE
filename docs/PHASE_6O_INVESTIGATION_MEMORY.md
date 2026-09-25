# PHASE 6O — INVESTIGATION REPLAY, COMPARISON & ENGINEERING MEMORY

Methodology reference for `replay_engineering_investigation`,
`verify_engineering_snapshot`, `compare_engineering_investigations`,
`retrieve_engineering_memory` (MCP) and the `/api/catalog/
engineering-investigation/{replay,compare}` + `/api/catalog/
engineering-memory` endpoints. Companion report:
`PHASE_6O_COMPLETION_REPORT.md`.

## 1. Mission

Phase 6N answers *what does the evidence say for this investigation?*
Phase 6O answers:

> Can we reproduce that investigation, compare it with another
> investigation, identify exactly what changed, and preserve the
> engineering knowledge without turning it into unsupported conclusions?

Principle: REPRODUCE → COMPARE → EXPLAIN DELTAS → TRACE → LEARN — never
RANK → SCORE → PREDICT → OPTIMIZE.

## 2. Snapshot architecture

Module: `src/racewise/data/historical/investigation_memory.py`
(`6o_memory_v1`, snapshot `6o_snapshot_v1`). 6N's built-in
`investigation_snapshot` block (input, evidence IDs, source hashes,
hypothesis states, counterfactual IDs) is **reused verbatim**;
`build_investigation_snapshot()` wraps the complete 6N output with
integrity fields: `snapshot_version`, `snapshot_hash` (sha256[:16] over the
canonical body) and `source_hashes` (per-evidence). Identity depends only
on normalized input and canonical output — no timestamp, PID, machine ID,
duration or random UUID. `export_snapshot_canonical_json()` provides the
deterministic canonical-JSON export. Snapshots are DATA: no field is ever
executed.

## 3–4. Replay engine & verification

`verify_investigation_snapshot()` recomputes the hash and reports
`VALID / HASH_MISMATCH / INVALID_SCHEMA / MISSING_PROVENANCE /
INCOMPLETE_SNAPSHOT` — never silently repairs.

`replay_engineering_investigation()` verifies the snapshot, reruns the
exact 6N engine from the snapshot's structured input, rebuilds the
snapshot and compares. Statuses: `IDENTICAL`, `DIFFERENT_DATA`,
`DIFFERENT_TOOL_VERSION`, `DIFFERENT_SCHEMA`, `DIFFERENT_RESULT`,
`INVALID_SNAPSHOT` (an invalid snapshot is never blindly rerun).

## 5. Replay difference engine

Non-identical replays return structured differences — `path`, `old_value`,
`new_value`, `category` (INPUT/DATA/TOOL/PROVENANCE/EVIDENCE/HYPOTHESIS/
FALSIFICATION/COUNTERFACTUAL/SYNTHESIS/SCHEMA_CHANGE) plus
`changed_sources` / `changed_tools` / `changed_schema_keys` — never "results
differ".

## 6. Comparison

`compare_engineering_investigations()` first classifies scope
compatibility: `COMPARABLE` (same question type + scope),
`PARTIALLY_COMPARABLE` (same type, differing scope keys listed),
`NOT_COMPARABLE` (different question types or a non-VALID side).
Eleven dimensions are compared independently (QUESTION, SCOPE, HYPOTHESES,
EVIDENCE_COVERAGE, HYPOTHESIS_STATES, FALSIFICATION, COUNTERFACTUALS,
RESIDUALS, SYNTHESIS, LIMITATIONS, PROVENANCE). No overall score exists.

## 7–8. Evidence & hypothesis deltas

Evidence deltas: `ADDED / REMOVED / VALUE_CHANGED / STATE_CHANGED /
COVERAGE_CHANGED / SOURCE_CHANGED` with measured `delta` where numeric.
Boundary notes travel with the data: *added evidence is not better
evidence; removed evidence is evidence loss, never resolution*.
Hypothesis deltas cover all six canonical hypotheses descriptively
(state, counts, falsification, unresolved contradictions) — "H1 changed
from PARTIALLY_SUPPORTED to MIXED_EVIDENCE", never "H1 got worse".

## 9. Falsification deltas

`NEW_CONTRADICTION`, `PERSISTING_CONTRADICTION`, `RESOLVED_CONTRADICTION`
(only when the conflict's evidence still exists on side B),
`EVIDENCE_UNAVAILABLE` (the contradiction vanished *because its evidence
vanished* — preserved as evidence loss), `NEW_SUPPORT`, `SUPPORT_REMOVED`,
`TESTABILITY_CHANGE`.

## 10–12. Counterfactual, synthesis & trace deltas

Counterfactual deltas (`ADDED / REMOVED / RESULT_CHANGED / UNCHANGED`) keep
MODELLED outputs separate from historical evidence; a larger negative model
delta is never "better". Synthesis transitions are descriptive names
(`SAME`, `MORE_SUPPORTED`, `LESS_SUPPORTED`, `MIXED_TO_INSUFFICIENT`, …)
with no score. Decision-trace comparison reports `TRACE_ADDED / REMOVED /
BASIS_CHANGED / STATUS_CHANGED / UNCHANGED` with old/new basis — showing
exactly which evidence produced a conclusion change.

## 13–15. Engineering memory, invalidation, lineage

`derive_memory_items()` derives scope-limited memory from a completed 6N
investigation (≤ 20 items). Only statements with traceable evidence IDs,
explicit scope, provenance (`source_hashes`) and limitations are derived —
and a hypothesis-state item requires at least one supporting/contradicting
evidence item, so absence never becomes knowledge. Statements are
scope-bound ("In the 2023 R1 … investigation, …"), never general.
MODELLED counterfactual memory stays a separate `COUNTERFACTUAL` evidence
type. Memory is **derived-on-read**: nothing is persisted, zero storage
growth (persistence was deliberately not added; §28/§29 of the phase
contract preferred the existing architecture).

`invalidate_memory_item()` moves ACTIVE → INVALIDATED with a closed reason
vocabulary (`NEW_EVIDENCE`, `SOURCE_INVALIDATED`, `REPLAY_MISMATCH`,
`SCOPE_ERROR`, `MODEL_VERSION_CHANGE`, `HUMAN_REVIEW`, `DATA_CORRECTION`)
and preserves history (`prior_status` + provenance). Retrieval
(`retrieve_engineering_memory()`) is exact scope/provenance matching only —
season, round, driver, driver_pair, hypothesis, pattern, scope type — never
semantic similarity; invalidated items are excluded unless explicitly
requested. Lineage records `COMPARED_WITH` relationships with provenance
on every comparison; the full relationship vocabulary is `REPLAY_OF`,
`COMPARED_WITH`, `DERIVED_MEMORY_FROM`, `INVALIDATED_BY`, `SUPERSEDES`,
`RELATED_TO` — never causal.

**No unsupported generalization**: prior memory never transfers a
conclusion to a new investigation; the retrieval policy states this in
data.

## 16–17. MCP & API

Four new MCP tools (27 historical total): `replay_engineering_investigation`
(structured 6N input), `verify_engineering_snapshot` (snapshot object as
data), `compare_engineering_investigations` (two structured inputs), and
`retrieve_engineering_memory` (≤ 4 investigation inputs + exact-scope
selectors). All closed enums, bounded (memory inputs ≤ 4, hypotheses ≤ 6),
unknown-parameter rejection at the tool contract. API:
`GET /api/catalog/engineering-investigation/replay`,
`GET /api/catalog/engineering-investigation/compare` (a_/b_ prefixed
sides), `GET /api/catalog/engineering-memory`.

## 18–21. Determinism, security, storage, performance

In-process repeats of snapshot/compare/memory byte-identical; replay
IDENTICAL in-process, via API repeat and MCP wire repeat (`duration_ms`
excluded); subprocess replay identical under `PYTHONHASHSEED=3` and `=29`.
No eval/exec/shell/SQL/dynamic invocation in 6O code; imported snapshot
content is data only. Storage: zero growth (no persistence). Q17
performance: golden snapshot+verify+replay ≈ 0.1–3.3 s each; comparisons
and memory retrieval are sub-second except where 6N itself re-runs 6L/6M
scans (documented, not hidden).

## 22. Q17

`q17_benchmarks.py`: 4 golden snapshots (2023 R1 LAP6, 2023 R1 STINT1,
2024 R14 RACE_GAP, 2022 R4 REGIME — all verify VALID + replay IDENTICAL)
plus cases Q17.1–Q17.12 and the negative-control block (corrupt/tampered →
HASH_MISMATCH, missing provenance, invalid schema, incomplete, invalid
replay, NOT_COMPARABLE, memory scope mismatch, closed memory states).

## 23. Limitations

- Memory is derived-on-read from caller-supplied investigation inputs; a
  future phase may add immutable snapshot storage (with migrations, FK,
  immutability tests) if a workspace requires it.
- Cross-race (6L/6M-scoped) investigations inherit the ~30–60 s corpus
  scan cost of 6N; 6O adds only sub-second delta computation on top.
- Vector-assisted discovery is explicitly out of scope; exact matching is
  authoritative.

## 24. Epistemic boundaries

Inherited from 6N verbatim, plus 6O-specific: MORE_EVIDENCE ≠ BETTER,
EVIDENCE_LOSS ≠ RESOLUTION, REPLAYED ≠ REinterpreted, MEMORY ≠ GENERAL
RULE, RELATED ≠ TRANSFERABLE, MODELLED ≠ HISTORICAL in every delta.
