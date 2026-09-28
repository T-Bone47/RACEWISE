# PHASE 6S COMPLETION REPORT

## 1. Executive summary

Phase 6S implemented exactly the four capability gaps documented by Phase
6R in `docs/NEXT_CAPABILITY_GAPS.md` — no invented scope, no new
architecture. All four gaps are CLOSED with layered evidence (unit /
integration / API / negative / determinism / provenance tests, 18 new
benchmark cases, 3 new goldens, E2E browser validation). Every Phase 6R
guarantee is preserved: the original race-path outputs are byte-identical
(including the honest-limitation goldens), determinism holds same-process
and cross-process (PYTHONHASHSEED 3/29), replay remains IDENTICAL, graph
integrity and memory leakage protection are intact, storage growth is
bounded and intentional, and no data is fabricated.

Final status: **READY_WITH_DOCUMENTED_LIMITATIONS** — now with materially
fewer limitations (qualifying is investigable, fused-lap coverage more
than doubled, graphs are id-addressable, memory is discoverable), and
every remaining limitation explicitly documented.

## 2. Phase 6R starting state

Commit `aebbe83` (feat(racewise): validate full engineering system):
54 benchmark cases, 696 regression tests + 5 legacy integration, 12
goldens, 17 validated frontend views, READY_WITH_DOCUMENTED_LIMITATIONS
with exactly 4 documented capability gaps.

## 3. The four approved capability gaps

Authoritative scope in `docs/PHASE_6S_GAP_PLAN.md` (written first, from
the gap document and measured store facts):

1. GAP_1_INVESTIGATION_ID_GRAPH — API_CAPABILITY.
2. GAP_2_QUALIFYING_INVESTIGATIONS — ANALYTICAL_CAPABILITY +
   API_CAPABILITY.
3. GAP_3_WIDER_FUSED_LAP_COVERAGE — DATA_CAPABILITY +
   ANALYTICAL_CAPABILITY (chosen policy: raise the evenly-spaced probe
   bound 12 → 24 laps/driver; strictly additive re-ingestion).
4. GAP_4_RELATED_MEMORY_RETRIEVAL — MEMORY_CAPABILITY (deterministic
   structural matching; vector/semantic search explicitly rejected).

## 4. Gap-by-gap implementation

### GAP 1 — investigation-id-addressed graph

The 6N investigation id is a content hash of the canonical input and no
stored registry exists (6R architecture). The honest implementation adds
an additive `investigation_id` parameter to the existing graph route: the
endpoint re-runs the investigation for the supplied scope, recomputes the
id, and verifies the binding. Match → graph built by the unchanged
builder (byte-identical to the scope-addressed graph, plus an `addressing`
marker). Wrong id or non-VALID scope → 404; id without scope → 422 with
the deterministic-reconstruction explanation. No registry invented, no
silent fallback. Frontend: replay results expose the investigation id
with a deep link to the id-addressed graph.

### GAP 2 — qualifying investigations

`SESSION_TYPES = ("RACE", "QUALIFYING")` in the engine; the session type
is part of the question scope and the content-addressed id (all existing
RACE ids unchanged). Qualifying comparability semantics are explicit:
stint-scoped questions and RACE_GAP → INVALID with reasons; pre-2018 →
UNAVAILABLE (canonical qualifying lap times begin 2018, measured);
participants resolved from `canonical_qualifying` (no canonical_results
rows exist for qualifying sessions; `get_qualifying` now joins
`driver_key`). New `fuse_qualifying_lap_evidence`: measured lap delta +
complete sector decomposition (sums exactly to the lap delta; residual
0.0 for covered laps), compound/age and weather confound checks, a
pit-phase scope fact, and the documented formal hypothesis rules — which
honestly hold telemetry-dependent hypotheses at NOT_TESTABLE /
INSUFFICIENT_EVIDENCE because no qualifying telemetry exists. Sector
splits locate the measured delta but never credit mechanism hypotheses
(no fabricated support). Provenance names the actual tool and
session-scoped source tables. API: session_type across all 6N/6O/6P
routes with closed-vocabulary validation; stint+QUALIFYING → 422;
default-pair policy refused for QUALIFYING. Frontend: session selector
with stint→lap guard.

