# NEXT CAPABILITY GAPS (Phase 6R output)

Documented gaps demonstrated by benchmark/E2E evidence. Per the 6R fix
policy none of these were implemented automatically; each is recorded with
why it matters and what it would require. None is a correctness defect.

## 1. Investigation-id-addressed graph endpoint

- Gap: `GET /api/catalog/investigation-graph` rebuilds from a full scope
  (question_type + drivers + season/round + lap/stint/pattern). There is no
  way to request the graph of a stored/investigation-id directly.
- Why it matters: replay and memory workflows produce investigation ids;
  graph navigation from a replay result currently requires reconstructing
  the original scope.
- Affected benchmark evidence: EQ-K family; golden capture script had to
  pass full scopes for all graph goldens.
- Required: a catalog route accepting `investigation_id` that resolves the
  scope from the investigation snapshot and reuses `build_investigation_graph`.
- Architectural impact: low (thin route over existing functions).
- Future phase candidate: yes (small).

## 2. Non-RACE session investigations

- Gap: the 6N engine hard-requires `session_type == "RACE"` (422 otherwise).
  QUALIFYING/FP sessions are catalog-visible with capability metadata but not
  investigable through the engineering chain.
- Why it matters: qualifying-vs-race engineering questions (grid-to-race
  delta) are natural race-engineering workflows.
- Affected evidence: baseline audit §7; API probe of session catalog shows
  qualifying capability across eras.
- Required: scope/session-type plumbing through 6E–6N layers plus
  qualifying-specific comparability rules (single-lap, no stint context).
- Architectural impact: medium (comparability semantics differ per session
  type).
- Future phase candidate: yes, only after data coverage for qualifying
  telemetry is verified per era.

## 3. Wider fused-lap coverage

- Gap: fused lap evidence exists only on the 6D probe laps; lap-scoped
  investigations on other laps return honest INSUFFICIENT_EVIDENCE.
- Why it matters: per-lap engineering questions are currently restricted to
  pre-selected laps.
- Affected evidence: EQ-A03/A04 measured INSUFFICIENT_EVIDENCE with the
  counterfactual candidate reporting TELEMETRY_UNAVAILABLE.
- Required: either a bounded expansion policy (e.g., N evenly spaced fused
  laps per race) or an on-demand fusion path with explicit cost bounds.
- Architectural impact: medium (ingest/compute cost; the fusion itself is
  deterministic and reused unchanged).
- Future phase candidate: yes (data-volume tradeoff must be decided first).

## 4. Related-memory retrieval (explicitly out of scope by design)

- Gap: engineering memory is exact-scope matching only; there is no
  similarity/related-item retrieval.
- Why it matters: an engineer investigating a new race cannot ask "what
  similar investigations exist?" — only exact-scope lookups.
- Affected evidence: EQ-I02 proves zero leakage for wrong scopes (the
  intended behavior); the policy text states the limitation.
- Required: a deliberately designed similarity layer with provenance-preserving
  behavior; the current architecture intentionally refuses to generalize.
- Architectural impact: high (epistemic guarantees must be redefined).
- Future phase candidate: no — current exact-match semantics are the
  documented contract; any change deserves its own design phase.
