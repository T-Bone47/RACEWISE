# PHASE 6S CAPABILITY MATRIX

Before/after per approved gap (`docs/NEXT_CAPABILITY_GAPS.md`). Statuses:
CLOSED / PARTIALLY_CLOSED / DOCUMENTED_LIMITATION / BLOCKED. "Never claim
CLOSED unless all relevant layers work" — every CLOSED row below is backed
by unit/integration/API/negative/determinism/provenance tests, benchmark
cases, a golden, and (where user-facing) E2E browser validation.

Starting state: Phase 6R `aebbe83`, READY_WITH_DOCUMENTED_LIMITATIONS,
54 benchmark cases, 696 regression tests, 12 goldens.

---

## GAP 1 — Investigation-id-addressed graph retrieval

Classification: API_CAPABILITY.

| Layer | BEFORE | AFTER |
|---|---|---|
| DATA | n/a (derived-on-read) | unchanged (zero storage growth) |
| BACKEND | investigation id only a returned field | scope→id binding verified against the content hash; `addressing` marker (SCOPE / INVESTIGATION_ID) on every graph response |
| API | scope-only `GET /api/catalog/investigation-graph` | additive `investigation_id` param: match → identical graph; wrong id / non-VALID scope → 404; id without scope → 422 |
| MCP | no engineering tools (unchanged) | no engineering tools (verified) |
| FRONTEND | replay result could not drive the graph | replay panel renders the investigation id + "Open graph addressed by this investigation id →" deep link |
| GRAPH | builder untouched | builder untouched (no second implementation) |
| MEMORY | unchanged | unchanged |
| REPLAY | unchanged | unchanged (replay remains IDENTICAL on the id-addressed path) |
| PROVENANCE | graph provenance complete | identical (byte-equal graphs across addressing modes) |
| TESTS | — | 6 API tests (identity/404/422/422/422/determinism), EQ-L01–L04, golden G13, runner probe `graph_by_id` (+ mismatch negative), 2 API probes |
| PERFORMANCE | graph build ~2.9s | unchanged (id path adds one hash comparison) |
| STATUS | — | **CLOSED** |

## GAP 2 — Non-RACE (QUALIFYING) session investigations

Classification: ANALYTICAL_CAPABILITY + API_CAPABILITY.

| Layer | BEFORE | AFTER |
|---|---|---|
| DATA | qualifying lap times 2018–2025 + weather/race-control/stints present, unused by the chain | consumed: canonical_qualifying (classification of record, `driver_key` join added), session-scoped lap facts, sector splits, stints, weather |
| BACKEND | `session_type == "RACE"` hardcoded in 3 validation checks + collectors | `SESSION_TYPES = ("RACE","QUALIFYING")`; qualifying comparability semantics (stint/RACE_GAP → INVALID with reason; pre-2018 → UNAVAILABLE with coverage reason; participants from canonical qualifying); `fuse_qualifying_lap_evidence` (measured sector decomposition summing to the lap delta, preserved residual, honest telemetry hypothesis states, pit-phase scope fact); precise provenance (`fuse_qualifying_lap_evidence` + qualifying source tables) |
| API | 422 for anything ≠ RACE | `session_type` on investigation / replay / compare (a_/b_) / memory / graph + path/evidence/hypothesis; closed vocabulary (unknown → 422); stint+QUALIFYING → 422; default-pair policy refused for QUALIFYING (422, no silent race-pair reuse) |
| MCP | no engineering tools | no engineering tools (verified) |
| FRONTEND | RACE only | session selector (Race / Qualifying (2018+)) with stint→lap guard on switch |
| GRAPH | SESSION/LAP/STINT nodes hardcoded RACE | parameterized by scope session_type (QUALIFYING session nodes verified in E2E) |
| MEMORY | RACE-scoped items | qualifying investigations derive memory items through the same 6O machinery |
| REPLAY | RACE only | qualifying replay IDENTICAL (engine test + EQ-M05 + API probe) |
| PROVENANCE | race tables only | session-scoped source_tables (canonical_qualifying, no canonical_telemetry claimed) |
| TESTS | — | 21 tests (validation matrix, fusion honesty, determinism ×3, cross-process 3/29, replay, race-golden regression guards, API 200/422/unavailable), EQ-M01–M05 (incl. pre-2018 limitation + stint negative), golden G14, 3 API probes |
| PERFORMANCE | — | qualifying lap ~0.2–0.3s (no telemetry layers to execute) |
| STATUS | — | **CLOSED** (telemetry-dependent hypotheses honestly NOT_TESTABLE/INSUFFICIENT in qualifying — a documented epistemic fact, not an open defect) |

## GAP 3 — Wider fused-lap coverage

Classification: DATA_CAPABILITY + ANALYTICAL_CAPABILITY.

