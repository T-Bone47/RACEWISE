import { useCallback, useEffect, useState } from 'react'

interface OfficialResult {
  gap_s: number | null
  semantics: string
  driver_a: { position: number | null; time: string | null; laps: number | null; status: string | null }
  driver_b: { position: number | null; time: string | null; laps: number | null; status: string | null }
}

interface Segment {
  kind: string
  stint_number: number | null
  pattern: string
  comparable_laps: number
  lap_range: [number, number] | number[]
}

interface GapEvent {
  type: string
  at_lap?: number
  previous_state?: string
  new_state?: string
  stint_number?: number
  compound?: string | null
  detail?: string
}

interface HypothesisEvolution {
  [id: string]: { summary: string; per_stint: Array<{ stint_number: number | null; summary: string | null }> }
}

interface RaceGap {
  status: string
  reason?: string
  driver_a?: string
  driver_b?: string
  official_result?: OfficialResult
  timeline_summary?: { total_laps: number; comparable: number; non_comparable: number; unavailable: number; reasons: Record<string, number> }
  segments?: Segment[]
  cumulative_comparable_gap_s?: number
  gap_events?: GapEvent[]
  pit_windows?: Array<{ driver: string; lap: number; observed_transition_s: number | null; mechanism: string }>
  race_control_windows?: Array<{ start_lap: number; end_lap: number; classification: string }>
  stint_evidence?: Array<{ stint_number: number | null; status: string | null; valid_laps: number | null; trend?: { status: string; slope_per_stint_lap?: number } }>
  hypothesis_evolution?: HypothesisEvolution
  residual_accounting?: { comparable_count: number; non_comparable_count: number; unavailable_count: number; official_vs_analytical: string }
  counterfactual_gate?: string
  conclusion?: string
  methodology_version?: string
}

interface SessionRef { season: number; round: number; label: string }

const KNOWN_SESSIONS: Array<{ season: number; round: number }> = [
  { season: 2025, round: 1 },
  { season: 2024, round: 14 },
  { season: 2024, round: 1 },
  { season: 2023, round: 1 },
  { season: 2022, round: 4 },
]

const EV_CLASS: Record<string, string> = {
  CONSISTENTLY_SUPPORTED: 'ef-supported',
  MOSTLY_SUPPORTED: 'ef-supported',
  INTERMITTENTLY_SUPPORTED: 'ef-untestable',
  CONTRADICTED_OVER_TIME: 'ef-contradicted',
  NOT_SUPPORTED: 'ef-contradicted',
  INSUFFICIENT_EVIDENCE: 'ef-untestable',
}

const PATTERN_CLASS: Record<string, string> = {
  WIDENING: 'ef-contradicted',
  NARROWING: 'ef-supported',
  STABLE: 'ef-untestable',
  INSUFFICIENT_EVIDENCE: 'ef-untestable',
}

