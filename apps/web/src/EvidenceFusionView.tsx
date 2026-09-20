import { useCallback, useEffect, useState } from 'react'

interface EvidenceItem {
  source_id: string
  source_type: string
  statement: string
  relationship: string
  evidence_type: string
  provider: string
  values?: Record<string, unknown>
}

interface Hypothesis {
  hypothesis_id: string
  statement: string
  status: string
  supporting: string[]
  contradicting: string[]
  not_tested_by: string[]
  rationale: string
}

interface Fusion {
  status: string
  reason?: string
  observed_delta_s?: number
  lap_times?: { driver_a: number; driver_b: number }
  authoritative_sector_decomposition?: Array<{ sector: number; delta_s: number }> | null
  evidence_items?: EvidenceItem[]
  hypotheses?: Hypothesis[]
  residual_s?: number
  residual_class?: string
  conclusion?: string
  source_dependencies?: Record<string, string[]>
  counterfactual_gate?: string
  assumptions?: string[]
  provenance?: Record<string, unknown>
  methodology_version?: string
}

interface SessionRef {
  season: number
  round: number
  label: string
}

const KNOWN_SESSIONS: Array<{ season: number; round: number }> = [
  { season: 2025, round: 1 },
  { season: 2025, round: 12 },
  { season: 2024, round: 14 },
  { season: 2024, round: 1 },
  { season: 2023, round: 9 },
  { season: 2023, round: 1 },
  { season: 2022, round: 10 },
  { season: 2022, round: 1 },
]

const STATUS_CLASS: Record<string, string> = {
  SUPPORTED: 'ef-supported',
  PARTIALLY_SUPPORTED: 'ef-supported',
  NOT_SUPPORTED: 'ef-contradicted',
  CONTRADICTED: 'ef-contradicted',
  NOT_TESTABLE: 'ef-untestable',
  INSUFFICIENT_EVIDENCE: 'ef-untestable',
}

