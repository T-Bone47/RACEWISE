# RACEWISE Frontier Release Gates

**Date:** 2026-10-14
**Version:** 1.0

---

## Purpose

These gates define the minimum quality bar that must be met before any release. They are not aspirational targets — they are hard requirements. A release that fails any gate is not released.

## Gate 1: Repository Integrity

| Check | Criteria | Verification |
|---|---|---|
| Working tree | Clean (no uncommitted changes) | `git status --short` |
| Branch sync | Local matches remote | `git log --oneline -1` matches remote |
| No secrets | No API keys, tokens, passwords in tracked files | `git grep -i "api_key\|secret\|token\|password"` |
| .gitignore | Properly excludes .env, caches, binaries | `git check-ignore` for each pattern |

## Gate 2: Build & Type Safety

| Check | Criteria | Verification |
|---|---|---|
| Python build | Package installs without error | `pip install -e .` |
| TypeScript build | No type errors | `cd apps/web && npx tsc -b` |
| Frontend build | Production build succeeds | `cd apps/web && npm run build` |
| Lint | No lint errors | `cd apps/web && npm run lint` |

## Gate 3: Test Suite

| Check | Criteria | Verification |
|---|---|---|
| Backend unit tests | All pass | `python -m pytest tests/unit/ -q` |
| Backend integration tests | All pass | `python -m pytest tests/integration/ -q` |
| Frontend tests | All pass | `cd apps/web && npx vitest run` |
| Design system tests | All pass | Included in frontend tests |
| No skipped tests | 0 skipped (or documented why) | Check test output |

## Gate 4: Benchmark Regression

| Check | Criteria | Verification |
|---|---|---|
| Investigation completion | ≥ 95% (baseline: 100%) | `python tests/benchmark/run_benchmark.py` |
| Falsification rate | ≥ 95% (baseline: 100%) | Benchmark output |
| Counterfactual rate | ≥ 95% (baseline: 100%) | Benchmark output |
| Tool call success | ≥ 95% (baseline: 100%) | Benchmark output |
| Question engine pass rate | ≥ baseline (62.2%) | `python -m pytest tests/benchmark/ -q` |
| No new failures | No category regresses > 5% | Compare before/after |

## Gate 5: Deterministic Correctness

| Check | Criteria | Verification |
|---|---|---|
| Numerical regression | No change in deterministic outputs | Compare tool output hashes |
| Schema validation | All outputs validate against schemas | Pydantic validation |
| Provenance | All claims traceable | Verification engine |
| No fabrication | Zero unsupported claims | Adversarial tests |

## Gate 6: Security

| Check | Criteria | Verification |
|---|---|---|
| Input validation | All inputs validated | Pydantic schemas |
| Tool sandboxing | Only allow-listed tools execute | Tool registry |
| No injection | No SQL/code injection vectors | Code review |
| Secret management | No secrets in code or logs | `git grep` + code review |
| Rate limiting | API has rate limits | Configured and tested |
| Error messages | No internal details leaked | Error handling review |

## Gate 7: API Contracts

| Check | Criteria | Verification |
|---|---|---|
| Schema compatibility | No breaking changes | API contract tests |
| Route availability | All registered routes mounted | Route assertion tests |
| Capability registry | All capabilities map to working tools | Registry tests |
| Error responses | Structured, informative errors | Error handling tests |

## Gate 8: Frontend Quality

| Check | Criteria | Verification |
|---|---|---|
| No dead controls | Every control has real behavior | Manual + automated review |
| Loading states | All async surfaces have loading states | Component tests |
| Error states | All async surfaces have error states | Component tests |
| Empty states | All views have empty states | Component tests |
| Keyboard accessibility | Full keyboard navigation | Manual + automated review |
| Focus visibility | Visible focus states | CSS review |
| Reduced motion | Respects prefers-reduced-motion | CSS + motion tests |
| Responsive | Works at desktop, tablet, mobile | Viewport tests |
| Console errors | No console errors on load | Browser tests |

## Gate 9: Documentation

| Check | Criteria | Verification |
|---|---|---|
| README | Accurate and current | Review |
| Architecture | Matches implementation | Review |
| API docs | All routes documented | Review |
| Design system | Matches implementation | Design system tests |
| Known limitations | Honestly documented | Review |
| Evaluation results | Current and reproducible | Re-run and verify |

## Gate 10: Performance

| Check | Criteria | Baseline | Target |
|---|---|---|---|
| Investigation latency | Median end-to-end | ~4.8s | ≤ 5s |
| Frontend bundle | Gzip size | 123.3 kB | ≤ 100 kB |
| Test suite runtime | Full backend suite | >120s | ≤ 120s |
| API response time | p95 | Not measured | ≤ 500ms |

## Gate 11: Integration

| Check | Criteria | Verification |
|---|---|---|
| LFI evidence_v1 | Contract compliance tested | Integration tests |
| F1 Pro Simulator | Interface verified (if integrated) | Contract tests |
| Data providers | All adapters functional | Adapter tests |
| Persistence | Data survives restart | Persistence tests |

## Gate 12: Honesty

| Check | Criteria | Verification |
|---|---|---|
| No fake data | No hardcoded values presented as real | Code review |
| No fake progress | No simulated progress indicators | Code review |
| No fake AI | No simulated AI reasoning | Code review |
| Honest degradation | System reports unavailable honestly | Component tests |
| No overstated confidence | Confidence language is appropriate | Review |

---

## Release Checklist

Before tagging a release:

- [ ] All 12 gates pass
- [ ] Benchmark results recorded and compared to baseline
- [ ] Full test suite passes
- [ ] Documentation updated
- [ ] Known limitations documented
- [ ] Security review complete
- [ ] Performance targets met or documented as blockers
- [ ] No secrets in repository
- [ ] Working tree clean
- [ ] Local and remote branches synchronized

## Gate Failure Handling

If any gate fails:
1. **Stop** — do not release
2. **Investigate** — find the root cause
3. **Fix** — address the issue
4. **Re-verify** — run the failed gate again
5. **Document** — record the failure and fix

Do not:
- Weaken assertions to pass
- Skip tests
- Hide failures
- Release with known critical issues
