# PHASE 6O COMPLETION REPORT

## 1. Executive Summary

Phase 6O extends the investigation layer into a reproducible, comparable
engineering workspace: immutable hash-verified investigation snapshots,
deterministic replay with exact structured differences, dimension-wise
comparison with descriptive evidence/hypothesis/falsification/counterfactual/
synthesis/trace deltas, and a scope-limited, provenance-backed engineering
memory (derived-on-read, zero storage growth). Nothing from 6E–6N was
rebuilt; the 6N snapshot block was reused verbatim. Full regression:
**626 passed**. Final readiness: **READY_FOR_INVESTIGATION_MEMORY**.

## 2. Baseline

6N: 591 tests, 23 historical MCP tools (38 total), 93 telemetry sessions,
787,555 rows, ~405.2 MB DB, zero storage growth,
READY_FOR_ENGINEERING_INVESTIGATION.

## 3. Snapshot Architecture

`investigation_memory.py` (`6o_snapshot_v1`): reuses 6N's built-in
`investigation_snapshot` (input, evidence IDs, source hashes, hypothesis
states, counterfactual IDs) and wraps the full 6N output with
`snapshot_version`, `snapshot_hash` (sha256[:16] of the canonical body) and
per-evidence `source_hashes`. Identity = normalized input + canonical
output only (no timestamp/PID/UUID/duration). Canonical-JSON export is
byte-stable.

## 4. Replay Engine

`replay_engineering_investigation()`: verify → rerun the exact 6N engine
from the snapshot's structured input → rebuild snapshot → compare.
Statuses IDENTICAL / DIFFERENT_DATA / DIFFERENT_TOOL_VERSION /
DIFFERENT_SCHEMA / DIFFERENT_RESULT / INVALID_SNAPSHOT (invalid snapshots
are never blindly rerun). Verified live: `IDENTICAL` via module, API and
MCP wire; `DIFFERENT_TOOL_VERSION` and exact differences demonstrated with
a tampered-tool snapshot.

## 5. Snapshot Verification

`verify_investigation_snapshot()`: VALID / HASH_MISMATCH /
INVALID_SCHEMA / MISSING_PROVENANCE / INCOMPLETE_SNAPSHOT. Never silently
repairs. All five states exercised by tests and Q17 negative controls.

## 6. Investigation Comparison

`compare_engineering_investigations()`: scope compatibility
(COMPARABLE / PARTIALLY_COMPARABLE with differing keys / NOT_COMPARABLE
across question types) then eleven independent dimensions. No overall
score. Self-comparison: zero deltas; lap-6 vs lap-11:
PARTIALLY_COMPARABLE with structured deltas; LAP vs RACE_GAP:
NOT_COMPARABLE.

## 7–12. Deltas