export default function EvidenceFusionView() {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState('2023-1')
  const [driverA, setDriverA] = useState('max-verstappen')
  const [driverB, setDriverB] = useState('sergio-perez')
  const [result, setResult] = useState<Fusion | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const resp = await fetch('/api/catalog/sessions?capability=telemetry&page_size=100')
        if (!resp.ok) return
        const data = await resp.json()
        const refs: SessionRef[] = (data.sessions || []).map(
          (s: { season: number; round: number; race_name: string | null }) => ({
            season: s.season,
            round: s.round,
            label: s.race_name || `${s.season} R${s.round}`,
          }),
        )
        if (refs.length > 0) {
          setSessions(refs)
          setSelected(`${refs[0].season}-${refs[0].round}`)
        }
      } catch {
        /* fallback list below */
      }
    }
    load()
  }, [])

  const run = useCallback(async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const [season, round] = selected.split('-')
      const params = new URLSearchParams({ driver_a: driverA, driver_b: driverB })
      const resp = await fetch(
        `/api/catalog/evidence-fusion/${season}/${round}?${params.toString()}`,
      )
      if (!resp.ok) throw new Error(`Evidence fusion request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    finally {
      setLoading(false)
    }
  }, [selected, driverA, driverB])

  const sessionList: SessionRef[] =
    sessions.length > 0
      ? sessions
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const valid = result && (result.status === 'VALID_COMPARISON' || result.status === 'VALID_WITH_CAVEATS')
  const sectors = result?.authoritative_sector_decomposition || []
  const maxSector = sectors.length ? Math.max(...sectors.map((s) => Math.abs(s.delta_s))) : 0

  return (
    <div className="catalog attribution-view">
      <h2>Evidence Fusion</h2>
      <p className="muted small">
        Independent canonical sources (sectors, telemetry metrics, stints, weather, race control,
        pit stops) are fused into formal hypothesis verdicts. Consistency is not causation; the
        unexplained residual is reported, never assigned.
      </p>

      <div className="catalog-filters">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {sessionList.map((s) => (
            <option key={`${s.season}-${s.round}`} value={`${s.season}-${s.round}`}>
              {s.season} R{s.round} — {s.label}
            </option>
          ))}
        </select>
        <input
          aria-label="Driver A key"
          value={driverA}
          onChange={(e) => setDriverA(e.target.value)}
          placeholder="driver A key"
        />
        <input
          aria-label="Driver B key"
          value={driverB}
          onChange={(e) => setDriverB(e.target.value)}
          placeholder="driver B key"
        />
        <button onClick={run} disabled={loading}>
          {loading ? 'Fusing…' : 'Fuse Evidence'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && !valid && (
        <div className="catalog-empty">
          {result.status} — {result.reason || 'fusion not possible with current evidence'}
        </div>
      )}

      {result && valid && (
        <div className="catalog-detail">
          <div className="tv-headline">
            Observed lap delta (B − A): <strong>{result.observed_delta_s}s</strong>
            <span className="muted small">
              {' '}
              (A: {result.lap_times?.driver_a}s · B: {result.lap_times?.driver_b}s)
            </span>
          </div>

          {sectors.length > 0 && (
            <>
              <h4>Authoritative sector decomposition — measured, sums to the delta</h4>
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>Sector</th>
                    <th>Δ (B − A)</th>
                  </tr>
                </thead>
                <tbody>
                  {sectors.map((s) => (
                    <tr key={s.sector}>
                      <td>S{s.sector}</td>
                      <td>
                        <span className="tv-cell">{s.delta_s}s</span>
                        <div
                          className={s.delta_s < 0 ? 'tv-bar tv-bar-neg' : 'tv-bar'}
                          style={{ width: `${maxSector ? Math.min(100, (Math.abs(s.delta_s) / maxSector) * 100) : 0}%` }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <h4>Hypotheses — formal verdicts from the evidence</h4>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Hypothesis</th>
                <th>Verdict</th>
                <th>Basis</th>
              </tr>
            </thead>
            <tbody>
              {(result.hypotheses || []).map((h) => (
                <tr key={h.hypothesis_id}>
                  <td>
                    <strong>{h.hypothesis_id}</strong>
                    <div className="muted small">{h.statement}</div>
                  </td>
                  <td>
                    <span className={`ef-badge ${STATUS_CLASS[h.status] || 'ef-untestable'}`}>
                      {h.status}
                    </span>
                  </td>
                  <td className="small">
                    {h.supporting.length > 0 && <div>+ {h.supporting.join(', ')}</div>}
                    {h.contradicting.length > 0 && <div>− {h.contradicting.join(', ')}</div>}
                    {h.not_tested_by.length > 0 && (
                      <div className="muted">· not tested: {h.not_tested_by.join(', ')}</div>
                    )}
                    <div className="muted small">{h.rationale}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="tv-assoc">
            <div>
              Unexplained component: <strong>{result.residual_s}s</strong> —{' '}
              {result.residual_class}
            </div>
            <div className="muted small">
              Reported, not assigned to any hypothesis. {result.counterfactual_gate}
            </div>
          </div>

          <h4>Evidence chain</h4>
          <ul className="ef-chain">
            {(result.evidence_items || []).map((e) => (
              <li key={e.source_id}>
                <span className={`ef-badge ${e.relationship === 'SUPPORTS' ? 'ef-supported' : e.relationship === 'CONTRADICTS' ? 'ef-contradicted' : 'ef-untestable'}`}>
                  {e.relationship}
                </span>{' '}
                <strong>{e.source_type}</strong> ({e.evidence_type}, {e.provider}) —{' '}
                {e.statement}
              </li>
            ))}
          </ul>

          {result.source_dependencies && (
            <div className="tv-assumptions small">
              <h4>Source dependencies (no double-counting)</h4>
              <ul>
                {Object.entries(result.source_dependencies).map(([k, deps]) => (
                  <li key={k}>
                    {k} ← {deps.length > 0 ? deps.join(', ') : '(independent)'}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="tv-assumptions">
            <h4>Assumptions</h4>
            <ul>
              {(result.assumptions || []).map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>

          <div className="muted small">
            {result.conclusion} — methodology {result.methodology_version}
          </div>
        </div>
      )}
    </div>
  )
}
