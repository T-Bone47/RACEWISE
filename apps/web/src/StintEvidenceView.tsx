import { useCallback, useEffect, useState } from 'react'

interface TrajLap {
  lap_number: number
  status?: string
  reason?: string
  observed_delta_s?: number | null
  residual_s?: number | null
  compound?: string | null
  restricted?: boolean
  rain_in_window?: boolean
}

interface TrendBlock {
  status: string
  reason?: string
  slope_per_stint_lap?: number
  first?: number
  last?: number
  min?: number
  max?: number
  n?: number
}

interface HypothesisEvolution {
  [id: string]: {
    label: string
    summary: string
    valid_observations: number
    supported_count: number
    partially_supported_count: number
    not_supported_count: number
    contradicted_count: number
    not_testable_count: number
    support_fraction: number | null
    status_transitions: number
    first_supported_lap: number | null
    last_supported_lap: number | null
  }
}

interface StintEvidence {
  status: string
  reason?: string
  stint_number?: number
  driver_a?: string
  driver_b?: string
  selection?: { candidate_laps: number; valid_laps: number; excluded: Array<{ lap_number: number; reason: string }> }
  trajectory?: TrajLap[]
  performance?: {
    trend?: TrendBlock
    mean_delta_s?: number
    median_delta_s?: number
    first_delta_s?: number
    last_delta_s?: number
    cumulative_gap_s?: { value: number; semantics: string }
  }
  residuals?: {
    trend?: TrendBlock
    cumulative_observed_s?: number
    cumulative_pace_component_s?: number
    cumulative_residual_s?: number
    conservation?: string
  }
  change_point?: { status: string; reason?: string; direction?: string; slope_delta?: number }
  hypothesis_evolution?: HypothesisEvolution
  context_transitions?: Array<{ at_lap_number: number; from: Record<string, unknown>; to: Record<string, unknown> }>
  conclusion?: string
  methodology_version?: string
}

interface SessionRef { season: number; round: number; label: string }

const KNOWN_SESSIONS: Array<{ season: number; round: number }> = [
  { season: 2025, round: 1 },
  { season: 2024, round: 14 },
  { season: 2024, round: 1 },
  { season: 2023, round: 1 },
  { season: 2022, round: 10 },
  { season: 2022, round: 4 },
  { season: 2022, round: 2 },
]

const EV_CLASS: Record<string, string> = {
  CONSISTENTLY_SUPPORTED: 'ef-supported',
  MOSTLY_SUPPORTED: 'ef-supported',
  INTERMITTENTLY_SUPPORTED: 'ef-untestable',
  CONTRADICTED_OVER_TIME: 'ef-contradicted',
  NOT_SUPPORTED: 'ef-contradicted',
  INSUFFICIENT_EVIDENCE: 'ef-untestable',
}

function DeltaBar({ value, max }: { value: number; max: number }) {
  if (!max) return null
  const pct = Math.min(100, (Math.abs(value) / max) * 100)
  return (
    <div className={value < 0 ? 'tv-bar tv-bar-neg' : 'tv-bar'} style={{ width: `${pct}%` }} />
  )
}

