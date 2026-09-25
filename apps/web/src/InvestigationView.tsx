import { useCallback, useState } from 'react'

/* ============ 6N API shapes (render-only mirror of the Python contract) ============ */

interface Scope {
  season: number
  round: number
  driver_a: string
  driver_b: string
  lap_number: number | null
  stint_number: number | null
  session_type: string
  pattern_id: string | null
}

interface Question {
  type: string
  scope: Scope
}

interface LedgerItem {
  evidence_id: string
  evidence_type: string
  source_phase: string
  source_tool: string
  source_hash: string
  claim: string
  claim_class: string
  measured_value: number | null
  units: string | null
  state: string | null
  hypothesis_ids: string[]
  assumptions: string[]
  limitations: string[]
  supports: boolean
  contradicts: boolean
}

interface HypothesisEvaluation {
  hypothesis_id: string
  requested: boolean
  aggregate_state: string
  supporting_evidence: string[]
  contradicting_evidence: string[]
  non_decisive_evidence: string[]
  evidence_coverage: {
    items_total: number
    supporting: number
    contradicting: number
    non_decisive: number
  }
  falsification_status: string
  unresolved_contradictions: boolean
}

interface Gate {
  any_unresolved_contradictions: boolean
  establishable_hypotheses: string[]
  hypotheses_with_unresolved_contradictions: string[]
  rule: string
}

interface TraceEntry {
  trace_id: string
  statement: string
  basis: string[]
  type: string
  supporting_hypotheses: string[]
  contradictory_evidence: string[]
  status: string
}

interface Conflict {
  conflict_id: string
  evidence_ids: string[]
  hypothesis_ids: string[]
  conflict_type: string
  description: string
  resolution_status: string
}

interface CfCandidate {
  candidate_id: string
  kind: string
  status: string
  reason: string
  model_scope: string
  required_data: string[]
  missing_data: string[]
  telemetry_required: boolean
  baseline_available: boolean
}

interface CfExecuted {
  candidate_id: string
  kind: string
  baseline: string
  intervention: { type: string; fraction: number }
  parameter: { signal: string; fraction: number }
  model: string
  result: Record<string, unknown>
  delta_s: number | null
  claim_class: string
  epistemics: string
}

interface Synthesis {
  question_restated: Question
  established_facts: Array<{
    evidence_id: string
    claim: string
    measured_value: number | null
    units: string | null
  }>
  measured_findings: Array<{
    evidence_id: string
    claim: string
    measured_value: number | null
    units: string | null
    method: string
  }>
  hypothesis_findings: Record<string, {
    aggregate_state: string
    falsification_status: string
  }>
  contradictory_evidence: Array<{
    evidence_id: string
    hypothesis_id: string
    note: string
  }>
  unavailable_evidence: Array<{ kind: string; note: string }>
  counterfactual_findings: Array<{
    candidate_id: string
    kind: string
    delta_s: number | null
    claim_class: string
    epistemics: string
    hypothesis_ids: string[]
  }>
  unresolved_questions: string[]
  conclusion_state: string
  limitations: string[]
  decision_trace_refs: string[]
}

interface Snapshot {
  input: Record<string, unknown>
  evidence_ids: string[]
  evidence_source_hashes: string[]
  hypothesis_states: Record<string, string>
  counterfactual_ids: string[]
}

interface InvestigationResult {
  status: string
  reason?: string
  question: Question
  investigation_id: string
  investigation_version: string
  hypotheses_in_scope: string[]
  evidence_plan: string[]
  evidence_ledger: LedgerItem[]
  collection: Record<string, unknown>
  hypothesis_evaluations: Record<string, HypothesisEvaluation>
  falsification_gate: Gate
  evidence_conflicts: Conflict[]
  counterfactual_candidates: CfCandidate[]
  executed_counterfactuals: CfExecuted[]
  synthesis: Synthesis
  decision_trace: TraceEntry[]
  investigation_snapshot: Snapshot
  provenance: {
    analytical_chain: string[]
    method: string
    investigation_version: string
    layers_executed: string[]
    provider: string
    source_tables: string[]
  }
  limitations: string[]
  epistemic_boundaries: string[]
  output_hash: string
}