### GAP 3 — wider fused-lap coverage

`TelemetryPolicy.max_laps_per_driver` 12 → 24 (single source of truth,
honest policy note; unchanged 2M-sample/session budget). The 93
telemetry-covered RACE sessions were re-ingested additively (upsert
identity preserves every existing lap byte-for-byte — verified: G01/G08
goldens and the lap-6 fused outputs are unchanged). The run was
rate-limit-aware (FastF1/LiftData 500 calls/h: the first pass completed
22 sessions, a checkpointed retry loop with --stop-on-rate-limit finished
the remaining 71; final state 93/93 completed, 0 failures). Measured
outcome: 1,551,999 → 1,964,265 telemetry rows (+412,266, +26.6%); store
695.9 → 794.8 MB (+98.9 MB, intentional, documented, per-session budget
never hit). Previously-uncovered laps now reach measured outcomes
(2023 R1 lap 8: SUPPORTED_BY_AVAILABLE_EVIDENCE, counterfactual ELIGIBLE
— previously TELEMETRY_UNAVAILABLE); still-uncovered laps keep honest
INSUFFICIENT_EVIDENCE + TELEMETRY_UNAVAILABLE (2023 R1 lap 44 — covered
for one driver only, not pair-coverable). Latent defect surfaced by the
wider data and fixed: 6K regime sensitivity passed context-dirty laps to
the envelope (which correctly rejects them with INVALID) — the regime
probe now pre-filters with the exact clean-comparable-lap criteria.

### GAP 4 — related-memory retrieval

