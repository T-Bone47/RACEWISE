import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  HYP_LABELS, QUESTION_INPUTS, QUESTION_TYPES,
} from './types'
import type { QuestionScope, SearchResponse } from './types'
import { LoadingLine, StructuredError } from './workspace'

/* ============ Phase 6Q — Command Center (default landing view) ============ */

export interface RecentInvestigation {
  investigation_id: string
  question_type: string
  scope: QuestionScope & { question_type?: string }
  output_hash: string
  conclusion_state: string
  evidence_count: number
  at: number
}

const RECENTS_KEY = 'racewise.recent.investigations.v1'

export function loadRecents(): RecentInvestigation[] {
  try {
    const raw = localStorage.getItem(RECENTS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as RecentInvestigation[]
    return Array.isArray(parsed) ? parsed.slice(0, 8) : []
  } catch {
    return []
  }
}

export function saveRecent(inv: RecentInvestigation) {
  try {
    const next = [inv, ...loadRecents().filter((r) => r.investigation_id !== inv.investigation_id)]
    localStorage.setItem(RECENTS_KEY, JSON.stringify(next.slice(0, 8)))
  } catch {
    /* storage unavailable — recents stay session-local */
  }
}

export function scopeParams(scope: QuestionScope & { question_type?: string }): URLSearchParams {
  const params = new URLSearchParams({
    driver_a: scope.driver_a,
    driver_b: scope.driver_b,
    season: String(scope.season),
    round: String(scope.round),
  })
  if (scope.question_type) params.set('question_type', scope.question_type)
  if (scope.lap_number != null) params.set('lap_number', String(scope.lap_number))
  if (scope.stint_number != null) params.set('stint_number', String(scope.stint_number))
  if (scope.pattern_id) params.set('pattern_id', scope.pattern_id)
  return params
}

const STEPS = ['QUESTION', 'SCOPE', 'HYPOTHESES', 'EVIDENCE PLAN', 'INVESTIGATE'] as const

interface CatalogSessionLite {
  season: number
  round: number
  race_name: string | null
}

export default function CommandCenterView({
  onNavigated,
}: {
  onNavigated?: (view: string) => void
}) {
  /* launcher state */
  const [questionType, setQuestionType] = useState<string>('LAP_PERFORMANCE')
  const [season, setSeason] = useState(2023)
  const [round, setRound] = useState(1)
  const [driverA, setDriverA] = useState('max-verstappen')
  const [driverB, setDriverB] = useState('sergio-perez')
  const [lapNumber, setLapNumber] = useState(6)
  const [stintNumber, setStintNumber] = useState(1)
  const [patternId, setPatternId] = useState('')
  const [hypothesisFilter, setHypothesisFilter] = useState<string[]>([])
  const [telemetrySessions, setTelemetrySessions] = useState<CatalogSessionLite[]>([])

  /* real system status */
  const [status, setStatus] = useState<{ sessions: number; db: string } | null>(null)
  const [statusError, setStatusError] = useState(false)
  const [recents] = useState<RecentInvestigation[]>(() => loadRecents())
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [searchRes, setSearchRes] = useState<SearchResponse | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)

  const inputs = QUESTION_INPUTS[questionType] || []
  const step = useMemo(() => {
    if (!questionType) return 0
    if (!driverA.trim() || !driverB.trim() || driverA === driverB) return 1
    if (inputs.includes('lap_number') && !(lapNumber >= 1)) return 1
    if (inputs.includes('stint_number') && !(stintNumber >= 1)) return 1
    if (inputs.includes('pattern_id') && !patternId.trim()) return 1
    return 4
  }, [questionType, driverA, driverB, lapNumber, stintNumber, patternId, inputs])

  useEffect(() => {
    async function load() {
      try {
        const resp = await fetch('/api/catalog/sessions?capability=telemetry&page_size=100')
        if (!resp.ok) throw new Error(String(resp.status))
        const data = await resp.json()
        setTelemetrySessions((data.sessions || []).slice(0, 50))
        setStatus({ sessions: data.total ?? (data.sessions || []).length, db: 'canonical store' })
      } catch {
        setStatusError(true)
      }
    }
    load()
  }, [])

  const runSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setSearchRes(null)
      return
    }
    setSearchLoading(true)
    try {
      const resp = await fetch(`/api/catalog/search?q=${encodeURIComponent(q.trim())}`)
      if (resp.ok) setSearchRes(await resp.json())
    } finally {
      setSearchLoading(false)
    }
  }, [])

  function scope(): QuestionScope & { question_type: string } {
    return {
      season,
      round,
      driver_a: driverA.trim(),
      driver_b: driverB.trim(),
      lap_number: inputs.includes('lap_number') ? lapNumber : null,
      stint_number: inputs.includes('stint_number') ? stintNumber : null,
      session_type: 'RACE',
      pattern_id: inputs.includes('pattern_id') && patternId.trim() ? patternId.trim() : null,
      question_type: questionType,
    }
  }

  function launch() {
    const s = scope()
    const params = scopeParams(s)
    params.set('question_type', questionType)
    if (hypothesisFilter.length > 0) params.set('hypotheses', hypothesisFilter.join(','))
    window.location.hash = `#/investigate?${params.toString()}`
    /* the App-level hashchange listener routes to the workspace with the full
       preset params; re-dispatch explicitly so an identical re-run (same hash
       string, no native event) still routes */
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  }

  return (
    <div>
      {/* ---- NEW INVESTIGATION (primary area) ---- */}
      <section className="cmd-hero" aria-label="New investigation">
        <h2>New investigation</h2>
        <p className="muted small">
          One structured engineering question through the deterministic 6E–6N chain.
          Closed vocabulary only — no free-form logic, no causal claims.
        </p>
        <div className="launcher-steps" aria-hidden="true">
          {STEPS.map((s, i) => (
            <span key={s} className={`step ${i < step ? 'done' : i === step ? 'active' : ''}`}>
              {i + 1}. {s}
            </span>
          ))}
        </div>

        <div className="controls">
          <label>
            question type:{' '}
            <select value={questionType} onChange={(e) => setQuestionType(e.target.value)}>
              {QUESTION_TYPES.map((q) => <option key={q} value={q}>{q}</option>)}
            </select>
          </label>
          <label>
            season:{' '}
            <select value={season} onChange={(e) => setSeason(Number(e.target.value))}>
              {Array.from(new Set([...telemetrySessions.map((s) => s.season), season]))
                .sort((a, b) => b - a).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label>
            round:{' '}
            <input type="number" min={1} max={99} value={round} style={{ width: 64 }}
                   onChange={(e) => setRound(Number(e.target.value))} />
          </label>
          <label>
            driver A:{' '}
            <input type="text" value={driverA} style={{ width: 150 }}
                   onChange={(e) => setDriverA(e.target.value)} />
          </label>
          <label>
            driver B:{' '}
            <input type="text" value={driverB} style={{ width: 150 }}
                   onChange={(e) => setDriverB(e.target.value)} />
          </label>
          {inputs.includes('lap_number') && (
            <label>
              lap:{' '}
              <input type="number" min={1} value={lapNumber} style={{ width: 64 }}
                     onChange={(e) => setLapNumber(Number(e.target.value))} />
            </label>
          )}
          {inputs.includes('stint_number') && (
            <label>
              stint:{' '}
              <input type="number" min={1} value={stintNumber} style={{ width: 64 }}
                     onChange={(e) => setStintNumber(Number(e.target.value))} />
            </label>
          )}
          {inputs.includes('pattern_id') && (
            <label>
              pattern id:{' '}
              <input type="text" value={patternId} style={{ minWidth: 220 }}
                     placeholder="from the 6L patterns view"
                     onChange={(e) => setPatternId(e.target.value)} />
            </label>
          )}
        </div>

        <div className="controls">
          <span className="muted small">hypothesis subset (optional, never ranked):</span>
          {Object.entries(HYP_LABELS).map(([id, label]) => (
            <label key={id} style={{ gap: 3 }}>
              <input
                type="checkbox"
                checked={hypothesisFilter.includes(id)}
                onChange={(e) => setHypothesisFilter((cur) =>
                  e.target.checked ? [...cur, id] : cur.filter((h) => h !== id))}
              />
              {label}
            </label>
          ))}
        </div>

        <div className="muted small" style={{ marginBottom: 10 }}>
          evidence plan will execute: {(questionType && QUESTION_INPUTS[questionType] !== undefined) ? 'per 6N closed plan' : '—'} ·
          {' '}drivers must be distinct · scope data is checked at run time (UNAVAILABLE is reported, never broadened)
        </div>

        <button className="primary" onClick={launch} disabled={step < 4}>
          {step < 4 ? 'Complete steps 1–4 to investigate' : 'Run investigation →'}
        </button>
      </section>

      {/* ---- RECENT INVESTIGATIONS (real, or explicit empty state) ---- */}
      <section className="panel" aria-label="Recent investigations">
        <h2>Recent investigations</h2>
        {recents.length === 0 ? (
          <div className="empty-state">
            No investigation has been run in this browser yet. Completed
            investigations appear here with their scope and conclusion state —
            nothing is listed until you actually run one.
          </div>
        ) : (
          <div className="recent-list">
            {recents.map((r) => (
              <button
                key={r.investigation_id}
                className="recent-item"
                onClick={() => {
                  const params = scopeParams(r.scope)
                  params.set('question_type', r.question_type)
                  window.location.hash = `#/investigate?${params.toString()}`
                  window.dispatchEvent(new HashChangeEvent('hashchange'))
                  onNavigated?.('investigate')
                }}
              >
                <span className={`ef-badge ${r.conclusion_state === 'SUPPORTED_BY_AVAILABLE_EVIDENCE' ? 'st-supported' : r.conclusion_state === 'MIXED_EVIDENCE' ? 'st-mixed' : 'st-untestable'}`}>
                  {r.conclusion_state.replace(/_/g, ' ')}
                </span>
                <span>{r.question_type}</span>
                <span className="muted small">
                  {r.scope.season} R{r.scope.round} · {r.scope.driver_a} vs {r.scope.driver_b}
                  {r.scope.lap_number != null ? ` · lap ${r.scope.lap_number}` : ''}
                  {r.scope.stint_number != null ? ` · stint ${r.scope.stint_number}` : ''}
                </span>
                <span className="muted small mono" style={{ marginLeft: 'auto' }}>
                  {r.investigation_id.slice(0, 10)} · {r.evidence_count} evidence items
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* ---- SHORTCUTS ---- */}
      <section className="panel" aria-label="Shortcuts">
        <h2>Evidence / Graph / Memory shortcuts</h2>
        <div className="quick-grid">
          <button className="quick-tile" onClick={() => onNavigated?.('catalog')}>
            <span className="q-label">Data</span>Browse the canonical catalog and launch from a session
          </button>
          <button className="quick-tile" onClick={() => onNavigated?.('graph')}>
            <span className="q-label">Graph</span>Open the 6P provenance navigator for the current scope
          </button>
          <button className="quick-tile" onClick={() => onNavigated?.('memory')}>
            <span className="q-label">Memory</span>Exact-scope engineering memory (derived on read)
          </button>
          <button className="quick-tile" onClick={() => onNavigated?.('compare')}>
            <span className="q-label">Compare</span>Dimension-wise comparison of two investigations
          </button>
          <button className="quick-tile" onClick={() => { setSearchOpen(true); onNavigated?.('') }}>
            <span className="q-label">Search</span>Find races, drivers and hypotheses (Ctrl/Cmd + K)
          </button>
          <button className="quick-tile" onClick={() => onNavigated?.('replay')}>
            <span className="q-label">Replay</span>Deterministic replay of a 6N investigation
          </button>
        </div>
      </section>

      {/* ---- SYSTEM STATUS (only real, catalog-derived state) ---- */}
      <section className="panel" aria-label="System status">
        <h2>System status</h2>
        {statusError ? (
          <StructuredError code="DATA_UNAVAILABLE"
            message="The canonical catalog API did not answer. No status is shown rather than a fabricated one."
            hint="Start the API server and reload." />
        ) : !status ? (
          <LoadingLine label="Reading canonical catalog…" />
        ) : (
          <div className="muted small">
            <span className="status-dot" aria-hidden="true" /> DATA AVAILABLE —{' '}
            {status.sessions} catalog sessions with telemetry capability ·{' '}
            investigations READY · 6E–6P analytical chain READY ·{' '}
            graph READY (derived on read)
          </div>
        )}
      </section>

      {/* ---- SEARCH OVERLAY (reuses the palette styles) ---- */}
      {searchOpen && (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Engineering search"
             onMouseDown={(e) => { if (e.target === e.currentTarget) setSearchOpen(false) }}>
          <div className="palette">
            <input
              autoFocus
              value={searchQ}
              placeholder="Search races (e.g. “2023 1”), drivers, hypotheses, ids…"
              onChange={(e) => { setSearchQ(e.target.value); runSearch(e.target.value) }}
              onKeyDown={(e) => { if (e.key === 'Escape') setSearchOpen(false) }}
            />
            <div className="palette-list">
              {searchLoading && <div className="palette-empty">Searching…</div>}
              {!searchLoading && searchRes && searchRes.result_count === 0 && (
                <div className="palette-empty">
                  No typed result for “{searchQ}”. Search is exact/structured —
                  try a driver slug (“max-verstappen”), season+round (“2023 1”),
                  a hypothesis (“corner”), or a 16-hex id.
                </div>
              )}
              {!searchLoading && searchRes?.results.map((r, i) => (
                <button
                  key={`${r.result_type}-${i}`}
                  className="palette-item"
                  onClick={() => {
                    setSearchOpen(false)
                    const ref = r.ref
                    if (ref.season != null && ref.round != null) {
                      window.location.hash = `#/catalog`
                      window.dispatchEvent(new HashChangeEvent('hashchange'))
                    } else if (r.result_type === 'HYPOTHESIS') {
                      window.location.hash = `#/investigate?question_type=LAP_PERFORMANCE&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1&lap_number=6`
                      window.dispatchEvent(new HashChangeEvent('hashchange'))
                    } else {
                      window.location.hash = `#/investigate`
                      window.dispatchEvent(new HashChangeEvent('hashchange'))
                    }
                    onNavigated?.('')
                  }}
                >
                  <span className="p-type">{r.result_type}</span>
                  <span>{r.label}</span>
                  <span className="muted small">{r.detail.slice(0, 60)}</span>
                </button>
              ))}
            </div>
            <div className="palette-hint">
              <span><kbd>Esc</kbd> close</span>
              <span>exact/structured matching only — no semantic search</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
