# RACEWISE — System Architecture

**Version:** 0.1.0  
**Date:** 17 September 2026  
**Architecture principle:** AI orchestrates investigation; deterministic software owns computation.

## 1. System overview

```text
                         ┌─────────────────────┐
                         │       React UI       │
                         │ Investigation Workbench│
                         └──────────┬──────────┘
                                    │
                              REST / SSE
                                    │
                         ┌──────────▼──────────┐
                         │      FastAPI API     │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼────────────────┐
                    │               │                │
                    ▼               ▼                ▼
             Investigation      Evidence        Scenario
              Orchestrator       Store           Engine
                    │               │                │
                    │               │                │
                    └───────────────┼────────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   Agent Runtime      │
                         │ Union Alpha Adapter  │
                         └──────────┬──────────┘
                                    │
                              Tool Calls
                                    │
          ┌─────────────────────────┼──────────────────────────┐
          │                         │                          │
          ▼                         ▼                          ▼
   OpenF1/FastF1               Analytics Tools          Counterfactual
      Adapters                  Deterministic              Simulator
          │                         │                          │
          └─────────────────────────┼──────────────────────────┘
                                    │
                              Evidence Nodes
                                    │
                         ┌──────────▼──────────┐
                         │ Provenance / Replay │
                         └─────────────────────┘
```

## 2. Architectural separation

### Layer 1 — Data

Responsibilities:
- fetch historical session data
- cache raw responses
- normalize into canonical internal schemas

Adapters:
- OpenF1
- FastF1

The application must never expose provider-specific JSON directly to the agent.

## 3. Canonical domain model

### Session
```python
Session(
    session_id,
    meeting_id,
    event_name,
    session_type,
    date,
    circuit
)
```

### Lap
```python
Lap(
    session_id,
    driver_id,
    lap_number,
    lap_time,
    sector_1,
    sector_2,
    sector_3,
    compound,
    tyre_age,
    pit_in,
    pit_out,
    is_valid
)
```

### Observation
```python
Observation(
    id,
    metric,
    value,
    unit,
    time_window,
    source,
    method_version
)
```

### Hypothesis
```python
Hypothesis(
    id,
    statement,
    predicted_observables,
    falsifiers,
    status,
    confidence
)
```

### Evidence
```python
Evidence(
    id,
    type,
    observation_ids,
    tool_execution_id,
    supports,
    contradicts,
    strength
)
```

### Counterfactual
```python
Counterfactual(
    baseline_id,
    intervention,
    assumptions,
    predicted_delta,
    uncertainty,
    simulator_version
)
```

### Conclusion
```python
Conclusion(
    statement,
    confidence,
    evidence_ids,
    counterfactual_ids,
    limitations
)
```

## 4. Investigation state machine

```text
CREATED
  │
  ▼
FRAMING
  │
  ▼
HYPOTHESIS_GENERATION
  │
  ▼
EVIDENCE_PLANNING
  │
  ▼
EVIDENCE_COLLECTION
  │
  ▼
HYPOTHESIS_TESTING
  │
  ├───────────────┐
  │               │
  ▼               ▼
FALSIFICATION   MORE_DATA
  │               │
  └───────┬───────┘
          ▼
COUNTERFACTUAL_ANALYSIS
          │
          ▼
SYNTHESIS
          │
          ▼
VERIFICATION
          │
          ▼
COMPLETED
```

Failure states:
- `DATA_UNAVAILABLE`
- `TOOL_FAILURE`
- `MODEL_FAILURE`
- `INSUFFICIENT_EVIDENCE`

## 5. Agent architecture

The MVP uses one model with role-structured prompts rather than a swarm of independent LLMs.

### Agent roles

#### Supervisor
Frames the question and controls the investigation state.

#### Hypothesis planner
Produces competing explanations and falsifiers.

#### Evidence planner
Selects tools.

#### Investigator
Interprets tool results.

#### Falsifier
Attempts to disprove the leading explanation.

#### Synthesizer
Produces the final report.

These can be implemented as prompt phases over one Union Alpha session initially. The architecture must permit splitting them into separate agents later.

## 6. Tool contract

Every tool must implement:

```python
Tool(
    name,
    description,
    input_schema,
    output_schema,
    version,
    execute()
)
```

Example:

```python
analyze_tyre_degradation(
    session_id,
    driver_id,
    stint_id,
    clean_lap_policy
) -> TyreDegradationResult
```

The agent receives:
- what the tool does
- accepted parameters
- expected output
- known limitations

The agent does NOT receive arbitrary database access.

## 7. Core tool catalogue

### Data
- `get_session`
- `get_driver`
- `get_laps`
- `get_stints`
- `get_weather`
- `get_race_control`
- `get_pit_stops`
- `get_team_radio`

### Analysis
- `filter_clean_laps`
- `compare_sectors`
- `analyze_tyre_degradation`
- `analyze_traffic`
- `analyze_pit_loss`
- `compare_driver_pace`
- `correlate_weather`
- `detect_pace_anomaly`

### Counterfactual
- `simulate_pit_timing`
- `simulate_compound_change`
- `compare_strategy_scenarios`

## 8. Evidence model

The system must distinguish four evidence classes:

### FACT
Directly retrieved from a source.

### CALCULATION
Computed deterministically from facts.

### INFERENCE
Agent interpretation supported by evidence.

### COUNTERFACTUAL
Model/simulator output under explicit assumptions.

UI must use distinct labels for these classes.

## 9. Falsification engine

Pseudo-flow:

```python
leading = select_leading_hypothesis(hypotheses)

tests = generate_falsification_tests(
    hypothesis=leading,
    evidence=current_evidence
)

for test in tests:
    result = execute(test)
    update_hypothesis(leading, result)

if contradictory_evidence_is_material():
    downgrade_confidence()
```

