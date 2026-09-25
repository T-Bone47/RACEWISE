# PHASE 6P — ENGINEERING KNOWLEDGE GRAPH & INVESTIGATION GRAPH

## 1. Mission

Phase 6P connects the existing investigation ecosystem (6E → 6O) into a
deterministic, provenance-backed graph so an engineer can navigate

    QUESTION → HYPOTHESIS → EVIDENCE → ANALYSIS
      → RACE / LAP / STINT / REGIME / PATTERN
      → COUNTERFACTUAL → INVESTIGATION → MEMORY

The graph answers "why does this conclusion exist?", "what contradicts
this?" and "where did this knowledge come from?" — as navigation, not as
new analysis. Core principle: **CONNECT EVIDENCE**, never INVENT
KNOWLEDGE. The graph consumes existing 6N/6O outputs and canonical data
and performs no new F1 analytical calculation.

## 2. Architecture

`src/racewise/data/historical/investigation_graph.py` (`6p_graph_v1`).
Derived-on-read: no graph database, no Neo4j, no new persistence layer,
zero storage growth. Inputs are (a) the canonical DB via `CanonicalQueries`
and (b) caller-supplied 6N investigation results (and 6O lineage blocks).
The module exposes:

- `build_investigation_graph(queries, investigation)` — full graph for one
  6N result (nodes, edges, provenance, `graph_id`, `output_hash`).
- `build_graph_snapshot` / `verify_graph_snapshot` / `replay_graph_snapshot`
  — deterministic snapshot, hash verification and replay.
- `traverse_graph` — bounded BFS with structured traversal kinds.
- `explain_investigation_path` — ordered provenance path from an
  investigation to a target node.
- `trace_evidence_to_source` — evidence → analytical source → scope.
- `trace_hypothesis_evidence` — supporting/contradicting/non-decisive
  evidence + related counterfactuals per hypothesis.
- `merge_investigation_graphs` + `add_lineage_edges` — connect
  investigations with 6O-imported lineage (COMPARED_WITH, REPLAY_OF, ...).

## 3. Node model

Closed vocabulary of 19 node types: INVESTIGATION, QUESTION, DRIVER,
DRIVER_PAIR, SEASON, RACE, SESSION, LAP, STINT, REGIME, PATTERN,
HYPOTHESIS, EVIDENCE, COUNTERFACTUAL, SYNTHESIS, DECISION_TRACE, MEMORY,
ANALYTICAL_SOURCE, SNAPSHOT. Every node carries `node_id`, `node_type`,
`label`, `canonical_reference`, `metadata`, `provenance`. Metadata is
descriptive only (claim, state, measured value, limitations) — never an
unsupported conclusion. COUNTERFACTUAL nodes carry the full model block:
model, intervention, parameter, baseline, measured_delta_s,
validation_state, telemetry_scope — always marked MODELLED.

Node identity is deterministic and content-addressed:

    investigation:<6n_investigation_id>      question:<hash>
    driver:<driver_key>                      driver_pair:<a>:<b> (sorted)
    season:<y>   race:<y>:<r>   session:<y>:<r>:RACE
    lap:<y>:<r>:<driver>:<n>    stint:<y>:<r>:<driver>:<n>
    regime:<y>:<r>:<start>-<end>             pattern:<pattern_id>
    hypothesis:H1_corner_speed               evidence:<evidence_id>
    memory:<memory_id>                       analytical_source:<phase>:<tool>
    snapshot:<snapshot_hash>

No random UUIDs; scope nodes (race/session/stint) are created only when
the canonical store actually contains the referenced entity — never a
placeholder.

## 4. Edge model

Closed vocabulary of 26 edge types: INVESTIGATES, TARGETS, COMPARES_WITH,
CONTAINS, HAS_LAP, HAS_STINT, HAS_REGIME, PARTICIPATES_IN, TESTS, SUPPORTS,
CONTRADICTS, DERIVED_FROM, MEASURED_BY, MODELS, SENSITIVITY_OF,
HAS_EVIDENCE, HAS_COUNTERFACTUAL, HAS_SYNTHESIS, HAS_DECISION_TRACE,
GENERATED_MEMORY, REPLAY_OF, COMPARED_WITH, RELATED_TO, SUPERSEDES,
INVALIDATED_BY, HAS_SOURCE. Every edge carries `edge_id` (hash of
endpoints + type + source reference), `provenance` naming the exact 6N/6O
block it was imported from (e.g. `6n evidence_ledger`,
`6n hypothesis_evaluations`, `6n evidence_conflicts`,
`6o derive_memory_items`), and `source_reference`. There is no generic
CONNECTED_TO. Edges are only created where an existing analytical result
states the relationship; edges are never inferred from topology.

