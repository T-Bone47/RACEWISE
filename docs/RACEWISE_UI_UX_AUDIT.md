# RACEWISE UI/UX Audit — Research Response & Before/After Verification

**Round 2 audit** (research-report driven, applied on the workstation from commit `8294b28`).
**Round 1 audit:** `docs/UX_AUDIT_RACEWISE.md` (17 audited problems → fixes, all shipped).
**Product truth:** `PRODUCT.md` · **Visual authority:** `DESIGN.md` ·
**Component contract:** `docs/RACEWISE_DESIGN_SYSTEM.md` ·
**Workspace composition:** `docs/RACEWISE_WORKSPACE_ARCHITECTURE.md`.

---

## 1. Research findings → response

| Research finding | Response (round 2) | Status |
|---|---|---|
| "Very dense and card-heavy; multiple panels with equal visual weight" | Workstation stage gating (round 1) already removed the scroll-wall; round 2 removed the remaining frames inside the center: `.stage-panel` surfaces became transparent — the instrument, tables and hypothesis list keep the one recessed viewport; everything else is whitespace-separated | **SHIPPED** |
| "Small charts; primary chart should be ~50–65% of the analytical workspace" | Observation stage: canvas spans the dominant center column (~60% with the inspector open, more in focus mode); 300px instrument viewport; zoom/region controls | **SHIPPED** |
| "Progressive disclosure — details on demand" | Hypothesis rows now open the **right inspector drawer** (Prediction / evaluated evidence / falsification criterion / Result / limitations) instead of expanding inline; evidence detail stays in the drawer; raw provenance behind "trace to source" | **SHIPPED** |
| "Focus/zen mode" | **Focus mode**: `Ctrl/Cmd+Shift+F` or palette → sidebar + status bar hide, header collapses, workspace maximizes; explicit "Exit focus" affordance | **SHIPPED** |
| "Question-first hierarchy" | Command Center leads with "What do you want to investigate?" — the real 6T question input is the hero, templates directly beneath, structured launcher after | **SHIPPED** |
| "Recognition over recall for hypothesis/evidence states" | Evidence table gained a compact **EFFECT** column (`→ H1` supports / `↮ H1` contradicts — real relations from the ledger); hypothesis rows carry state chip + counts inline | **SHIPPED** |
| "Consistent design tokens" | One token layer (`:root`), pinned by contract tests; round 2 raised `.panel h2` to 15px, question to 26px, table cells to 12.5px — dense but readable | **SHIPPED** |
| "Never color alone" | Every state chip carries text; the new effect glyphs (`→`/`↮`) pair with hypothesis ids and tooltips | **SHIPPED** (was already in place; re-verified) |
| "Calm factual empty/error states" | `StatePanel` (round 1) remains the single source; errors keep `role="alert"` | **SHIPPED** |
| "Restrained palette; no decoration" | Detector-clean (0 findings): no AI-tell borders, no gradients, no glow; accent reserved for "where you are / what is live" | **VERIFIED** |

## 2. Before/After test (per the mission)

| Question | Before (pre-round-1) | After (now) |
|---|---|---|
| Can the user immediately identify the main task? | No — 15 equal panels | Yes — the question is the largest element; the observation band answers it in one line |
| Are important charts small? | Yes — mid-scroll tile | No — the dominant instrument, zoomable, crosshair + region bands |
| Are details visible everywhere? | Yes — all at once | No — hypothesis/evidence detail in the drawer; provenance behind trace-to-source |
| Do cards dominate? | Yes | No — one recessed viewport per stage; whitespace groups the rest |
| Does it feel like a dashboard? | Yes | No — an engineering instrument: rail → canvas → trace |

## 3. The 5-second flagship test

Looking at the Active Investigation for 5 seconds, a race engineer reads:

1. **The question** — largest type, top of screen.
2. **The observation** — observed delta, comparability, evidence counts, residual, state — one compact band.
3. **The data** — the canvas shows measured traces with loss-window bands and the honest grid label.
4. **Where to look** — the stage rail with real per-stage statuses.
5. **Hypotheses under test** — H1–H6 with states and support/contradict counts.
6. **Evidence support/contradiction** — one click from any hypothesis row (drawer), or the Evidence stage with the EFFECT column.
7. **What remains unknown** — the residual callout (`UNRESOLVED — never assigned to a mechanism`) + unresolved questions.
8. **Traceability** — the bottom trace strip; every claim links to evidence ids; provenance drawer on demand.

## 4. Remaining honest limitations

- No time↔sector mapping exists in the telemetry corpus, so the instrument
  shows window bands (not sector markers) — the UI does not invent sectors.
- Evidence→canvas region linking exists only for comparison windows (the one
  evidence class that carries time windows); ledger evidence without a time
  window is linked by class, not by geometry.
- Visual QA was performed at HTTP/DOM level (no desktop browser connected to
  this session): all module transforms serve, 89/89 tests, live API E2E
  12/12. Pixel-level screenshots remain for a connected-browser session.
