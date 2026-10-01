import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import {
  IconGauge, IconSearch, IconGraph, IconHistory, IconGitCompare, IconArrowsExchange, IconReload,
  IconDatabase, IconActivity, IconChartBar, IconChartLine, IconStack2,
  IconBoxMultiple, IconChartHistogram, IconListNumbers, IconMathFunction, IconTable,
} from '@tabler/icons-react'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './App.css'
import CommandCenterView from './CommandCenterView'
import CommandPalette from './CommandPalette'
import InvestigationView from './InvestigationView'
import { GraphPanel, ReplayPanel, ComparePanel, MemoryPanel } from './panels'
import { LoadingLine } from './workspace'

const CatalogExplorer = lazy(() => import('./CatalogExplorer'))
const TelemetryView = lazy(() => import('./TelemetryView'))
const AttributionView = lazy(() => import('./AttributionView'))
const EvidenceFusionView = lazy(() => import('./EvidenceFusionView'))
const StintEvidenceView = lazy(() => import('./StintEvidenceView'))
const RaceGapView = lazy(() => import('./RaceGapView'))
const CounterfactualView = lazy(() => import('./CounterfactualView'))
const FalsificationMatrixView = lazy(() => import('./FalsificationMatrixView'))
const PerformanceEnvelopeView = lazy(() => import('./PerformanceEnvelopeView'))
const PerformanceRegimeView = lazy(() => import('./PerformanceRegimeView'))
const PerformancePatternView = lazy(() => import('./PerformancePatternView'))
const PatternEvidenceView = lazy(() => import('./PatternEvidenceView'))
const AutonomousView = lazy(() => import('./AutonomousView'))

/* ============ Phase 6Q — application shell ============ */

type ViewId =
  | 'command' | 'autonomous' | 'investigate' | 'falsification' | 'graph' | 'replay' | 'compare' | 'memory'
  | 'catalog' | 'telemetry' | 'attribution' | 'fusion' | 'stint'
  | 'racegap' | 'counterfactual' | 'envelope' | 'regime' | 'patterns'
  | 'patternevidence' | 'legacy'

/* one professional icon family (tabler) — no emoji as functional UI.
   Navigation IA (mission §7): grouped by workflow stage — INVESTIGATION,
   KNOWLEDGE, ANALYSIS, DATA, WORKSPACE — every existing route preserved. */