## 5. Evidence graph

The canonical path is navigable end-to-end and verified by tests:

    INVESTIGATION → SYNTHESIS → DECISION_TRACE → EVIDENCE
      → ANALYTICAL_SOURCE (phase + tool) → RACE → LAP / STINT

Example (2023 R1 VER/PER lap 6): `INVESTIGATION` →(HAS_SYNTHESIS)→
`SYNTHESIS` →(HAS_DECISION_TRACE)→ `TRACE-001` →(HAS_EVIDENCE)→
`evidence_001` →(DERIVED_FROM)→ `analytical_source:6E:attribute_lap_loss`,
and →(MEASURED_BY)→ `lap:2023:1:max-verstappen:6` →(HAS_LAP)← `session`.
`trace_evidence_to_source` returns source tool, phase, source hash and the
scope the evidence is measured on, plus an explicit `missing_provenance`
list when a field is absent — never a fabricated path.

## 6. Contradiction graph

Contradictions are imported from the 6N `evidence_conflicts` block as
explicit evidence→evidence CONTRADICTS edges carrying `conflict_id`,
`conflict_type` (DIRECT_CONTRADICTION) and `resolution_status`
(UNRESOLVED). Hypothesis-facing CONTRADICTS edges are imported from the 6N
`hypothesis_evaluations`. No contradiction is ever inferred from graph
connectivity (test-enforced: every pairwise CONTRADICTS edge must carry a
6N conflict_id).

## 7. Falsification graph

Per hypothesis, the 6N aggregate state is imported verbatim on the
INVESTIGATION→(TESTS)→HYPOTHESIS edge: SUPPORTED, PARTIALLY_SUPPORTED,
NOT_SUPPORTED, CONTRADICTED, MIXED_EVIDENCE, NOT_TESTABLE,
INSUFFICIENT_EVIDENCE, NOT_REQUESTED — never collapsed, never ranked.
Evidence-level SUPPORTS / CONTRADICTS / non-decisive (TESTS) families stay
separate; `trace_hypothesis_evidence` reports the three families disjointly.

## 8. Counterfactual graph

Executed 6I counterfactuals become COUNTERFACTUAL nodes (a distinct node
type from EVIDENCE — historical and modelled are never merged) with the
full MODELLED payload and a MODELS edge anchoring the modelled result to
its lap/stint node. The frontend renders these nodes with a distinct
dashed MODELLED badge.

## 9. Memory graph

MEMORY nodes come from 6O `derive_memory_items`. Every memory node has a
GENERATED_MEMORY edge from its source investigation (never orphaned,
test-enforced) and at least one DERIVED_FROM edge to a ledger evidence
item, plus RELATED_TO edges to its hypothesis ids. Memory stays scope-
bound; a related prior investigation never transfers its conclusion.

## 10. Investigation lineage

6O lineage vocabulary (REPLAY_OF, COMPARED_WITH, DERIVED_MEMORY_FROM,
INVALIDATED_BY, SUPERSEDES, RELATED_TO) is imported via
`add_lineage_edges`, which accepts only that closed vocabulary and
requires both endpoint investigations to exist in the graph. Each
investigation graph also contains its own SNAPSHOT node (6O identity)
with a REPLAY_OF edge. Q18.10 demonstrates two lap investigations merged
and connected by the exact COMPARED_WITH provenance from
`compare_engineering_investigations`, after which a provenance path
between the two investigations exists.

## 11. Traversal

`traverse_graph` offers eight structured kinds only (NEIGHBORS, EVIDENCE,
HYPOTHESES, INVESTIGATIONS, PROVENANCE, COUNTERFACTUALS, MEMORY, SOURCES)
and three directions (OUT/IN/BOTH). No arbitrary query language, no Cypher,
no graph endpoints beyond the bounded surface. Bounds are hard caps —
max_depth ≤ 8, max_nodes ≤ 500, max_edges ≤ 1500 — and values beyond the
caps are REJECTED (INVALID), never silently clamped.

## 12. Provenance

Every edge names its source block; every evidence node carries
source_phase, source_tool and the 16-hex source_hash from the 6N ledger.
`explain_investigation_path` returns each hop with its edge type and
provenance; the note "a path is provenance navigation, not a causal chain"
is part of the response contract.