export default function RaceGapView() {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState('2023-1')
  const [result, setResult] = useState<RaceGap | null>(null)
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
      const resp = await fetch(`/api/catalog/race-gap/${season}/${round}`)
      if (!resp.ok) throw new Error(`Race gap request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    finally {
      setLoading(false)
    }
  }, [selected])

  const sessionList: SessionRef[] =
    sessions.length > 0
      ? sessions
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const valid = result && (result.status === 'VALID_COMPARISON' || result.status === 'VALID_WITH_CAVEATS')
  const off = result?.official_result
  const hyps = result?.hypothesis_evolution || {}

  return (
    <div className="catalog attribution-view">
      <h2>Race Gap Decomposition</h2>
      <p className="muted small">
        Where during the race was the performance relationship created, recovered, or changed —
        as an evidence map. Official gap and analytical comparable gap are different quantities
        and are never forced to reconcile. Observed-gap language is not time-lost causation.
      </p>

      <div className="catalog-filters">
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {sessionList.map((s) => (
            <option key={`${s.season}-${s.round}`} value={`${s.season}-${s.round}`}>
              {s.season} R{s.round} — {s.label}
            </option>
          ))}
        </select>
        <button onClick={run} disabled={loading}>
          {loading ? 'Decomposing…' : 'Decompose Race Gap'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && !valid && (
        <div className="catalog-empty">
          {result.status} — {result.reason || 'race decomposition not possible with current evidence'}
        </div>
      )}

      {result && valid && (
        <div className="catalog-detail">
          <div className="tv-headline">
            {result.driver_a} vs {result.driver_b}
          </div>

          <table className="catalog-table">
            <thead>
              <tr>
                <th>Official classified gap</th>
                <th>Analytical comparable-lap gap</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>{off?.gap_s != null ? `${off.gap_s}s` : 'not computable'}</strong>
                </td>
                <td>
                  <strong>{result.cumulative_comparable_gap_s}s</strong>{' '}
                  <span className="muted small">
                    (across {result.residual_accounting?.comparable_count} comparable laps)
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <div className="muted small">{result.residual_accounting?.official_vs_analytical}</div>

          <h4>
            Race timeline — {result.timeline_summary?.comparable} comparable ·{' '}
            {result.timeline_summary?.non_comparable} non-comparable ·{' '}
            {result.timeline_summary?.unavailable} unavailable
          </h4>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Segment</th>
                <th>Laps</th>
                <th>Comparable</th>
                <th>Gap pattern</th>
              </tr>
            </thead>
            <tbody>
              {(result.segments || []).map((s, i) => (
                <tr key={i}>
                  <td>
                    {s.kind === 'stint' ? `Stint ${s.stint_number}` : 'Unknown stint'}
                  </td>
                  <td className="small muted">
                    {s.lap_range?.[0]}–{s.lap_range?.[1]}
                  </td>
                  <td>{s.comparable_laps}</td>
                  <td>
                    <span className={`ef-badge ${PATTERN_CLASS[s.pattern] || 'ef-untestable'}`}>
                      {s.pattern}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h4>Gap events</h4>
          <ul className="ef-chain">
            {(result.gap_events || []).slice(0, 12).map((e, i) => (
              <li key={i}>
                <span className="ef-badge ef-untestable">{e.type}</span>{' '}
                {e.at_lap != null && <>at lap {e.at_lap} — </>}
                {e.previous_state && (
                  <>{e.previous_state} → {e.new_state} </>
                )}
                {e.stint_number != null && <>stint {e.stint_number} </>}
                {e.detail && <span className="muted small">{e.detail}</span>}
              </li>
            ))}
          </ul>

          <h4>Pit windows</h4>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Driver</th>
                <th>Lap</th>
                <th>Observed transition</th>
                <th>Mechanism</th>
              </tr>
            </thead>
            <tbody>
              {(result.pit_windows || []).map((w, i) => (
                <tr key={i}>
                  <td>{w.driver}</td>
                  <td>{w.lap}</td>
                  <td>{w.observed_transition_s != null ? `${w.observed_transition_s}s` : '—'}</td>
                  <td className="small muted">{w.mechanism}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {(result.race_control_windows?.length || 0) > 0 && (
            <div className="tv-assumptions">
              <h4>Race-control windows (exact lap overlap)</h4>
              <ul>
                {result.race_control_windows!.map((w, i) => (
                  <li key={i}>
                    Laps {w.start_lap}–{w.end_lap}: {w.classification}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <h4>Hypothesis evolution across the race</h4>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Hypothesis</th>
                <th>Race verdict</th>
                <th>Per stint</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(hyps).map(([id, h]) => (
                <tr key={id}>
                  <td className="small">{id}</td>
                  <td>
                    <span className={`ef-badge ${EV_CLASS[h.summary] || 'ef-untestable'}`}>
                      {h.summary}
                    </span>
                  </td>
                  <td className="small muted">
                    {h.per_stint.map((p) => `S${p.stint_number}: ${p.summary || '—'}`).join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="tv-assumptions small">
            <h4>Residual accounting</h4>
            <div>
              comparable {result.residual_accounting?.comparable_count} · non-comparable{' '}
              {result.residual_accounting?.non_comparable_count} · unavailable{' '}
              {result.residual_accounting?.unavailable_count} — the residual is reported, never
              assigned to a hypothesis. {result.counterfactual_gate}
            </div>
          </div>

          <div className="muted small">{result.conclusion}</div>
          <div className="muted small">methodology {result.methodology_version}</div>
        </div>
      )}
    </div>
  )
}
