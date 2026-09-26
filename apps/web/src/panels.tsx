import { useCallback, useEffect, useState } from 'react'
import { stateChipClass, HYP_LABELS } from './types'
import type {
  CompareResult, GraphNode, GraphPathResult, GraphResult,
  HypothesisTraceResult, MemoryResult, QuestionScope, ReplayResult,
} from './types'
import { LoadingLine, ProvenanceDrawer, StateChip, StructuredError } from './workspace'
import type { ProvenanceTarget } from './workspace'

/* ============ 6Q shared workspace panels (graph / replay / compare / memory) ============ */

export const GRAPH_NODE_TYPES = [
  'EVIDENCE', 'HYPOTHESIS', 'DECISION_TRACE', 'MEMORY', 'COUNTERFACTUAL',
  'SYNTHESIS', 'ANALYTICAL_SOURCE', 'RACE', 'LAP', 'STINT', 'REGIME',
  'PATTERN', 'SNAPSHOT', 'QUESTION', 'DRIVER', 'SESSION', 'SEASON',
  'DRIVER_PAIR', 'INVESTIGATION',
]

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

/* ---------- GraphPanel: 6P provenance navigator (§16/§17) ---------- */

export function GraphPanel({
  scopeParams,
  focusNode,
  onNodeFocused,
  onOpenProvenance,
}: {
  scopeParams: () => URLSearchParams
  focusNode?: { type: string; key: string } | null
  onNodeFocused?: (n: GraphNode) => void
  onOpenProvenance?: (t: ProvenanceTarget) => void
}) {
  const [graph, setGraph] = useState<GraphResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [path, setPath] = useState<GraphPathResult | null>(null)
  const [pathLoading, setPathLoading] = useState(false)
  const [hypTrace, setHypTrace] = useState<HypothesisTraceResult | null>(null)

  const build = useCallback(async () => {
    setLoading(true)
    setError(null)
    setGraph(null)
    setSelected(null)
    setPath(null)
    setHypTrace(null)
    try {
      const t0 = performance.now()
      const params = scopeParams()
      params.set('max_depth', '4')
      const resp = await fetch(`/api/catalog/investigation-graph?${params}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Graph request failed (${resp.status})`)
      }
      const j = (await resp.json()) as GraphResult & { status?: string; reason?: string }
      if (j.status === 'INVALID' || j.status === 'UNAVAILABLE') {
        throw new Error(j.reason || j.status || 'graph unavailable')
      }
      setGraph(j)
      window.setTimeout(() => {
        void t0
      }, 0)
    } catch (e) {
      setError({ code: 'TOOL_FAILURE', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }, [scopeParams])

  const traceTo = useCallback(async (node: GraphNode) => {
    setSelected(node)
    setPath(null)
    setHypTrace(null)
    setPathLoading(true)
    try {
      const params = scopeParams()
      const key = node.node_id.includes(':')
        ? node.node_id.slice(node.node_id.indexOf(':') + 1)
        : node.node_id
      params.set('target_node_type', node.node_type)
      params.set('target_key', key)
      const resp = await fetch(`/api/catalog/investigation-graph/path?${params}`)
      const j = (await resp.json()) as GraphPathResult
      setPath(resp.ok ? j : { status: 'NOT_FOUND' })
      onNodeFocused?.(node)
    } catch {
      setPath({ status: 'NOT_FOUND' })
    } finally {
      setPathLoading(false)
    }
  }, [scopeParams, onNodeFocused])

  const traceHypothesis = useCallback(async (hypId: string) => {
    setSelected(null)
    setPath(null)
    setHypTrace(null)
    setPathLoading(true)
    try {
      const params = scopeParams()
      params.set('hypothesis', hypId)
      const resp = await fetch(`/api/catalog/investigation-graph/hypothesis?${params}`)
      setHypTrace(resp.ok ? await resp.json() : null)
    } finally {
      setPathLoading(false)
    }
  }, [scopeParams])

  /* external focus requests (cross-navigation from the workspace) */
  useEffect(() => {
    if (!focusNode || !graph) return
    const node = graph.nodes.find((n) =>
      n.node_type === focusNode.type &&
      (focusNode.key === '' || n.node_id.endsWith(focusNode.key)))
    if (node) {
      setSelected(node)
      onNodeFocused?.(node)
    }
  }, [focusNode, graph, onNodeFocused])

  return (
    <div className="gp-graph">
      <div className="controls">
        <label>
          focus type:{' '}
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value="">all node types</option>
            {GRAPH_NODE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          hypothesis focus:{' '}
          <select value="" onChange={(e) => { if (e.target.value) traceHypothesis(e.target.value) }}>
            <option value="">trace hypothesis evidence…</option>
            {Object.keys(HYP_LABELS).map((h) => <option key={h} value={h}>{HYP_LABELS[h]}</option>)}
          </select>
        </label>
        <button className="primary" onClick={build} disabled={loading}>
          {loading ? 'Building evidence graph…' : graph ? 'Rebuild graph' : 'Build investigation graph'}
        </button>
      </div>

      {error && <StructuredError code={error.code} message={error.message} />}
      {loading && <LoadingLine label="Building evidence graph…" />}

      {graph && (
        <>
          <p className="muted small">
            graph <code>{graph.graph_id}</code> · {graph.node_count} nodes ·{' '}
            {graph.edge_count} edges · hash <code>{graph.output_hash}</code> ·
            {' '}click a node to trace its provenance path from the investigation
          </p>
          <div className="gp-columns">
            <div className="gp-node-list">
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th scope="col">Node</th>
                    <th scope="col">Type</th>
                    <th scope="col">Label</th>
                  </tr>
                </thead>
                <tbody>
                  {graph.nodes
                    .filter((n) => !typeFilter || n.node_type === typeFilter)
                    .map((n) => (
                      <tr
                        key={n.node_id}
                        className={`clickable ${selected?.node_id === n.node_id ? 'selected' : ''}`}
                        onClick={() => traceTo(n)}
                      >
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
              {selected && (
                <div className="cf-intervention">
                  <div><strong>node:</strong> <code>{selected.node_id}</code></div>
                  <div>
                    <strong>type:</strong>{' '}
                    <span className={`gp-node ${NODE_CLASS[selected.node_type] || ''}`}>
                      {selected.node_type === 'COUNTERFACTUAL' ? 'COUNTERFACTUAL (MODELLED)' : selected.node_type}
                    </span>
                  </div>
                  <div><strong>label:</strong> {selected.label}</div>
                  {Object.keys(selected.provenance).length > 0 && (
                    <div>
                      <strong>provenance:</strong>{' '}
                      <button className="linklike" onClick={() =>
                        onOpenProvenance?.({
                          kind: selected.node_type,
                          id: selected.node_id,
                          provenance: selected.provenance,
                          canonicalReference: selected.canonical_reference,
                          extra: Object.entries(selected.metadata)
                            .filter(([, v]) => v != null)
                            .slice(0, 8)
                            .map(([k, v]) => ({ k, v: <code className="small">{JSON.stringify(v)}</code> })),
                        })
                      }>
                        open provenance drawer
                      </button>
                    </div>
                  )}
                  <div>
                    <strong>relationships:</strong>
                    <span className="small">
                      {graph.edges
                        .filter((e) => e.source_node === selected.node_id || e.target_node === selected.node_id)
                        .slice(0, 12)
                        .map((e) => {
                          const outgoing = e.source_node === selected.node_id
                          const other = outgoing ? e.target_node : e.source_node
                          return (
                            <div key={e.edge_id} className="small">
                              <span className={`gp-edge ${EDGE_CLASS[e.edge_type] || 'gp-edge-neutral'}`}>{e.edge_type}</span>
                              {' '}{outgoing ? '→' : '←'}{' '}
                              <button
                                className="linklike small"
                                onClick={() => {
                                  const target = graph.nodes.find((x) => x.node_id === other)
                                  if (target) traceTo(target)
                                }}
                              >
                                {other.length > 42 ? `${other.slice(0, 42)}…` : other}
                              </button>
                            </div>
                          )
                        })}
                    </span>
                  </div>
                  <div>
                    <strong>provenance path from investigation:</strong>
                    {pathLoading && <LoadingLine label="Tracing path…" />}
                    {!pathLoading && path?.status === 'OK' && path.path && (
                      <ol className="gp-path small">
                        {path.path.map((s, i) => (
                          <li key={i}>
                            <span className={`gp-node ${NODE_CLASS[s.node_type] || ''}`}>{s.node_type}</span>
                            {s.via_edge_type && (
                              <>
                                {' '}via{' '}
                                <span className={`gp-edge ${EDGE_CLASS[s.via_edge_type] || 'gp-edge-neutral'}`}>
                                  {s.via_edge_type}
                                </span>
                              </>
                            )}
                            {' '}<code>{s.step.length > 46 ? `${s.step.slice(0, 46)}…` : s.step}</code>
                          </li>
                        ))}
                      </ol>
                    )}
                    {!pathLoading && path && path.status !== 'OK' && (
                      <span className="muted small"> {path.reason || path.status}</span>
                    )}
                  </div>
                </div>
              )}
              {hypTrace && (
                <div className="cf-intervention">
                  <div><strong>{HYP_LABELS[hypTrace.hypothesis_id] || hypTrace.hypothesis_id} — evidence state</strong></div>
                  <div className="small">supporting: {hypTrace.supporting_evidence.length} · contradicting: {hypTrace.contradicting_evidence.length} · non-decisive: {hypTrace.non_decisive_evidence.length} · modelled: {hypTrace.counterfactuals.length}</div>
                  <div className="muted small">{hypTrace.note || 'descriptive lists — no ranking, no scoring'}</div>
                  {[['supporting', hypTrace.supporting_evidence], ['contradicting', hypTrace.contradicting_evidence], ['non-decisive', hypTrace.non_decisive_evidence]].map(([label, arr]) => (
                    <div key={label as string} className="small">
                      <strong>{label as string}:</strong>{' '}
                      {(arr as Array<{ node_id: string }>).map((r) => r.node_id.replace('evidence:', '')).join(', ') || '—'}
                    </div>
                  ))}
                </div>
              )}
              {!selected && !hypTrace && <p className="muted small">click a node to inspect it</p>}
            </div>
          </div>
          <ul className="muted small">
            {graph.epistemic_boundaries.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        </>
      )}
      {!graph && !loading && !error && (
        <div className="empty-state">
          No graph built for this scope yet. The graph is assembled on read from
          the 6N investigation of the current scope — build it to navigate
          evidence, hypotheses, contradictions and memory.
        </div>
      )}
    </div>
  )
}

/* ---------- ReplayPanel (§18) ---------- */

export function ReplayPanel({ scopeParams }: { scopeParams: () => URLSearchParams }) {
  const [replay, setReplay] = useState<ReplayResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)

  async function run() {
    setLoading(true)
    setError(null)
    setReplay(null)
    try {
      const resp = await fetch(`/api/catalog/engineering-investigation/replay?${scopeParams()}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Replay request failed (${resp.status})`)
      }
      setReplay(await resp.json())
    } catch (e) {
      setError({ code: 'TOOL_FAILURE', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <button className="primary" onClick={run} disabled={loading}>
        {loading ? 'Replaying investigation…' : 'Replay investigation'}
      </button>
      {error && <StructuredError code={error.code} message={error.message} />}
      {loading && <LoadingLine label="Replaying investigation…" />}
      {replay && (
        <div style={{ marginTop: 10 }}>
          <p className="muted small">
            snapshot <code>{replay.snapshot?.snapshot_hash ?? replay.original_hash}</code> → replay{' '}
            <code>{replay.replay_hash ?? '—'}</code>
          </p>
          {replay.identical ? (
            <p>
              <span className={`ef-badge ${stateChipClass('SUPPORTED')}`}>IDENTICAL REPLAY</span>{' '}
              <span className="muted small">byte-identical canonical output from the same store</span>
            </p>
          ) : replay.status === 'INVALID_SNAPSHOT' ? (
            <StructuredError code="INVALID" message="The snapshot failed integrity verification and was not re-run." />
          ) : (
            <>
              <p>
                <span className={`ef-badge ${stateChipClass('CONTRADICTED')}`}>{replay.status.replace(/_/g, ' ')}</span>{' '}
                <span className="muted small">{replay.difference_count} structured difference(s)</span>
              </p>
              {replay.differences.length > 0 && (
                <table className="catalog-table">
                  <thead>
                    <tr><th scope="col">Category</th><th scope="col">Path</th><th scope="col">Old</th><th scope="col">New</th></tr>
                  </thead>
                  <tbody>
                    {replay.differences.slice(0, 30).map((d, i) => (
                      <tr key={i}>
                        <td className="small">{d.category}</td>
                        <td className="small"><code>{d.path}</code></td>
                        <td className="small muted">{JSON.stringify(d.old_value)?.slice(0, 80)}</td>
                        <td className="small muted">{JSON.stringify(d.new_value)?.slice(0, 80)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      )}
      {!replay && !loading && !error && (
        <div className="empty-state" style={{ marginTop: 10 }}>
          No replay run yet. Replay re-runs the exact 6N engine for this scope
          and compares canonical hashes — a differing result is reported as
          exact structured differences, never “something changed”.
        </div>
      )}
    </div>
  )
}

/* ---------- ComparePanel (§19) ---------- */

export function ComparePanel({
  baseScope,
  initialBLap,
}: {
  baseScope: () => URLSearchParams
  initialBLap?: number
}) {
  const [bLap, setBLap] = useState(initialBLap ?? 11)
  const [cmp, setCmp] = useState<CompareResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)

  async function run() {
    setLoading(true)
    setError(null)
    setCmp(null)
    try {
      const a = baseScope()
      /* side-A params carry the a_ prefix per the 6O compare contract; only
         the endpoint's accepted keys are forwarded */
      const b = new URLSearchParams()
      const aKeys = ['question_type', 'driver_a', 'driver_b', 'season', 'round',
        'lap_number', 'stint_number', 'pattern_id', 'hypotheses'] as const
      for (const k of aKeys) {
        const v = a.get(k)
        if (v) b.set(`a_${k}`, v)
      }
      b.set('b_question_type', a.get('question_type') || '')
      b.set('b_driver_a', a.get('driver_a') || '')
      b.set('b_driver_b', a.get('driver_b') || '')
      b.set('b_season', a.get('season') || '')
      b.set('b_round', a.get('round') || '')
      if (a.get('lap_number')) b.set('b_lap_number', String(bLap))
      if (a.get('stint_number')) b.set('b_stint_number', a.get('stint_number') || '')
      if (a.get('pattern_id')) b.set('b_pattern_id', a.get('pattern_id') || '')
      const resp = await fetch(`/api/catalog/engineering-investigation/compare?${b}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Compare request failed (${resp.status})`)
      }
      setCmp(await resp.json())
    } catch (e) {
      setError({ code: 'TOOL_FAILURE', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }

  const compatClass = (state?: string) =>
    state === 'COMPARABLE' ? 'st-supported' : state === 'PARTIALLY_COMPARABLE' ? 'st-mixed' : 'st-untestable'

  return (
    <div>
      <div className="controls">
        <label>
          B lap:{' '}
          <input type="number" min={1} value={bLap} style={{ width: 64 }}
                 onChange={(e) => setBLap(Number(e.target.value))} />
        </label>
        <button className="primary" onClick={run} disabled={loading}>
          {loading ? 'Comparing investigations…' : 'Compare with lap B'}
        </button>
      </div>
      {error && <StructuredError code={error.code} message={error.message} />}
      {loading && <LoadingLine label="Comparing investigations…" />}
      {cmp && (
        <div>
          <p className="muted small">
            compatibility:{' '}
            <span className={`ef-badge ${compatClass(cmp.compatibility.state)}`}>
              {cmp.compatibility.state.replace(/_/g, ' ')}
            </span>
            {(cmp.compatibility.differing_scope_keys?.length ?? 0) > 0 &&
              ` (differing: ${cmp.compatibility.differing_scope_keys?.join(', ')})`}{' '}
            · synthesis:{' '}
            <StateChip state={cmp.synthesis_delta.old_conclusion_state} /> →{' '}
            <StateChip state={cmp.synthesis_delta.new_conclusion_state} />{' '}
            ({cmp.synthesis_delta.transition})
          </p>
          <div className="split">
            <table className="catalog-table">
              <thead>
                <tr><th scope="col">Hypothesis</th><th scope="col">A</th><th scope="col">B</th><th scope="col">Changed</th></tr>
              </thead>
              <tbody>
                {cmp.hypothesis_deltas.map((d) => (
                  <tr key={d.hypothesis_id}>
                    <td className="small">{HYP_LABELS[d.hypothesis_id] || d.hypothesis_id}</td>
                    <td><StateChip state={d.old_state} /></td>
                    <td><StateChip state={d.new_state} /></td>
                    <td className="small">{d.state_changed ? 'STATE_CHANGED' : 'unchanged'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table className="catalog-table">
              <thead>
                <tr><th scope="col">Falsification delta</th><th scope="col">Hypotheses</th></tr>
              </thead>
              <tbody>
                {cmp.falsification_deltas.map((d, i) => (
                  <tr key={i}>
                    <td className="small">{d.change_type}</td>
                    <td className="small">{d.hypothesis_ids.map((h) => HYP_LABELS[h] || h).join(', ') || '—'}</td>
                  </tr>
                ))}
                {cmp.falsification_deltas.length === 0 && (
                  <tr><td colSpan={2} className="muted small">no falsification deltas</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="muted small">
            evidence deltas: {cmp.evidence_deltas.length} · counterfactual deltas: {cmp.counterfactual_deltas.length} ·
            decision-trace: {cmp.decision_trace_delta.added_count} added / {cmp.decision_trace_delta.removed_count} removed /{' '}
            {cmp.decision_trace_delta.unchanged_count} unchanged — descriptive transitions only, no better/worse.
          </p>
        </div>
      )}
      {!cmp && !loading && !error && (
        <div className="empty-state" style={{ marginTop: 10 }}>
          No comparison run yet. Comparisons are descriptive dimension deltas —
          evidence loss stays evidence loss, never resolution.
        </div>
      )}
    </div>
  )
}

/* ---------- MemoryPanel (§20) ---------- */

export function MemoryPanel({ scopeParams, driverA }: { scopeParams: () => URLSearchParams; driverA: string }) {
  const [mem, setMem] = useState<MemoryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ code: string; message: string } | null>(null)
  const [prov, setProv] = useState<ProvenanceTarget | null>(null)

  async function run() {
    setLoading(true)
    setError(null)
    setMem(null)
    try {
      const params = scopeParams()
      params.set('driver', driverA)
      const resp = await fetch(`/api/catalog/engineering-memory?${params}`)
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(detail?.detail || `Memory request failed (${resp.status})`)
      }
      setMem(await resp.json())
    } catch (e) {
      setError({ code: 'TOOL_FAILURE', message: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <button className="primary" onClick={run} disabled={loading}>
        {loading ? 'Retrieving engineering memory…' : 'Retrieve engineering memory'}
      </button>
      {error && <StructuredError code={error.code} message={error.message} />}
      {loading && <LoadingLine label="Retrieving engineering memory…" />}
      {mem && (
        mem.match_count === 0 ? (
          <div className="empty-state" style={{ marginTop: 10 }}>
            No related memory exists within this scope. Memory is derived on
            read from completed investigations and retrieved by exact scope —
            absence here is not negative evidence.
          </div>
        ) : (
          <table className="catalog-table" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th scope="col">Memory ID</th>
                <th scope="col">Statement</th>
                <th scope="col">Class</th>
                <th scope="col">Validity</th>
              </tr>
            </thead>
            <tbody>
              {mem.matching_memory_items.map((m) => (
                <tr key={m.memory_id}>
                  <td className="small"><code>{m.memory_id.slice(0, 12)}</code></td>
                  <td className="small">{m.statement}</td>
                  <td className="small">{m.evidence_type} · {m.claim_class}</td>
                  <td className="small">
                    <button className="linklike" onClick={() => setProv({
                      kind: 'MEMORY',
                      id: m.memory_id,
                      provenance: {
                        source_investigation_ids: m.source_investigation_ids,
                        evidence_ids: m.evidence_ids,
                        evidence_type: m.evidence_type,
                        claim_class: m.claim_class,
                      },
                      canonicalReference: m.scope,
                      limitations: m.limitations,
                    })}>
                      {m.validity_status}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
      {!mem && !loading && !error && (
        <div className="empty-state" style={{ marginTop: 10 }}>
          No memory retrieval run yet. Memory items are evidence-bound and
          scope-limited — a related prior investigation never transfers its
          conclusion.
        </div>
      )}
      <ProvenanceDrawer target={prov} onClose={() => setProv(null)} />
    </div>
  )
}

export function scopeOfQuestion(questionType: string, base: URLSearchParams): QuestionScope & { question_type: string } {
  return {
    question_type: questionType,
    season: Number(base.get('season') || 2023),
    round: Number(base.get('round') || 1),
    driver_a: base.get('driver_a') || '',
    driver_b: base.get('driver_b') || '',
    lap_number: base.get('lap_number') ? Number(base.get('lap_number')) : null,
    stint_number: base.get('stint_number') ? Number(base.get('stint_number')) : null,
    session_type: 'RACE',
    pattern_id: base.get('pattern_id') || null,
  }
}