const NAV: Array<{ group: string; items: Array<{ id: ViewId; label: string; icon: typeof IconGauge }> }> = [
  {
    group: 'Investigation',
    items: [
      { id: 'command', label: 'Command Center', icon: IconGauge },
      { id: 'investigate', label: 'Active Investigation', icon: IconSearch },
      { id: 'falsification', label: 'Falsification', icon: IconListNumbers },
      { id: 'counterfactual', label: 'Counterfactual Lab', icon: IconBoxMultiple },
    ],
  },
  {
    group: 'Knowledge',
    items: [
      { id: 'graph', label: 'Investigation Graph', icon: IconGraph },
      { id: 'memory', label: 'Engineering Memory', icon: IconHistory },
      { id: 'patterns', label: 'Cross-Race Patterns', icon: IconMathFunction },
      { id: 'patternevidence', label: 'Pattern Evidence', icon: IconTable },
    ],
  },
  {
    group: 'Analysis',
    items: [
      { id: 'telemetry', label: 'Lap Comparison', icon: IconActivity },
      { id: 'attribution', label: 'Lap Attribution', icon: IconChartBar },
      { id: 'fusion', label: 'Evidence Fusion', icon: IconChartLine },
      { id: 'stint', label: 'Stint Analysis', icon: IconStack2 },
      { id: 'racegap', label: 'Race Gap', icon: IconArrowsExchange },
      { id: 'envelope', label: 'Performance Envelope', icon: IconChartHistogram },
      { id: 'regime', label: 'Regime Timeline', icon: IconListNumbers },
    ],
  },
  {
    group: 'Data',
    items: [
      { id: 'catalog', label: 'Sessions & Drivers', icon: IconDatabase },
    ],
  },
  {
    group: 'Workspace',
    items: [
      { id: 'autonomous', label: 'Autonomous Query', icon: IconSearch },
      { id: 'compare', label: 'Compare', icon: IconGitCompare },
      { id: 'replay', label: 'Replay', icon: IconReload },
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
  /* honest engine status: one real /api/health probe — the bar never claims
     readiness the engine did not confirm (UX audit §16) */
  const [engineUp, setEngineUp] = useState<boolean | null>(null)
  /* analysis focus mode (mission): hide navigation and metadata, maximize
     the analytical workspace — Ctrl/Cmd+Shift+F toggles */
  const [zen, setZen] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => { setEngineUp(r.ok) })
      .catch(() => { setEngineUp(false) })
  }, [])

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

  /* keyboard: Ctrl/Cmd+K opens the command palette; Ctrl/Cmd+Shift+F
     toggles analysis focus mode */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(true)
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault()
        setZen((z) => !z)
      }
      /* Esc closes the palette from anywhere (no keyboard traps, §28) */
      if (e.key === 'Escape') {
        setPaletteOpen(false)
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
    <div className={`shell ${zen ? 'zen' : ''}`}>
      {/* ================= HEADER — Stitch topbar with context crumb ================= */}
      <header className="shell-header">
        <h1>RACE<span>WISE</span></h1>
        <span className="shell-tagline">evidence-driven race engineering</span>
        {[...params.keys()].length > 0 && params.get('season') && (
          <span className="shell-tagline" aria-label="current scope">
            {params.get('season')} R{params.get('round') ?? '·'}
            {params.get('driver_a') ? ` · ${params.get('driver_a')} vs ${params.get('driver_b') ?? '—'}` : ''}
            {params.get('lap_number') ? ` · lap ${params.get('lap_number')}` : ''}
          </span>
        )}
        <span className="spacer" />
        {zen && (
          <button
            className="zen-exit"
            onClick={() => setZen(false)}
            title="Exit focus mode (Ctrl/Cmd+Shift+F)"
          >
            Exit focus
          </button>
        )}
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

      {/* ================= SIDEBAR — Stitch Navigation Deck ================= */}
      <nav className="shell-sidebar" aria-label="Workspace navigation">
        <button
          className="primary"
          style={{ width: '100%', marginBottom: 10 }}
          onClick={() => navigate('command')}
        >
          + New investigation
        </button>
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

        {view === 'falsification' && (
          /* Stitch Falsification Matrix → the dedicated matrix view over the
             real hypothesis-evaluation investigation (H1–H6 with engine
             verdicts, evidence links and the decision trace) */
          <Suspense fallback={<LoadingLine label="Loading falsification matrix…" />}>
            <FalsificationMatrixView
              key={params.toString()}
              presetParams={[...params.keys()].length > 0 ? params : undefined}
            />
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
            <CounterfactualView
              key={params.toString()}
              presetParams={[...params.keys()].length > 0 ? params : undefined}
            />
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
          <span
            className={`status-dot ${engineUp === false ? 'status-dot-down' : ''}`}
            aria-hidden="true"
          />
          {engineUp == null ? 'ENGINE PROBE…' : engineUp ? 'ENGINE REACHABLE · DETERMINISTIC CHAIN' : 'ENGINE UNREACHABLE — VIEWS DEGRADE HONESTLY'}
        </span>
        {engineUp !== false && <span className="statusbar-item">EVIDENCE-DRIVEN · ZERO STORAGE GROWTH</span>}
        {recentsCount > 0 && <span className="statusbar-item">{recentsCount} RECENT INVESTIGATION(S)</span>}
        <span className="statusbar-item" style={{ marginLeft: 'auto' }}>RACEWISE ENGINEERING WORKSTATION</span>
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
            onNavigate={(v) => {
              setPaletteOpen(false)
              if (v === 'zen') { setZen((z) => !z); return }
              navigate(v)
            }}
            currentView={view}
            currentParams={params}
          />
        </div>
      )}
    </div>
  )
}

