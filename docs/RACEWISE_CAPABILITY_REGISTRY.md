# RACEWISE Capability Registry

A machine-readable description of every deterministic engineering capability
RACEWISE **actually has**. The question engine discovers capabilities from this
registry rather than hardcoding names.

## The rule that makes it worth having

> Every capability names a real deterministic tool and a real mounted HTTP
> route. This is enforced by tests, not by convention.

`tests/unit/test_question_engine.py` parses the tool sources and the API app and
asserts every `mcp_tool` exists in the `ToolRegistry` and every `api_route` is
mounted. A registry that drifts into documenting capabilities the product does
not have is worse than no registry, because the planner would promise evidence
no provider can supply.

Verified at the time of writing: **21 capabilities, 0 untrue claims**, against
45 registered tools and 39 mounted routes.

## Shape

```python
Capability(
    capability_id,          # stable, referenced by the planner
    name, description,
    mcp_tool,               # MUST exist in ToolRegistry
    api_route,              # MUST be mounted in the API app
    inputs, outputs,
    required_data,          # canonical facets; absence blocks the capability
    optional_data,          # absence degrades it honestly, never silently
    supported_session_types,
    supported_time_scopes,
    driver_relationships,
    prerequisites,          # enables composition
    limitations,            # what it cannot do — surfaced in every answer
    computational_cost,     # TRIVIAL | LOW | MODERATE | EXPENSIVE
    provenance_requirements,
    deterministic_version,
    evidence_types_produced,
    hypothesis_types_supported,
    intents,                # semantic intents it can serve
    analysis_levels,        # 0 context … 6 counterfactual
)
```

`required_data` and `optional_data` are the distinction that matters most. A
capability whose *required* facet is missing is `UNAVAILABLE` and is reported as
untestable. A capability whose *optional* facet is missing is `LIMITED`: it runs
degraded and says so. Collapsing the two is how a system either refuses to
answer a question it can partly answer, or claims a resolution it cannot
deliver.

## Registered capabilities

| capability | tool | cost | notes |
|---|---|---|---|
| `resolve_session_context` | `get_historical_session` | TRIVIAL | availability is record-count derived |
| `compare_laps` | `compare_driver_pace` | LOW | the observed delta everything else explains |
| `attribute_lap_loss` | `attribute_historical_lap_loss` | MODERATE | decomposition + residual; degrades without telemetry |
| `fuse_lap_evidence` | `fuse_historical_lap_evidence` | MODERATE | hypothesis verdicts, contradictions preserved |
| `analyze_stint` | `get_historical_stints` | LOW | measured degradation trend |
| `attribute_stint_loss` | `attribute_historical_stint_loss` | MODERATE | stint-level attribution |
| `decompose_race_gap` | `decompose_historical_race_gap` | MODERATE | race-scoped only |
| `analyze_performance_regimes` | `analyze_historical_performance_regimes` | MODERATE | race sessions only |
| `analyze_performance_envelope` | `analyze_historical_performance_envelope` | MODERATE | driver/car envelope |
| `simulate_telemetry_counterfactual` | `simulate_historical_telemetry_counterfactual` | EXPENSIVE | output is MODELLED, never truth |
| `analyze_cross_race_pattern` | `analyze_cross_race_performance_patterns` | EXPENSIVE | bounded season span |
| `evaluate_cross_race_hypotheses` | `analyze_cross_race_pattern_evidence` | EXPENSIVE | includes contradicting instances |
| `run_engineering_investigation` | `run_engineering_investigation` | EXPENSIVE | full deterministic lifecycle |
| `synthesize_investigation` | `verify_engineering_snapshot` | LOW | grounded conclusion |
| `build_investigation_graph` | `build_investigation_graph` | LOW | question → conclusion graph |
| `trace_evidence_source` | `trace_evidence_source` | TRIVIAL | the provenance primitive |
| `retrieve_memory` | `retrieve_engineering_memory` | LOW | structural precedent |
| `compare_investigations` | `compare_engineering_investigations` | LOW | structural comparison |
| `replay_investigation` | `replay_engineering_investigation` | MODERATE | determinism check |
| `inspect_race_control` | `get_historical_race_control` | TRIVIAL | unavailable pre-race-control era |
| `inspect_weather` | `get_historical_weather` | TRIVIAL | absence reported, never imputed |

## Coverage matrix

`GET /api/capabilities/coverage` returns, per intent: the capabilities that can
serve it, the data they require, the session types supported, the maximum
analysis level, and the limitations that apply. This is the planner's source of
truth, and it is what lets the planner promise only what is deliverable.

Intents are **semantic, not pages**. "Where did the time go" and "which sector
cost us most" are both `LOCATE`. Neither has a route.

## Adding a capability

1. implement the deterministic tool and register it
2. mount the API route if it needs one
3. add one `Capability` row
4. run the tests — the tool and route assertions will fail if either is missing

There is no step that lets the registry and the product disagree.