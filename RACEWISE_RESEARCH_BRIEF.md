# RACEWISE — Deep Research & Product Direction Brief

**Date:** 17 September 2026  
**Working title:** RACEWISE — Autonomous Evidence-Driven Race Engineering  
**Purpose:** Establish a genuinely new project that is not a reimplementation of Live F1 Intelligence or the F1 Lap-Time Simulator, and exploit the limited Union Alpha free window as a controlled agentic-AI engineering experiment.

## 1. Executive conclusion

RACEWISE should **not** be another telemetry dashboard, race narrator, strategy recommender, or simulator.

Its core problem is:

> Given an engineering question about a race, autonomously construct and test competing explanations using deterministic data tools and counterfactual experiments, then produce a traceable evidence-backed conclusion.

The differentiator is the **investigation loop**, not the LLM itself.

The system should behave more like a scientific investigator / race-engineering analyst:

1. Frame the question.
2. Generate explicit hypotheses.
3. Select the minimum useful evidence.
4. Call deterministic analysis tools.
5. Compare evidence against hypotheses.
6. Search for contradictory evidence.
7. Run counterfactual experiments where appropriate.
8. Update confidence.
9. Produce a causal/evidentiary report.
10. Preserve the complete investigation trace.

## 2. Union Alpha research

OpenRouter currently describes Union Alpha as a stealth multimodal model for research, coding and agentic workflows. It exposes a 262K-token context window, image input, tool calling and structured JSON output. It was released 16 September 2026 and is currently free. The provider is anonymous; OpenRouter says prompts/completions may be retained by the provider, though not used for training. Therefore RACEWISE should not send secrets, credentials or proprietary source material to the model.

Union Alpha's benchmark evidence is still immature. Its public benchmark page references Terminal-Bench v4.0 and warns that the model is stealth, the provider is anonymous, the model may change, and current pricing is anticipated rather than established. Independent reporting likewise notes the absence of a complete, reproducible suite of standard frontier benchmarks and mixed early reports about speed and long-running agent reliability.

**Decision:** Use Union Alpha as an experimental agent runtime, not as an unquestioned source of truth. The project must be useful even if the model is replaced.

## 3. Existing-project collision analysis

### Live F1 Intelligence

Primary question: **What is happening?**

Typical architecture:
`data ingestion -> normalization -> analytics -> real-time publication -> dashboard`

RACEWISE must not duplicate:
- live telemetry ingestion infrastructure
- timing dashboard surfaces
- WebSocket race feed
- basic sector/tyre visualizations
- generic live narration

RACEWISE may consume these capabilities through adapters.

### F1 Lap-Time Simulator

Primary question: **What happens under specified engineering parameters?**

Typical architecture:
`parameters -> vehicle/tyre/track model -> simulation -> result`

RACEWISE must not duplicate:
- vehicle physics model
- full lap-time simulation UI
- setup optimizer as the primary product

RACEWISE may call a simulator as a **counterfactual experiment tool**.

### RACEWISE

Primary question:
**Why did this happen, what competing explanations fit the evidence, and what intervention would change the outcome?**

Architecture:
`question -> hypotheses -> evidence plan -> tool calls -> falsification -> counterfactuals -> synthesis -> provenance`

## 4. Competitive / research landscape

The research scan shows that several adjacent ideas already exist:

- F1 StratLab targets AI strategy recommendations and has moved toward live-race inference.
- OpenF1ow provides transparent post-race analytics and LLM-generated race verdicts.
- Academic work has explored explainable tyre-energy prediction and counterfactual explanations.
- Recent research has explored automated hypothesis validation through sequential falsification.
- Recent Nature work such as Robin and Co-Scientist demonstrates a broader pattern: AI systems can iteratively generate hypotheses, use specialized tools/agents, analyze results, critique hypotheses, and refine conclusions.

This means a generic "AI race strategist" is not sufficiently differentiated.

The defensible novelty for a one-week portfolio build is to bring the **hypothesis → evidence → falsification → counterfactual → provenance** pattern into an F1 engineering environment, with deterministic analysis tools separating computation from language-model interpretation.

## 5. Data feasibility

