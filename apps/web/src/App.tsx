import { useState, useEffect } from 'react'
import './App.css'
import CatalogExplorer from './CatalogExplorer'
import TelemetryView from './TelemetryView'
import AttributionView from './AttributionView'
import EvidenceFusionView from './EvidenceFusionView'
import StintEvidenceView from './StintEvidenceView'
import RaceGapView from './RaceGapView'
import CounterfactualView from './CounterfactualView'
import PerformanceEnvelopeView from './PerformanceEnvelopeView'
import PerformanceRegimeView from './PerformanceRegimeView'
import PerformancePatternView from './PerformancePatternView'

interface Session {
  year: number
  event: string
  session_type: string
  label: string
  session_key: string
  availability: string
}

interface Hypothesis {
  id: string
  statement: string
  status: string
  confidence: number
  supporting_evidence: string[]
  contradicting_evidence: string[]
}

interface EvidenceItem {
  id: string
  type: string
  statement: string
  strength: number
}

interface CounterfactualItem {
  id: string
  intervention: string
  predicted_delta_s: number | null
  uncertainty_s: number | null
  assumptions: string[]
  simulator_version: string
}

interface GraphNode {
  id: string
  type: string
  label: string
  full_statement: string
  strength: number
  evidence_type: string
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

interface GraphEdge {
  id: string
  source: string
  target: string
  relationship: string
  provenance?: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

interface ConclusionItem {
  statement: string
  confidence: number
  evidence_ids: string[]
  limitations: string[]
}

interface ToolExec {
  id: string
  tool: string
  status: string
  duration_ms: number | null
  input_hash: string
  output_hash: string
}

interface Investigation {
  investigation_id: string
  question: string
  state: string
  hypotheses: Hypothesis[]
  evidence: EvidenceItem[]
  counterfactuals: CounterfactualItem[]
  conclusion: ConclusionItem | null
  tool_executions: ToolExec[]
}

interface TraceEntry {
  type: string
  payload: Record<string, unknown>
  timestamp: string
}

const FAILURE_STATES = new Set(['DATA_UNAVAILABLE', 'TOOL_FAILURE', 'MODEL_FAILURE', 'INSUFFICIENT_EVIDENCE'])

function friendlyType(t: string): string {
  return t.replaceAll('.', ' ').replaceAll('_', ' ')
}

interface CatalogSessionRef {
  season: number
  round: number
  session_type: string
  race_name: string | null
}

const CATALOG_TO_FASTF1: Record<string, string> = {
  RACE: 'R',
  QUALIFYING: 'Q',
  SPRINT: 'S',
  SPRINT_QUALIFYING: 'SQ',
  FREE_PRACTICE_1: 'FP1',
  FREE_PRACTICE_2: 'FP2',
  FREE_PRACTICE_3: 'FP3',
  FREE_PRACTICE_4: 'FP4',
}

function catalogEventName(raceName: string | null): string {
  // Derive the FastF1 event selector from the canonical race name
  // (e.g. "Formula 1 Gulf Air Bahrain Grand Prix 2023" -> "Bahrain").
  if (!raceName) return 'Bahrain'
  const words = raceName
    .replace(/\d{4}/g, '')
    .replace(/Formula 1|F1|Grand Prix|GP|Heuer|Louis Vuitton|Crypto|AWS|Qatar/gi, '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  const candidate = words[words.length - 1] || 'Bahrain'
  return candidate
}

export default function App() {
  const [question, setQuestion] = useState('Why did VER lose pace during the second stint, and would an earlier pit stop have changed the outcome?')
  const [investigation, setInvestigation] = useState<Investigation | null>(null)
  const [trace, setTrace] = useState<TraceEntry[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [catalogSession, setCatalogSession] = useState<CatalogSessionRef | null>(null)
  const [selectedSession, setSelectedSession] = useState<Session | null>(null)
  const [drivers, setDrivers] = useState<string[]>([])
  const [selectedDriver, setSelectedDriver] = useState('VER')

  useEffect(() => {
    async function loadSessions() {
      try {
        const resp = await fetch('/api/sessions')
        if (resp.ok) {
          const data = await resp.json()
          setSessions(data.sessions || [])
          if (data.sessions && data.sessions.length > 0) {
            // Prefer a catalog-selected session, else the first available.
            const target = catalogSession
              ? data.sessions.find(
                  (s: Session) =>
                    s.year === catalogSession.season && s.session_type === catalogSession.session_type,
                )
              : undefined
            const fallback = data.sessions.find((s: Session) => s.event === 'Bahrain') || data.sessions[0]
            setSelectedSession(target || fallback)
          }
        }
      } catch (e) {
        console.error('Failed to load sessions:', e)
      }
    }
    loadSessions()
  }, [])

  useEffect(() => {
    const sessionKey = selectedSession?.session_key
    if (sessionKey) {
      async function loadDrivers() {
        try {
          const resp = await fetch(`/api/sessions/${sessionKey}/drivers`)
          if (resp.ok) {
            const data = await resp.json()
            setDrivers(data.drivers || [])
            if (data.drivers && data.drivers.length > 0) {
              setSelectedDriver(data.drivers.includes('VER') ? 'VER' : data.drivers[0])
            }
          }
        } catch (e) {
          console.error('Failed to load drivers:', e)
        }
      }
      loadDrivers()
    }
  }, [selectedSession?.session_key])

  async function runInvestigation() {
    if (!selectedSession || !selectedDriver) return
    
    setRunning(true)
    setError(null)
    setTrace([])
    setInvestigation(null)
    try {
      const createResp = await fetch('/api/investigations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          question, 
          year: selectedSession.year, 
          event: selectedSession.event, 
          driver: selectedDriver,
          session_type: selectedSession.session_type
        }),
      })
      if (!createResp.ok) throw new Error(`Create failed: ${createResp.status}`)
      const { investigation_id: invId } = await createResp.json()

      const streamResp = await fetch(`/api/investigations/${invId}/stream`)
      if (!streamResp.body) throw new Error('No stream')
      const reader = streamResp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const entries: TraceEntry[] = []
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''
        for (const part of parts) {
          if (!part.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(part.slice(6))
            if (evt.type === 'investigation.started') continue
            if (evt.type === 'done') continue
            entries.push(evt as TraceEntry)
            setTrace([...entries])
          } catch { /* partial chunk */ }
        }
      }

      const detailResp = await fetch(`/api/investigations/${invId}`)
      const detail = await detailResp.json()
      setInvestigation(detail)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const [_graphData, _setGraphData] = useState<GraphData>({ nodes: [], edges: [] })

  async function _loadEvidenceGraph(invId: string) {
    try {
      const resp = await fetch(`/api/investigations/${invId}/evidence-graph`)
      if (resp.ok) {
        const data = await resp.json()
        const nodesWithPos = data.nodes.map((node: GraphNode, i: number) => ({
          ...node,
          x: 400 + Math.cos((i / Math.max(1, data.nodes.length)) * 2 * Math.PI) * 200,
          y: 300 + Math.sin((i / Math.max(1, data.nodes.length)) * 2 * Math.PI) * 200,
        }))
        _setGraphData({ nodes: nodesWithPos, edges: data.edges })
      }
    } catch (e) {
      console.error('Failed to load evidence graph:', e)
    }
  }

  const _getNodeColor = (type: string) => {
    switch (type) {
      case 'FACT': return '#2e7d32'
      case 'CALCULATION': return '#1565c0'
      case 'INFERENCE': return '#f57f17'
      case 'COUNTERFACTUAL': return '#6a1b9a'
      case 'ASSUMPTION': return '#c62828'
      default: return '#424242'
    }
  }

  const _getEdgeColor = (relationship: string) => {
    switch (relationship) {
      case 'SUPPORTS': return '#2e7d32'
      case 'CONTRADICTS': return '#c62828'
      case 'DERIVES_FROM': return '#1565c0'
      case 'INFORMS': return '#f57f17'
      case 'CONSTRAINS': return '#6a1b9a'
      default: return '#757575'
    }
  }

  // Suppress unused variable warnings for future implementation
  void _loadEvidenceGraph
  void _getNodeColor
  void _getEdgeColor

  return (
    <div className="app">
      <header>
        <h1>RACE<span>WISE</span></h1>
        <span className="tagline">Autonomous evidence-driven race engineering — investigations, not answers</span>
      </header>

      <CatalogExplorer
        onInvestigate={(session) => {
          // Catalog → Investigation handoff: derive the FastF1 selector from
          // canonical identity. No hardcoded race.
          const fastf1Code = CATALOG_TO_FASTF1[session.session_type] || 'R'
          void catalogEventName(session.race_name)
          const match = sessions.find(
            (s) => s.year === session.season && s.session_type === fastf1Code,
          )
          if (match) {
            setSelectedSession(match)
          } else {
            setCatalogSession({
              season: session.season,
              round: session.round,
              session_type: fastf1Code,
              race_name: session.race_name,
            })
            setError(
              `Session ${session.season} R${session.round} is in the canonical catalog but not yet ` +
              'in the FastF1 investigation session list. Ingest it via the data CLI to investigate.',
            )
          }
        }}
      />

      <TelemetryView />

      <AttributionView />

      <EvidenceFusionView />

      <StintEvidenceView />

      <RaceGapView />

      <CounterfactualView />

      <PerformanceEnvelopeView />

      <PerformanceRegimeView />

      <PerformancePatternView />

      <div className="controls">
        <div className="session-selector">
          <label>Session:</label>
          <select 
            value={selectedSession?.session_key || ''} 
            onChange={(e) => {
              const session = sessions.find(s => s.session_key === e.target.value)
              setSelectedSession(session || null)
            }}
            disabled={running}
          >
            {sessions.map(s => (
              <option key={s.session_key} value={s.session_key}>
                {s.label} {s.availability !== 'AVAILABLE' ? ` (${s.availability})` : ''}
              </option>
            ))}
          </select>
        </div>
        
        <div className="driver-selector">
          <label>Driver:</label>
          <select 
            value={selectedDriver} 
            onChange={(e) => setSelectedDriver(e.target.value)}
            disabled={running || drivers.length === 0}
          >
            {drivers.map(d => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>

        <div className="question-input">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask an engineering question..."
          />
          <button onClick={runInvestigation} disabled={running || question.trim().length < 5 || !selectedSession || !selectedDriver}>
            {running ? 'Investigating...' : 'Investigate'}
          </button>
        </div>
      </div>

      {error && <div className="panel">Error: {error}</div>}

      <div className="grid">
        <div>
          <section className="panel">
            <h2>
              Investigation Trace
              {investigation && (
                <span className={FAILURE_STATES.has(investigation.state) ? 'state-pill failure' : investigation.state === 'COMPLETED' ? 'state-pill completed' : 'state-pill'}>
                  {investigation.state}
                </span>
              )}
            </h2>
            {trace.length === 0 && <p className="muted">No active investigation.</p>}
            {trace.map((entry, i) => (
              <div key={i} className="trace-entry">
                <span className="time">{new Date(entry.timestamp).toLocaleTimeString()}</span>
                {friendlyType(entry.type)}
                {entry.payload && typeof entry.payload === 'object' && 'tool' in entry.payload && (
                  <span> — {String((entry.payload as { tool?: string }).tool)}</span>
                )}
                {entry.type === 'state.changed' && typeof (entry.payload as { state?: string }).state === 'string' && (
                  <strong> → {String((entry.payload as { state: string }).state)}</strong>
                )}
              </div>
            ))}
          </section>

          {investigation?.conclusion && (
            <section className="panel">
              <h2>Engineering Report</h2>
              <div className="conclusion">{investigation.conclusion.statement}</div>
              <h3 className="subhead">Limitations</h3>
              <ul className="limitations">
                {investigation.conclusion.limitations.map((lim, i) => (
                  <li key={i}>{lim}</li>
                ))}
              </ul>
            </section>
          )}

          {investigation && investigation.counterfactuals.length > 0 && (
            <section className="panel">
              <h2>Counterfactual Lab</h2>
              {investigation.counterfactuals.map((cf) => (
                <div key={cf.id} className="cf-card">
                  <div className="cf-label">COUNTERFACTUAL — {cf.intervention}</div>
                  <div className="cf-delta">
                    {cf.predicted_delta_s !== null && cf.predicted_delta_s > 0 ? '+' : ''}
                    {cf.predicted_delta_s?.toFixed(2)}s ± {cf.uncertainty_s?.toFixed(2)}s
                  </div>
                  <ul className="assumptions-list">
                    {cf.assumptions.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                  <p className="muted small">Under the stated assumptions, the model estimates this delta. Simulator v{cf.simulator_version}. Not an observed result.</p>
                </div>
              ))}
            </section>
          )}
        </div>

        <div>
          <section className="panel">
            <h2>Evidence Graph</h2>
            {investigation ? (
              <canvas
                width={800}
                height={500}
                style={{ border: '1px solid #ddd', borderRadius: '4px', background: '#fafafa', width: '100%', height: 'auto', maxWidth: '800px' }}
              />
            ) : (
              <p className="muted">Run an investigation to see the evidence graph.</p>
            )}
          </section>
        </div>

        <div>
          <section className="panel">
            <h2>Hypothesis Board</h2>
            {investigation?.hypotheses.map((hyp) => (
              <div key={hyp.id} className="hypothesis-card">
                <div className="statement">
                  <strong>{hyp.id}</strong> — {hyp.statement}
                </div>
                <div>
                  <span className={`status status-${hyp.status.toLowerCase()}`}>{hyp.status}</span>
                </div>
                <div className="confidence-bar">
                  <div style={{ width: `${hyp.confidence * 100}%` }} />
                </div>
                <div className="muted small">
                  {hyp.supporting_evidence.length > 0 && <span>{hyp.supporting_evidence.length} supporting · </span>}
                  {hyp.contradicting_evidence.length > 0 && <span>{hyp.contradicting_evidence.length} contradicting</span>}
                </div>
              </div>
            ))}
            {!investigation && <p className="muted">Hypotheses appear here after an investigation runs.</p>}
          </section>

          <section className="panel">
            <h2>Evidence Log</h2>
            {investigation?.evidence.map((ev) => (
              <div key={ev.id} className="evidence-item">
                <span className={`evidence-tag tag-${ev.type}`}>{ev.type}</span>
                {ev.statement}
              </div>
            ))}
            {!investigation && <p className="muted">Evidence appears here with its taxonomy label.</p>}
          </section>

          <section className="panel">
            <h2>Tool Executions & Provenance</h2>
            {investigation?.tool_executions.map((te) => (
              <div key={te.id} className="tool-exec">
                <span>{te.tool} <span className={te.status === 'completed' ? 'ok' : 'fail'}>[{te.status}]</span></span>
                <span>
                  {te.duration_ms !== null ? `${te.duration_ms}ms ` : ''}
                  <span className="hash">{te.output_hash?.slice(0, 10)}</span>
                </span>
              </div>
            ))}
            {!investigation && <p className="muted">Every tool call is hashed and traceable.</p>}
          </section>
        </div>
      </div>
    </div>
  )
}