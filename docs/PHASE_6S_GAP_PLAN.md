# PHASE 6S GAP PLAN

Authoritative scope: `docs/NEXT_CAPABILITY_GAPS.md` (Phase 6R output).
Phase 6S implements exactly the four gaps below — no fifth gap, no
additional analytics, no architecture redesign. Every 6R guarantee
(canonical data, provenance, determinism, evidence taxonomy, hypothesis
vocabulary, falsification semantics, residual handling, counterfactual
gates, replay, graph integrity, memory leakage protection, lifecycle,
API contracts, frontend workflows) is preserved. All changes are additive
unless a documented defect requires a corrective change.

Measured facts this plan relies on (verified against the current store on
2026-09-28):

- `investigation_id` is a content hash of
  `{analysis, version, question, pair}` (16 hex chars). There is no
  stored investigation registry; the chain is derived-on-read.
- 6D telemetry probe laps: 93 RACE sessions (2021 R10, 2022–2025 full
  seasons), 12–19 evenly spaced laps each, top-2 classified drivers.
- Qualifying canonical data: lap times 2018–2025 (173 sessions), weather,
  race-control and stints present; no `canonical_results` rows for
  qualifying sessions (classification lives in `canonical_qualifying`);
  no telemetry rows for any qualifying session.
- FastF1 cache contains expanded-lap `car_data` only for 2024 R1 RACE;
  network is reachable for the remaining sessions.

---

## GAP 1 — Investigation-id-addressed graph retrieval

- gap_id: GAP_1_INVESTIGATION_ID_GRAPH
- classification: API_CAPABILITY (thin route over existing deterministic
  components; no new mathematics, no new storage)
- title: Graph retrieval addressed by a verified investigation id

- description: `GET /api/catalog/investigation-graph` rebuilds from a full
  scope. The replay and memory workflows expose `investigation_id` values,
  but there is no API path that addresses a graph by that id.

- why_it_matters: graph navigation from a replay/memory result currently
  requires reconstructing the original scope by hand.

- affected_questions: EQ-K family (graph); all 6N/6P consumers.

- required_data: none (reuses canonical data and derived-on-read chain).

- required_model: none (reuses `run_engineering_investigation` +
  `build_investigation_graph` unchanged).

- architectural_impact: low.

- current_limitation: scope-only addressing; investigation ids produced by
  replay/memory cannot drive graph retrieval.

- design (honest resolution of the content-hash fact): because the 6N
  investigation id is a content hash of the canonical input, a stored
  id→scope registry does not exist and must not be invented (it would add
  persistence that violates zero-storage-growth without justification).
  The closed implementation extends the existing route with an additive
  `investigation_id` parameter:
  - scope + `investigation_id` → the endpoint re-runs the investigation
    for that scope, recomputes the canonical id, and verifies the binding.
    On match it returns the graph built by the unchanged
    `build_investigation_graph`. On mismatch it returns 404 (no
    investigation exists with that id for the requested scope) — never a
    graph for a different investigation.
  - `investigation_id` without scope → 422 with the deterministic
    reconstruction requirement stated in the error detail.
  - scope alone → exactly the existing behavior (default path unchanged).
  This gives `scope → graph` and `investigation_id → graph` the same
  canonical graph semantics: the id-addressed path is a verified replay of
  the scope-addressed path, byte-identical (same graph_id, nodes, edges,
  snapshot hash).

- acceptance_condition:
  1. Graph built via `investigation_id` + scope is identical (graph_id,
     node/edge ids, snapshot hash) to the scope-only route for the same
     investigation.
  2. Wrong id → 404; missing scope with id → 422; invalid scope → 422;
     unavailable data → `status: UNAVAILABLE` body (existing convention).
  3. Determinism: same-process x3 and cross-process (PYTHONHASHSEED 3/29)
     identical graphs through the id-addressed path.
  4. Zero storage growth; existing scope-based route behavior unchanged.

- tests: unit (id binding verify/mismatch), API (200/404/422/unavailable),
  negative, determinism, provenance (graph node/edge provenance complete),
  benchmark cases EQ-L family, golden `G13_GRAPH_BY_ID`.