OpenF1 provides historical F1 data from 2023 onward without authentication, including car data, laps, intervals, location, pit stops, position, race control, sessions, stints, weather and limited team radio. Real-time data requires a paid subscription. OpenF1 explicitly describes itself as independent and intended for educational, research and personal use.

FastF1 exposes session, timing, telemetry, results, circuit information and related APIs. It is a suitable historical-analysis adapter.

Important limitation: team-radio availability has decreased significantly in 2026 and is not guaranteed. RACEWISE must treat radio as optional evidence, never a required dependency.

## 6. Research-derived product principles

### Principle A — AI is the investigator, not the calculator

Numerical values must come from deterministic tools.

Bad:
`LLM: "Tyre degradation is 0.37 seconds/lap."`

Good:
`TyreAnalyzer -> 0.37 s/lap -> agent interprets significance.`

### Principle B — Every conclusion must be traceable

Every important claim should reference:
- data source
- query/tool
- analysis method/version
- time/lap window
- assumptions
- confidence
- contradictory evidence, if found

### Principle C — Falsification is a first-class action

The agent must be able to ask:
`What evidence would make my current hypothesis wrong?`

It should actively search for that evidence before finalizing a strong conclusion.

### Principle D — Counterfactuals must be simulations, not prose

"What if we pitted five laps earlier?" must call a deterministic scenario engine.

### Principle E — Preserve uncertainty

The system must distinguish:
- observed fact
- calculated metric
- inferred explanation
- counterfactual estimate
- model assumption

### Principle F — Model-agnostic core

The investigation engine must expose a provider interface so Union Alpha can be replaced by another model without changing domain logic.

## 7. Proposed core innovation

### Evidence-backed Investigation Graph

Each investigation becomes a graph:

`Question -> Hypothesis -> Evidence Request -> Tool Execution -> Observation -> Test -> Counter-evidence -> Updated Hypothesis -> Counterfactual -> Conclusion`

The UI can show this graph as a replayable investigation trace.

### Example

Question:
"Why did Driver X lose 0.8s/lap in the second stint?"

Hypotheses:
- tyre degradation
- traffic
- fuel/load effect
- weather
- driver management
- car performance
- strategy

The agent gathers evidence, rejects weak explanations, tests alternatives, and only then synthesizes a conclusion.

## 8. One-week feasibility

Scope is intentionally constrained to a vertical slice:

- 1–3 historical races
- 1 primary OpenF1 adapter
- 8–12 deterministic analysis tools
- 1 simplified counterfactual strategy engine
- 1 Union Alpha agent
- 1 investigation graph
- 1 evidence/provenance layer
- polished React UI
- evaluation suite of 15–20 investigation questions

Do not build a new live timing system, full F1 simulator, multi-season ML platform or production-grade authentication system during the one-week sprint.

## 9. Portfolio value

The project demonstrates:
- agentic architecture
- tool calling
- long-context reasoning
- multimodal analysis
- deterministic analytics
- causal reasoning discipline
- counterfactual simulation
- provenance
- evaluation
- F1 domain expertise
- full-stack engineering

The strongest portfolio claim is not "I used Union Alpha."

It is:

> "I built an evidence-driven autonomous investigation system in which an AI agent forms and falsifies engineering hypotheses using deterministic motorsport analysis tools and counterfactual simulation."

## 10. Sources

- OpenRouter — Union Alpha: https://openrouter.ai/stealth/union-alpha/
- Union Alpha benchmark page: https://unionalpha.io/benchmarks.html
- Union Alpha usage / OpenCode: https://unionalpha.io/how-to-use-union-alpha.html
- OpenF1 documentation: https://openf1.org/docs/
- OpenF1: https://openf1.org/
- FastF1 API reference: https://github.com/theOehrly/Fast-F1
- Automated Hypothesis Validation / POPPER: https://proceedings.mlr.press/v267n.html
- Nature — Robin: https://www.nature.com/articles/s41586-026-10652-y
- Nature — Co-Scientist: https://www.nature.com/articles/s41586-026-10644-y
- Explainable F1 tyre-energy prediction: https://arxiv.org/abs/2501.04067
- F1 tyre degradation state-space modeling: https://journals.sagepub.com/doi/10.1177/22150218261446170
- Pitwall race-strategy grounding research: https://arxiv.org/abs/2607.06495
- F1 StratLab: https://f1stratlab.com/
