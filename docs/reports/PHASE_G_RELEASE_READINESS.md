# Phase G — Release Readiness

## Decision: READY WITH DOCUMENTED LIMITATIONS

RaceWise executes a representative set of evidence-grounded F1
engineering investigations end to end, preserves numerical and
provenance integrity, handles provider failures safely, and discloses
its limits. The limitations below are measured and bounded — none is
an open correctness defect in a supported path.

## What release covers

- Question → classification → evidence → deterministic analysis →
  hypothesis evaluation → synthesis → schema validation → verification
  → answer, with the Phase G benchmark (12 cases) green.
- Optional model review (critique gate + bounded workflow) and live
  NVIDIA verification on the configured model.
- Frontend workstation unchanged this phase; last verified 139/139,
  `tsc` clean, production build clean.

## Documented limitations (all measured)

1. **Elliptical follow-up fragments** ("was it sector 2?") do not
   compile; full-sentence follow-ups work with inherited scope.
2. **`ask()`-path counterfactuals** report INSUFFICIENT (served by the
   lifecycle endpoint); counterfactual rigor covered at tool level and
   by goldens T-G10/T-G14.
3. **Time-aligned window estimates are upper bounds** (no distance
   channel ingested); disclosed in assumptions, scope notes, and the
   phase-mixing flag. Gross exposure is non-additive by construction.
4. **Live-model verdicts vary run to run** (observed UPHELD →
   INCONCLUSIVE on identical input); reviews are advisory metadata only.
5. **Live model omits the lap-level baseline** in concise sector answers
   (4/5 Perez checks); deterministic answer always carries it.
6. **8 of 9 catalog models unverified**; streaming/context-limit
   unprobed; no cost data (recorded as unknown, never zero).
7. **Two corpus edge cases** predate this work (Q006, Q076).

## Regression risks and mitigations

| Change | Risk | Mitigation |
|---|---|---|
| Planner scope completion | plan bloat / changed answers | budget trim unchanged; corpus 99.1% steady; goldens run (6N path untouched) |
| Bare-corner spatial rule | scope over-claim | consumers audited (provenance + guard only); "corner speed" excluded |
| Stint helper extraction | route behavior drift | existing route tests green (146-suite) |
| Corner guard | status changes | adds `not_established` only; no status logic touched |
| Golden re-verification | hash drift | 6N path files untouched this phase |

## Blockers

None. No credential, data, network, or infrastructure blocker remains
for this release. Live multi-model comparison across all catalog models
is explicitly deferred (quota stewardship), not blocked.

## Recommended next milestone

**Elliptical follow-up understanding** — the highest-value remaining
interaction gap: compiling scope-carrying fragments ("was it sector 2?",
"what about sector 1?") against inherited investigation context.
Justification: follow-up continuity is the flagship conversational
behavior; full sentences work, fragments (the natural follow-up shape)
do not. Bounded scope: intake-level fragment resolution with the merged
scope as context, covered by the Phase G benchmark's follow-up case.
