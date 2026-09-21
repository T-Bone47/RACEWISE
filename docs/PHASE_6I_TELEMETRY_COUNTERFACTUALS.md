# Phase 6I — Validated Telemetry Counterfactuals: Methodology

How RACEWISE answers *"if a measured driver-level performance profile changed in a
precisely defined way, what does the deterministic lap-time model predict?"* — and,
just as importantly, what it refuses to answer.

Companion to `PHASE_6I_COMPLETION_REPORT.md` (measured results),
`PHASE_6H_RACE_GAP_DECOMPOSITION.md` (race level), `PHASE_6F_EVIDENCE_FUSION.md`
(lap evidence), `PHASE_6E_TELEMETRY_ATTRIBUTION.md` (attribution internals).

## 1. The simulator audit (what exists, what does not)

The existing deterministic simulator (`src/racewise/simulator/strategy.py`) exposes
`simulate_pit_timing`, `simulate_compound_change` and `compare_strategy_scenarios`.
All three consume **lap times and scenario parameters** (`list[Lap]`, pit laps,
compounds, degradation rates). None accepts telemetry.

Therefore the 6E/6F/6G/6H gate — *"telemetry-profile counterfactuals are
UNSUPPORTED"* — was correct for the strategy simulator and **remains correct for it**:
no telemetry adapter is faked into `simulate_pit_timing`.

What *does* exist is a second, already-validated deterministic lap-time model built
in Phase 6E over the **speed** channel: the region loss `dt·(1 − v_B/v_A)`. Phase 6I
generalizes this model to its exact (non-linearized) form and uses it as the
counterfactual engine. This is the smallest scientifically defensible bridge.

## 2. The bridge: fixed-distance segment integration

For a measured speed profile `v(t)` on the 0.25 s lap-relative grid (exact Phase 6E
alignment semantics: linear interpolation, clamped, no extrapolation):

1. Tile the lap span into segments of width `segment_s` (default 6 s, bounds 2–30).
2. For each segment compute the **exact** integral `d_r = ∫ v dt` using the
   piecewise-linear interpolant (trapezoids on clipped sub-intervals — no
   rectangle-rule sampling error) and `mean_v_r = d_r / Δt_r`.
3. **Baseline:** with the original profile, `t_r = d_r / mean_v_r = Δt_r` exactly, so
   the modeled lap time equals the measured grid duration. This is enforced as a
   validation gate with tolerance 1e-6 s; on real data the error is exactly 0.
4. **Intervention:** transform the speed profile deterministically, **keep the
   segment distances fixed** (they describe the track, defined by the original
   measurement), recompute `t_r = d_r / mean_v_r'`, and sum.
5. **Delta:** `counterfactual_delta = counterfactual_time − baseline_time`. Pure
   calculation; nothing is estimated by prose.

Correspondence with 6E: for `d_r = v_orig·dt` the exact term
`d_r·(1/v_cf − 1/v_orig)` equals 6E's linearization `dt·(1 − v_cf/v_orig)` — same
first-order form. The 6E estimated pace component is surfaced as an *informational
cross-check* on reference-based interventions; the two quantities are never merged.

Why speed only: throttle, brake, gear, RPM and DRS have **no deterministic model
mapping them to lap time** anywhere in this codebase. Interventions on those signals
return `UNSUPPORTED`. No aerodynamics, tyre grip, engine maps or brake temperatures
are invented (the strategy simulator has none of them either).

## 3. Interventions (mathematical transformations, not "better driving")

| Type | Definition | Bounds | Identity |
|---|---|---|---|
| `REMOVE_DEFICIT` | `v' = v + f·max(v_ref − v, 0)` | f ∈ [0, 1] | f = 0 → delta exactly 0 |
| `BLEND_WITH_REFERENCE` | `v' = (1−w)·v + w·v_ref` | w ∈ [0, 1] | w = 0 → delta exactly 0 |
| `SCALE_SIGNAL` | `v' = v·(1 + f)` | f ∈ [−0.10, 0.10] | f = 0 → delta exactly 0 |

