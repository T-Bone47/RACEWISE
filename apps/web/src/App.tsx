import { useState } from 'react'
import './App.css'

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

export default function App() {
  const [question, setQuestion] = useState('Why did VER lose pace during the second stint, and would an earlier pit stop have changed the outcome?')
  const [investigation, setInvestigation] = useState<Investigation | null>(null)
  const [trace, setTrace] = useState<TraceEntry[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function runInvestigation() {
    setRunning(true)
    setError(null)
    setTrace([])
    setInvestigation(null)
    try {
      const createResp = await fetch('/api/investigations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, year: 2023, event: 'Bahrain', driver: 'VER' }),
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

  return (
    <div className="app">
      <header>
        <h1>RACE<span>WISE</span></h1>
        <span className="tagline">Autonomous evidence-driven race engineering — investigations, not answers</span>
      </header>

      <div className="controls">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask an engineering question..."
        />
        <button onClick={runInvestigation} disabled={running || question.trim().length < 5}>
          {running ? 'Investigating...' : 'Investigate'}
        </button>
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
            <h2>Tool Executions &amp; Provenance</h2>
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
