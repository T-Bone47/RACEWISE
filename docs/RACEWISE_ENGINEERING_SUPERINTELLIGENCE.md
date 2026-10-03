# RACEWISE Engineering Superintelligence

**Status.** The architecture is in place and measured. Phases A–J of the brief
are satisfied by the existing deterministic foundation and the question engine.
Phases K (Engineering Autopsy) and L (Engineering Decision Twin) are built,
tested and benchmarked. Phases M–T are **not** built — see
[What is not built](#what-is-not-built), which is the most useful section here.

## What the system is

RACEWISE answers arbitrary engineering questions by discovering and composing
the deterministic capabilities it already has:

```
any engineering question
        ↓
  question compiler      language → structured question, closed vocabulary
        ↓
  context resolver       canonicalise drivers/races/scope; ask, never guess
        ↓
  decomposer             compound question → sub-question DAG
        ↓
  planner                discover capabilities → check availability → budget
        ↓
  deterministic engine   ← the only thing that computes numbers
        ↓
  engineering autopsy    whole-race event timeline (K)
        ↓
  synthesizer            structured partial answer, grounded in real results
        ↓
  verification           every claim traceable; nothing ungrounded survives
        ↓
  decision twin          bounded modelled interventions (L)
```

The user never selects a question type, a capability, or a page. They ask.

## The governing rule

**The language model is not the engineering authority.**

The model may understand prose, resolve intent, decompose questions, organise
evidence and suggest follow-ups. It may not invent telemetry, invent numbers,
fabricate confidence, fabricate causality, override a deterministic
calculation, or turn a modelled scenario into a historical fact.

Every number in an answer came from one of the deterministic calls. The
synthesizer builds the engineering answer **first, as structure**, and generates
prose from that structure — never the reverse. A system that writes the
sentence first and attaches provenance afterwards will always be able to
produce a sentence with no provenance behind it.

Correct adversarial outcomes are `DATA_UNAVAILABLE`, `NOT_TESTABLE`,
`INSUFFICIENT_EVIDENCE`, `CONTEXT_UNRESOLVED` and `UNSUPPORTED_REQUEST`. These
are results, not failures, and are rendered as such.

## Measured state

| measurement | value |
| --- | --- |
| benchmark corpus | 230 questions |
| benchmark pass rate | **143/230 (62.2%)** |
| adversarial | 7/7 |
| autopsy questions recognised | 10/10 |
| scenario questions recognised | 6/6 |
| counterfactual | 12/12 |
| backend tests | see `tests/` |
| model latency | **zero** — no model is on the path |
| capability selection | asserted against the registry; unknown ids fail the benchmark |

Categories at zero are reported, not excluded: **cross-race 0/8**,
**qualifying 0/5**, **compound 3/14**, **stint 0/1**.

## The three new systems

### Engineering Autopsy (K)

A curation layer over `analyze_performance_regimes` and `decompose_race_gap`. It
reorders what those already returned into a lap-ordered timeline and **derives
nothing**. Every event carries the capability that produced it, and every event
is classified `ENGINEERING` (the car changed) or `MEASUREMENT` (what we could
measure changed).

That distinction is the whole point. An early run produced 99 events of which
46 were telemetry-availability flips; as engineering events they would have
buried the 7 genuine regime changes. See
[`RACEWISE_ENGINEERING_AUTOPSY.md`](RACEWISE_ENGINEERING_AUTOPSY.md).

### Engineering Decision Twin (L)

A bounded scenario sweep over the real `simulate_telemetry_counterfactual`.
Speed is the only signal with a lap-time model; every other dimension is refused
with a reason rather than approximated. Out-of-range fractions are refused, not
clamped. Every scenario point carries `claim_class: MODELLED` and
`is_historical_truth: false`. See
[`RACEWISE_DECISION_TWIN.md`](RACEWISE_DECISION_TWIN.md).

### Answer enrichment

`Answer` now carries `events`, `counter_evidence` and `answer_mode`.
`counter_evidence` resolves contradicting evidence ids against the ledger into
readable statements — a user asking "what contradicts that?" must be able to
*read* the disconfirming evidence, not be told that some exists. Unresolved ids
are still shown, flagged, so a dangling reference is visible rather than
silently dropped.

## Four bugs this phase found

Each would have shipped a wrong number or an unreadable UI:

1. **`limitations` serialised as a character array.** Grouping parentheses
   instead of a tuple meant `list(self.limitations)` split a sentence into one
   element per character — a 76-character limitation reached the UI as 76
   single-character strings. Found by a test asserting on *shape* rather than
   content.
2. **Regime laps vanished.** The regime analysis anchors on `transition_lap`;
   reading `lap_number` yields `None` and drops every change point.
3. **`UNMEASURED_INTERVAL` classified ENGINEERING.** A pit lap is a measurement
   gap, not a performance change. Inflated the material-event count by 10.
4. **The residual was anchored to a lap it does not belong to.** A residual is a
   whole-race quantity; it now carries an explicit note that it is not
   attributable to the lap it is displayed against.

A fifth was caught before shipping: the first decision-twin draft claimed
throttle and brake support. No lap-time model exists for either. Claiming them
would have meant inventing physics.

A sixth was found only by running the whole suite: extending the `INVESTIGATE`
rule across multiple adjacent raw-string literals produced a `||` between two
of them. An empty alternative in a regex matches *every* string, so
`detect_intents("banana")` returned `INVESTIGATE` and the closed vocabulary was
silently open. The fix cost 2 benchmark cases, which was the right price — two
`description` cases had been passing on the bogus match. Two genuine phrasings
("give me the story", "what did we learn") were then added to recover them
honestly. `test_no_intent_rule_contains_an_empty_alternative` now asserts the
*shape* of every rule so this cannot recur.

## Performance discipline

Importing the question engine at module scope regressed `import
racewise.api.app` from 1000 ms to 4455 ms. The engine is imported **inside route
handlers**, never at module scope; measured cost when actually imported is ~52
ms and stays off the boot path. The autopsy and decision twin are imported
lazily inside their handlers for the same reason.

## What is not built

Phases M–T of the brief remain open. Stating this plainly matters more than the
list of what works:

| not built | honest consequence |
| --- | --- |
| Cross-race precedent search | **0/8.** "Did this happen in another race?" is not answered. The planner selects cross-race capabilities but the compile status never reaches `PLANNED`. |
| Qualifying investigations | **0/5.** A separate code path the planner does not yet select capabilities for. |
| Compound decomposition reach | **3/14.** The DAG machinery works on resolvable input but compound phrasing as written does not reach it. |
| Structural engineering memory | Investigation memory exists; structural precedent retrieval over a case corpus does not. |
| Model-backed language understanding | Not started, and deliberately so. The measured bottleneck was question→pipeline, not language quality. Fine-tuning is **not** justified by current evidence. |

The benchmark is the argument for not fine-tuning: the failures are concentrated
in context resolution and decomposition — routing problems — not in parsing
prose. "Simulate removing the deficit" parsed fine once the rule existed.

## The loop

```
ASK → UNDERSTAND → RESOLVE → PLAN → INVESTIGATE → EXPLAIN → CHALLENGE
    → RECONCILE → WHAT REMAINS? → WHAT IF? → HAVE WE SEEN IT? → REMEMBER → REPLAY
```

The parts that work end-to-end today: ask, understand, resolve, plan,
investigate, explain, challenge, reconcile, "what remains", "what if".
The parts that do not yet: "have we seen it", "remember", and the full replay
surface across investigations.

## Related

- [`RACEWISE_QUESTION_ENGINE.md`](RACEWISE_QUESTION_ENGINE.md)
- [`RACEWISE_CAPABILITY_REGISTRY.md`](RACEWISE_CAPABILITY_REGISTRY.md)
- [`RACEWISE_INVESTIGATION_PLANNER.md`](RACEWISE_INVESTIGATION_PLANNER.md)
- [`RACEWISE_ENGINEERING_AUTOPSY.md`](RACEWISE_ENGINEERING_AUTOPSY.md)
- [`RACEWISE_DECISION_TWIN.md`](RACEWISE_DECISION_TWIN.md)
- [`RACEWISE_INTELLIGENCE_EVALUATION.md`](RACEWISE_INTELLIGENCE_EVALUATION.md)