## GAP 2 — Non-RACE (QUALIFYING) session investigations

- gap_id: GAP_2_QUALIFYING_INVESTIGATIONS
- classification: ANALYTICAL_CAPABILITY + API_CAPABILITY (existing chain
  parameterized by session type; no new math — comparability semantics are
  documented, deterministic gates)

- title: Engineering investigations over qualifying sessions

- description: the 6N engine hard-requires `session_type == "RACE"` (422
  otherwise). Qualifying sessions are catalog-visible with real canonical
  lap times (2018–2025), weather, race control and stints.

- why_it_matters: qualifying-vs-race engineering questions are natural
  race-engineering workflows; qualifying single-lap comparability is
  well-defined.

- affected_questions: EQ-A (lap), EQ-H (hypothesis) families; new
  qualifying-scoped benchmark family.

- required_data: already present for 2018–2025 (canonical qualifying lap
  times + weather + race control). Pre-2018 qualifying has no lap times →
  honest UNAVAILABLE. No qualifying telemetry exists → telemetry-dependent
  evidence honestly propagates INSUFFICIENT/UNAVAILABLE and
  telemetry-gated hypotheses evaluate NOT_TESTABLE (preserved distinction,
  per master prompt §5).

- required_model: none new; the engine's session validation, participant
  resolution, lap-existence check and evidence collection are parameterized
  by `session_type` (currently hardcoded RACE in three checks).

- architectural_impact: medium (comparability semantics per session type,
  documented).

- current_limitation: 422 for anything ≠ RACE.

- design:
  - `SESSION_TYPES = ("RACE", "QUALIFYING")` in the engine; `session_type`
    flows into `question.scope` (additive; changes content-addressed ids
    only for qualifying-scoped investigations — all existing RACE ids are
    unchanged).
  - Qualifying comparability rules (documented in the engine and in the
    response): single-lap comparison; no race context; stint-scoped
    questions (`STINT_PERFORMANCE`) are INVALID for QUALIFYING with an
    explicit reason; participants are drivers with canonical qualifying
    entries (no `canonical_results` for qualifying sessions); pit semantics
    are absent (no canonical pit rows for qualifying) and propagate
    honestly; counterfactual execution stays gated off when 6I telemetry
    extraction is unavailable (candidate reports TELEMETRY_UNAVAILABLE).
  - Hypothesis applicability: telemetry-dependent hypotheses
    (corner speed, throttle, braking, DRS) legitimately evaluate
    NOT_TESTABLE for qualifying; lap-time-derived comparisons remain
    measurable. The aggregate state vocabulary is unchanged.
  - API: `session_type` accepted by the investigation + graph routes with
    closed-vocabulary validation; unknown session types 422 (no silent
    broadening).

- acceptance_condition:
  1. Qualifying LAP_PERFORMANCE investigation (2018–2025) returns VALID
     with honest hypothesis states and complete provenance.
  2. Pre-2018 qualifying → `status: UNAVAILABLE` (no fabricated data).
  3. STINT_PERFORMANCE + QUALIFYING → INVALID (422 via API) with reason.
  4. Unknown session type → 422. Lap absent for driver → UNAVAILABLE.
  5. Replay of a qualifying investigation IDENTICAL; provenance complete;
     determinism same-process x3 + cross-process.
  6. All existing RACE behavior byte-identical (ids, outputs, goldens).

- tests: unit (validation matrix), integration (2018 + pre-2018 eras),
  API (200/422/unavailable), negative (stint/unknown session), determinism,
  provenance, benchmark cases EQ-M family, golden `G14_QUALIFYING_LAP`.

## GAP 3 — Wider fused-lap coverage (bounded expansion policy)

- gap_id: GAP_3_WIDER_FUSED_LAP_COVERAGE
- classification: DATA_CAPABILITY + ANALYTICAL_CAPABILITY (bounded
  telemetry re-ingestion under the existing policy; fusion reused
  unchanged)

- title: Broader per-lap evidence coverage via bounded probe expansion