| Layer | BEFORE | AFTER |
|---|---|---|
| DATA | 12–19 evenly spaced probe laps/driver on 93 RACE sessions (1,551,999 telemetry rows, 695.9 MB store) | 24-lap bound: 93/93 sessions re-ingested (rate-limit-aware, checkpointed, idempotent); 24–41 laps/session covered per session (union of both drivers' picks); 1,964,265 rows (+412,266, +26.6%); 794.8 MB (+98.9 MB, intentional and documented) |
| BACKEND | fusion limited to probe laps | `fuse_lap_evidence` unchanged and reused; coverage widened strictly additively (upsert identity, no deletes) |
| API | honest INSUFFICIENT_EVIDENCE outside probes | unchanged contract; more laps reach measured outcomes |
| MCP | no engineering tools | no engineering tools |
| FRONTEND | renders actual coverage | unchanged (verified) |
| GRAPH | unchanged | unchanged |
| MEMORY | — | more laps yield evidence-backed items (e.g. 2024 R1 lap 6: 7 items) |
| REPLAY | — | unchanged; previously covered laps byte-identical (G01/G08 goldens re-verified) |
| PROVENANCE | — | unchanged per-item; session provenance unchanged |
| TESTS | — | additive-identity guard (EQ-N04 + engine test), newly-covered positive (EQ-N01/N03: lap 8 measured, counterfactual ELIGIBLE), still-uncovered honest limitation (EQ-N02: lap 44 INSUFFICIENT + TELEMETRY_UNAVAILABLE), 6K sensitivity pre-filter fix (clean comparable lap intersection), 2 test-side data-state decouplings (stint trend rule, q9 thin-stint rule) |
| PERFORMANCE | case p50 1.14s (6R) | case p50 1.386s / p95 25.4s / max 115.8s (heavier fused stints + added 6S probes; API p50 improved 0.58→0.275s) |
| STATUS | — | **CLOSED** — the capability (bounded policy expansion) is delivered; the honest remaining limitation (uncovered laps report INSUFFICIENT_EVIDENCE, e.g. lap 44) is the documented trade-off of the bounded policy, re-documented below |

## GAP 4 — Related-memory retrieval (structural layer)

Classification: MEMORY_CAPABILITY. Explicitly NOT vector/semantic search.

| Layer | BEFORE | AFTER |
|---|---|---|
| DATA | derived-on-read | unchanged (zero storage growth) |
| BACKEND | exact-scope only | `retrieve_related_engineering_memory`: deterministic structural matching on declared fields (same_driver_pair, driver_overlap, hypothesis_overlap, adjacent_season); exact-scope hits excluded (they belong to the exact layer); invalidated excluded unless included; bounded (≤20); deterministic ordering; closed match-reason vocabulary; non-transfer policy on every item |
| API | exact-only `engineering-memory` | additive `include_related=true`: ±1-season deterministic neighbor pool (only VALID neighbors contribute), response carries `related_memory_items` (match_class STRUCTURAL, match_reasons, full provenance), `related_policy`, `related_neighbor_runs`; default responses byte-identical to 6R |
| MCP | no engineering tools | no engineering tools |
| FRONTEND | exact list only | "include structurally related items" control + related table (structural match reasons, statement, validity) + "pointers, not conclusions" policy line |
| GRAPH | unchanged | unchanged |
| MEMORY | zero-leakage exact contract (EQ-I02) | preserved: EQ-I02-equivalent leakage guard re-proven (EQ-O03); every related item keeps its own scope and provenance |
| REPLAY | unchanged | unchanged |
| PROVENANCE | — | every related pointer: source investigation ids, evidence ids, source hashes, scope, validity/invalidation, match_class, match_reasons |
| TESTS | — | 14 tests (match semantics, exact-layer identity, leakage, invalidation, provenance completeness, boundedness, determinism ×3, cross-process 3/29, API identity + related), EQ-O01–O05, golden G15, 2 API probes |
| PERFORMANCE | — | +1 neighbor investigation per related request (bounded, ~1.5s) |
| STATUS | — | **CLOSED** |

---

## Overall status by gap

| Gap | Status |
|---|---|
| GAP_1_INVESTIGATION_ID_GRAPH | CLOSED |
| GAP_2_QUALIFYING_INVESTIGATIONS | CLOSED |
| GAP_3_WIDER_FUSED_LAP_COVERAGE | CLOSED (bounded-coverage limitation re-documented) |
| GAP_4_RELATED_MEMORY_RETRIEVAL | CLOSED |

No DOCUMENTED_LIMITATION or BLOCKED entries beyond gap 3's inherent,
honest coverage bound (which the gap plan itself specifies as the chosen
policy: "uncovered laps continue to report honest INSUFFICIENT_EVIDENCE").
