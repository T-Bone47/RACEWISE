# PHASE 6R — CAPABILITY MATRIX

Evidence-based statuses from the 54-case benchmark corpus, 20 API probes,
browser E2E sweep and golden set. Statuses: VALIDATED / VALIDATED_WITH_LIMITATIONS
/ BROKEN / UNAVAILABLE. "Successful" counts benchmark cases exercising the
capability that completed with real analysis; "Insufficient/Unavailable"
counts cases whose correct outcome was an honest limitation.

| Capability | Validated Cases | Successful | Insufficient/Unavailable | Unexpected Failure | Backend | API | Frontend | E2E | Provenance | Replay | Graph | Performance (p50/p95/max) | Status | Known Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Lap performance investigation | 8 (A) | 6 | 2 honest (non-fused laps, unknown driver) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (58/185) | 0.02–0.92 s | VALIDATED_WITH_LIMITATIONS | fused evidence only on 6D probe laps |
| Stint performance investigation | 6 (B) | 4 | 2 honest (1950, stint 99) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (97/362) | 0.3–4.7 s | VALIDATED | — |
| Race gap investigation | 6 (C) | 4 | 2 honest (1950/2000) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (35/53) | 3.4–3.6 s (API) | VALIDATED_WITH_LIMITATIONS | historical eras degrade honestly |
| Performance regimes | 5 (D) | 3 | 2 honest (1950/2000) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (41/60) | 2.5–3.9 s (API) | VALIDATED_WITH_LIMITATIONS | requires per-lap telemetry eras |
| Cross-race patterns | 5 (E) | 3 | 2 honest (unknown id, 1950 discovery) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (investigation) | n/a (scope-based) | 10.4–59 s (incl. re-discovery) | VALIDATED_WITH_LIMITATIONS | pattern ids corpus-scope-dependent; slowest operation |
| Hypothesis evaluation | 6 (F) | 5 | 1 honest (1950) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | 0.9 s | VALIDATED | — |
| Counterfactuals (deterministic) | 5 (G) | 3 (1 executed with gates) | 4 gate-explained (1950, race-level, budget-0, partial) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | 0.02–0.2 s (API) | VALIDATED_WITH_LIMITATIONS | single-lap speed-profile model only; race-level structurally ineligible |
| Full investigation synthesis | 4 (H) | 4 | 0 (incl. honest-limitation chain) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0.1–1.1 s | VALIDATED | — |
| Engineering memory | 4 (I) + golden G12 | 4 | 0 (wrong-scope zero is the correct outcome) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | 0.5–1.5 s | VALIDATED_WITH_LIMITATIONS | exact-scope matching only (by design) |
| Replay | 2 (J) + 9 golden replays | 11 IDENTICAL | 0 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | <1 s lap scope | VALIDATED | — |
| Comparison | golden G11 + E2E | 1 | 0 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | n/a | ~1 s | VALIDATED | descriptive deltas only (by design) |
| Graph (investigation graph) | 3 (K) + 4 golden graphs | 7 | 0 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0.7–0.9 s | VALIDATED_WITH_LIMITATIONS | scope-based rebuild; no investigation-id route |
| Telemetry comparison | baseline + E2E | 1 | 0 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | n/a | 0.08–0.25 s | VALIDATED | — |
| Lap attribution | E2E + corpus | 1 | 1 honest (no clean lap at default scope) | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | n/a | 0.4–0.55 s | VALIDATED | — |
| Evidence fusion | E2E + corpus | 1 | 0 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | n/a | 0.3–1.1 s | VALIDATED | — |
| Performance envelope | E2E | 1 | 0 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | n/a | 0.28–0.41 s | VALIDATED | — |
| Catalog / search / sessions | API probes + E2E | 3 | 0 | 0 | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | n/a | 0.01–0.03 s | VALIDATED | — |
| Pattern evidence workflow | E2E (post-fix) | 1 | 1 honest (id outside default corpus) | 0 | ✓ (fixed) | ✓ (fixed) | ✓ (fixed) | ✓ | ✓ | n/a | n/a | 6–16 s | VALIDATED_WITH_LIMITATIONS | requires scope binding (now deep-linked) |

Summary: 17 capabilities — 8 VALIDATED, 9 VALIDATED_WITH_LIMITATIONS,
0 BROKEN, 0 UNAVAILABLE. No unexpected failures remain.