- description: fused lap evidence exists only on the 6D probe laps (12–19
  per race, top-2 drivers); other laps return honest INSUFFICIENT_EVIDENCE.

- why_it_matters: per-lap engineering questions are currently restricted
  to pre-selected laps.

- affected_questions: EQ-A03/A04 (measured INSUFFICIENT_EVIDENCE with
  TELEMETRY_UNAVAILABLE counterfactual candidates).

- required_data: FastF1 car-data for the already-covered 93 RACE sessions
  (expanded lap subset). No new sessions, no new eras, no new providers.

- required_model: none new; `_select_telemetry_laps` evenly-spaced
  selection is reused; `fuse_lap_evidence` is scope-free and reused
  unchanged.

- architectural_impact: medium (ingest/compute cost; decided and bounded
  below).

- current_limitation: honest INSUFFICIENT_EVIDENCE outside probe laps.

- design (chosen policy — "N evenly spaced fused laps per race"): raise
  the ingestion bound `max_laps_per_driver` 12 → 24 (TelemetryPolicy
  default), doubling coverage to roughly half of every covered race.
  Properties verified before implementation:
  - additive: upsert identity (sha1 of provider/session/driver/lap/time)
    means every existing probe lap is preserved byte-identically; no
    deletion, no re-derivation of existing fused outputs → no regression
    in any existing fused lap or golden.
  - bounded: per-session sample cap (2,000,000) unchanged and enforced in
    the ingestion path; measured storage delta documented before/after.
  - canonical: provider provenance, deterministic normalization, idempotent
    upsert, FK integrity, no-fabrication all inherited from the existing
    6C/6D path.
  Re-ingestion scope: the 93 already-telemetry-covered RACE sessions only
  (2021 R10, 2022–2025 seasons). The 2024 R1 session is fully cached
  locally (zero network); the rest are fetched through the existing
  FastF1 HTTP cache. Uncovered laps continue to report honest
  INSUFFICIENT_EVIDENCE — the limitation shrinks, it does not disappear.

- acceptance_condition:
  1. Distinct telemetry laps per covered session increase toward the 24
     bound (measured before/after); previously covered laps unchanged
     (spot-verified fused outputs identical).
  2. Lap investigations on previously-uncovered laps now reach measured
     outcomes (or remain honestly INSUFFICIENT where the lap is genuinely
     not comparable) — classified EXPECTED_CAPABILITY_EXTENSION.
  3. Counterfactual candidates on newly covered laps no longer report
     TELEMETRY_UNAVAILABLE; candidates on still-uncovered laps do.
  4. Storage delta measured and documented; zero row loss; determinism
     holds for the expanded fused outputs (same-process x3 + cross-process).
  5. G08 golden re-run and classified (expected: EXPECTED_CAPABILITY_
     EXTENSION if lap 12 becomes measurable).

- tests: data-integrity (idempotent re-ingest, additive identity), unit
  (selection policy), integration (lap investigation pre/post), negative
  (uncovered lap stays honest), determinism, provenance, benchmark cases
  EQ-N family.

## GAP 4 — Related-memory retrieval (structural match layer)

- gap_id: GAP_4_RELATED_MEMORY_RETRIEVAL
- classification: MEMORY_CAPABILITY (deterministic structural matching;
  explicitly NOT vector/semantic search)

- title: Provenance-preserving structural related-memory retrieval

- description: engineering memory is exact-scope matching only; there is no
  way to ask "what similar investigations exist?".

- why_it_matters: an engineer investigating a new race cannot discover
  related prior investigations (same driver pair, same hypothesis,
  adjacent season) without exact scope match.

- affected_questions: EQ-I family (memory).

- required_data: none (operates on derived-on-read memory items).

- required_model: deterministic structural matching on declared scope
  fields — no similarity scores, no embeddings, no opaque ranking.

- architectural_impact: high by nature (epistemic guarantees), handled by
  explicit policy: related items are pointers, never conclusion transfers.

- current_limitation: exact-scope only (documented contract; EQ-I02 proves
  zero leakage and must keep passing).

