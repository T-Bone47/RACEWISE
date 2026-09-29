import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import {
  IconGauge, IconSearch, IconGraph, IconHistory, IconGitCompare, IconArrowsExchange, IconReload,
  IconDatabase, IconActivity, IconChartBar, IconChartLine, IconStack2,
  IconBoxMultiple, IconChartHistogram, IconListNumbers, IconMathFunction, IconTable,
} from '@tabler/icons-react'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './App.css'
import CommandCenterView from './CommandCenterView'
import InvestigationView from './InvestigationView'
import { GraphPanel, ReplayPanel, ComparePanel, MemoryPanel } from './panels'
import { LoadingLine } from './workspace'
import type { SearchResponse } from './types'

const CatalogExplorer = lazy(() => import('./CatalogExplorer'))
const TelemetryView = lazy(() => import('./TelemetryView'))
const AttributionView = lazy(() => import('./AttributionView'))
const EvidenceFusionView = lazy(() => import('./EvidenceFusionView'))
const StintEvidenceView = lazy(() => import('./StintEvidenceView'))
const RaceGapView = lazy(() => import('./RaceGapView'))
const CounterfactualView = lazy(() => import('./CounterfactualView'))
const PerformanceEnvelopeView = lazy(() => import('./PerformanceEnvelopeView'))
const PerformanceRegimeView = lazy(() => import('./PerformanceRegimeView'))
const PerformancePatternView = lazy(() => import('./PerformancePatternView'))
const PatternEvidenceView = lazy(() => import('./PatternEvidenceView'))
const AutonomousView = lazy(() => import('./AutonomousView'))

/* ============ Phase 6Q — application shell ============ */

type ViewId =
  | 'command' | 'investigate' | 'graph' | 'replay' | 'compare' | 'memory'
  | 'catalog' | 'telemetry' | 'attribution' | 'fusion' | 'stint'
  | 'racegap' | 'counterfactual' | 'envelope' | 'regime' | 'patterns'
  | 'patternevidence' | 'autonomous' | 'legacy'

/* one professional icon family (tabler, §44) — no emoji as functional UI */
const NAV: Array<{ group: string; items: Array<{ id: ViewId; label: string; icon: typeof IconGauge }> }> = [
  {
    group: 'Command center',
    items: [
      { id: 'command', label: 'Overview', icon: IconGauge },
      { id: 'autonomous', label: 'Autonomous', icon: IconSearch },
      { id: 'investigate', label: 'Investigate', icon: IconSearch },
      { id: 'graph', label: 'Graph', icon: IconGraph },
      { id: 'compare', label: 'Compare', icon: IconGitCompare },
      { id: 'memory', label: 'Memory', icon: IconHistory },
      { id: 'replay', label: 'Replay', icon: IconReload },
    ],
  },
  {
    group: 'Data',
    items: [
      { id: 'catalog', label: 'Catalog', icon: IconDatabase },
    ],
  },
  {
    group: 'Engineering',
    items: [
      { id: 'telemetry', label: 'Lap Comparison', icon: IconActivity },
      { id: 'attribution', label: 'Lap Attribution', icon: IconChartBar },
      { id: 'fusion', label: 'Evidence Fusion', icon: IconChartLine },
      { id: 'stint', label: 'Stint Analysis', icon: IconStack2 },
      { id: 'racegap', label: 'Race Gap', icon: IconArrowsExchange },
      { id: 'counterfactual', label: 'Counterfactuals', icon: IconBoxMultiple },
      { id: 'envelope', label: 'Performance Envelope', icon: IconChartHistogram },
      { id: 'regime', label: 'Performance Regimes', icon: IconListNumbers },
      { id: 'patterns', label: 'Cross-Race Patterns', icon: IconMathFunction },
      { id: 'patternevidence', label: 'Pattern Evidence', icon: IconTable },
    ],
  },
]

function defaultScopeParams(): URLSearchParams {
  return new URLSearchParams({
    question_type: 'LAP_PERFORMANCE',
    driver_a: 'max-verstappen',
    driver_b: 'sergio-perez',
    season: '2023',
    round: '1',
    lap_number: '6',
  })
}

