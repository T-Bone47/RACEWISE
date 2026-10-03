# RACEWISE Engineering Decision Twin

**What it is.** A bounded scenario sweep over a measured deficit. Given a
driver, a lap and a reference, it models what would happen across a range of
intervention strengths and returns the response curve.

**What it is not.** It is not a vehicle model, not a forecast, and not a
prediction of any future lap.

## The constraint that defines this module

`counterfactual.MODELED_SIGNALS` is `("speed",)`.

**Speed is the only signal with a lap-time model in this codebase.** Throttle,
brake, gear, RPM and DRS have none. A first draft of this module claimed
support for throttle and brake; that would have meant inventing the physics of
an intervention the engine cannot compute, and presenting the result as
engineering. It was cut before shipping.

```python
SUPPORTED_DIMENSIONS = ("speed",)
```

A brake scenario returns:

```json
{
  "status": "UNSUPPORTED",
  "reason": "'brake' has no deterministic lap-time model; modelled signals: ['speed']",
  "scenario_space": [],
  "limitations": ["No physical model exists for this dimension; approximating one would invent an engineering result."]
}
```

`tests/unit/test_decision_twin.py::test_unmodelled_dimensions_are_refused_not_approximated`
parametrises over throttle, brake, braking, gear, rpm, drs, steering and
suspension. All eight refuse.

## Refusal, not clamping

A request outside the intervention's valid range is **refused**, never quietly
rounded into range. Clamping 1.5 to 1.0 would answer a question nobody asked,
and the resulting number would be indistinguishable from a legitimate one.

```
REMOVE_DEFICIT       [0.0, 1.0]
BLEND_WITH_REFERENCE [0.0, 1.0]
SCALE_SIGNAL         [-0.10, 0.10]   <- multiplicative, a different range entirely
```

`SCALE_SIGNAL` swept over 0..1 — the obvious mistake — is rejected with
`INVALID_REQUEST` and an explicit note that it is refused rather than clamped.
One impossible fraction invalidates the **whole** sweep; dropping it would
silently change the curve the user is reading.

## Every point is MODELLED

Each scenario point carries, without exception:

```python
"claim_class": MODELLED        # "MODELLED"
"is_historical_truth": False
```

No arithmetic anywhere converts a model into a measurement. The baseline lap
time is the one OBSERVED quantity, and it is labelled as such — so a user can
always see the measured anchor next to the modelled deltas.

## Measured sweep

2023 R1, `max-verstappen`, lap 6, reference `sergio-perez`, `REMOVE_DEFICIT`:

| fraction | modelled Δ | gates |
| --- | --- | --- |
| 0.00 | 0.000000 s | ALL_GATES_PASS |
| 0.25 | −0.516525 s | ALL_GATES_PASS |
| 0.50 | −1.019427 s | ALL_GATES_PASS |
| 0.75 | −1.509312 s | ALL_GATES_PASS |
| 1.00 | −1.986747 s | ALL_GATES_PASS |

`sensitivity.shape` = `MONOTONIC`, with the caveat attached in the payload
itself:

> Shape describes how the MODEL responds across the sweep. It is not evidence
> of physical causation.

The `f = 0 ⇒ 0.0` endpoint is load-bearing. A non-zero delta at zero removal
would mean the model carries an offset the sweep is absorbing, and every other
point on the curve would be misattributed.

## Failure is reported, never interpolated

When some points cannot be modelled the sweep returns `PARTIALLY_MODELLED` and
says how many failed. Failed points are present in `scenario_space` with their
own status and `delta_lap_time_s: null`. They are not dropped, and they are not
smoothed over with a line between their neighbours. When no point is usable the
status is `INSUFFICIENT_EVIDENCE` and the baseline reports
`lap_time_s: null, source: "unavailable"`.

## API

```
POST /api/investigations/decision-twin
{ season, round, driver, lap_number, reference_driver?,
  dimension?, intervention_type?, fractions?, session_type? }
```

A refusal is a successful HTTP response with a reasoned status — not an error.
The frontend renders `UNSUPPORTED` as a refusal carrying its reason.

## What a user must never be told

- That removing half the deficit *would have* produced −1.019 s. It would not.
  Half of it is modelled; half of it is a model.
- That the curve is monotonic in reality. It is monotonic *in the model*.
- That a brake intervention was refused because the request was malformed. It
  was refused because no brake physics exists.

## Related

- [`RACEWISE_ENGINEERING_AUTOPSY.md`](RACEWISE_ENGINEERING_AUTOPSY.md)
- [`RACEWISE_INTELLIGENCE_EVALUATION.md`](RACEWISE_INTELLIGENCE_EVALUATION.md)