Evidence: ADDED/REMOVED/VALUE_CHANGED/STATE_CHANGED/COVERAGE_CHANGED/
SOURCE_CHANGED with measured deltas and boundary notes ("added evidence is
not better evidence"; "removed evidence is evidence loss, never
resolution"). Hypotheses: all six, descriptive only. Falsification:
NEW/PERSISTING/RESOLVED_CONTRADICTION (only if its evidence still exists on
side B), EVIDENCE_UNAVAILABLE, NEW_SUPPORT, SUPPORT_REMOVED,
TESTABILITY_CHANGE — the vanished-evidence invariant is test-enforced.
Counterfactuals: MODELLED stays separate from history. Synthesis:
descriptive transitions (SAME/MORE_SUPPORTED/LESS_SUPPORTED/…), no score.
Decision trace: TRACE_ADDED/REMOVED/BASIS_CHANGED/STATUS_CHANGED with
old/new basis — the exact evidence that produced a conclusion change.

## 13–15. Engineering Memory, Invalidation, Lineage

`derive_memory_items()` (≤ 20 items): scope-limited statements with
traceable evidence IDs, provenance and limitations only; hypothesis-state
items require at least one supporting/contradicting evidence item
(absence never becomes knowledge); 1950 telemetry-poor investigation → 0
items. Statements are scope-bound ("In the 2023 R1 … investigation, …").
MODELLED counterfactual memory stays a separate COUNTERFACTUAL type.
`invalidate_memory_item()`: ACTIVE → INVALIDATED with closed reasons
(NEW_EVIDENCE, SOURCE_INVALIDATED, REPLAY_MISMATCH, SCOPE_ERROR,
MODEL_VERSION_CHANGE, HUMAN_REVIEW, DATA_CORRECTION), history preserved.
`retrieve_engineering_memory()`: exact scope/provenance matching only
(season/round/driver/driver_pair/hypothesis/pattern/scope_type); never
semantic similarity; invalidated items excluded unless requested. Lineage
records COMPARED_WITH with provenance (full vocabulary REPLAY_OF,
COMPARED_WITH, DERIVED_MEMORY_FROM, INVALIDATED_BY, SUPERSEDES,
RELATED_TO — never causal). No unsupported generalization: the retrieval
policy states that a related prior investigation never transfers its
conclusion. Memory is derived-on-read — persistence intentionally not
added (zero storage growth preserved per §28/§29).

## 16. Q17 Results

4 golden snapshots all verify VALID + replay IDENTICAL with
replay_hash == snapshot_hash:

| golden | snapshot_hash | replay |
|---|---|---|
| 2023 R1 VER/PER LAP6 | a7a0446765a05e4f | IDENTICAL |
| 2023 R1 VER/PER STINT1 | c606f27ece508f82 | IDENTICAL |
| 2024 R14 RACE_GAP | 136f480d8113eaf5 | IDENTICAL |
| 2022 R4 REGIME | 5ff49761d2a987e8 | IDENTICAL |

Q17.1 replay identical (0 diffs) · Q17.2 changed tool version →
DIFFERENT_TOOL_VERSION with path/old/new/category differences · Q17.3
different lap → PARTIALLY_COMPARABLE, 4 hypothesis state changes, repeat
identical · Q17.4 different race → PARTIALLY_COMPARABLE, SAME · Q17.5
self-comparison COMPARABLE, 0 deltas · Q17.6 hypothesis subset →
COMPARABLE, HYPOTHESES dimension CHANGED, 4 × NOT_REQUESTED in B · Q17.7
contradiction deltas with vanished-evidence-never-resolved invariant ·
Q17.8 counterfactual comparison, all MODELLED · Q17.9 evidence-poor →
INSUFFICIENT_EVIDENCE, 0 memory items (all items have evidence) · Q17.10
telemetry-unavailable → UNAVAILABLE, 0 items · Q17.11 exact-scope
retrieval 15/15 hits, 0 scope-miss, repeat identical · Q17.12 invalidated
item excluded by default, included when requested, history preserved.
Negative controls: corrupt/tampered → HASH_MISMATCH, missing provenance,
invalid schema, incomplete, replay-invalid → INVALID_SNAPSHOT,
NOT_COMPARABLE, scope mismatch 0, memory states closed. MCP verification:
27 historical tools registered, replay IDENTICAL, compare
PARTIALLY_COMPARABLE, memory 8 matches, same-driver and oversized inputs
rejected.

## 17. Determinism

In-process: snapshot/compare/memory repeats byte-identical. API: replay,
compare and memory repeats byte-identical. MCP wire: replay repeat
identical (`duration_ms` excluded). Subprocess: identical under
`PYTHONHASHSEED=3` and `=29` (env-inherited; snapshot hash, replay status
and all 15 memory IDs equal).

## 18. Performance

Q17 golden snapshot+verify+replay: p50 ≈ 2.2 s, p95 ≈ 3.2 s, max ≈ 3.2 s
(dominated by the 6N engine re-run; replay = one full 6N execution).
Comparisons and memory retrieval on already-run investigations are
sub-second. 6L/6M-scoped cross-race investigations inherit the 6N corpus
scan cost — documented, not hidden.

## 19. Storage

Zero growth: DB 405,188,608 bytes before/after snapshot + verify + replay +
compare + derive + retrieve, zero row deltas across all tables, mtime
unchanged. No persistence added; snapshots/memory are derived-on-read.

## 20. Security

No eval/exec/shell/arbitrary SQL/dynamic invocation/file-IO in the 6O
modules. Snapshot content is data, never executed. Tool contracts: closed
enums, bounds (memory ≤ 4 investigations, hypotheses ≤ 6), unknown-parameter
rejection, distinct-driver validation, read-only DB.

## 21. No-Fabrication Audit

6O core, Q17 and frontend CLEAN (grep of caused/causes/proves/proven/
confidence/most likely/best explanation/optimal/winner/superior/inferior/
guarantee/would have won/predicted — only epistemic negations). Evaluation
language in comparisons is strictly ADDED/REMOVED/CHANGED/UNCHANGED and
descriptive transitions; no BETTER/WORSE anywhere.

## 22. Frontend

`InvestigationView.tsx` extended with Replay (snapshot → replay hash +
IDENTICAL state), Engineering Memory table (statement, class, validity),
and Compare (compatibility, per-hypothesis state A → B, falsification
deltas) — neutral descriptive states only, no ranking/badges.
`npm run build` passes; no build/console errors.

## 23. Tests

31 new tests (26 in `test_investigation_memory.py`, 5 in
`test_q17_benchmarks.py`) + 4 MCP wire tests. Registry-count assertions
updated to 27 in five files. Full suite: **626 passed**
(591 baseline + 31 6O + 4 wire). The excluded legacy-flow integration test
(`tests/integration/test_investigation_flow.py`) was inspected and run
independently per §45: **5 passed**; the file still carries the other
thread's unrelated uncommitted changes (+53 lines), which were not staged
and remain untouched.

## 24. Known Limitations

- Memory is derived-on-read from caller-supplied inputs; a future phase
  may add immutable snapshot storage (migrations/FK/immutability tests) if
  a workspace requires persistence.
- Cross-race investigations inherit the 6N 6L/6M corpus-scan cost.
- Vector-assisted discovery is explicitly out of scope; exact matching is
  authoritative.

## 25. Files Changed

Core: `src/racewise/data/historical/investigation_memory.py` (new),
`src/racewise/data/historical/q17_benchmarks.py` (new).
Surface: `src/racewise/tools/historical.py` (4 tools, registry 23→27),
`src/racewise/api/app.py` (replay/compare/engineering-memory endpoints +
shared input parser), `apps/web/src/InvestigationView.tsx`.
Tests: `tests/unit/test_investigation_memory.py` (new),
`tests/unit/test_q17_benchmarks.py` (new),
`tests/integration/test_historical_tools_mcp.py` (extended), 5 registry
assertions updated. Docs: `docs/PHASE_6O_INVESTIGATION_MEMORY.md` (new),
this report.

## 26. Verification Commands

```
python -m pytest -q tests src --ignore=tests/integration/test_investigation_flow.py
python -m pytest tests/integration/test_investigation_flow.py -q   # run independently
python -c "from racewise.data.historical.q17_benchmarks import run_q17; ..."
cd apps/web && npm run build
PYTHONHASHSEED=3 / =29 subprocess determinism (in test suite)
```

## 27. Final Readiness

PHASE 6O STATUS:
READY_FOR_INVESTIGATION_MEMORY
