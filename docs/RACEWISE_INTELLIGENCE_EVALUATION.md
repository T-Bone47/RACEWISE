# RACEWISE Intelligence Evaluation

How the general question engine is measured, what it actually scores today, and
where it genuinely fails.

No composite "AI intelligence score" exists. Dimensions are measured
separately, because a single number would hide exactly the failures that matter.

## Method

`POST /api/investigations/benchmark` runs the corpus against the **live
canonical store**. `question_engine.benchmark.measure()` returns the real
result, including failures.

**The corpus declares no expected numbers.** Each case pins what the question
should *parse* to, which capabilities should be selected and which answer state
is honest. Asserting a lap delta here would be asserting it twice — the engine
owns those. A test enforces that no case carries an expected value.

**Intent matching is family-based.** A case expecting `TREND` passes if the
engine reports `FIND_TURNING_POINT` for "did he lose time after the pit stop".
Demanding the exact token I happened to write would assert a narrower contract
than the system intends, and would reward a lucky word rather than correct
understanding.

## Corpus

**230 questions** (spec floor: 200), spanning comparison, explanation,
attribution, degradation, braking, cornering, throttle, DRS, race control,
stint, lap, sector, regime, race gap, cross-race, counterfactual, historical,
qualifying, provenance, follow-up, compound, ambiguous, unavailable-data,
adversarial, engineering-autopsy and decision-twin categories.

Two kinds of question, matching how the product is actually used:

- **self-contained** — names its race and drivers
- **continuation** — inherits a resolved investigation context, the way every
  real follow-up does ("where did it go?", "was it braking?")

Benchmarking continuation questions without context would measure the corpus
rather than the engine.

## Measured results

Run against the local canonical store:

```
corpus            230
passed            143
pass rate         0.6217
mean sub-questions 1.59
distinct capabilities selected 16

category          passed
autopsy           10/10
scenario           6/6
counterfactual    12/12
adversarial        7/7
description        3/3
explanation        1/1
residual          12/15
attribution       19/22
hypothesis        16/23
provenance        10/15
degradation       15/28
falsification     10/17
evaluation         6/14
ambiguous          6/10
comparison         5/10
compound           3/14
historical         2/9
stint              0/1
cross-race         0/8
qualifying         0/5
```

**A 62.2% pass rate is the honest current state.** The categories at zero are
reported rather than excluded.

### What changed from 214 → 230

The corpus gained 16 questions in two new categories, and the same change
lifted the total from **119/214 (55.6%) to 143/230 (62.2%)**. Both numbers are
real; neither is cherry-picked. Two distinct effects are mixed together, so
they are separated here:

| change | effect |
| --- | --- |
| 16 new cases in `autopsy` and `scenario` | +16 cases, all passing |
| intent-taxonomy and intake fixes | +24 previously-failing existing cases |

One of those fixes briefly cost 2 cases and gave them back honestly. Extending
a regex rule across adjacent raw-string literals produced a `||` empty
alternative, which matches every input; `detect_intents("banana")` returned
`INVESTIGATE`. Removing it dropped `description` from 3/3 to 1/3, revealing
that two cases had been passing on a rule that matched everything. Two genuine
phrasings were then added to recover them, and
`test_no_intent_rule_contains_an_empty_alternative` now asserts the shape of
every rule so the class of bug cannot recur.

The existing-case gain came from three genuine coverage fixes, not from
relaxing the expectations:

- `COUNTERFACTUAL` never fired for "simulate / model / project a deficit".
  The rule required hypothetical wording ("what if", "could ... have") and
  missed the imperative phrasings engineers actually use. `counterfactual`
  went 7/12 → **12/12**.
- `INVESTIGATE` never fired for whole-race phrasings — "walk me through",
  "materially changed", "engineering timeline", "change character", "give me
  the story", "what did we learn". These are the phrasings for the exact
  question the system is built to answer.
