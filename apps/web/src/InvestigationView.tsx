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

interface ReplayResult {
  status: string
  identical: boolean
  original_hash: string
  replay_hash: string | null
  difference_count: number
  differences: Array<{ path: string; old_value: unknown; new_value: unknown; category: string }>
  snapshot?: { snapshot_hash: string; investigation_id: string; output_hash: string }
}

interface MemoryItem {
  memory_id: string
  statement: string
  evidence_ids: string[]
  hypothesis_ids: string[]
  evidence_type: string
  claim_class: string
  validity_status: string
  limitations: string[]
  scope: Record<string, unknown>
}

interface MemoryResult {
  match_count: number
  matching_memory_items: MemoryItem[]
  policy: string
}

interface CompareResult {
  compatibility: { state: string; differing_scope_keys?: string[] }
  hypothesis_deltas: Array<{
    hypothesis_id: string
    old_state: string | null
    new_state: string | null
    state_changed: boolean
  }>
  falsification_deltas: Array<{ change_type: string; hypothesis_ids: string[] }>
  synthesis_delta: {
    old_conclusion_state: string | null
    new_conclusion_state: string | null
    transition: string
  }
}

/* ============ 6P graph shapes (render-only mirror of the Python contract) ============ */

interface GraphNode {
  node_id: string
  node_type: string
  label: string
  canonical_reference: Record<string, unknown>
  metadata: Record<string, unknown>
  provenance: Record<string, unknown>
}

interface GraphEdge {
  edge_id: string
  source_node: string
  target_node: string
  edge_type: string
  provenance: Record<string, unknown>
  source_reference: Record<string, unknown>
}

interface GraphResult {
  graph_version: string
  graph_id: string
  node_count: number
  edge_count: number
  nodes: GraphNode[]
  edges: GraphEdge[]
  output_hash: string
  epistemic_boundaries: string[]
}

interface GraphPathStep {
  step: string
  node_type: string
  via_edge_type: string | null
  via_edge_id: string | null
  via_provenance: Record<string, unknown> | null
}

interface GraphPathResult {
  status: string
  path?: GraphPathStep[]
  path_length?: number
  reason?: string
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

/* ============ 6P graph node/edge rendering vocabulary (closed) ============ */

const NODE_CLASS: Record<string, string> = {
  INVESTIGATION: 'gp-node-investigation',
  QUESTION: 'gp-node-question',
  DRIVER: 'gp-node-context',
  DRIVER_PAIR: 'gp-node-context',
  SEASON: 'gp-node-context',
  RACE: 'gp-node-context',
  SESSION: 'gp-node-context',
  LAP: 'gp-node-context',
  STINT: 'gp-node-context',
  REGIME: 'gp-node-context',
  PATTERN: 'gp-node-context',
  HYPOTHESIS: 'gp-node-hypothesis',
  EVIDENCE: 'gp-node-evidence',
  COUNTERFACTUAL: 'gp-node-counterfactual',
  SYNTHESIS: 'gp-node-synthesis',
  DECISION_TRACE: 'gp-node-trace',
  MEMORY: 'gp-node-memory',
  ANALYTICAL_SOURCE: 'gp-node-source',
  SNAPSHOT: 'gp-node-source',
}

const EDGE_CLASS: Record<string, string> = {
  SUPPORTS: 'gp-edge-supports',
  CONTRADICTS: 'gp-edge-contradicts',
  DERIVED_FROM: 'gp-edge-derived',
  MEASURED_BY: 'gp-edge-derived',
  MODELS: 'gp-edge-models',
  REPLAY_OF: 'gp-edge-lineage',
  COMPARED_WITH: 'gp-edge-lineage',
  GENERATED_MEMORY: 'gp-edge-memory',
  RELATED_TO: 'gp-edge-neutral',
  TESTS: 'gp-edge-neutral',
}

const GRAPH_NODE_TYPES = [
  'EVIDENCE', 'HYPOTHESIS', 'DECISION_TRACE', 'MEMORY', 'COUNTERFACTUAL',
  'SYNTHESIS', 'ANALYTICAL_SOURCE', 'RACE', 'LAP', 'STINT', 'REGIME',
  'PATTERN', 'SNAPSHOT', 'QUESTION', 'DRIVER', 'SESSION', 'SEASON',
  'DRIVER_PAIR', 'INVESTIGATION',
]

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
  const [replay, setReplay] = useState<ReplayResult | null>(null)
  const [replayLoading, setReplayLoading] = useState(false)
  const [replayError, setReplayError] = useState<string | null>(null)
  const [memory, setMemory] = useState<MemoryResult | null>(null)
  const [memoryLoading, setMemoryLoading] = useState(false)
  const [memoryError, setMemoryError] = useState<string | null>(null)
  const [compareLap, setCompareLap] = useState(11)
  const [comparison, setComparison] = useState<CompareResult | null>(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [compareError, setCompareError] = useState<string | null>(null)
  const [graph, setGraph] = useState<GraphResult | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphError, setGraphError] = useState<string | null>(null)
  const [graphTypeFilter, setGraphTypeFilter] = useState('')
  const [graphDepth, setGraphDepth] = useState(4)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [nodePath, setNodePath] = useState<GraphPathResult | null>(null)
  const [pathLoading, setPathLoading] = useState(false)

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