## 13. Determinism

Nodes sorted by node_id; edges sorted by (source_node, edge_type,
target_node, edge_id); metadata canonicalized; hashed with the shared
sha256 canonical-JSON `_hash_obj` (16 hex). No timestamps, durations,
random IDs or PIDs participate in any hash. Verified: in-process repeat,
subprocess under PYTHONHASHSEED=3 and =29 (test-enforced), graph snapshot
replay IDENTICAL, MCP wire repeat identical (duration_ms excluded), API
repeat byte-identical.

## 14. Security

No eval/exec/shell/arbitrary SQL/dynamic invocation/filesystem access in
the 6P module (grep + test-enforced; the module contains no SQL at all —
graph assembly reads only through `CanonicalQueries`). Closed node/edge
vocabularies raise on unknown types; traversal is bounded and kind-
restricted; MCP/API inputs are closed enums with bounds and
unknown-parameter rejection through the existing `Tool` contract.

## 15. Frontend

`InvestigationView.tsx` gains a GRAPH panel (Phase 6P section): focus-type
filter (closed node list) + path depth control, a node table (type badge +
id + label) with a click-to-inspect detail column showing canonical
reference, provenance, relationships (typed edges with directional
notation) and the ordered provenance path from the investigation. Node
families are visually distinct via `gp-node-*` classes (evidence blue,
hypothesis purple, MODELLED counterfactual dashed orange, lineage purple,
memory brown, context grey); edge classes distinguish SUPPORTS / CONTRADICTS
/ DERIVED_FROM / MODELS / REPLAY_OF. No visual implies stronger/weaker/
better/worse; COUNTERFACTUAL nodes are always labelled MODELLED. Only
investigation-scoped graphs are fetched (no corpus rendering); the graph
render is a table + detail column, so large graphs degrade gracefully.

## 16. Q18

`q18_benchmarks.py` (`q18_investigation_graph_v1`): golden graphs for
Q18.1 lap / Q18.2 stint / Q18.3 race-gap / Q18.4 regime (each snapshot →
verify VALID → replay IDENTICAL with recorded node_count/edge_count/hash),
Q18.5 cross-race pattern graph (discovered real 6L pattern), Q18.6
hypothesis evidence trace, Q18.7 contradiction path, Q18.8 counterfactual
path, Q18.9 memory lineage path (no orphan memory), Q18.10 replay/compare
lineage, Q18.11 evidence-unavailable graph (1950 → zero evidence/
counterfactual/memory nodes), Q18.12 bounded-traversal negative controls.
Negative controls: tampered snapshot → HASH_MISMATCH, invalid schema →
INVALID_SCHEMA, replay of invalid → INVALID_SNAPSHOT, invalid
investigation → INVALID (no partial graph), invalid node/edge type
rejected, lap-beyond-race builds zero fabricated LAP nodes.

## 17. Performance (measured, LAP6 golden scope; see §17 of the completion
report for the table)

Graph build from an existing 6N result is ~18 ms p50. The dominant cost is
the 6N engine re-run embedded in build/replay when the investigation is
not already in hand (~0.6–0.7 s for LAP6; stint scopes cost more because
6G/6F collection does). Traversal ~5 ms, path/evidence/hypothesis traces
sub-0.1 ms, snapshot build/verify ~1.5 ms. Largest measured graph
(STINT1): 97 nodes / 362 edges, ~157 KB JSON — far below the 4 MB MCP
output cap. The frontend renders only investigation-scoped graphs.

## 18. Limitations

- The graph is per-investigation (plus explicit merges with lineage
  edges); there is no persistent global corpus graph (that would require a
  persistence layer, out of scope per the zero-storage philosophy).
- A graph node exists only where the canonical store contains the
  referenced entity (no placeholders); unavailable scopes therefore yield
  smaller honest graphs.
- Lineage edges require caller-supplied 6O provenance; nothing is inferred.
- REGIME node identity uses the start/end lap range from the 6N evidence
  reference (the 6N ledger does not carry a populated regime_index).

## 19. Epistemic boundaries

    a graph edge is an imported analytical relationship, not causation
    SUPPORTS/CONTRADICTS states are imported from 6N, never inferred from
      graph topology
    a path is provenance navigation, not a causal chain
    MODELLED counterfactual nodes stay separate from historical evidence
      nodes
    MEMORY stays bound to its evidence and source investigation
    the graph ranks nothing: no confidence, no strongest hypothesis
    SUPPORT != PROOF; absence of a node is not negative evidence
