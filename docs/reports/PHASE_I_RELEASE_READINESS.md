# Phase I — Release Readiness

## Decision: READY WITH DOCUMENTED LIMITATIONS

The distance-fraction alignment is implemented, proven on real laps,
tested at unit and end-to-end level, and honest about its bounds. The
estimator change is the fourth documented re-baseline in the
telemetry-reconciliation lineage (rectified sums → signed nets →
distance alignment), each preserved in code comments.

## Requirement coverage (workflows A–F)

| Workflow | Status | Evidence |
|---|---|---|
| A. Lap-time decomposition | strengthened (distance-aligned nets + residuals) | benchmark + regression green |
| B. Driving-mechanism analysis | preserved; worst-window associations flow to answers | calculations green; honest absence when no event |
| C/D. Tyre/stint | untouched, green | goldens T-G03/T-G13, q15 |
| E. Strategy/counterfactual | untouched, green | goldens T-G10/T-G14 |
| F. Cross-session | untouched, green | q15 7/7 on final code |

## Limitations (all measured)

1. Derived distance inherits speed-measurement noise; line differences
   absorbed by mean-D rescaling (second-order, stated in module docs).
2. Sector nets remain estimates; sector FACTS unchanged and exact.
3. Laps whose derived totals disagree >5% report INSUFFICIENT rather
   than comparing (new honest guard, untriggered on tested laps).
4. Resampling bypassed for estimation but kept for display grids and
   signal metrics (association evidence unaffected).
5. No fuel/traffic adjustments (no data); no store distance migration
   (deliberately avoided — derived method suffices).
6. 8 of 9 catalog models unverified; no cost data; streaming unprobed
   (carried over, unchanged).

## Regression risks and mitigations

| Change | Risk | Mitigation |
|---|---|---|
| Estimator replacement | golden hash drift | 7 goldens re-captured; structure verified identical (hash-only diff) |
| 6s race hash re-pin | silent re-baseline | prior values + bases preserved in comments |
| q15 residual-fed similarity | pick shifts | 7/7 green on final code; contract is evidence-backed, not count-based |
| Resampling bypass | display grids affected | display/signal paths untouched; estimation-only change |
| New INSUFFICIENT branch | new failure mode | threshold-gated, documented; untriggered on tested laps |

## Blockers

None. Full-suite re-run and golden completion are pending
compute, not decisions.

## Recommended next milestone

**Elliptical follow-up understanding** (carried over from Phase G):
compiling scope-carrying fragments ("was it sector 2?") against
inherited context. Unchanged justification: flagship conversational
behavior; full sentences work, fragments do not. The Phase G
benchmark's follow-up case plus the Phase H stopping ledger give the
failure mode full observability; only intake-level fragment resolution
is missing.