Layered design, both layers documented: layer 1 EXACT — existing
`retrieve_engineering_memory`, byte-identical by default; layer 2
STRUCTURAL — new `retrieve_related_engineering_memory`, opt-in,
deterministic matching on declared fields only (same_driver_pair,
driver_overlap, hypothesis_overlap, adjacent_season — closed vocabulary),
exact-scope hits excluded (they are the exact layer's results),
invalidated items excluded unless explicitly included, bounded to 20,
sorted by memory_id, every item tagged match_class STRUCTURAL with
explicit match_reasons, full provenance, and the non-transfer policy ("a
related item is a provenance-backed pointer, never a conclusion
transfer"). No embeddings, no similarity scores. API `include_related=true`
expands the pool deterministically: the same spec at seasons ±1, only
VALID neighbors contribute (runs recorded in the response). Frontend:
"include structurally related items" control + related table +
"pointers, not conclusions" policy line.

## 5. Architecture changes

None beyond the gap plan. Reused unchanged: 6E attribution, 6F race
fusion, 6G stint fusion, 6H/6I/6J/6K/6L/6M layers, 6N engine (except the
documented session parameterization), 6P graph builder (except the
session-scope parameterization), 6O memory (except the additive related
layer). No new database, no new graph implementation, no LLM components.

## 6. Data changes

- Telemetry: +412,266 rows (additive upsert, idempotent, no deletes);
  93/93 covered sessions re-ingested under the raised bound; storage
  695.9 → 794.8 MB.
- `get_qualifying` join: +driver_key column (additive; callers unaffected).
- Ingestion tooling: `scripts/phase_6s_telemetry_expansion.py`
  (checkpointed to `data/ingestion_state/phase_6s_telemetry_expansion.json`),
  `scripts/phase_6s_extend_corpus.py` (idempotent corpus update).

## 7. API changes

- `GET /api/catalog/investigation-graph`: +`investigation_id` (verified
  binding; 404/422 semantics), +`addressing` marker, +`session_type`.
- `GET /api/catalog/engineering-investigation`: `session_type` ∈
  {RACE, QUALIFYING}; stint+QUALIFYING → 422; default-pair refused for
  QUALIFYING.
- replay / compare (a_/b_ prefixes) / memory / graph path+evidence+
  hypothesis: +`session_type`.
- `GET /api/catalog/engineering-memory`: +`include_related`; response
  gains related items/policy/neighbor-runs when requested.

## 8. MCP changes

None required: the MCP registry hosts no engineering-investigation tools
(verified). The deterministic engineering chain is exposed through the
catalog API, as in 6R.

## 9. Frontend changes

- ReplayPanel: investigation id + id-addressed graph deep link (GAP 1).
- InvestigationView: session selector (Race / Qualifying (2018+)) with
  stint→lap guard (GAP 2).
- MemoryPanel: "include structurally related items" control, related
  table with match reasons, non-transfer policy line (GAP 4).
- types.ts: RelatedMemoryItem + MemoryResult extension.
- No phase names in the UI; engineering terminology throughout; tsc and
  production build clean.

## 10. Graph changes

Builder parameterized by the scope's session_type (SESSION/LAP/STINT
nodes resolve the actual session; QUALIFYING session nodes verified E2E:
47 nodes / 107 edges for G14). No parallel semantics; vocabularies
unchanged; the id-addressed route reuses the same builder.

## 11. Memory changes

Additive structural layer as described above. Zero-leakage guarantees
preserved and re-proven (EQ-O03 zero-related negative; invalidated
exclusion; exact-layer identity by default).

## 12. Replay changes

Qualifying investigations replay IDENTICAL (EQ-M05, engine test, API
probe, golden G14). Id-addressed graphs replay IDENTICAL (G13, EQ-L04).
All 6R replay behavior unchanged (G01–G12 goldens: only G02_STINT's
output hash changed, classified EXPECTED_CAPABILITY_EXTENSION — the
widened coverage measures more laps of the same stint).

## 13. Provenance changes

Precise tool attribution on qualifying ledgers
(`fuse_qualifying_lap_evidence`, no `attribute_lap_loss` claims) and
session-scoped source tables (canonical_qualifying present,
canonical_telemetry absent for qualifying). Related-memory items carry
complete provenance. Provenance completeness checks pass for all 72
benchmark cases.

## 14. Benchmark expansion

72 cases (54 original + 18 new: EQ-L01–04, EQ-M01–05, EQ-N01–04,
EQ-O01–05; 20 limitation cases, 28%). One original case updated with
explicit classification: EQ-A04 was coverage-bound INSUFFICIENT_EVIDENCE
under the 12-lap policy and now measures a fused outcome — classified
EXPECTED_CAPABILITY_EXTENSION (structural checks unchanged; no numeric
values asserted). Final run: **72/72 pass** (62 STRUCTURAL_PASS,
8 EXECUTED_LIMITATION, 2 STRUCTURAL_CONTROL), 0 unexpected failures;
same-process and cross-process determinism true; API validation all-pass
(29 probes incl. 6S: qualifying valid/stint-422/unknown-session-422/
pre-2018-unavailable, graph-by-id 404/422, related-memory default/
expanded); no-fabrication scan clean (29 guard-language occurrences, 0
suspicious); security scan clean (0 unsafe); frontend route probes all
200 (16 routes). Results: `data/benchmarks/6r_benchmark_results.json`
(runtime artifact, not committed, per 6R convention).

## 15. Regression results

`python -m pytest -q tests src --ignore=tests/integration/
test_investigation_flow.py -p no:cacheprovider`: **737 passed, 1 skipped**
(696 baseline + 41 new 6S tests), after the data-state decoupling of two
coverage-coupled tests (stint trend rule, q9 thin-stint rule — both now
assert the reporting rule, not the historical coverage state) and the 6K
sensitivity pre-filter fix. Legacy integration
`tests/integration/test_investigation_flow.py` (run separately, never
staged): **5 passed**. Frontend: tsc clean, production build clean.

## 16. E2E results

Real-browser validation (1440×900) of every new user-facing capability:
qualifying investigation (VALID, 11 evidence items, hash matches golden
G14 `86aa93daa3`, honest hypothesis states, session QUALIFYING rendered);
related-memory toggle (7 exact + 7 structural pointers from the 2024 R1
neighbor, `adjacent_season, same_driver_pair`, policy line rendered);
id-addressed graph deep link (58 nodes / 185 edges, graph_id
`b2494a57c6a5268e` — identical to the scope-addressed G01 golden graph).
Route shell probes: 16/16 routes 200.

## 17. Security

Security scan clean (0 unsafe findings across src + apps/web: no eval/
exec/shell/unsafe HTML/dynamic SQL/secret exposure). No-Fabrication scan
clean (guard-language only). No new filesystem, network (beyond the
existing provider ingestion path), or MCP surface. API rejects invalid
input with explicit errors (never silent empties).

## 18. Determinism

Same-process ×3 and cross-process (PYTHONHASHSEED 3/29) identical for:
qualifying investigations (id d045ea5c7cfb0818), related-memory
retrieval, id-addressed graphs, plus the runner-wide determinism
validation (true). New goldens bind input, investigation id, output hash,
snapshot/replay hash, provenance hash and graph hashes.

## 19. Performance

Benchmark case latency: p50 1.386s / p95 25.433s / max 115.801s (6R:
1.14 / 17.7 / 59.1) — heavier fused stints under the widened coverage
plus 18 added cases; not an optimization claim, documented per §22 of the
master prompt. API validation latency improved: p50 0.275s / p95 10.877s
/ max 20.326s (6R: 0.58 / 6.29 / 16.0; p95/max reflect cold telemetry
paths on first-hit sessions). Qualifying investigations are fast (~0.2s)
because no telemetry layers execute. Related-memory adds one bounded
neighbor investigation (~1.5s).

## 20. Storage

Before: 1,551,999 telemetry rows / 695.9 MB. After: 1,964,265 rows /
794.8 MB. The delta is the deliberate, bounded GAP 3 expansion
(+26.6% rows; per-session sample budget never exceeded; per-session cap
enforced in the ingestion path; idempotent upsert; zero duplicate
analytical storage; memory and graph layers remain derived-on-read with
zero storage growth). No retention policy change: canonical raw data is
preserved, derived data is not persisted.

## 21. Remaining limitations

- Fused-lap coverage is bounded by policy: laps outside the 24/driver
  picks (e.g. 2023 R1 lap 44) report honest INSUFFICIENT_EVIDENCE with
  TELEMETRY_UNAVAILABLE counterfactual candidates. The bound is the
  documented data-volume trade-off; expansion remains a policy constant.
- Qualifying investigations cannot claim telemetry-dependent mechanisms
  (H1/H2/H3/H6 remain evidence-honest at NOT_TESTABLE/INSUFFICIENT):
  canonical qualifying sessions carry no telemetry. Sector-split facts
  and confound checks remain measurable.
- Pre-2018 qualifying is UNAVAILABLE (no canonical lap facts).
- Structural related-memory is limited to declared-field matching by
  design; no semantic similarity (per the gap document).
- Benchmarks are structural: they assert closed-vocabulary states, never
  numeric answers.

## 22. New genuine gaps discovered

None requiring a new phase entry. One latent defect was found and fixed
inside GAP 3's scope (6K regime sensitivity probe not pre-filtering clean
comparable laps — fixed in the engine, tested). A coverage-coupled
frailty in two live-data tests was fixed by asserting the reporting rule
rather than the historical data state.

## 23. Goldens (v2, `tests/benchmarks/phase_6r_goldens.json`)

G01–G12 preserved (G02_STINT output hash changed, classified
EXPECTED_CAPABILITY_EXTENSION; all others unchanged including G08's
honest INSUFFICIENT_EVIDENCE). New: G13_GRAPH_BY_ID (id-addressed graph,
addressed_by verified), G14_QUALIFYING_LAP (id d045ea5c7cfb0818, output
86aa93daa3dc6e88, replay IDENTICAL, graph 47/107 IDENTICAL),
G15_RELATED_MEMORY (±1-season neighbor runs recorded: 2022 VALID but 0
items — honest; 2024 VALID 7 items → 7 related pointers,
adjacent_season + same_driver_pair).

## 24. Commit

`feat(racewise): close validated engineering capability gaps` — code,
tests, corpus, goldens, capture/ingestion scripts, and docs
(PHASE_6S_GAP_PLAN, PHASE_6S_CAPABILITY_MATRIX, this report). Runtime
artifacts (benchmark results JSON, server logs, ingestion state/logs)
remain untracked per convention.