The system should prefer tests that can materially distinguish between competing hypotheses.

## 10. Counterfactual engine

The simulator is intentionally simpler than the existing F1 Lap-Time Simulator.

Inputs:
- observed race state
- intervention
- tyre assumptions
- pit loss
- traffic assumptions
- remaining laps

Outputs:
- predicted time delta
- position implications where model permits
- uncertainty
- assumptions
- simulation version

It must not pretend to reproduce an actual team's race simulator.

## 11. Provenance architecture

```text
Claim
 │
 ├── Evidence
 │    ├── Observation
 │    ├── Tool Execution
 │    └── Source Record
 │
 ├── Method Version
 ├── Model Version
 └── Investigation ID
```

Every final claim should be reconstructible.

### Event log

```json
{
  "event_id": "...",
  "investigation_id": "...",
  "type": "tool_execution",
  "tool": "analyze_tyre_degradation",
  "version": "1.0.0",
  "input_hash": "...",
  "output_hash": "...",
  "timestamp": "..."
}
```

## 12. Storage

MVP:
- SQLite for local development
- PostgreSQL for deployment
- object storage optional for generated plots/reports

Tables:
- investigations
- hypotheses
- evidence
- observations
- tool_executions
- counterfactuals
- conclusions
- event_log
- datasets

## 13. API

### POST
`/api/investigations`

Creates an investigation.

### GET
`/api/investigations/{id}`

Returns current state.

### GET
`/api/investigations/{id}/events`

Returns replayable event stream.

### POST
`/api/investigations/{id}/challenge`

Starts falsification.

### POST
`/api/investigations/{id}/counterfactual`

Runs a scenario.

### GET
`/api/investigations/{id}/report`

Returns final report.

### GET
`/api/sessions`

Lists supported sessions.

## 14. Streaming

Use Server-Sent Events for MVP:

```text
investigation.started
hypothesis.created
tool.started
tool.completed
evidence.added
hypothesis.updated
falsification.started
counterfactual.started
counterfactual.completed
synthesis.started
investigation.completed
```

WebSockets are unnecessary for the first vertical slice.

## 15. Model abstraction

```python
class ModelProvider(Protocol):
    def respond(self, messages, tools, response_format=None):
        ...

class UnionAlphaProvider(ModelProvider):
    ...

class FutureProvider(ModelProvider):
    ...
```

Union Alpha is configured externally:

```text
MODEL_PROVIDER=union_alpha
MODEL_ID=stealth/union-alpha
```

No domain logic may depend on the model name.

## 16. Prompt architecture

System prompt sections:
1. role
2. domain rules
3. evidence taxonomy
4. tool policy
5. hypothesis policy
6. falsification requirement
7. uncertainty rules
8. provenance rules
9. output schema

Hard rule:

> Never invent a numerical measurement when a deterministic tool can calculate it.

## 17. Model context strategy

Because Union Alpha supports 262K context, the system may maintain a rich investigation context. However, the application should not dump every dataset row into the prompt.

Use:
- compact evidence summaries
- selected observations
- tool outputs
- references to cached raw data
- progressive context construction

This improves latency and reduces irrelevant context.

## 18. Multimodal strategy

The backend can generate:
- lap-time traces
- sector deltas
- tyre degradation plots
- position timelines
- strategy timelines

The agent may receive selected plots as images for visual cross-checking.

Images are secondary evidence. Numeric truth remains in deterministic outputs.

## 19. Evaluation architecture

```text
Benchmark Question
       │
       ▼
RACEWISE Agent
       │
       ├── tool trace
       ├── evidence graph
       └── final report
       │
       ▼
Evaluation Harness
       │
       ├── numerical correctness
       ├── evidence coverage
       ├── hypothesis quality
       ├── falsification
       ├── hallucination
       └── reproducibility
```

Maintain a gold/reference answer for each benchmark question.

## 20. Security and privacy

- no secrets in model context
- environment variables for credentials
- tool sandboxing
- allow-listed tools
- read-only data tools
- counterfactual simulator isolated from external side effects
- prompt injection defenses for external text
- investigation logs sanitized before public demo

Union Alpha's current provider is anonymous; use only non-sensitive research data during the free experiment.

## 21. Repository structure

```text
racewise/
├── apps/
│   ├── api/
│   └── web/
├── packages/
│   ├── domain/
│   ├── data/
│   ├── analytics/
│   ├── investigation/
│   ├── agent/
│   ├── simulator/
│   ├── provenance/
│   └── evaluation/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── benchmark/
├── datasets/
│   └── fixtures/
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   └── RESEARCH_BRIEF.md
├── scripts/
├── docker/
├── .env.example
└── README.md
```

## 22. Deployment

MVP target:
- React/Vite frontend
- FastAPI backend
- PostgreSQL
- containerized deployment
- SSE streaming

Optional:
- Vercel frontend
- managed Postgres
- container host for API

## 23. Architectural boundary with previous projects

RACEWISE may import existing capabilities only through adapters/interfaces.

It must not copy:
- Live F1 Intelligence's real-time publication layer
- RaceMind's complete ingestion architecture
- F1 Lap-Time Simulator's full physics engine

Instead:
- `F1DataAdapter` consumes data
- `SimulatorAdapter` exposes counterfactual capability
- `InvestigationEngine` is the new core IP

## 24. Future evolution

After MVP:
1. multi-model evaluation
2. richer causal models
3. probabilistic strategy simulation
4. multi-agent debate
5. cross-race knowledge base
6. automated research notebooks
7. uncertainty calibration
8. driver/team-specific engineering profiles

The one-week version must remain focused on the investigation loop.