  const investigationInputParams = useCallback(() => {
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
    return params
  }, [questionType, season, round, driverA, driverB, lapNumber, stintNumber, patternId])

  const runReplay = useCallback(async () => {
    setReplayLoading(true)
    setReplayError(null)
    setReplay(null)
    try {
      const resp = await fetch(
        `/api/catalog/engineering-investigation/replay?${investigationInputParams()}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Replay request failed (${resp.status})`)
      }
      setReplay((await resp.json()) as ReplayResult)
    } catch (e) {
      setReplayError(e instanceof Error ? e.message : String(e))
    } finally {
      setReplayLoading(false)
    }
  }, [investigationInputParams])

  const runMemory = useCallback(async () => {
    setMemoryLoading(true)
    setMemoryError(null)
    setMemory(null)
    try {
      const params = investigationInputParams()
      params.set('driver', driverA.trim())
      const resp = await fetch(`/api/catalog/engineering-memory?${params}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Memory request failed (${resp.status})`)
      }
      setMemory((await resp.json()) as MemoryResult)
    } catch (e) {
      setMemoryError(e instanceof Error ? e.message : String(e))
    } finally {
      setMemoryLoading(false)
    }
  }, [investigationInputParams, driverA])

  const runCompare = useCallback(async () => {
    setCompareLoading(true)
    setCompareError(null)
    setComparison(null)
    try {
      const a = investigationInputParams()
      const b = new URLSearchParams(a)
      b.set('b_question_type', a.get('question_type') || '')
      b.set('b_driver_a', a.get('driver_a') || '')
      b.set('b_driver_b', a.get('driver_b') || '')
      b.set('b_season', a.get('season') || '')
      b.set('b_round', a.get('round') || '')
      if (b.get('lap_number')) b.set('b_lap_number', compareLap.toString())
      ;['question_type', 'lap_number'].forEach((k) => b.delete(k))
      const resp = await fetch(`/api/catalog/engineering-investigation/compare?${b}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Compare request failed (${resp.status})`)
      }
      setComparison((await resp.json()) as CompareResult)
    } catch (e) {
      setCompareError(e instanceof Error ? e.message : String(e))
    } finally {
      setCompareLoading(false)
    }
  }, [investigationInputParams, compareLap])

  const runGraph = useCallback(async () => {
    setGraphLoading(true)
    setGraphError(null)
    setGraph(null)
    setSelectedNode(null)
    setNodePath(null)
    try {
      const params = investigationInputParams()
      params.set('max_depth', String(graphDepth))
      const resp = await fetch(`/api/catalog/investigation-graph?${params}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Graph request failed (${resp.status})`)
      }
      setGraph((await resp.json()) as GraphResult)
    } catch (e) {
      setGraphError(e instanceof Error ? e.message : String(e))
    } finally {
      setGraphLoading(false)
    }
  }, [investigationInputParams, graphDepth])

  const openNodePath = useCallback(async (node: GraphNode) => {
    setSelectedNode(node)
    setNodePath(null)
    setPathLoading(true)
    try {
      const params = investigationInputParams()
      const key = node.node_id.includes(':')
        ? node.node_id.slice(node.node_id.indexOf(':') + 1)
        : node.node_id
      params.set('target_node_type', node.node_type)
      params.set('target_key', key)
      const resp = await fetch(`/api/catalog/investigation-graph/path?${params}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Path request failed (${resp.status})`)
      }
      setNodePath((await resp.json()) as GraphPathResult)
    } catch {
      setNodePath({ status: 'NOT_FOUND' })
    } finally {
      setPathLoading(false)
    }
  }, [investigationInputParams])

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

          {/* ---------- 6O: REPLAY ---------- */}
          <h3>Replay (Phase 6O)</h3>
          <button onClick={runReplay} disabled={loading || replayLoading}>
            {replayLoading ? 'Replaying…' : 'Replay investigation'}
          </button>
          {replayError && <p className="error">{replayError}</p>}
          {replay && (
            <p className="muted small">
              snapshot <code>{replay.snapshot?.snapshot_hash}</code> → replay{' '}
              <code>{replay.replay_hash}</code>:{' '}
              <Chip state={replay.identical ? 'SUPPORTED' : 'CONTRADICTED'} />{' '}
              {replay.status}
              {replay.difference_count > 0 && ` · ${replay.difference_count} difference(s)`}
            </p>
          )}

          {/* ---------- 6O: MEMORY ---------- */}
          <h3>Engineering memory (Phase 6O)</h3>
          <p className="muted small">
            Evidence-bound, scope-limited memory derived on-read from this
            investigation (exact scope matching only; a related prior
            investigation never transfers its conclusion).
          </p>
          <button onClick={runMemory} disabled={loading || memoryLoading}>
            {memoryLoading ? 'Retrieving…' : 'Retrieve engineering memory'}
          </button>
          {memoryError && <p className="error">{memoryError}</p>}
          {memory && (
            <table className="catalog-table">
              <thead>
                <tr>
                  <th>Memory ID</th>
                  <th>Statement</th>
                  <th>Class</th>
                  <th>Validity</th>
                </tr>
              </thead>
              <tbody>
                {memory.matching_memory_items.map((m) => (
                  <tr key={m.memory_id}>
                    <td className="small"><code>{m.memory_id.slice(0, 12)}</code></td>
                    <td className="small">{m.statement}</td>
                    <td className="small">{m.evidence_type} · {m.claim_class}</td>
                    <td className="small">{m.validity_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {/* ---------- 6O: COMPARE ---------- */}
          <h3>Compare (Phase 6O)</h3>
          <p className="muted small">
            Descriptive deltas only — no ranking, no better/worse. Evidence
            loss is never resolution; MODELLED counterfactuals stay separate
            from historical evidence.
          </p>
          <div className="controls">
            <label>
              B lap:{' '}
              <input type="number" min={1} value={compareLap}
                     onChange={(e) => setCompareLap(Number(e.target.value))}
                     style={{ width: 60 }} />
            </label>
            <button onClick={runCompare} disabled={loading || compareLoading}>
              {compareLoading ? 'Comparing…' : 'Compare with lap B'}
            </button>
          </div>
          {compareError && <p className="error">{compareError}</p>}
          {comparison && (
            <div>
              <p className="muted small">
                compatibility:{' '}
                <Chip state={comparison.compatibility.state === 'COMPARABLE' ? 'SUPPORTED'
                              : comparison.compatibility.state === 'PARTIALLY_COMPARABLE' ? 'PARTIALLY_SUPPORTED'
                              : 'NOT_SUPPORTED'} />{' '}
                {comparison.compatibility.state}
                {(comparison.compatibility.differing_scope_keys?.length ?? 0) > 0 &&
                  ` (differing: ${comparison.compatibility.differing_scope_keys?.join(', ')})`}{' '}
                · synthesis: {comparison.synthesis_delta.old_conclusion_state} →{' '}
                {comparison.synthesis_delta.new_conclusion_state} ({comparison.synthesis_delta.transition})
              </p>
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>Hypothesis</th>
                    <th>A</th>
                    <th>B</th>
                    <th>Changed</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.hypothesis_deltas.map((d) => (
                    <tr key={d.hypothesis_id}>
                      <td className="small">{HYP_LABELS[d.hypothesis_id] || d.hypothesis_id}</td>
                      <td><Chip state={d.old_state} /></td>
                      <td><Chip state={d.new_state} /></td>
                      <td className="small">{d.state_changed ? 'STATE_CHANGED' : 'unchanged'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>Falsification delta</th>
                    <th>Hypotheses</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.falsification_deltas.map((d, i) => (
                    <tr key={i}>
                      <td className="small">{d.change_type}</td>
                      <td className="small">
                        {d.hypothesis_ids.map((h: string) => HYP_LABELS[h] || h).join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                  {comparison.falsification_deltas.length === 0 && (
                    <tr><td colSpan={2} className="muted small">no falsification deltas</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* ---------- 6P: INVESTIGATION GRAPH ---------- */}
          <h3>Investigation graph (Phase 6P)</h3>
          <p className="muted small">
            Provenance-backed navigation over this investigation&apos;s evidence:
            edges are imported analytical relationships (SUPPORTS is
            evidence-consistency, not causation; CONTRADICTS comes from the
            preserved 6N conflicts; MODELLED counterfactuals stay separate).
            Click a node to trace its provenance path from the investigation.
          </p>
          <div className="controls">
            <label>
              focus type:{' '}
              <select value={graphTypeFilter}
                      onChange={(e) => setGraphTypeFilter(e.target.value)}>
                <option value="">all node types</option>
                {GRAPH_NODE_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label>
              path depth:{' '}
              <input type="number" min={1} max={8} value={graphDepth}
                     onChange={(e) => setGraphDepth(Number(e.target.value))}
                     style={{ width: 60 }} />
            </label>
            <button onClick={runGraph} disabled={loading || graphLoading}>
              {graphLoading ? 'Building graph…' : 'Build investigation graph'}
            </button>
          </div>
          {graphError && <p className="error">{graphError}</p>}
          {graph && (
            <div className="gp-graph">
              <p className="muted small">
                graph <code>{graph.graph_id}</code> · {graph.node_count} nodes ·{' '}
                {graph.edge_count} edges · hash <code>{graph.output_hash}</code>
              </p>
              <div className="gp-columns">
                <div className="gp-node-list">
                  <table className="catalog-table">
                    <thead>
                      <tr>
                        <th>Node</th>
                        <th>Type</th>
                        <th>Label</th>
                      </tr>
                    </thead>
                    <tbody>
                      {graph.nodes
                        .filter((n) => !graphTypeFilter || n.node_type === graphTypeFilter)
                        .map((n) => (
                          <tr key={n.node_id}
                              className={selectedNode?.node_id === n.node_id ? 'selected' : ''}
                              onClick={() => openNodePath(n)}>
                            <td className="small">
                              <span className={`gp-node ${NODE_CLASS[n.node_type] || ''}`}>
                                {n.node_type === 'COUNTERFACTUAL' ? 'MODELLED' : n.node_type}
                              </span>{' '}
                              <code>{n.node_id.length > 44 ? `${n.node_id.slice(0, 44)}…` : n.node_id}</code>
                            </td>
                            <td className="small">{n.node_type}</td>
                            <td className="small">{n.label}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <div className="gp-detail">
                  {selectedNode ? (
                    <div className="cf-intervention">
                      <div><strong>node:</strong> <code>{selectedNode.node_id}</code></div>
                      <div>
                        <strong>type:</strong>{' '}
                        <span className={`gp-node ${NODE_CLASS[selectedNode.node_type] || ''}`}>
                          {selectedNode.node_type === 'COUNTERFACTUAL'
                            ? 'COUNTERFACTUAL (MODELLED)'
                            : selectedNode.node_type}
                        </span>
                      </div>
                      <div><strong>label:</strong> {selectedNode.label}</div>
                      {Object.keys(selectedNode.canonical_reference).length > 0 && (
                        <div>
                          <strong>canonical reference:</strong>{' '}
                          <code className="small">
                            {JSON.stringify(selectedNode.canonical_reference).slice(0, 220)}
                          </code>
                        </div>
                      )}
                      {Object.keys(selectedNode.provenance).length > 0 && (
                        <div>
                          <strong>provenance:</strong>{' '}
                          <code className="small">
                            {JSON.stringify(selectedNode.provenance).slice(0, 220)}
                          </code>
                        </div>
                      )}
                      <div>
                        <strong>relationships:</strong>{' '}
                        <span className="small">
                          {graph.edges
                            .filter((e) => e.source_node === selectedNode.node_id
                                        || e.target_node === selectedNode.node_id)
                            .slice(0, 12)
                            .map((e) => {
                              const other = e.source_node === selectedNode.node_id
                                ? e.target_node : e.source_node
                              const dir = e.source_node === selectedNode.node_id ? '→' : '←'
                              return (
                                <div key={e.edge_id} className="small">
                                  <span className={`gp-edge ${EDGE_CLASS[e.edge_type] || 'gp-edge-neutral'}`}>
                                    {e.edge_type}
                                  </span>{' '}
                                  {dir} <code>{other.length > 40 ? `${other.slice(0, 40)}…` : other}</code>
                                </div>
                              )
                            })}
                        </span>
                      </div>
                      <div>
                        <strong>provenance path from investigation:</strong>
                        {pathLoading && <span className="muted small"> tracing…</span>}
                        {nodePath && nodePath.status === 'OK' && nodePath.path && (
                          <ol className="gp-path small">
                            {nodePath.path.map((s, i) => (
                              <li key={i}>
                                <span className={`gp-node ${NODE_CLASS[s.node_type] || ''}`}>
                                  {s.node_type}
                                </span>
                                {s.via_edge_type && (
                                  <>
                                    {' '}via{' '}
                                    <span className={`gp-edge ${EDGE_CLASS[s.via_edge_type] || 'gp-edge-neutral'}`}>
                                      {s.via_edge_type}
                                    </span>
                                  </>
                                )}
                                {' '}
                                <code>{s.step.length > 46 ? `${s.step.slice(0, 46)}…` : s.step}</code>
                              </li>
                            ))}
                          </ol>
                        )}
                        {nodePath && nodePath.status !== 'OK' && (
                          <span className="muted small"> {nodePath.reason || nodePath.status}</span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="muted small">click a node to inspect it</p>
                  )}
                </div>
              </div>
              <ul className="muted small">
                {graph.epistemic_boundaries.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
