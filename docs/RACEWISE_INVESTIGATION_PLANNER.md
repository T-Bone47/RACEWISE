# RACEWISE Investigation Planner

How a structured question becomes a bounded plan against real capabilities.

Three jobs, in order: **availability before analysis**, **composition**, and
**budget**. Everything the planner refuses to do is recorded rather than
silently dropped.

## 1. Availability before analysis

Every capability declares the canonical facets it requires. The planner checks
the store *before* anything runs and marks each capability:

| verdict | meaning |
|---|---|
| `TESTABLE` | every required facet is available |
| `LIMITED` | only *optional* facets are missing — runs degraded and says so |
| `UNAVAILABLE` | a *required* facet is missing — reported as untestable |
| `NOT_APPLICABLE` | the capability does not support this session type |

Availability is always derived from record counts in the canonical store, never
inferred from a season year. A 1950 session genuinely has lap times and no
telemetry, no stints and no race control, and the plan says so.

Hypothesis reachability is checked the same way: a hypothesis whose facet is
absent is recorded `NOT_TESTABLE` **with its reason**. Silently omitting it
would let the absence read as "nothing to say about DRS" rather than "no
evidence about DRS".

## 2. Composition

No single capability answers "where exactly did he lose the time". That is a
comparison, then an attribution, then a hypothesis test, then a residual.

The planner walks the registry's `prerequisites` graph and returns the
dependency closure, dependency-first:

```
simulate_telemetry_counterfactual
  └─ attribute_lap_loss
       └─ compare_laps
```

`GET /api/capabilities/{id}` returns the closure for any capability, so
composition is inspectable rather than implicit.

## 3. Budget — minimum sufficient computation

Analysis depth (§24) rises only as far as the question requires:

| level | meaning | example |
|---|---|---|
| 0 | context / provenance | "where does this evidence come from?" |
| 1 | simple comparison | "who was faster?" |
| 2 | quantitative decomposition | "attribute the deficit" |
| 3 | hypothesis testing | "was it braking?" |
| 4 | temporal / regime | "did it degrade?" |
| 5 | cross-race | "did it happen elsewhere?" |
| 6 | bounded counterfactual | "what if half were removed?" |

Every plan carries explicit limits: `max_capabilities`, `max_analysis_level`,
`max_cross_race_scans`, `max_counterfactuals`.

When a budget is exhausted the affected steps move to `deferred` with the reason
attached (`"deferred: cross-race scan budget exhausted"`), and the answer lists
them under *not established*. **Nothing is ever silently truncated** — a plan
that quietly dropped work would report a conclusion as if it were complete.

## Partial planning

A question whose data cannot support any capability does not fail wholesale. It
returns `DATA_UNAVAILABLE` with the plan intact, the availability report, and the
reason. A question with some capabilities blocked returns `PLANNED` and runs the
rest.

## Cancellation

Each investigation carries an id. Starting a new investigation for the same
scope **supersedes** the previous one: the older run stops at its next
checkpoint and can never overwrite the newer result. A cancelled run raises
`InvestigationCancelled` rather than writing a stale answer.

## Lap anchoring

Many capabilities need a lap number and users often do not name one. Choosing
arbitrarily would manufacture a result. Instead the engine walks shared
telemetry laps in descending order and takes the first yielding a `VALID` or
`VALID_CAVEATS` comparison — the same convention the existing catalog routes
use — recording the lap it anchored to and why. If no lap qualifies, the answer
reports that rather than substituting one.

## Plan shape

```json
{
  "status": "PLANNED",
  "analysis_level": 3,
  "sub_questions": [ … ordered DAG … ],
  "availability": { "available": [...], "unavailable": [...], "counts": {...} },
  "steps": [ { "capability_id": "...", "testability": "TESTABLE",
               "rationale": "serves TEST_HYPOTHESIS at level 3", … } ],
  "deferred": [ … ],
  "hypotheses_planned": [...],
  "hypotheses_unavailable": { "H5_race_control": "requires race_control data, …" },
  "budget": {...},
  "planner_version": "question_engine_planner_v1"
}
```

## Related

- [`RACEWISE_QUESTION_ENGINE.md`](RACEWISE_QUESTION_ENGINE.md)
- [`RACEWISE_CAPABILITY_REGISTRY.md`](RACEWISE_CAPABILITY_REGISTRY.md)
- [`RACEWISE_INTELLIGENCE_EVALUATION.md`](RACEWISE_INTELLIGENCE_EVALUATION.md)