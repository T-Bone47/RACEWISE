# PHASE 6Q — ENGINEERING COMMAND CENTER & INVESTIGATION WORKSPACE

## 1. Product architecture

Phase 6Q productizes the complete 6E–6P analytical chain without adding any
analytical engine. The chain below is the product; 6Q is its single,
investigation-first surface:

    COMMAND CENTER (landing)
      ↓  5-step launcher: QUESTION → SCOPE → HYPOTHESES → EVIDENCE PLAN → INVESTIGATE
    INVESTIGATION WORKSPACE (#/investigate)
      ├─ investigation header (id, question, scope, conclusion state)
      ├─ hypothesis matrix (H1–H6, equal treatment, never ranked)
      ├─ evidence ledger (filters: hypothesis / type / class / state / phase; text search)
      ├─ evidence detail drawer (+ TRACE TO SOURCE)
      ├─ decision trace (TRACE-001… with supporting/contradicting evidence)
      ├─ investigation graph (6P, in-workspace + standalone)
      ├─ counterfactuals / sensitivity (HISTORICAL vs MODELLED separated)
      ├─ synthesis (established facts / measured findings / unresolved / preserved contradictions)
      ├─ replay (6O) · compare (6O) · engineering memory (6O)
      └─ provenance drawer (universal "show me why")
    GRAPH / REPLAY / COMPARE / MEMORY views (standalone panels, same components)
    CATALOG ↔ INVESTIGATION (bidirectional scope handoff, context preserved)
    COMMAND PALETTE (Ctrl/Cmd+K): real commands + global typed search

Routing is hash-based (`#/view?scope=params`) so every scope is a shareable
URL; navigation is driven exclusively by `hashchange` events.

## 2. Design system

One token layer in `App.css` (`:root` custom properties); components
reference `var(--*)` exclusively:

- dark technical theme: near-black surfaces, precise 1px borders, restrained
  radii; no neon, no crypto-dashboard, no gaming UI
- semantic state colors cover FACT / CALCULATION / INFERENCE / COUNTERFACTUAL
  / SUPPORTED / MIXED / CONTRADICTED / NOT_SUPPORTED / NOT_TESTABLE /
  INSUFFICIENT_EVIDENCE / UNAVAILABLE / MODELLED / HISTORICAL — every state
  also carries its literal text label, so color is never the only signal
- `MODELLED` is additionally dashed-bordered orange, visually distinct from
  historical fact chips
- motion: 120–220 ms micro-transitions, 220–350 ms panel/drawer transitions,
  fully disabled under `prefers-reduced-motion`
- `:focus-visible` outlines; `ef-*` chip classes shared with the 6N/6O panels

## 3. Application shell

Header (brand, tagline, search trigger) + left sidebar (grouped:
Command Center / Investigate / Graph / Compare / Memory / Replay, then
Data: Catalog / Telemetry, then the analytical chain 6E–6M) + workspace +
status footer (CHAIN 6E–6P READY · REGISTRY 31 HISTORICAL TOOLS ·
DERIVED-ON-READ · ZERO STORAGE GROWTH). Status text is rendered only from
real API data; when the API is unreachable the command center shows a
structured UNAVAILABLE status, never a fabricated green light.

## 4–12. Investigation workspace

- **Header**: investigation id (content-addressed, deterministic), question
  type, scope controls, conclusion state chip, and "Open race in catalog →"
  (§35 handoff preserving season/round/session_type).
- **Hypothesis matrix**: six rows (H1 Corner Speed … H6 DRS) with evidence /
  supporting / contradicting / non-decisive / falsification / state columns.
  No score column, no winner, equal structural treatment.
- **Evidence ledger**: filters (hypothesis, type, claim class, state, source
  phase) + text search; row click opens the detail drawer whose fields are
  imported from the ledger verbatim ("nothing is derived for display") with
  a TRACE TO SOURCE button that opens the provenance drawer (source phase,
  source tool, source hash, canonical scope) and centers the 6P graph path.
- **Decision trace**: TRACE-001… entries with status, supporting and
  contradicting evidence; each evidence reference opens the same drawer, so
  conclusion → trace → evidence → source is fully traversable.
- **Falsification**: rendered from the 6N falsification gate; contradictions
  are prominent but labelled exactly (DIRECT_CONTRADICTION, UNRESOLVED);
  states use NO_FALSIFICATION_FOUND language, never CONFIRMED.
- **Counterfactuals / sensitivity**: BASELINE → INTERVENTION → MODEL →
  RESULT → VALIDATION → LIMITATIONS; MODELLED chips everywhere a modelled
  number appears; deltas shown as measured deltas only, never "better".
- **Loading states** are context-specific ("Investigating…", "Collecting
  evidence…", "Building evidence graph…", "Replaying investigation…",
  "Comparing investigations…"); **empty states** are honest ("No
  investigation selected…", "No related memory exists within this scope");
  **errors** are structured (code + message + scope hint), never raw stacks.

## 13. Graph integration (6P)

The GraphPanel (shared by workspace and standalone view) builds the
investigation-scoped graph on demand ("Build investigation graph" — no
corpus rendering by default), reports node/edge counts, supports focus by
node type (HYPOTHESIS/EVIDENCE/…), node selection with per-node provenance
path from the investigation, relationship rows with typed edges
(SUPPORTS / CONTRADICTS / DERIVED_FROM / MODELS / REPLAY_OF…), and displays
the epistemic guardrails verbatim: edges are imported analytical
relationships, SUPPORTS is not causation, CONTRADICTS comes from preserved
conflicts, the graph ranks nothing. Clicking a hypothesis in the matrix
highlights/filters ledger rows and focuses the graph (§17 cross-navigation).

## 14–15. Replay / Compare / Memory

ReplayPanel shows snapshot hash → replay hash and IDENTICAL/DIFFERENT
verdicts with structured diff categories; ComparePanel drives the 6O
`a_`/`b_`-prefixed compare contract and renders per-hypothesis deltas with
neutral transition terminology (SAME/ENTERED/EXITED/CHANGED — no
better/worse); MemoryPanel retrieves exact-scope memory with validity
(ACTIVE/SUPERSEDED/INVALIDATED/CONTEXT_LIMITED) and binds each statement to
its source evidence and investigation.

## 16. Search + command palette

Ctrl/Cmd+K opens the palette: real application commands (one per view)
plus **global search** against `GET /api/catalog/search` (debounced 200 ms,
min 2 chars) returning typed results — RACE / DRIVER / HYPOTHESIS /
INVESTIGATION / MEMORY / PATTERN — each navigating to a real workspace with
the matched scope (race → investigation workspace with season/round; driver
→ workspace with driver preset; hypothesis → HYPOTHESIS_EVALUATION with the
id preset). Exact/structured matching only; no semantic search.

## 17. Catalog ↔ investigation

Catalog "Investigate Session →" carries season/round/session_type into the
launcher; investigation header "Open race in catalog →" pre-opens the exact
session detail (§35, no context silently lost). Verified round-trip: the
same scope deterministically reproduces the same investigation id.

## 18. Accessibility

Semantic buttons throughout; `aria-label` on search trigger, palette,
dialogs; `aria-current` on nav; Esc closes drawers/palette; ArrowUp/Down +
Enter + Esc in the palette; focus management on palette open (autofocus);
`:focus-visible` outlines; contrast-verified dark palette; state chips
always carry text; `prefers-reduced-motion` disables transitions.

## 19. Performance (measured, 127.0.0.1, p50 of 6, live dev servers)

| surface | p50 | budget | status |
|---|---|---|---|
| command-center status API | 18.4 ms | — | — |
| global search API | 36.0 ms | — | — |
| investigation workspace data (6N) | 740.1 ms | < 2 s | PASS |
| graph initial build (6P, 58 nodes/185 edges) | 720.6 ms | < 1 s | PASS |
| replay (6O) | 1519.4 ms | — | dominated by exact 6N re-run |
| compare (6O) | 1635.6 ms | — | two 6N runs |
| memory retrieval (6O) | 806.7 ms | — | — |
| production bundle | 285 kB (84.6 kB gzip) | — | — |

Initial note: measurements against `localhost` showed a ~2 s floor from
IPv6/IPv4 fallback resolution overhead in the HTTP client; measurements
against `127.0.0.1` reflect actual server time. React.lazy keeps the
non-command views out of the initial chunk; the graph renders on demand.

## 20. Security

No `dangerouslySetInnerHTML`, `eval`, `new Function`, `innerHTML` writes,
`window.open`, or `location.href` assignment anywhere in the 6Q frontend;
no external URLs; no secrets in the bundle (design-"token" grep hit is the
CSS token comment); the backend search endpoint uses parameterized SQL
(`?` placeholders) with closed result-type enum and bounded results; hash
routing never interpolates into queries.

## 21. No-fabrication audit

Searched all 6Q UI text for caused/causes/proves/proven/most likely/best
explanation/optimal/winner/better/worse/confidence: every hit is an explicit
epistemic negation ("no better/worse, no winner", "not causation") or the
legitimate word "provenance". The UI reports states exactly as the backend
determines them and never upgrades evidence language.

## 22. Limitations

- Desktop-first: narrow widths collapse the sidebar to an icon rail; tablet
  layouts are functional but not optimized.
- Search covers races/drivers/hypotheses/pattern-ids and 16-hex
  investigation/memory ids; free-text evidence search arrives via the
  in-workspace ledger filter, not global search.
- Browser-automation screenshots were unavailable in this environment; the
  E2E walkthrough (§42) was executed against the live DOM with real data
  and every step's outcome recorded programmatically.
- Recents live in `localStorage` (explicitly marked as browser-local, never
  fabricated).
