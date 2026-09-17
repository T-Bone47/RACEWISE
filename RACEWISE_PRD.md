# RACEWISE — Product Requirements Document

**Version:** 0.1.0  
**Date:** 17 September 2026  
**Status:** Development-ready MVP specification

## 1. Product definition

**RACEWISE (Autonomous Evidence-Driven Race Engineering)** is an AI-assisted investigation platform for Formula 1 engineering questions.

RACEWISE does not primarily tell the user what happened. It investigates **why** an observed outcome occurred and tests alternative explanations.

### Product promise

> Ask a race-engineering question. RACEWISE constructs hypotheses, gathers evidence through deterministic tools, attempts to falsify its own explanations, runs counterfactual scenarios, and produces a traceable engineering report.

## 2. Problem

F1 analytics systems commonly expose metrics and visualizations. Strategy systems can recommend actions. Simulators can estimate outcomes.

The missing portfolio-scale interaction is an integrated loop that connects:
- an open-ended engineering question
- explicit competing hypotheses
- evidence retrieval
- deterministic analysis
- falsification
- counterfactual experimentation
- uncertainty
- provenance

RACEWISE fills that gap as an experimental research/engineering system.

## 3. Target users

### Primary
- Motorsport engineering students
- Performance-engineering enthusiasts
- Data scientists
- AI/agent researchers
- F1 analysts

### Secondary
- Recruiters and technical interviewers evaluating engineering/AI portfolios
- Researchers exploring agentic decision-support systems

## 4. MVP user journeys

### Journey A — Explain an anomaly

Input:
"Why did Driver 16 lose pace from laps 28–36?"

System:
1. creates hypotheses
2. selects evidence
3. calls analysis tools
4. evaluates evidence
5. runs contradiction checks
6. produces conclusion and uncertainty

### Journey B — Challenge a conclusion

User clicks `Challenge conclusion`.

System:
1. extracts current claims
2. generates falsification tests
3. searches for contradictory evidence
4. revises confidence
5. displays what changed

### Journey C — Counterfactual strategy

User asks:
"What if the pit stop happened 5 laps earlier?"

System:
1. freezes observed state
2. calls strategy simulator
3. compares baseline vs counterfactual
4. reports estimated delta and assumptions

### Journey D — Compare drivers

Question:
"Was Driver A genuinely slower, or did traffic explain the gap?"

System compares matched/clean laps and separates observed pace from contextual effects.

## 5. Functional requirements

### FR-01 Investigation creation
The system shall accept a natural-language engineering question plus race/session/driver context.

### FR-02 Hypothesis generation
The agent shall generate multiple plausible hypotheses with measurable predictions.

Each hypothesis must contain:
- id
- statement
- predicted observable
- required evidence
- potential falsifier

### FR-03 Evidence planning
The agent shall select tools based on information value rather than blindly calling every endpoint.

### FR-04 Deterministic tools
All quantitative calculations shall be performed by versioned Python services/functions.

Initial tools:
- session metadata
- lap extraction
- clean-lap filtering
- sector comparison
- stint comparison
- tyre-age degradation
- traffic exposure
- pit-loss analysis
- weather correlation
- race-control event correlation
- driver comparison
- strategy counterfactual

### FR-05 Tool execution trace
Every tool call shall record:
- tool name/version
- parameters
- timestamp
- result hash
- execution status

### FR-06 Hypothesis evaluation
Each hypothesis shall receive:
- supporting evidence
- contradictory evidence
- unresolved evidence
- confidence
- status: supported / weakened / unresolved / rejected

### FR-07 Falsification
The agent shall explicitly attempt to find evidence that could invalidate its leading hypothesis.

### FR-08 Counterfactual simulation
The system shall support at least:
- earlier pit
- later pit
- compound change

The simulator must expose assumptions and uncertainty.

### FR-09 Provenance
Every final claim shall link to evidence nodes.

### FR-10 Final report
Reports shall contain:
1. question
2. observed facts
3. hypotheses considered
4. evidence
5. contradictions
6. counterfactuals
7. conclusion
8. confidence
9. limitations
10. reproducibility metadata

