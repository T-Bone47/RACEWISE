# Phase 6J — Measured Performance Envelope & Scenario Sensitivity: Methodology

How RACEWISE answers *"what performance envelope did the driver actually operate
within across the measured laps, and how does the validated model respond to
bounded changes inside that envelope?"*

Companion to `PHASE_6J_COMPLETION_REPORT.md` (measured results),
`PHASE_6I_TELEMETRY_COUNTERFACTUALS.md` (the lap-time model this phase reuses),
`PHASE_6F_EVIDENCE_FUSION.md` (evidence verdicts).

## 1. The one rule

**OBSERVED ≠ ENVELOPE ≠ OPTIMAL ≠ PREDICTION.**

The envelope is the driver's own measured variability over clean comparable laps.
It is not an ideal lap, not a theoretical maximum, not a driver model, and its
upper bound is **not** "the fastest the driver could ever go" — it is "the fastest
the driver was *measured* going, at that point of the lap, across the sampled
clean laps". Every output states this; the word "optimal" appears nowhere.

## 2. Envelope definition (mathematical formulation)

Profiles are extracted with Phase 6I's `extract_speed_profile` exactly (0.25 s
lap-relative grid, linear interpolation, clamped, no extrapolation). For laps
L₁…L_k of one driver (clean + telemetry-covered):

- Interpolate all profiles onto their common grid span (6E semantics; laps whose
  span does not fully overlap are excluded with a reason).
- Per grid point t:
  - `lower(t) = min_i v_i(t)` — slowest measured form
  - `upper(t) = max_i v_i(t)` — fastest measured form
  - `centre(t) = median_i v_i(t)` — band centre

Normalization is lap-relative time only; raw measured values are never modified
or persisted. The model baseline is the median profile through the Phase 6I
fixed-distance model, so **baseline reproduction is exact by construction**
(error 0.0, identity delta exactly 0.0 — hard invariants, test-enforced).

A `profile_id` (deterministic hash of session+driver+lap set+grid) identifies the
envelope without persisting anything.

## 3. Lap selection (what may enter the band)

Session scope: the driver's own clean telemetry-covered laps under the Phase 6E
context rules (pit-in/pit-out/deleted excluded, restricted track status excluded,
flagged-inaccurate excluded, per-lap-window rain excluded) — every exclusion
returned with its reason, nothing silently dropped, bounded by an evenly spaced
sample (cap 12 laps).

Stint scope: Phase 6G `_select_common_laps` (canonical stint identity, telemetry
coverage for both drivers) — the stint envelope is a *pair* construction by
definition, so a reference driver is required there.

## 4. Scenarios (typed enums; no caller expressions)

| Type | Definition | Parameter |
|---|---|---|
| `OBSERVED` | identity — the measured median profile unchanged | must be 0.0 |
| `DEFICIT_REDUCTION` | `v' = v + f·max(v_ref − v, 0)` vs the reference driver on the anchor lap | f ∈ [0, 1] |
| `REFERENCE_BLEND` | `v' = (1−w)·v + w·v_ref` | w ∈ [0, 1] |
| `ENVELOPE_LOWER_BOUND` | the slowest measured form per grid point | none |
| `ENVELOPE_UPPER_BOUND` | the fastest measured form per grid point | none |

Bounds are validated in the module (→ `INVALID`/`UNSUPPORTED` status) **and**
re-enforced at the tool boundary (→ `ToolError`): NaN/inf rejected, |parameter| ≤ 1,
`max_scenarios ≤ 11`, `max_laps ≤ 12`, `segment_s ∈ [2, 30]`, unknown parameters
rejected by the registry, scenario types are a closed enum enforced contract-wide.
Reference drivers are explicit — nothing assumes winner/teammate.

## 5. Sensitivity sweep

Reference scenarios sweep the full parameter range on a bounded evenly spaced grid
(2–11 points). Every point runs through the **Phase 6I model only** (no second
simulator): transform profile → exact piecewise-linear integration over the
baseline's fixed distances → delta. Sanity bounds per point: finite, non-negative
speeds, |delta| < lap duration, no stationary exclusions.

Response classification — descriptive finite differences, no fits:

- `FLAT`: all |delta| ≤ 1e-6 s
- `MONOTONIC`: first differences all ≤ 0 or all ≥ 0
- `NON_MONOTONIC`: sign change in first differences
- `INSUFFICIENT_DATA`: < 3 valid points

`max_abs_second_difference_s` is reported alongside: on the Q12 matrix every sweep
is MONOTONIC **and** measurably non-linear (second differences > 0) — the response
is measured, never assumed linear.

## 6. Regional analysis

At the anchor parameter, per-segment deltas
`d_r·(1/v_cf − 1/v_base)` (the exact 6I term) are ranked; the three largest
responses are reported with their time windows. This is **model sensitivity by
region** — it is not sector causality, and no sector-causal language is used.

## 7. Stint scope and degradation interaction

For stint envelopes, the mid-parameter scenario is additionally applied to *each
measured stint lap* on its own grid (reference interpolated onto the lap/reference
common span — no extrapolation; laps with insufficient overlap are skipped and
counted). The per-lap deltas and their OLS trend over lap order are reported with
one interpretation only: *"interpret alongside canonical degradation evidence — no
new tyre model is built here."* Sensitivity changing across a stint is an observed
model property, not a tyre claim.

## 8. Evidence integration (epistemic separation)

Six-layer chain — 6F evidence verdicts, 6G stint evidence, 6H race timeline, 6I
counterfactual sensitivity, 6J envelope sensitivity — and the categories never
merge. The correct joint statement is exactly:

> "The historical evidence supports the hypothesis, and the validated model is
> sensitive to the corresponding intervention."

Incorrect (and blocked): *"the model proves corner speed caused X seconds."*
The investigation-engine integration records envelope sensitivity as
`EvidenceType.COUNTERFACTUAL` with honest supporting *and* contradicting evidence,
and the falsification gate must pass.

## 9. Race-level boundary

Unchanged from 6I: results cover only the sampled measured laps. Scenario results
are **not** summed into an alternate race result; race-wide extrapolation is not
offered. Non-speed signals remain UNSUPPORTED.

## 10. Determinism

Same canonical data + parameters ⇒ byte-identical JSON (`output_hash` embedded,
excluding itself). Verified in-process, across fresh subprocesses, through the
registry, the API (byte-identical repeat) and the MCP server (hash
`36b5fd19e6bb2fea` matches every context). Derived on read; zero storage growth.