- design: layered retrieval, layers explicitly justified:
  - layer 1 EXACT: existing `retrieve_engineering_memory` behavior,
    unchanged and default (`include_related=false` → byte-identical
    responses).
  - layer 2 STRUCTURAL: new deterministic `related` matching, opt-in via
    `include_related=true`, over declared fields only: driver_pair
    (overlap), season (same or ±1), hypothesis overlap, pattern_id, lap/
    stint presence, scope_type. Every related item is returned with its
    full provenance (source investigation id, evidence ids, source hashes,
    scope, validity/invalidation state) plus `match_class: STRUCTURAL`,
    `match_reasons` (the exact structural fields that matched), and the
    policy text stating that a related item never transfers its conclusion
    to a new investigation. Invalidated items are excluded unless
    explicitly included (same rule as the exact layer).
  - NO semantic layer (no vectors, no embeddings) — rejected by the gap
    document.
  Memory items keep every required field: source investigation, evidence,
  provenance, scope, creation state, validity, invalidation state.
  No information crosses incompatible scopes: related results are marked
  non-transferable and carry their own scope; the exact layer remains the
  only source of scope-matched conclusions.

- acceptance_condition:
  1. Default retrieval responses are identical to Phase 6R (regression
     guard; EQ-I02 zero-leakage case still passes).
  2. `include_related=true` returns structural matches with complete
     provenance, explicit match_class and match_reasons, and policy text;
     no conclusion transfer (statements of related items are never merged
     into the requesting scope's evidence).
  3. Negative: a scope with no structural neighbors returns zero related
     items (no leakage); invalidated items excluded by default.
  4. Determinism: same-process x3 + cross-process identical related sets.
  5. Provenance completeness on every related item; zero storage growth.

- tests: unit (match semantics, exclusion rules, invalidation), API
  (param validation 200/422, default-identity regression), negative
  (leakage guard), determinism, provenance, benchmark cases EQ-O family,
  golden `G15_RELATED_MEMORY`.

## MCP

The 6N/6O/6P/6S deterministic engineering chain is exposed through the
catalog API (and the workspace frontend). The legacy MCP registry
(`racewise.mcp.server`) hosts the agent tool layer and does not carry
engineering-investigation tools; therefore no MCP changes are required by
any of the four gaps. This is re-verified during implementation; if an
engineering tool is found registered there, the corresponding gap adds it
using the existing registry conventions.

## Frontend

- GAP 1: Graph view gains an investigation-id field (deep-link
  `#/graph?investigation_id=…&…` with the scope params) — engineering
  terminology, no phase names.
- GAP 2: Investigation view gains a session-type selector (Race /
  Qualifying) and renders honest NOT_TESTABLE/UNAVAILABLE states for
  qualifying (already supported by the existing renderer).
- GAP 3: no UI change required (telemetry views already render actual
  coverage); verified, not assumed.
- GAP 4: Memory view gains an explicit "include related" control rendering
  the related section with provenance and the non-transferable policy.

## Benchmark expansion (master prompt §19)

- EQ-L (GAP 1): 4 cases — positive id-addressed graph equality, negative
  wrong id (404), invalid missing scope (422), provenance/replay case.
- EQ-M (GAP 2): 5 cases — positive qualifying lap investigation, limitation
  pre-2018 UNAVAILABLE, negative stint+qualifying 422, replay IDENTICAL,
  provenance completeness.
- EQ-N (GAP 3): 4 cases — positive newly covered lap, limitation
  still-uncovered honest INSUFFICIENT, counterfactual availability delta,
  additive-identity regression case.
- EQ-O (GAP 4): 5 cases — default-identity regression, positive structural
  retrieval, negative leakage guard, invalidation exclusion, provenance
  completeness.
- Total: 18 new cases (≥4 per gap; ≥16 required). All structural
  expectations only; no invented numeric answer keys.

## Implementation order and gates

GAP 1 → implementation → unit/integration/API/negative/determinism/
provenance tests → targeted regression. Then GAP 2, GAP 3, GAP 4 in the
same pattern. After all four: extend the corpus, re-run the complete 6R
benchmark (54 original + new), re-run goldens with hash-change
classification, full regression suite, docs, commit.