`REMOVE_DEFICIT` never makes the target slower than measured (the max-term is
one-sided). `SCALE_SIGNAL` is reference-free. Bounds are enforced in the module
(`ValueError` → `INVALID`/`UNSUPPORTED` status) **and again at the tool boundary**
(`ToolError`), because the generic payload validator does not check numeric ranges.
NaN/infinity are rejected at both layers (the contract rejects non-finite floats;
the module re-checks).

## 4. Validation gates

Every result carries six explicit gates; `PASS` / `FAIL` / `NOT_RUN` per gate:

1. **telemetry** — target (and reference, when required) profiles exist with ≥ 20
   raw samples (6E `MIN_SAMPLES_PER_SIGNAL`).
2. **alignment** — shared 0.25 s lap-relative grid, ≥ 50 points.
3. **intervention** — known type, finite parameter inside explicit bounds.
4. **simulator_mapping** — the signal has a documented lap-time model (speed only).
5. **baseline_reproduction** — model baseline equals the measured grid duration
   (error ≤ 1e-6 s; measured 0.0 on the full matrix) **and** the identity-parameter
   run yields delta exactly 0.0.
6. **sanity_bounds** — finite outputs, non-negative transformed speeds,
   |delta| < lap duration, no stationary segments excluded.

Any failed gate stops the computation and returns an explicit status
(`INSUFFICIENT_EVIDENCE` / `UNAVAILABLE` / `UNSUPPORTED` / `INVALID`) with the
failing gate's detail. Nothing proceeds on a broken premise.

## 5. Levels

- **Lap** (implemented, verified): single-lap counterfactual, full gates.
- **Stint** (implemented, verified): aggregation over the **Phase 6G common-lap
  selector** (canonical stint identity, telemetry coverage for both drivers, every
  exclusion reported) with `MIN_STINT_LAPS = 3`, a monotonicity sanity check
  (closing more deficit must not gain less time), and explicit cumulative semantics:
  *"sum over the SAMPLED comparable laps only; not race time, not a season or race
  claim."*
- **Race** (not implemented, by design): the telemetry policy covers 12 clean laps
  per driver, not whole races. A race-wide counterfactual would require
  extrapolation across non-comparable intervals — exactly what 6H refuses to do.
  The gate stays: no race-level telemetry counterfactual is offered.

## 6. Epistemics (the most important section)

A counterfactual result is a **model-sensitivity measurement**: how strongly the
fixed-distance lap-time model responds to a specified intervention. It is:

- **not** a historical fact (the intervention never happened),
- **not** a prediction (no claim about future races),
- **not** a causal proof (sensitivity of a model to a lever is not evidence that
  the lever moved historically),
- **not** an equality with the measured lap delta: at full deficit removal the
  model adopts the reference trace over the *target's* segment distances, so the
  limit is a model quantity and the Phase 6E reconciliation residual applies.

Every output carries `epistemics` with exactly this statement, plus a
`delta_sign_convention` and per-assumption list. The 6F evidence-fusion statuses
are untouched: evidence verdicts come from `fuse_lap_evidence`; counterfactual
sensitivity is a *different epistemic object* and the Q11.8 integration records
them side by side, never merged. In the investigation engine the counterfactual is
recorded as `EvidenceType.COUNTERFACTUAL` with honest supporting *and* contradicting
evidence ("sensitivity ≠ causality"), and the falsification gate must pass.

## 7. Precision and determinism

- Reported times are rounded to 1e-6 s (the model's actual numerical precision);
  segment means are displayed at 1e-3 km/h. No fake decimal places beyond the
  quadrature's exactness.
- Same canonical data + same parameters ⇒ byte-identical JSON (verified across
  fresh subprocesses, the registry path, the API and the MCP server; hashes match
  across all contexts). `output_hash` (sha256/16, excluding itself) is embedded.
- Derived on read: **zero storage growth**, raw telemetry immutable.

## 8. What RACEWISE does NOT claim

- It does not claim telemetry proves what would have happened.
- It does not offer throttle/brake/gear/RPM/DRS counterfactuals.
- It does not offer race-level telemetry counterfactuals.
- It does not modify the strategy simulator to accept telemetry.
- It does not collapse evidence verdicts and model sensitivity into one number,
  score, or narrative.
