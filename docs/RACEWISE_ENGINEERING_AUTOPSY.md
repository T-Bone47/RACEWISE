# RACEWISE Engineering Autopsy

**What it is.** A race-wide event timeline. Given one race and a driver pair, it
returns everything the deterministic engine already established changed during
that race, in lap order, each event naming the capability that produced it.

**What it is not.** It is not a race summary, a narrative generator, or a
second opinion on causality. It derives nothing.

## The one property that matters

The autopsy is a **curation layer**. It reads `analyze_performance_regimes` and
`decompose_race_gap` and reorders what they returned. It does not detect change
points, does not rank events by importance, and does not infer a turning point
that neither source reported.

This is enforced, not asserted. `tests/unit/test_autopsy.py` bounds the event
count by the engine's own output:

```python
engine_supplied = (
    len(regimes["change_points"])
    + len(regimes["context_transitions"])
    + len(regimes["unavailable_intervals"])
    + len(gap["gap_events"])
)
assert timeline["event_count"] <= engine_supplied
```

and separately asserts that empty input produces an empty timeline rather than
filler. If a future change makes the autopsy cleverer than its sources, this
test fails.

## Materiality: the distinction that keeps it honest

An early measured run over Bahrain 2023 R1 (Verstappen vs Pérez) produced 99
events. Reading them as a list, **59 were context transitions and 46 of those
were telemetry-availability flips** — artefacts of *our instrumentation*, not of
the car. Presented as engineering events they would have swamped the 7 genuine
regime changes the timeline exists to show.

Every event therefore carries one of two classifications:

| materiality | meaning | examples |
| --- | --- | --- |
| `ENGINEERING` | something about the racing changed | regime change, gap rate change, pit stop, compound change, rejected candidate |
| `MEASUREMENT` | what we could *measure* changed | telemetry availability flip, lap not comparable |

Two boundary cases are worth naming, because both were bugs first:

- **A pit stop is ENGINEERING.** The materiality split is not "context is
  noise". A tyre change altered how the car behaved and belongs on the
  engineering timeline. Verified by
  `test_world_changing_context_transitions_stay_engineering`.
- **An unmeasurable lap is MEASUREMENT.** `UNMEASURED_INTERVAL` — typically a
  pit lap — was originally classified ENGINEERING by falling through to the
  default. That put a pit lap on the same footing as a real regime change and
  inflated `material_event_count` by 10 on the fixture race. Fixed, and pinned
  by `test_unmeasured_intervals_are_measurement_not_engineering`.

The corrected measured result for Bahrain 2023 R1 is **43 ENGINEERING / 56
MEASUREMENT** out of 99.

## Measured output

`analyze_performance_regimes` + `decompose_race_gap` over 2023 R1,
`max-verstappen` vs `sergio-perez`:

```
event types         CONTEXT_TRANSITION 59
                    GAP_CHANGE         23
                    UNMEASURED_INTERVAL 10
                    REGIME_CHANGE       7
                    TOTAL               99
materiality         ENGINEERING 43 / MEASUREMENT 56
sources             analyze_performance_regimes, decompose_race_gap
unanchored          TELEMETRY_EVIDENCE_CHANGE (1 type, no lap anchor)
```

Not every gap event carries a lap. `TELEMETRY_EVIDENCE_CHANGE` is a
session-wide availability note; it is reported in `unanchored_events` rather
than silently dropped or assigned an invented lap.

## Three real bugs this work surfaced

Recorded because each would have shipped a wrong number to the UI:

1. **Regime laps vanished.** The regime analysis anchors on `transition_lap`.
   Reading `lap_number` yields `None`, which quietly dropped *every* change
   point. Pinned by `test_regime_laps_use_transition_lap_not_lap_number`.
2. **`limitations` serialised as a character array.** Four construction sites
   wrote `limitations=("some sentence")` — grouping parentheses, not a tuple —
   so `as_dict`'s `list(self.limitations)` produced one element per character.
   A 76-character limitation reached the UI as 76 single-character strings.
   Pinned by `test_limitations_are_lists_of_sentences_not_characters`, which
   asserts on shape rather than content.
3. **The residual was anchored to a lap it does not belong to.** A residual is a
   whole-race quantity. It is placed at the first regime's opening lap so it
   has a position on an ordered timeline, and the event now carries an explicit
   note saying it is not attributable to that lap.

## How a question earns a timeline

The autopsy is not offered on every question. `engine._wants_autopsy` fires on:

- an `INVESTIGATE`, `FIND_REGIME`, `FIND_TURNING_POINT` or `TREND` intent, or
- a sub-question at analysis level ≥ 4 (race-wide rather than lap/sector), or
- explicitly race-wide phrasing ("what materially changed", "walk me through").

A question like *"how much time did he lose in sector 2 on lap 6?"* gets no
timeline — verified: `narrow -> autopsy: False events: 0`.

The helper never raises. If the underlying analysis is unavailable for a race,
the answer proceeds without the timeline and records why. A timeline is an
enrichment; making it mandatory would turn an optional view into a total
outage for every whole-race question.

## API

```
POST /api/investigations/autopsy
{ season, round, driver_a, driver_b, session_type?, residual_s?, residual_source? }
```

`residual_s` is **supplied by the caller**, never recomputed here — the autopsy
reports a residual, it does not compute one. Either source analysis may be
unavailable; one failing degrades the timeline rather than failing the request.

A whole-race `POST /api/investigations/ask` also returns the timeline inline as
`answer.events` and `autopsy`.

## Limits

- **Curation only.** No event is inferred. If the deterministic stack did not
  report it, it is not here.
- **Two drivers.** The timeline is always a comparison; there is no solo
  autopsy.
- **Same store, same answer.** No clocks, no randomness; event ids are content
  hashes and are stable across processes.
- **Not a causality ranking.** Events are ordered by lap. Nothing claims one
  event caused another.

## Related

- [`RACEWISE_DECISION_TWIN.md`](RACEWISE_DECISION_TWIN.md) — bounded
  interventions on a measured deficit
- [`RACEWISE_QUESTION_ENGINE.md`](RACEWISE_QUESTION_ENGINE.md)
- [`RACEWISE_INTELLIGENCE_EVALUATION.md`](RACEWISE_INTELLIGENCE_EVALUATION.md)