/* ================= state styling (existing ef-* vocabulary) ================= */

const STATE_CLASS: Record<string, string> = {
  SUPPORTED: 'ef-supported',
  PARTIALLY_SUPPORTED: 'ef-supported',
  NOT_SUPPORTED: 'ef-contradicted',
  CONTRADICTED: 'ef-contradicted',
  MIXED_EVIDENCE: 'ef-contradicted',
  INSUFFICIENT_EVIDENCE: 'ef-untestable',
  NOT_TESTABLE: 'ef-untestable',
  NOT_REQUESTED: 'ef-untestable',
  UNAVAILABLE: 'ef-untestable',
  TELEMETRY_UNAVAILABLE: 'ef-untestable',
  UNSUPPORTED_MODEL: 'ef-untestable',
  ELIGIBLE: 'ef-supported',
  INELIGIBLE: 'ef-contradicted',
  SUPPORTED_BY_AVAILABLE_EVIDENCE: 'ef-supported',
}

function Chip({ state }: { state: string | null }) {
  if (!state) return null
  return (
    <span className={`ef-badge ${STATE_CLASS[state] || 'ef-untestable'}`}>
      {state.replace(/_/g, ' ')}
    </span>
  )
}

const HYP_LABELS: Record<string, string> = {
  H1_corner_speed: 'H1 corner speed',
  H2_throttle: 'H2 throttle',
  H3_braking: 'H3 braking',
  H4_tyre_state: 'H4 tyre state',
  H5_race_control: 'H5 race control',
  H6_drs: 'H6 DRS',
}

const QUESTION_TYPES = [
  'LAP_PERFORMANCE',
  'STINT_PERFORMANCE',
  'RACE_GAP',
  'PERFORMANCE_REGIME',
  'CROSS_RACE_PATTERN',
  'HYPOTHESIS_EVALUATION',
  'COUNTERFACTUAL_ELIGIBILITY',
]

const QUESTION_INPUTS: Record<string, Array<'lap_number' | 'stint_number' | 'pattern_id'>> = {
  LAP_PERFORMANCE: ['lap_number'],
  STINT_PERFORMANCE: ['stint_number'],
  RACE_GAP: [],
  PERFORMANCE_REGIME: [],
  CROSS_RACE_PATTERN: ['pattern_id'],
  HYPOTHESIS_EVALUATION: ['lap_number'],
  COUNTERFACTUAL_ELIGIBILITY: [],
}

/* ================= component ================= */