function parseHash(): { view: ViewId; params: URLSearchParams } {
  const hash = window.location.hash.replace(/^#\/?/, '')
  const [view, query] = hash.split('?')
  const params = new URLSearchParams(query || '')
  const known = new Set(NAV.flatMap((g) => g.items.map((i) => i.id)))
  const v = (known.has(view as ViewId) ? view : 'command') as ViewId
  return { view: v, params }
}

export default function App() {
  const [{ view, params }, setRoute] = useState(parseHash)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [recentsCount, setRecentsCount] = useState(0)

  useEffect(() => {
    function onHash() {
      setRoute(parseHash())
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const navigate = useCallback((v: string) => {
    if (!v) return
    window.location.hash = `#/${v}`
    setRoute(parseHash())
  }, [])

  /* keyboard: Ctrl/Cmd+K opens the command palette */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem('racewise.recent.investigations.v1')
      setRecentsCount(raw ? (JSON.parse(raw) as unknown[]).length : 0)
    } catch {
      setRecentsCount(0)
    }
  }, [view])

  const presetParams = view === 'investigate' && [...params.keys()].length > 0 ? params : undefined

  const scopeParams = useCallback(() => {
    if ([...params.keys()].length > 0) return new URLSearchParams(params)
    return defaultScopeParams()
  }, [params])

  return (
    <div className="shell">
      {/* ================= HEADER ================= */}
      <header className="shell-header">
        <h1>RACE<span>WISE</span></h1>
        <span className="shell-tagline">evidence-driven race engineering — investigations, not answers</span>
        <span className="spacer" />
        <button
          className="search-trigger"
          onClick={() => setPaletteOpen(true)}
          aria-label="Open command palette and search"
        >
          <IconSearch size={15} strokeWidth={1.75} aria-hidden="true" />
          <span className="search-hint">Search / commands</span>
          <kbd>Ctrl K</kbd>
        </button>
      </header>

      {/* ================= SIDEBAR ================= */}
      <nav className="shell-sidebar" aria-label="Workspace navigation">
        {NAV.map((group) => (
          <div key={group.group}>
            <div className="nav-group-label">{group.group}</div>
            {group.items.map((item) => (
              <button
                key={item.id}
                className={`nav-item ${view === item.id ? 'active' : ''}`}
                onClick={() => navigate(item.id)}
                aria-current={view === item.id ? 'page' : undefined}
              >
                <span className="nav-ico" aria-hidden="true"><item.icon size={16} strokeWidth={1.75} /></span>
                <span className="nav-label">{item.label}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>

      {/* ================= WORKSPACE ================= */}
      <main className="shell-workspace">
        {view === 'command' && <CommandCenterView onNavigated={navigate} />}

        {view === 'autonomous' && (
          <Suspense fallback={<div className="panel"><LoadingLine label="autonomous workspace" /></div>}>
            <AutonomousView />
          </Suspense>
        )}

        {view === 'investigate' && (
          <InvestigationView key={params.toString()} presetParams={presetParams} />
        )}

        {view === 'graph' && (
          <section className="panel">
            <h2>Engineering graph — provenance navigator</h2>
            <p className="muted small">
              Assembled on read from the investigation of the scope below.
              Click a node to trace its path; use the hypothesis focus to see
              supporting / contradicting / non-decisive evidence side by side.
            </p>
            <GraphPanel scopeParams={scopeParams} />
          </section>
        )}

        {view === 'replay' && (
          <section className="panel">
            <h2>Replay</h2>
            <p className="muted small">
              Deterministic replay: rebuild the snapshot, re-run the exact
              engine, compare canonical hashes. Divergence is reported as
              exact structured differences with categories.
            </p>
            <ReplayPanel scopeParams={scopeParams} />
          </section>
        )}

        {view === 'compare' && (
          <section className="panel">
            <h2>Comparison</h2>
            <p className="muted small">
              Dimension-wise deltas between investigation A (current scope)
              and B (same scope, different lap). Neutral transition
              terminology — no better/worse, no winner.
            </p>
            <ComparePanel baseScope={scopeParams} />
          </section>
        )}

        {view === 'memory' && (
          <section className="panel">
            <h2>Engineering memory</h2>
            <p className="muted small">
              Evidence-bound, scope-limited memory derived on read and
              retrieved by exact scope — never semantic similarity, never
              universal truth.
            </p>
            <MemoryPanel scopeParams={scopeParams} driverA={scopeParams().get('driver_a') || ''} />
          </section>
        )}

        {view === 'catalog' && (
          <Suspense fallback={<LoadingLine label="Loading data catalog…" />}>
            <CatalogExplorer
              presetSession={
                view === 'catalog' && [...params.keys()].length > 0
                  ? {
                      season: Number(params.get('season') || 0),
                      round: Number(params.get('round') || 0),
                      session_type: params.get('session_type') || 'RACE',
                    }
                  : undefined
              }
              onInvestigate={(session) =>
                navigate(
                  `investigate?season=${session.season}&round=${session.round}` +
                  `&session_type=${encodeURIComponent(session.session_type)}`,
                )
              }
            />
          </Suspense>
        )}

        {view === 'telemetry' && (
          <Suspense fallback={<LoadingLine label="Loading telemetry view…" />}>
            <TelemetryView />
          </Suspense>
        )}

        {view === 'attribution' && (
          <Suspense fallback={<LoadingLine label="Loading attribution view…" />}>
            <AttributionView />
          </Suspense>
        )}
        {view === 'fusion' && (
          <Suspense fallback={<LoadingLine label="Loading evidence fusion view…" />}>
            <EvidenceFusionView />
          </Suspense>
        )}
        {view === 'stint' && (
          <Suspense fallback={<LoadingLine label="Loading stint evidence view…" />}>
            <StintEvidenceView />
          </Suspense>
        )}
        {view === 'racegap' && (
          <Suspense fallback={<LoadingLine label="Loading race gap view…" />}>
            <RaceGapView />
          </Suspense>
        )}
        {view === 'counterfactual' && (
          <Suspense fallback={<LoadingLine label="Loading counterfactual view…" />}>
            <CounterfactualView />
          </Suspense>
        )}
        {view === 'envelope' && (
          <Suspense fallback={<LoadingLine label="Loading envelope view…" />}>
            <PerformanceEnvelopeView />
          </Suspense>
        )}
        {view === 'regime' && (
          <Suspense fallback={<LoadingLine label="Loading regimes view…" />}>
            <PerformanceRegimeView />
          </Suspense>
        )}
        {view === 'patterns' && (
          <Suspense fallback={<LoadingLine label="Loading patterns view…" />}>
            <PerformancePatternView />
          </Suspense>
        )}
        {view === 'patternevidence' && (
          <Suspense fallback={<LoadingLine label="Loading pattern evidence view…" />}>
            <PatternEvidenceView />
          </Suspense>
        )}
      </main>

      {/* ================= STATUS BAR (§33 — only real state) ================= */}
      <footer className="shell-statusbar">
        <span className="statusbar-item">
          <span className="status-dot" aria-hidden="true" />
          DETERMINISTIC CHAIN READY
        </span>
        <span className="statusbar-item">EVIDENCE-DRIVEN · ZERO STORAGE GROWTH</span>
        {recentsCount > 0 && <span className="statusbar-item">{recentsCount} RECENT INVESTIGATION(S)</span>}
        <span className="statusbar-item" style={{ marginLeft: 'auto' }}>RACEWISE ENGINEERING WORKSPACE</span>
      </footer>

      {/* ================= COMMAND PALETTE (§26) ================= */}
      {paletteOpen && (
        <div
          className="overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Command palette"
          onMouseDown={(e) => { if (e.target === e.currentTarget) setPaletteOpen(false) }}
        >
          <CommandPalette
            onClose={() => setPaletteOpen(false)}
            onNavigate={(v) => { setPaletteOpen(false); navigate(v) }}
            currentView={view}
          />
        </div>
      )}
    </div>
  )
}

/* ---------- command palette: only real application actions ---------- */

function CommandPalette({
  onClose,
  onNavigate,
}: {
  onClose: () => void
  onNavigate: (v: string) => void
  currentView: string
}) {
  const [q, setQ] = useState('')
  const [idx, setIdx] = useState(0)
  const [search, setSearch] = useState<SearchResponse | null>(null)

  /* global search (§25): exact/structured matching via /api/catalog/search —
     no semantic search, deterministic retrieval only */
  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) {
      setSearch(null)
      return
    }
    let cancelled = false
    const t = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/catalog/search?q=${encodeURIComponent(term)}`)
        if (resp.ok && !cancelled) setSearch(await resp.json())
      } catch {
        /* search stays silent on transport errors — commands still work */
      }
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [q])

  const commands = [
    { label: 'New investigation', view: 'command' },
    { label: 'Open investigation workspace', view: 'investigate' },
    { label: 'Open investigation graph', view: 'graph' },
    { label: 'Compare investigations', view: 'compare' },
    { label: 'Open engineering memory', view: 'memory' },
    { label: 'Replay investigation', view: 'replay' },
    { label: 'Open data catalog', view: 'catalog' },
    { label: 'Open lap comparison', view: 'telemetry' },
    { label: 'Open lap attribution', view: 'attribution' },
    { label: 'Open evidence fusion', view: 'fusion' },
    { label: 'Open stint analysis', view: 'stint' },
    { label: 'Open race gap decomposition', view: 'racegap' },
    { label: 'Open counterfactual simulator', view: 'counterfactual' },
    { label: 'Open performance envelope', view: 'envelope' },
    { label: 'Open performance regimes', view: 'regime' },
    { label: 'Open cross-race patterns', view: 'patterns' },
    { label: 'Open pattern evidence', view: 'patternevidence' },
  ]
  const filtered = commands.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()))
  /* keyboard selection spans commands first, then typed search results */
  const entries = [
    ...filtered.map((c) => ({ kind: 'COMMAND' as const, view: c.view, label: c.label, detail: '', type: 'COMMAND' })),
    ...(search?.results || []).map((r) => ({
      kind: 'RESULT' as const,
      view: r.result_type === 'RACE' || r.result_type === 'DRIVER'
        ? `investigate?season=${r.ref.season ?? 2023}&round=${r.ref.round ?? 1}&driver_a=${r.ref.driver_key ?? r.ref.hypothesis_id ?? ''}`
        : r.result_type === 'HYPOTHESIS'
          ? `investigate?question_type=HYPOTHESIS_EVALUATION&hypotheses=${r.ref.hypothesis_id ?? ''}&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1&lap_number=6`
          : r.result_type === 'INVESTIGATION' || r.result_type === 'MEMORY'
            ? `memory`
            : r.result_type === 'PATTERN'
              ? `patternevidence`
              : `investigate`,
      label: r.label,
      detail: r.detail,
      type: r.result_type,
    })),
  ]
  const active = Math.min(idx, Math.max(0, entries.length - 1))

  return (
    <>
      <input
        autoFocus
        value={q}
        placeholder="Type a command…"
        aria-label="Command search"
        onChange={(e) => { setQ(e.target.value); setIdx(0) }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onClose()
          if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, filtered.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)) }
          if (e.key === 'Enter' && entries[active]) onNavigate(entries[active].view)
        }}
      />
      <div className="palette-list">
        {entries.length === 0 && (
          <div className="palette-empty">No command matches “{q}”.</div>
        )}
        {filtered.map((c, i) => (
          <button
            key={`cmd-${c.view}`}
            className={`palette-item ${i === active ? 'active' : ''}`}
            onMouseEnter={() => setIdx(i)}
            onClick={() => onNavigate(c.view)}
          >
            <span className="p-type">COMMAND</span>
            <span>{c.label}</span>
          </button>
        ))}
        {(search?.results || []).map((r, j) => {
          const i = filtered.length + j
          const view =
            r.result_type === 'RACE' && typeof r.ref.season === 'number'
              ? `investigate?season=${r.ref.season}&round=${r.ref.round ?? 1}`
              : r.result_type === 'DRIVER' && typeof r.ref.driver_key === 'string'
                ? `investigate?season=2023&round=1&driver_a=${encodeURIComponent(r.ref.driver_key)}&driver_b=sergio-perez&lap_number=6`
                : r.result_type === 'HYPOTHESIS'
                  ? `investigate?question_type=HYPOTHESIS_EVALUATION&hypotheses=${r.ref.hypothesis_id ?? ''}`
                  : r.result_type === 'INVESTIGATION' || r.result_type === 'MEMORY'
                    ? 'memory'
                    : r.result_type === 'PATTERN'
                      ? 'patternevidence'
                      : 'investigate'
          return (
            <button
              key={`res-${r.result_type}-${r.label}-${i}`}
              className={`palette-item ${i === active ? 'active' : ''}`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => onNavigate(view)}
            >
              <span className="p-type">{r.result_type}</span>
              <span>{r.label}{r.detail ? <em className="muted"> — {r.detail}</em> : null}</span>
            </button>
          )
        })}
      </div>
      <div className="palette-hint">
        <span><kbd>↑↓</kbd> navigate</span>
        <span><kbd>Enter</kbd> run</span>
        <span><kbd>Esc</kbd> close</span>
        <span>search is also here — types: RACE / DRIVER / HYPOTHESIS / ids</span>
      </div>
    </>
  )
}