### FR-11 Investigation replay
A completed investigation shall be replayable from its event log.

### FR-12 Model abstraction
Union Alpha shall be one provider implementation, not a hard-coded architectural dependency.

### FR-13 Image evidence
The agent may inspect generated telemetry/strategy plots and use them as secondary evidence.

## 6. Non-functional requirements

### Reliability
- deterministic tool outputs
- schema validation
- retries
- idempotent tool execution

### Explainability
No high-level conclusion without evidence references.

### Safety / trust
The UI must visually distinguish:
`FACT`, `CALCULATION`, `INFERENCE`, `COUNTERFACTUAL`, `ASSUMPTION`.

### Performance
MVP target:
- initial question acknowledgement < 2 s
- tool calls streamed progressively
- investigation visible incrementally
- no blocking requirement for model completion

### Reproducibility
Each investigation stores:
- data source version
- model identifier
- prompt version
- tool versions
- configuration
- random seeds where applicable

## 7. UI requirements

### Screen 1 — Investigation Workspace
- race/session selector
- driver selector
- question input
- investigation status
- live agent trace

### Screen 2 — Hypothesis Board
Cards for each hypothesis:
- claim
- evidence score
- confidence
- supporting evidence
- contradictory evidence
- status

### Screen 3 — Evidence Graph
Interactive graph:
`Question -> Hypothesis -> Evidence -> Test -> Result -> Conclusion`

### Screen 4 — Counterfactual Lab
Baseline and scenario comparison:
- pit lap
- compound
- predicted pace
- predicted race delta
- assumptions

### Screen 5 — Engineering Report
A clean report suitable for export/share.

## 8. Evaluation requirements

Build a fixed benchmark set of 15–20 questions.

Categories:
- tyre degradation
- traffic
- strategy
- weather
- driver comparison
- pit timing
- anomalous pace
- safety-car effects
- counterfactuals

Score:
- factual accuracy
- numerical accuracy
- tool-selection efficiency
- evidence coverage
- contradiction detection
- hallucination rate
- conclusion calibration
- reproducibility
- latency

Do not claim Union Alpha is superior to other models unless the experiment actually demonstrates it.

## 9. Explicit non-goals

MVP will NOT include:
- licensed F1 live data
- a full race broadcast product
- a replacement for Live F1 Intelligence
- a replacement for the F1 simulator
- autonomous real-world race control
- production financial/payment systems
- full multi-team race strategy optimization
- unrestricted web browsing by the agent
- unverified LLM-generated numerical calculations

## 10. Definition of done

MVP is complete when:

- one historical race can be investigated end-to-end
- at least 8 deterministic tools work
- agent can generate and evaluate ≥3 hypotheses
- agent performs at least one explicit falsification step
- one counterfactual strategy scenario executes deterministically
- every final conclusion has provenance
- investigation can be replayed
- 15–20 benchmark questions are scored
- polished web UI is deployable
- README contains architecture, limitations and evaluation results

## 11. Seven-day plan

### Day 1
Repo, schemas, OpenF1 adapter, storage, model provider abstraction.

### Day 2
Deterministic analysis tools and evidence model.

### Day 3
Investigation orchestrator, hypothesis schema, tool calling, Union Alpha integration.

### Day 4
Falsification loop + counterfactual strategy engine.

### Day 5
React investigation workspace + evidence graph + trace.

### Day 6
Evaluation harness + report export + robustness fixes.

### Day 7
UI polish, deployment, documentation, benchmark, demo recording.

## 12. Portfolio deliverables

- deployed web application
- GitHub repository
- architecture diagram
- PRD
- benchmark report
- investigation examples
- 2–3 minute demo
- technical write-up
- reproducibility manifest

## 13. Success metrics

The MVP succeeds if:
- ≥90% of deterministic numerical outputs match reference calculations
- ≥90% of final factual claims have evidence links
- falsification is attempted on ≥95% of eligible investigations
- ≥80% of benchmark investigations reach a defensible conclusion
- replay produces equivalent deterministic tool outputs
- model can be swapped without domain-code changes