export default function StintEvidenceView() {
  const [sessions, setSessions] = useState<SessionRef[]>([])
  const [selected, setSelected] = useState('2022-4')
  const [stint, setStint] = useState('2')
  const [result, setResult] = useState<StintEvidence | null>(null)
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
      const resp = await fetch(
        `/api/catalog/stint-evidence/${season}/${round}?stint=${encodeURIComponent(stint)}`,
      )
      if (!resp.ok) throw new Error(`Stint evidence request failed (${resp.status})`)
      setResult(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    finally {
      setLoading(false)
    }
  }, [selected, stint])

  const sessionList: SessionRef[] =
    sessions.length > 0
      ? sessions
      : KNOWN_SESSIONS.map((s) => ({ ...s, label: `${s.season} R${s.round}` }))

  const valid = result && (result.status === 'VALID_COMPARISON' || result.status === 'VALID_WITH_CAVEATS')
  const traj = (result?.trajectory || []).filter((t) => t.observed_delta_s != null)
  const maxDelta = traj.length ? Math.max(...traj.map((t) => Math.abs(t.observed_delta_s || 0))) : 0
  const trend = result?.performance?.trend
  const hyps = result?.hypothesis_evolution || {}

  return (
    <div className="catalog attribution-view">
      <h2>Stint Evidence</h2>
      <p className="muted small">
        How the lap-delta explanation evolved across one canonical stint. Temporal summaries are
        descriptive facts about evidence status over laps — not confidence scores, not causation.
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
          aria-label="Stint number"
          type="number"
          min={1}
          value={stint}
          onChange={(e) => setStint(e.target.value)}
          style={{ width: '6em' }}
        />
        <button onClick={run} disabled={loading}>
          {loading ? 'Fusing…' : 'Fuse Stint'}
        </button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}

      {result && !valid && (
        <div className="catalog-empty">
          {result.status} — {result.reason || 'stint fusion not possible with current evidence'}
        </div>
      )}

      {result && valid && (
        <div className="catalog-detail">
          <div className="tv-headline">
            Stint {result.stint_number} · {result.driver_a} vs {result.driver_b}
            <span className="muted small">
              {' '}
              ({result.selection?.valid_laps} valid of {result.selection?.candidate_laps} candidate laps)
            </span>
          </div>

          <h4>Performance trajectory (B − A per lap)</h4>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Lap</th>
                <th>Δ (s)</th>
                <th>Context</th>
              </tr>
            </thead>
            <tbody>
              {traj.map((t) => (
                <tr key={t.lap_number}>
                  <td>{t.lap_number}</td>
                  <td>
                    <span className="tv-cell">{t.observed_delta_s}s</span>
                    <DeltaBar value={t.observed_delta_s || 0} max={maxDelta} />
                  </td>
                  <td className="muted small">
                    {t.compound || ''}
                    {t.restricted ? ' · restricted' : ''}
                    {t.rain_in_window ? ' · rain' : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="tv-assoc">
            <div>
              Trend:{' '}
              {trend?.status === 'VALID' && trend.slope_per_stint_lap != null ? (
                <>
                  <strong>{trend.slope_per_stint_lap}s / stint lap</strong>{' '}
                  ({trend.slope_per_stint_lap > 0 ? 'widening' : 'narrowing'} gap, {trend.n} laps)
                </>
              ) : (
                <span className="muted">{trend?.status} — {trend?.reason}</span>
              )}
            </div>
            <div className="muted small">
              First {result.performance?.first_delta_s}s → last {result.performance?.last_delta_s}s ·
              cumulative {result.performance?.cumulative_gap_s?.value}s (selected comparable laps only)
            </div>
          </div>

          <h4>Hypothesis evolution</h4>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Hypothesis</th>
                <th>Over time</th>
                <th>Facts</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(hyps).map(([id, h]) => (
                <tr key={id}>
                  <td>
                    <strong>{h.label}</strong>
                  </td>
                  <td>
                    <span className={`ef-badge ${EV_CLASS[h.summary] || 'ef-untestable'}`}>
                      {h.summary}
                    </span>
                  </td>
                  <td className="small muted">
                    support {h.supported_count}+{h.partially_supported_count}/{h.valid_observations}
                    {' · '}contradicted {h.contradicted_count}
                    {' · '}transitions {h.status_transitions}
                    {h.first_supported_lap != null && (
                      <> · supported laps {h.first_supported_lap}–{h.last_supported_lap}</>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {(result.context_transitions?.length || 0) > 0 && (
            <div className="tv-assumptions">
              <h4>Context transitions</h4>
              <ul>
                {result.context_transitions!.map((c, i) => (
                  <li key={i}>
                    Lap {c.at_lap_number}: {JSON.stringify(c.from)} → {JSON.stringify(c.to)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="tv-assoc">
            <div>
              Change-point: <strong>{result.change_point?.status}</strong>
              {result.change_point?.direction ? ` (${result.change_point.direction})` : ''}
              {result.change_point?.reason ? ` — ${result.change_point.reason}` : ''}
            </div>
            <div className="muted small">
              Cumulative residual {result.residuals?.cumulative_residual_s}s — reported, not
              assigned to any hypothesis. {result.residuals?.conservation}
            </div>
          </div>

          <div className="muted small">{result.conclusion}</div>
          <div className="muted small">methodology {result.methodology_version}</div>
        </div>
      )}
    </div>
  )
}
