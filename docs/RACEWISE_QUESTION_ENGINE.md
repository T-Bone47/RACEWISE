# RACEWISE Question Engine

The general engineering question engine: free text in, a bounded, evidence-grounded
investigation out.

It does **not** replace the deterministic engine. It sits above it and decides
what to ask of it.

```
user language
     ↓
[ compiler ]     language → structured engineering question   (deterministic)
     ↓
[ decomposer ]   compound question → sub-question DAG          (deterministic)
     ↓
[ planner ]      capabilities → availability → evidence plan   (deterministic)
     ↓
[ deterministic engine ]   ← the only thing that computes numbers
     ↓
[ synthesizer ]  structured partial answer grounded in results (deterministic)
     ↓
[ verification ] every claim traceable, checked unconditionally (deterministic)
```

## Why the model is absent from this diagram

The architecture allows a language model at exactly one boundary — turning prose
into the compiler's schema. It is not required, and nothing in the measured path
uses it. With no provider configured the deterministic compiler handles the
supported vocabulary and the system stays honest.

This is deliberate. A model that can be asked "interpret this" is one step from
a model that can be asked "interpret this number", and the second version is a
fabrication engine. Keeping interpretation in closed, testable rules removes an
entire class of failure, and the benchmark in
[`RACEWISE_INTELLIGENCE_EVALUATION.md`](RACEWISE_INTELLIGENCE_EVALUATION.md)
shows where those rules currently fail so the next increment is informed rather
than speculative.

`LanguageModelProvider` abstraction (§54) and a structured-output schema (§55)
remain the extension point; `MODEL_FAILURE` is a declared terminal state.

## The compiler

`compile_question()` produces a canonical `CompiledQuestion`:

| field | meaning |
|---|---|
| `detected_intents` | semantic intents, closed vocabulary, first-match order |
| `spatial_scopes` / `sectors` / `corners` | finest resolution the user asked for |
| `temporal_scopes` | lap / stint / regime / race-control transition / cross-race |
| `comparatives`, `negations`, `causal_claims` | comparative language; negation; causal framing |
| `requested_hypotheses` | named hypotheses (a subset request, never a verdict) |
| `unsupported_terms` | domain terms with no deterministic capability behind them |
| `clarifications` | the minimum questions blocking investigation |

Uncertainty is never a score. It either resolves deterministically or becomes a
clarification request. There is no third option.

### Context resolution by participation

`question_intake` requires an explicit race. That is right for the first
question of a session and wrong for the common case of naming a season and a
driver pair, so the compiler adds one deterministic rule:

> If both drivers are resolved and the season is known, and the pair shares
> **exactly one** race in that season, that race is the scope.

A unique candidate is a fact, not a guess. With 22 shared races the rule does
not fire and the compiler asks, listing candidates. Both paths are tested.

### Causal language is quarantined

"Did tyres cause the loss?" and "can you prove DRS caused it?" are detected as
causal claims and translated into testable sub-questions. The user's premise is
never accepted by default, and no confidence percentage is ever produced.

## Decomposition

One sentence is frequently several questions. `decompose()` splits on clause
boundaries and emits a **topologically ordered DAG**, because the order is
engineering rather than cosmetic: you cannot attribute a deficit you have not
measured.

Three nodes are injected when the text implies them:

- **Q0 — the observed difference.** Any attribution presupposes a measurement.
- **Q_RESIDUAL — what remains unexplained.** An explanation that omits its own
  remainder is not an explanation.
- **Q_HYPOTHESES** — only when the user named specific hypotheses, and framed
  as falsification when the question was negated.

Analysis depth is chosen as the *minimum sufficient* level (§24). Level 6
counterfactuals are expensive and easily misread, so they are reserved for an
explicit request.

## Partial answers

When a question is only partly answerable the output is not "cannot answer":

```
what we can establish
what we cannot establish
why
available evidence
missing evidence
```

Refusing wholesale would discard real, correct findings, which is its own kind
of dishonesty. Throwing away a measured 0.732 s deficit because DRS telemetry
was missing is as dishonest as inventing the DRS telemetry.

## Verification

`verify_answer()` runs unconditionally before an answer is presented:

- every numeric claim has a producing capability that actually executed
- no claim cites a capability absent from the results
- counterfactuals stay `MODELLED` and never claim historical truth
- residuals are reported, never assigned to a mechanism
- provenance names only capabilities that ran
- follow-up suggestions all name a real capability

Tests deliberately construct phantom capabilities, promoted counterfactuals and
assigned residuals and assert verification catches each one.

## What was fixed to make this work

Two real defects were found and fixed in the existing intake, both on the most
canonical path in the product:

1. **Accented names never cleared the text.** `sergio-perez` is canonical as
   `Pérez`; users type `Perez`. Matching was accent-insensitive but removal used
   the accented label against ASCII text, so the leftover was re-read as a place
   name and race resolution failed. *G001 — "Why did Verstappen lose time to
   Perez on lap 6 in 2023?" — could not resolve.*

2. **Job titles resolved to real people.** The canonical store contains a driver
   whose family name is *Driver*, so "Test Driver" silently resolved to a
   different actual person — a substitution, which the resolution contract
   forbids. Driver *title* words are now excluded.

Both are covered by regression tests.

## Related

- [`RACEWISE_CAPABILITY_REGISTRY.md`](RACEWISE_CAPABILITY_REGISTRY.md)
- [`RACEWISE_INVESTIGATION_PLANNER.md`](RACEWISE_INVESTIGATION_PLANNER.md)
- [`RACEWISE_INTELLIGENCE_EVALUATION.md`](RACEWISE_INTELLIGENCE_EVALUATION.md)
- [`AUTONOMOUS_ENGINEERING_INTELLIGENCE.md`](AUTONOMOUS_ENGINEERING_INTELLIGENCE.md)