import { useCallback, useEffect, useState } from 'react'

interface Region {
  region: number
  t_start_s: number
  t_end_s: number
  mean_speed_a_kmh: number | null
  mean_speed_b_kmh: number | null
  speed_delta_kmh: number
  attributed_loss_s: number
}

interface SectorAttrib {
  sector: number
  delta_s: number
  telemetry_estimated_loss_s: number
  note: string
}

interface FalsCheck {
  hypothesis: string
  verdict: string
  evidence: string
}

interface Attribution {
  status: string
  reason?: string
  observed_delta_s?: number
  lap_times?: { driver_a: number; driver_b: number }
  n_regions?: number
  regions?: Region[]
  top_loss_regions?: Region[]
  sector_attribution?: SectorAttrib[] | null
  residual_s?: number
  reconciliation?: {
    observed_delta_s: number
    estimated_pace_component_s: number
    residual_s: number
    within_tolerance: boolean
    interpretation: string
  }
  signal_metrics?: Record<string, Record<string, unknown>>
  falsification?: { checks: FalsCheck[]; n_supported: number }
  assumptions?: string[]
  provenance?: Record<string, unknown>
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

function DeltaBar({ value, max, negative }: { value: number; max: number; negative?: boolean }) {
  if (!max) return null
  const pct = Math.min(100, (Math.abs(value) / max) * 100)
  return (
    <div className={negative ? 'tv-bar tv-bar-neg' : 'tv-bar'} style={{ width: `${pct}%` }} />
  )
}

export default function AttributionView() {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState('2023-1')
  const [driverA, setDriverA] = useState('max-verstappen')
  const [driverB, setDriverB] = useState('sergio-perez')
  const [result, setResult] = useState<Attribution | null>(null)
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
        `/api/catalog/attribution/${season}/${round}?${params.toString()}`,
      )
      if (!resp.ok) throw new Error(`Attribution request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selected, driverA, driverB])

  const sessionList: SessionRef[] =
    sessions.length > 0
      ? sessions
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const sectors = result?.sector_attribution || []
  const maxSector = sectors.length ? Math.max(...sectors.map((s) => Math.abs(s.delta_s))) : 0
  const regions = result?.top_loss_regions || []
  const maxRegion = regions.length
    ? Math.max(...regions.map((r) => Math.abs(r.attributed_loss_s)))
    : 0

  return (
    <div className="catalog attribution-view">
      <h2>Loss Attribution</h2>
      <p className="muted small">
        Observed lap delta is measured from canonical lap facts; telemetry only explains it.
        Sector deltas sum exactly to the delta; region losses are speed-trace estimates with an
        explicit residual.
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
          {loading ? 'Attributing…' : 'Attribute Lap'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && result.status !== 'VALID_COMPARISON' && result.status !== 'VALID_WITH_CAVEATS' && (
        <div className="catalog-empty">
          {result.status} — {result.reason || 'comparison not possible with current evidence'}
        </div>
      )}

      {result && (result.status === 'VALID_COMPARISON' || result.status === 'VALID_WITH_CAVEATS') && (
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
              <h4>Sector attribution — measured, sums to the delta</h4>
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>Sector</th>
                    <th>Δ (B − A)</th>
                    <th>Telemetry estimate</th>
                  </tr>
                </thead>
                <tbody>
                  {sectors.map((s) => (
                    <tr key={s.sector}>
                      <td>S{s.sector}</td>
                      <td>
                        <span className="tv-cell">{s.delta_s}s</span>
                        <DeltaBar value={s.delta_s} max={maxSector} negative={s.delta_s < 0} />
                      </td>
                      <td>{s.telemetry_estimated_loss_s}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <h4>Top loss regions — speed-trace estimate (not causal)</h4>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Window</th>
                <th>Speed Δ (km/h)</th>
                <th>Est. loss</th>
              </tr>
            </thead>
            <tbody>
              {regions.map((r) => (
                <tr key={r.region}>
                  <td>{r.t_start_s}–{r.t_end_s}s</td>
                  <td>{r.speed_delta_kmh}</td>
                  <td>
                    <span className="tv-cell">{r.attributed_loss_s}s</span>
                    <DeltaBar value={r.attributed_loss_s} max={maxRegion} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {result.reconciliation && (
            <div className="tv-assoc">
              <div>
                Residual: <strong>{result.reconciliation.residual_s}s</strong> (observed{' '}
                {result.reconciliation.observed_delta_s}s vs estimated{' '}
                {result.reconciliation.estimated_pace_component_s}s)
              </div>
              <div>{result.reconciliation.interpretation}</div>
            </div>
          )}

          {result.falsification && (
            <div className="tv-assumptions">
              <h4>Falsification — alternative explanations tested</h4>
              <ul>
                {result.falsification.checks.map((c, i) => (
                  <li key={i}>
                    <strong>{c.verdict}</strong> — {c.hypothesis} <em>({c.evidence})</em>
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
        </div>
      )}
    </div>
  )
}
