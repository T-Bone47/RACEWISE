import { useCallback, useEffect, useState } from 'react'

interface MaxLossWindow {
  t_start_s: number
  t_end_s: number
  speed_delta_kmh: number
  throttle_delta_pct: number
  brake_delta_frac: number
  est_time_loss_s: number
}

interface TelemetryComparison {
  verdict?: string
  reason?: string
  season?: number
  round?: number
  lap_number?: number
  driver_a?: string
  driver_b?: string
  n_windows?: number
  total_est_time_loss_s?: number
  total_scope_note?: string | null
  net_est_time_loss_s?: number
  measured_delta_s?: number | null
  net_residual_s?: number | null
  reconciles_within_tolerance?: boolean | null
  rectification_gap_s?: number
  phase_mixing_flag?: boolean
  phase_mixing_note?: string | null
  max_loss_window?: MaxLossWindow
  top_windows?: MaxLossWindow[]
  throttle_association?: string | null
  brake_association?: string | null
  assumptions?: string[]
  provenance?: string
}

interface SessionRef {
  season: number
  round: number
  race_name: string | null
  telemetry_available: boolean
}

// Sessions the bounded Phase 6C policy actually ingested — the dropdown is
// still driven by the catalog API below, never hardcoded.
const KNOWN_SESSIONS: Array<{ season: number; round: number }> = [
  { season: 2025, round: 1 },
  { season: 2024, round: 1 },
  { season: 2023, round: 1 },
  { season: 2022, round: 1 },
  { season: 2021, round: 10 },
]

function Bar({ value, max, negative }: { value: number; max: number; negative?: boolean }) {
  if (!max) return null
  const pct = Math.min(100, (Math.abs(value) / max) * 100)
  return (
    <div className={`tv-bar ${negative ? 'tv-bar-neg' : ''}`} style={{ width: `${pct}%` }} />
  )
}

export default function TelemetryView() {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState<string>('2023-1')
  const [driverA, setDriverA] = useState('max-verstappen')
  const [driverB, setDriverB] = useState('sergio-perez')
  const [result, setResult] = useState<TelemetryComparison | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const resp = await fetch('/api/catalog/sessions?capability=telemetry&page_size=50')
        if (!resp.ok) return
        const data = await resp.json()
        const refs: SessionRef[] = (data.sessions || []).map((s: { season: number; round: number; race_name: string | null }) => ({
          season: s.season,
          round: s.round,
          race_name: s.race_name,
          telemetry_available: true,
        }))
        if (refs.length > 0) {
          setSessions(refs)
          setSelected(`${refs[0].season}-${refs[0].round}`)
        }
      } catch {
        // keep fallback KNOWN_SESSIONS order; the select below handles empty state
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
      const resp = await fetch(`/api/catalog/telemetry-comparison/${season}/${round}?${params.toString()}`)
      if (!resp.ok) throw new Error(`Telemetry request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [selected, driverA, driverB])

  const sessionList: Array<{ season: number; round: number; label: string }> =
    sessions.length > 0
      ? sessions.map((s) => ({ season: s.season, round: s.round, label: s.race_name || `${s.season} R${s.round}` }))
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const maxLoss = result?.top_windows?.length
    ? Math.max(...result.top_windows.map((w) => Math.abs(w.est_time_loss_s)))
    : 0
  const maxSpeedDelta = result?.top_windows?.length
    ? Math.max(...result.top_windows.map((w) => Math.abs(w.speed_delta_kmh)))
    : 0

  return (
    <div className="catalog telemetry-view">
      <h2>Telemetry Investigation</h2>
      <p className="muted small">
        Deterministic per-window comparison (speed/throttle/brake). Numbers come from the
        canonical telemetry store — this view renders results, it never computes them.
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
          placeholder="driver A key (max-verstappen)"
        />
        <input
          aria-label="Driver B key"
          value={driverB}
          onChange={(e) => setDriverB(e.target.value)}
          placeholder="driver B key (sergio-perez)"
        />
        <button onClick={run} disabled={loading}>
          {loading ? 'Analysing…' : 'Compare Lap'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && result.verdict === 'INSUFFICIENT_EVIDENCE' && (
        <div className="catalog-empty">
          INSUFFICIENT_EVIDENCE — {result.reason || 'no telemetry for this session/lap'}
        </div>
      )}

      {result && result.verdict === 'PASS' && (
        <div className="catalog-detail">
          <h3>
            Lap {result.lap_number}: {result.driver_b} vs {result.driver_a}
          </h3>
          <div className="tv-headline">
            Measured lap delta:{' '}
            <strong>{result.measured_delta_s != null ? `${result.measured_delta_s}s` : '—'}</strong>
            {' '}· net telemetry estimate:{' '}
            <strong>{result.net_est_time_loss_s}s</strong>
            {result.net_residual_s != null && (
              <> (residual <strong>{result.net_residual_s}s</strong>)</>
            )}
          </div>
          <div className="muted small">
            Gross slower-window exposure: {result.total_est_time_loss_s}s across {result.n_windows} windows —
            non-additive localisation aid (faster windows zeroed, not offset), not a second loss figure.
          </div>
          {result.phase_mixing_flag && result.phase_mixing_note && (
            <div className="catalog-empty">{result.phase_mixing_note}</div>
          )}
          <div className="tv-assoc">
            {result.throttle_association && <div>Throttle: {result.throttle_association}</div>}
            {result.brake_association && <div>Brake: {result.brake_association}</div>}
          </div>

          <table className="catalog-table">
            <thead>
              <tr>
                <th>Window start</th>
                <th>Speed Δ (km/h)</th>
                <th>Throttle Δ (%)</th>
                <th>Brake Δ</th>
                <th>Est. loss (s)</th>
              </tr>
            </thead>
            <tbody>
              {(result.top_windows || []).map((w) => (
                <tr key={`${w.t_start_s}`}>
                  <td>{w.t_start_s}s</td>
                  <td>
                    <span className="tv-cell">{w.speed_delta_kmh}</span>
                    <Bar value={w.speed_delta_kmh} max={maxSpeedDelta} negative />
                  </td>
                  <td>{w.throttle_delta_pct}</td>
                  <td>{w.brake_delta_frac}</td>
                  <td>
                    <span className="tv-cell">{w.est_time_loss_s}</span>
                    <Bar value={w.est_time_loss_s} max={maxLoss} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="tv-assumptions">
            <h4>Documented assumptions</h4>
            <ul>
              {(result.assumptions || []).map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
            <p className="muted small">{result.provenance}</p>
          </div>
        </div>
      )}
    </div>
  )
}