export default function InvestigationView() {
  const [questionType, setQuestionType] = useState('STINT_PERFORMANCE')
  const [season, setSeason] = useState(2023)
  const [round, setRound] = useState(1)
  const [driverA, setDriverA] = useState('max-verstappen')
  const [driverB, setDriverB] = useState('sergio-perez')
  const [lapNumber, setLapNumber] = useState(6)
  const [stintNumber, setStintNumber] = useState(1)
  const [patternId, setPatternId] = useState('')
  const [result, setResult] = useState<InvestigationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openTrace, setOpenTrace] = useState<string | null>(null)

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    setOpenTrace(null)
    try {
      const params = new URLSearchParams({
        question_type: questionType,
        driver_a: driverA.trim(),
        driver_b: driverB.trim(),
        season: String(season),
        round: String(round),
      })
      const inputs = QUESTION_INPUTS[questionType] || []
      if (inputs.includes('lap_number')) params.set('lap_number', String(lapNumber))
      if (inputs.includes('stint_number')) params.set('stint_number', String(stintNumber))
      if (inputs.includes('pattern_id') && patternId.trim()) {
        params.set('pattern_id', patternId.trim())
      }
      const resp = await fetch(`/api/catalog/engineering-investigation?${params}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Investigation request failed (${resp.status})`)
      }
      const j = (await resp.json()) as InvestigationResult
      if (j.status !== 'VALID') throw new Error(j.reason || `status ${j.status}`)
      setResult(j)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [questionType, season, round, driverA, driverB, lapNumber, stintNumber, patternId])

  return (
    <div className="panel">
      <h2>Phase 6N — Engineering Investigation &amp; Decision Trace</h2>
      <p className="muted small">
        Deterministic orchestration of the verified 6E–6M analytical chain for one
        structured engineering question. Every synthesis statement carries a decision
        trace to evidence IDs. Hypotheses are never ranked and no &quot;most likely
        cause&quot; is produced: contradictions block an established explanation,
        counterfactuals stay MODELLED sensitivity (not history, not prediction), and
        missing evidence stays missing. SUPPORT is not PROOF.
      </p>

      <div className="controls">
        <label>
          question type:{' '}
          <select value={questionType} onChange={(e) => setQuestionType(e.target.value)}>
            {QUESTION_TYPES.map((q) => (
              <option key={q} value={q}>{q}</option>
            ))}
          </select>
        </label>
        <label>
          season:{' '}
          <input type="number" min={1950} max={2100} value={season}
                 onChange={(e) => setSeason(Number(e.target.value))} style={{ width: 80 }} />
        </label>
        <label>
          round:{' '}
          <input type="number" min={1} max={99} value={round}
                 onChange={(e) => setRound(Number(e.target.value))} style={{ width: 60 }} />
        </label>
        <label>
          driver A:{' '}
          <input type="text" value={driverA} onChange={(e) => setDriverA(e.target.value)}
                 style={{ width: 150 }} />
        </label>
        <label>
          driver B:{' '}
          <input type="text" value={driverB} onChange={(e) => setDriverB(e.target.value)}
                 style={{ width: 150 }} />
        </label>
        {(QUESTION_INPUTS[questionType] || []).includes('lap_number') && (
          <label>
            lap:{' '}
            <input type="number" min={1} value={lapNumber}
                   onChange={(e) => setLapNumber(Number(e.target.value))} style={{ width: 60 }} />
          </label>
        )}
        {(QUESTION_INPUTS[questionType] || []).includes('stint_number') && (
          <label>
            stint:{' '}
            <input type="number" min={1} value={stintNumber}
                   onChange={(e) => setStintNumber(Number(e.target.value))} style={{ width: 60 }} />
          </label>
        )}
        {(QUESTION_INPUTS[questionType] || []).includes('pattern_id') && (
          <input type="text" placeholder="pattern_id from Phase 6L view"
                 value={patternId} onChange={(e) => setPatternId(e.target.value)}
                 style={{ minWidth: 220 }} />
        )}
        <button onClick={run} disabled={loading}>
          {loading ? 'Investigating…' : 'Run investigation'}
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div>
          <p className="muted small">
            investigation <code>{result.investigation_id}</code> ·{' '}
            {result.question.type} · {result.evidence_ledger.length} evidence items ·{' '}
            conclusion <Chip state={result.synthesis.conclusion_state} /> · hash{' '}
            <code>{result.output_hash}</code>
          </p>
          <p className="muted small">evidence plan: {result.evidence_plan.join(' → ')}</p>

          {/* ---------- HYPOTHESES ---------- */}
          <h3>Hypotheses (never ranked)</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Hypothesis</th>
                <th>State</th>
                <th>Support</th>
                <th>Contradict</th>
                <th>Non-decisive</th>
                <th>Falsification</th>
              </tr>
            </thead>
            <tbody>
              {Object.values(result.hypothesis_evaluations).map((h) => (
                <tr key={h.hypothesis_id}>
                  <td className="small">{HYP_LABELS[h.hypothesis_id] || h.hypothesis_id}</td>
                  <td><Chip state={h.aggregate_state} /></td>
                  <td>{h.evidence_coverage.supporting}</td>
                  <td>{h.evidence_coverage.contradicting}</td>
                  <td>{h.evidence_coverage.non_decisive}</td>
                  <td className="small">
                    {h.unresolved_contradictions ? 'unresolved contradictions' : h.falsification_status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">{result.falsification_gate.rule}</p>
          {result.falsification_gate.hypotheses_with_unresolved_contradictions.length > 0 && (
            <p className="muted small">
              blocked from established synthesis:{' '}
              {result.falsification_gate.hypotheses_with_unresolved_contradictions
                .map((h) => HYP_LABELS[h] || h).join(', ')}
            </p>
          )}

          {/* ---------- EVIDENCE LEDGER ---------- */}
          <h3>Evidence ledger ({result.evidence_ledger.length})</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type / class</th>
                <th>Source</th>
                <th>Claim</th>
                <th>Value</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {result.evidence_ledger.map((it) => (
                <tr key={it.evidence_id}>
                  <td className="small">{it.evidence_id}</td>
                  <td className="small">{it.evidence_type} · {it.claim_class}</td>
                  <td className="muted small" title={`source hash ${it.source_hash}`}>
                    {it.source_phase} {it.source_tool}
                  </td>
                  <td className="small">
                    {it.claim}
                    {it.contradicts && <Chip state="CONTRADICTED" />}
                    {it.supports && !it.contradicts && <Chip state="SUPPORTED" />}
                  </td>
                  <td className="small">
                    {it.measured_value != null ? `${it.measured_value} ${it.units ?? ''}` : '—'}
                  </td>
                  <td><Chip state={it.state} /></td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* ---------- CONTRADICTIONS ---------- */}
          {result.evidence_conflicts.length > 0 && (
            <div>
              <h3>Preserved contradictions ({result.evidence_conflicts.length})</h3>
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Hypotheses</th>
                    <th>Type</th>
                    <th>Description</th>
                    <th>Resolution</th>
                  </tr>
                </thead>
                <tbody>
                  {result.evidence_conflicts.map((c) => (
                    <tr key={c.conflict_id}>
                      <td className="small">{c.conflict_id}</td>
                      <td className="small">
                        {c.hypothesis_ids.map((h) => HYP_LABELS[h] || h).join(', ')}
                      </td>
                      <td className="small">{c.conflict_type}</td>
                      <td className="small">{c.description}</td>
                      <td className="small">{c.resolution_status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* ---------- COUNTERFACTUALS ---------- */}
          <h3>Counterfactuals</h3>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Kind</th>
                <th>State</th>
                <th>Reason</th>
                <th>Δ (modelled)</th>
              </tr>
            </thead>
            <tbody>
              {result.counterfactual_candidates.map((c) => {
                const exec = result.executed_counterfactuals.find(
                  (x) => x.candidate_id === c.candidate_id,
                )
                return (
                  <tr key={c.candidate_id}>
                    <td className="small"><code>{c.candidate_id}</code></td>
                    <td className="small">{c.kind}</td>
                    <td><Chip state={c.status} /></td>
                    <td className="muted small">{c.reason}</td>
                    <td className="small">
                      {exec
                        ? `${exec.delta_s} s — ${exec.claim_class}: ${exec.epistemics}`
                        : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {/* ---------- SYNTHESIS ---------- */}
          <h3>Synthesis</h3>
          <p>
            conclusion state: <Chip state={result.synthesis.conclusion_state} />
          </p>
          <table className="catalog-table">
            <tbody>
              <tr>
                <th>Established facts</th>
                <td className="small">
                  {result.synthesis.established_facts.map((f) => (
                    <div key={f.evidence_id}>
                      {f.claim} = {f.measured_value} {f.units}{' '}
                      <span className="muted">[{f.evidence_id}]</span>
                    </div>
                  ))}
                  {result.synthesis.established_facts.length === 0 && <span className="muted">none</span>}
                </td>
              </tr>
              <tr>
                <th>Measured findings</th>
                <td className="small">
                  {result.synthesis.measured_findings.map((f) => (
                    <div key={f.evidence_id}>
                      {f.claim} = {f.measured_value != null ? f.measured_value : '—'} {f.units}{' '}
                      <span className="muted">[{f.evidence_id} · {f.method}]</span>
                    </div>
                  ))}
                  {result.synthesis.measured_findings.length === 0 && <span className="muted">none</span>}
                </td>
              </tr>
              <tr>
                <th>Hypothesis findings</th>
                <td className="small">
                  {Object.entries(result.synthesis.hypothesis_findings).map(([h, f]) => (
                    <div key={h}>
                      {HYP_LABELS[h] || h}: <Chip state={f.aggregate_state} />{' '}
                      <span className="muted">{f.falsification_status}</span>
                    </div>
                  ))}
                </td>
              </tr>
              <tr>
                <th>Counterfactual findings</th>
                <td className="small">
                  {result.synthesis.counterfactual_findings.map((f) => (
                    <div key={f.candidate_id}>
                      {f.kind}: {f.delta_s} s <Chip state={f.claim_class} />{' '}
                      <span className="muted">{f.epistemics}</span>
                    </div>
                  ))}
                  {result.synthesis.counterfactual_findings.length === 0 && <span className="muted">none executed</span>}
                </td>
              </tr>
              <tr>
                <th>Unavailable</th>
                <td className="small">
                  {result.synthesis.unavailable_evidence.map((u, i) => (
                    <div key={i}>{u.kind}: <span className="muted">{u.note}</span></div>
                  ))}
                  {result.synthesis.unavailable_evidence.length === 0 && <span className="muted">none</span>}
                </td>
              </tr>
              <tr>
                <th>Unresolved</th>
                <td className="small">
                  {result.synthesis.unresolved_questions.map((u, i) => (
                    <div key={i}>{u}</div>
                  ))}
                  {result.synthesis.unresolved_questions.length === 0 && <span className="muted">none</span>}
                </td>
              </tr>
            </tbody>
          </table>

          {/* ---------- DECISION TRACE ---------- */}
          <h3>Decision trace ({result.decision_trace.length}) — statement → evidence → source</h3>
          <ul className="ef-chain">
            {result.decision_trace.map((t) => (
              <li key={t.trace_id}>
                <button
                  className="linklike"
                  onClick={() => setOpenTrace(openTrace === t.trace_id ? null : t.trace_id)}
                >
                  {t.trace_id}
                </button>{' '}
                <span className="small">{t.statement}</span>{' '}
                <Chip state={t.status} />
                {openTrace === t.trace_id && (
                  <div className="cf-intervention">
                    <div><strong>type:</strong> {t.type}</div>
                    <div><strong>basis:</strong> {t.basis.join(', ')}</div>
                    {t.supporting_hypotheses.length > 0 && (
                      <div>
                        <strong>hypotheses:</strong>{' '}
                        {t.supporting_hypotheses.map((h) => HYP_LABELS[h] || h).join(', ')}
                      </div>
                    )}
                    {t.contradictory_evidence.length > 0 && (
                      <div>
                        <strong>contradicting:</strong> {t.contradictory_evidence.join(', ')}
                      </div>
                    )}
                    {t.basis.map((eid) => {
                      const item = result.evidence_ledger.find((x) => x.evidence_id === eid)
                      if (!item) return null
                      return (
                        <div key={eid} className="muted small">
                          {eid}: {item.evidence_type}/{item.claim_class} via {item.source_phase}{' '}
                          {item.source_tool} (source hash <code>{item.source_hash}</code>)
                          {item.measured_value != null &&
                            ` · measured ${item.measured_value} ${item.units ?? ''}`}
                          {item.limitations.length > 0 && ` · limits: ${item.limitations.join('; ')}`}
                        </div>
                      )
                    })}
                  </div>
                )}
              </li>
            ))}
          </ul>

          {/* ---------- SNAPSHOT / PROVENANCE / BOUNDARIES ---------- */}
          <h3>Provenance &amp; replay</h3>
          <p className="muted small">
            provenance chain: {result.provenance.analytical_chain.join(' → ')} ·{' '}
            layers executed: {result.provenance.layers_executed.join(', ')} ·{' '}
            {result.investigation_snapshot.evidence_ids.length} evidence refs ·{' '}
            {result.investigation_snapshot.counterfactual_ids.length} counterfactual refs
          </p>
          <p className="muted small">method: {result.provenance.method}</p>
          <ul className="muted small">
            {result.epistemic_boundaries.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