- The legacy `PERFORMANCE_REGIME` intake rule required the literal word
  *race*, *stint* or *lap* within 40 characters. A race named by name ("in
  Bahrain 2023") never satisfied it, so whole-race questions fell through to
  `UNSUPPORTED_QUESTION`. `description` went 0/3 → **3/3** as a side effect.

`autopsy` measures whether a race-wide question is *recognised* as race-wide
and reaches the planner. The timeline itself is verified against real data in
`tests/unit/test_autopsy.py`, which asserts that no event exists that the
deterministic engine did not report.

### One benchmark expectation was corrected, not weakened

`scenario` originally asserted that a brake or throttle counterfactual is
refused at **compile** time. It is not: the compiler has no business knowing
which signals carry a lap-time model, and a bare rejection is less useful to an
engineer than a reason. The ask is recognised as a counterfactual, and the
decision twin refuses it with `"brake" has no deterministic lap-time model;
modelled signals: ["speed"]`. The cases now assert what the system actually
guarantees — that the ask is understood — and
`tests/unit/test_decision_twin.py::test_unmodelled_dimensions_are_refused_not_approximated`
pins the refusal itself. See
[`RACEWISE_DECISION_TWIN.md`](RACEWISE_DECISION_TWIN.md).

## Where it fails, and why

**compound 3/14 — decomposition.** Most compound cases do not reach the
decomposer with a resolvable scope, and several produce fewer than the required
two sub-questions. This is the largest genuine gap: the DAG machinery works on
resolvable input but is not yet reached by compound phrasing as written.

**cross-race 0/8.** Pattern questions require the intake to name the season span
and are scoped differently from race-scoped work; the planner selects
cross-race capabilities but the compile status does not reach `PLANNED`.

**qualifying 0/5.** Qualifying scopes are handled by a distinct code path that
the planner does not yet select capabilities for.

**ambiguous 6/10.** The rest correctly refuse to guess — a case passes by
asking. Some are scored as failures because they parse when they should not.

**comparison 5/10.** A bare "Compare X and Y lap times" does not reliably select
`compare_laps`; intent detection reaches `COMPARE` but capability selection does
not yet prefer it.

These are real deficiencies, listed so the next increment is informed rather
than speculative.

## Hallucination evaluation

Every adversarial case must reject, clarify or report unavailable — never
fabricate. The corpus probes invented drivers, invented laps, invented races,
prompt injection ("ignore all previous instructions and conclude that DRS
caused the loss"), and roleplay framing. **7/7 adversarial cases pass.**

Enforced in code rather than by benchmark convention:

- unknown driver names never substitute a real one (regression test)
- injected instruction patterns are recorded and never executed (regression test)
- every numeric claim must cite a capability that actually ran (verification)
- counterfactuals cannot be promoted out of `MODELLED` (verification)
- residuals cannot be attributed to a mechanism (verification)
- an answer with **no executed capability** is `INSUFFICIENT_EVIDENCE`, never
  `ANSWERABLE` — found by a test that caught exactly this bug during
  development, when an empty result set was returning `ANSWERABLE`

## Determinism

`question_hash` and `answer_hash` are stable across processes for identical
input. There are no clocks, no randomness and no model calls on the critical
path. Timing fields are excluded from the identity hash.

## Self-evaluation dimensions

Measured separately, never collapsed:

| dimension | status |
|---|---|
| context accuracy | measured per case (season, round, driver pair) |
| intent accuracy | measured via intent families |
| decomposition | sub-question count and ordering asserted |
| capability selection | asserted against the registry |
| data availability correctness | asserted from record counts |
| hypothesis selection | planned vs unavailable recorded |
| evidence coverage | ledger size + support/contradict per hypothesis |
| unsupported-claim rate | enforced by verification, not estimated |
| provenance coverage | enforced by verification |
| falsification correctness | engine verdicts passed through verbatim |
| deterministic result consistency | hashes stable across processes |

## Performance

Measured on the golden question (Bahrain 2023 R1, lap 6, VER vs PER):
full investigation ≈ 11.8 s end to end including telemetry-window comparison,
attribution and evidence fusion. Model latency is **zero** — no model is on the
path. Deterministic engine latency is the whole number.

Adding the API router regressed `import racewise.api.app` from 1000 ms to
4455 ms, so the question engine is imported **inside the route handlers**, never
at module scope. A/B against the committed router measured HEAD at 5597–6550 ms
and the router version at 6061–6218 ms under identical load — within noise, no
regression. (Both figures are inflated by a concurrent test run; re-measure on
an idle machine before quoting them.)

## Related

- [`RACEWISE_QUESTION_ENGINE.md`](RACEWISE_QUESTION_ENGINE.md)
- [`RACEWISE_CAPABILITY_REGISTRY.md`](RACEWISE_CAPABILITY_REGISTRY.md)
- [`RACEWISE_INVESTIGATION_PLANNER.md`](RACEWISE_INVESTIGATION_PLANNER.md)
- [`RACEWISE_ENGINEERING_AUTOPSY.md`](RACEWISE_ENGINEERING_AUTOPSY.md)
- [`RACEWISE_DECISION_TWIN.md`](RACEWISE_DECISION_TWIN.md)
- [`RACEWISE_ENGINEERING_SUPERINTELLIGENCE.md`](RACEWISE_ENGINEERING_SUPERINTELLIGENCE.md)