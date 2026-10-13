# RACEWISE Frontier Baseline Audit

**Date:** 2026-10-14
**Auditor:** Automated baseline audit
**Repository:** https://github.com/T-Bone47/RACEWISE
**Branch:** master
**Commit:** 098831a

---

## 1. Repository State

| Property | Value |
|---|---|
| Branch | master |
| Remote | https://github.com/T-Bone47/RACEWISE.git |
| Local commit | 098831a |
| Remote commit | 098831a |
| Working tree | clean |
| Total commits | 16 |
| Tracked files | ~350 |

## 2. Test Baseline

### Backend (Python)

| Suite | Result |
|---|---|
| tests/unit/test_question_engine.py | 50 passed, 2 skipped |
| tests/unit/test_simulator.py + test_analytics_reference.py | 12 passed |
| Full suite | Timed out at 120s (needs longer timeout) |

### Frontend (React/Vitest)

| Suite | Result |
|---|---|
| All 12 test files | **136 passed (136)** |
| Duration | 67.82s |

### Benchmark (from docs/EVALUATION.md, dated 2026-09-18)

| Metric | Value |
|---|---|
| Benchmark questions | 23 |
| Investigations COMPLETED | 23/23 (100%) |
| Falsification attempted | 23/23 (100%) |
| Counterfactual executed | 23/23 (100%) |
| All tool calls completed | 115/115 |
| Median latency | ~4.8s |

### Question Engine Benchmark (from docs/RACEWISE_INTELLIGENCE_EVALUATION.md)

| Metric | Value |
|---|---|
| Corpus size | 230 questions |
| Pass rate | 143/230 (62.2%) |
| Adversarial | 7/7 (100%) |
| Autopsy | 10/10 (100%) |
| Counterfactual | 12/12 (100%) |
| Cross-race | 0/8 (0%) |
| Qualifying | 0/5 (0%) |
| Compound | 3/14 (21.4%) |
| Stint | 0/1 (0%) |

## 3. Architecture Map

### Backend (Python/FastAPI)

| Module | Path | Status |
|---|---|---|
| Domain schemas | src/racewise/domain/schemas.py | Implemented |
| Data adapters | src/racewise/data/ | FastF1, F1DB, API-Sports, F1API, F1LivePulse |
| Historical pipeline | src/racewise/data/historical/ | Implemented (40+ modules) |
| Investigation engine | src/racewise/investigation/engine.py | Implemented |
| Question engine | src/racewise/question_engine/ | Implemented (12 modules) |
| Tools | src/racewise/tools/ | 45 registered tools |
| Simulator | src/racewise/simulator/strategy.py | Implemented |
| MCP server | src/racewise/mcp/server.py | Implemented |
| API | src/racewise/api/app.py | FastAPI + SSE, 39 routes |
| Agent provider | src/racewise/agent/provider.py | UnionAlphaProvider |
| Persistence | src/racewise/persistence/store.py | SQLite |

### Frontend (React/Vite)

| Module | Path | Status |
|---|---|---|
| App shell | App.tsx | Implemented |
| Command center | CommandCenterView.tsx | Implemented |
| Investigation workspace | InvestigationView.tsx | Implemented (flagship) |
| Falsification matrix | FalsificationMatrixView.tsx | Implemented |
| Counterfactual lab | CounterfactualView.tsx | Implemented |
| Evidence fusion | EvidenceFusionView.tsx | Implemented |
| Telemetry | TelemetryView.tsx | Implemented |
| Design system | App.css + design-system.css | Implemented |
| Motion system | motion.ts | Implemented |
| Command palette | CommandPalette.tsx | Implemented |

## 4. Capability Registry

21 registered capabilities, 0 untrue claims, against 45 registered tools and 39 mounted routes.

Key capabilities:
- resolve_session_context, compare_laps, attribute_lap_loss
- fuse_lap_evidence, analyze_stint, attribute_stint_loss
- decompose_race_gap, analyze_performance_regimes, analyze_performance_envelope
- simulate_telemetry_counterfactual, analyze_cross_race_pattern
- run_engineering_investigation, synthesize_investigation
- build_investigation_graph, trace_evidence_source
- retrieve_memory, compare_investigations, replay_investigation

## 5. Known Gaps (from documentation)

| Gap | Status | Impact |
|---|---|---|
| Cross-race precedent search | 0/8 | "Did this happen in another race?" not answered |
| Qualifying investigations | 0/5 | Separate code path not wired to planner |
| Compound decomposition | 3/14 | DAG machinery exists but not reached |
| Structural engineering memory | Not built | No precedent retrieval over case corpus |
| Model-backed language understanding | Not started | Deliberate — failures are routing, not parsing |
| LFI evidence_v1 integration | Not verified | Contract documented but runtime untested |
| F1 Pro Simulator integration | Not verified | No explicit interface exists |

## 6. Security Posture

| Item | Status |
|---|---|
| .env files | Properly gitignored |
| API keys in source | None found (all use env vars) |
| racewise.env | Contains real API keys, properly excluded |
| Input validation | Pydantic schemas |
| Tool sandboxing | Allow-listed tools |
| Rate limiting | Not implemented |
| Authentication | Not implemented (local tool) |

## 7. Frontend Bundle

| Metric | Value |
|---|---|
| Entry gzip | 123.3 kB |
| Target | ~100 kB (not met) |
| React DOM floor | ~220 kB minified |

## 8. Design System

- Token layer: App.css :root (pinned by design-system.test.ts)
- Component inventory: 25+ components mapped in RACEWISE_DESIGN_SYSTEM.md
- Motion system: motion.ts with 3-speed scale
- Accessibility: focus-visible, keyboard nav, reduced motion
- Responsive: 4 breakpoints (desktop, tablet, mobile, small mobile)

## 9. What Works Well

1. **Deterministic pipeline** — 23/23 investigations complete with falsification and counterfactual
2. **Question engine** — 230-question corpus with honest scoring
3. **Adversarial handling** — 7/7 adversarial cases pass
4. **Design system** — Comprehensive token layer with contract tests
5. **Frontend** — 136/136 tests pass, all views implemented
6. **Provenance** — Hash-chained executions, event log
7. **Honest degradation** — System reports UNAVAILABLE/INSUFFICIENT_EVIDENCE honestly

## 10. What Needs Improvement

1. **Question engine pass rate** — 62.2% is the honest baseline; cross-race, qualifying, compound, and stint categories are at or near zero
2. **Model integration** — UnionAlphaProvider implemented but unexercised (no credentials)
3. **LFI integration** — evidence_v1 contract documented but runtime untested
4. **Bundle size** — 123.3 kB gzip exceeds 100 kB target
5. **Test suite runtime** — Full backend suite times out at 120s
6. **Memory/precedent** — Structural precedent retrieval not built
7. **Rate limiting** — Not implemented
8. **Security** — No authentication/authorization for API access
