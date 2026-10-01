import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { LapFact, ProfileSamples, SessionContext, StintWindow } from './types'
import { StateChip } from './workspace'

/* ============ Stitch-pattern components backed by real payloads ============
   Every value rendered here comes from a real API response. Where a facet
   is missing the component renders an honest unavailable state - it never
   invents a compound, a temperature, a slope or a trace sample.
   ========================================================================= */

/* ---------- session-context fetch (real rows only) ---------- */

export function useSessionContext(
  season: number,
  round: number,
  sessionType: string,
  drivers: Array<string | undefined>,
): SessionContext | null {
  const [ctx, setCtx] = useState<SessionContext | null>(null)
  const key = `${season}-${round}-${sessionType}-${drivers.filter(Boolean).join(',')}`
  useEffect(() => {
    let cancelled = false
    setCtx(null)
    const params = new URLSearchParams()
    if (sessionType) params.set('session_type', sessionType)
    const list = drivers.filter(Boolean).join(',')
    if (list) params.set('drivers', list)
    fetch(`/api/catalog/session-context/${season}/${round}?${params.toString()}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: SessionContext) => { if (!cancelled) setCtx(j) })
      .catch(() => { if (!cancelled) setCtx(null) })
    return () => { cancelled = true }
  }, [key, season, round, sessionType])
  return ctx
}

/* ---------- measured lap fact for one driver at one lap ---------- */

export function lapFact(
  ctx: SessionContext | null,
  driver: string | undefined,
  lap: number | null,
  stintNumber: number | null,
): LapFact | StintWindow | null {
  if (!ctx || !driver) return null
  const laps = ctx.laps_by_driver?.[driver]
  if (laps && laps.length > 0 && lap != null) {
    const hit = laps.find((l) => l.lap_number === lap)
    if (hit) return hit
  }
  const windows = ctx.stints_by_driver?.[driver]
  if (windows && windows.length > 0) {
    if (stintNumber != null) {
      const hit = windows.find((w) => w.stint_number === stintNumber)
      if (hit) return hit
    }
    if (lap != null) return windows.find((w) => w.lap_start != null && w.lap_end != null
      && lap >= (w.lap_start as number) && lap <= (w.lap_end as number)) || null
  }
  return null
}

/* ---------- context chips (compound · tyre life · position · weather) ---------- */

function shortDriver(driver: string | undefined): string {
  if (!driver) return '—'
  const parts = driver.split('-')
  return parts[parts.length - 1].slice(0, 3).toUpperCase()
}

export function ContextStrip({
  season, round, sessionType, driverA, driverB, lap, stint,
}: {
  season: number
  round: number
  sessionType: string
  driverA: string
  driverB: string
  lap: number | null
  stint: number | null
}) {
  const ctx = useSessionContext(season, round, sessionType, [driverA, driverB])
  if (!ctx) return null

  const chip = (driver: string) => {
    const f = lapFact(ctx, driver, lap, stint)
    if (!f) {
      return (
        <span className="ctx-chip" data-driver={shortDriver(driver)}>
          <span className="ctx-code">{shortDriver(driver)}</span>
          <span className="ctx-detail muted">lap context not in canonical rows</span>
        </span>
      )
    }
    const compound = 'compound' in f ? f.compound : null
    const tyreLife = 'tyre_life' in f ? f.tyre_life : null
    const position = 'position' in f ? f.position : null
    const window = 'lap_start' in f ? `stint ${f.stint_number}` : `lap ${f.lap_number}`
    return (
      <span className="ctx-chip" data-driver={shortDriver(driver)}>
        <span className="ctx-code">{shortDriver(driver)}</span>
        {position != null && <span className="ctx-pos">P{position}</span>}
        {compound && <span className="ctx-compound">{compound}</span>}
        {tyreLife != null && <span className="ctx-detail">{tyreLife}L tyre life</span>}
        {!compound && tyreLife == null && position == null && (
          <span className="ctx-detail muted">{window}</span>
        )}
      </span>
    )
  }

  return (
    <div className="ctx-strip" aria-label="Measured session context">
      {chip(driverA)}
      <span className="ctx-vs muted">vs</span>
      {chip(driverB)}
      {ctx.weather.status === 'AVAILABLE' ? (
        <span className="ctx-chip" title={`${ctx.weather.observations} measured observations`}>
          <span className="ctx-label">AIR</span>
          <span className="ctx-detail mono">
            {ctx.weather.air_temp_c_first ?? '—'}→{ctx.weather.air_temp_c_last ?? '—'}°C
          </span>
          <span className="ctx-label">TRK</span>
          <span className="ctx-detail mono">
            {ctx.weather.track_temp_c_first ?? '—'}→{ctx.weather.track_temp_c_last ?? '—'}°C
          </span>
          {(ctx.weather.rainfall_observations ?? 0) > 0 && (
            <span className="ctx-detail rg-warn">{ctx.weather.rainfall_observations} rainfall obs</span>
          )}
        </span>
      ) : (
        <span className="ctx-chip">
          <span className="ctx-detail muted">weather not recorded</span>
        </span>
      )}
      <span className="ctx-chip" title={ctx.telemetry.policy}>
        <span className="ctx-label">TELEMETRY</span>
        <span className="ctx-detail mono">
          {ctx.telemetry.available
            ? `${ctx.telemetry.covered_laps.length} covered laps · ${ctx.telemetry.analysis_grid_s}s grid`
            : 'not ingested (bounded policy)'}
        </span>
      </span>
    </div>
  )
}

/* ---------- real aligned speed-profile canvas (include_profile) ---------- */

const PAD = { left: 44, right: 12, top: 14, bottom: 22 }
const W = 860
const H = 260

function buildPath(
  xs: number[], ys: number[], xScale: (v: number) => number, yScale: (v: number) => number,
): string {
  if (xs.length === 0) return ''
  let d = `M ${xScale(xs[0]).toFixed(1)},${yScale(ys[0]).toFixed(1)}`
  for (let i = 1; i < xs.length; i++) {
    d += ` L ${xScale(xs[i]).toFixed(1)},${yScale(ys[i]).toFixed(1)}`
  }
  return d
}

export function SpeedProfileCanvas({
  samples,
  referenceLabel,
  targetLabel,
  showCounterfactual,
  counterfactualLabel,
  emptyReason,
  caption,
}: {
  samples: ProfileSamples | null
  referenceLabel?: string
  targetLabel?: string
  showCounterfactual?: boolean
  counterfactualLabel?: string
  emptyReason?: string
  caption?: ReactNode
}) {
  const [hover, setHover] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)

  const geo = useMemo(() => {
    if (!samples || samples.t_s.length === 0) return null
    const t0 = samples.t_s[0]
    const t1 = samples.t_s[samples.t_s.length - 1]
    const all = [...samples.target_kmh,
      ...(samples.reference_kmh ?? []),
      ...(showCounterfactual ? samples.counterfactual_kmh : [])]
    const lo = Math.min(...all)
    const hi = Math.max(...all)
    const span = Math.max(hi - lo, 1e-6)
    const yLo = Math.max(0, lo - span * 0.08)
    const yHi = hi + span * 0.08
    const xScale = (v: number) => PAD.left + ((v - t0) / Math.max(t1 - t0, 1e-6)) * (W - PAD.left - PAD.right)
    const yScale = (v: number) => H - PAD.bottom - ((v - yLo) / Math.max(yHi - yLo, 1e-6)) * (H - PAD.top - PAD.bottom)
    return { t0, t1, yLo, yHi, xScale, yScale }
  }, [samples, showCounterfactual])

  if (!samples || !geo) {
    return (
      <div className="tv-canvas">
        <div className="tv-empty">{emptyReason || 'speed profiles unavailable for this scope'}</div>
      </div>
    )
  }

  const n = samples.t_s.length
  const idx = hover != null ? Math.max(0, Math.min(n - 1, hover)) : null
  const fmt = (v: number | null | undefined, d = 1) =>
    v === null || v === undefined ? '—' : v.toFixed(d)

  const yTicks = 5
  const xTicks = 6

  return (
    <div className="tv-canvas" data-testid="speed-profile-canvas">
      <div className="tv-badges">
        <span className="tv-badge">0.25 S ANALYSIS GRID</span>
        <span className="tv-badge tv-badge-dim">
          {n} OF {samples.n_total_points} POINTS (DETERMINISTIC DECIMATION, DISPLAY ONLY)
        </span>
      </div>
      <svg
        ref={svgRef}
        className="tv-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Aligned speed profiles on the lap-relative analysis grid"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const relX = ((e.clientX - rect.left) / rect.width) * W
          const frac = (relX - PAD.left) / (W - PAD.left - PAD.right)
          setHover(Math.round(frac * (n - 1)))
        }}
        onMouseLeave={() => setHover(null)}
      >
        {/* horizontal grid + y ticks */}
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const v = geo.yLo + ((geo.yHi - geo.yLo) * i) / yTicks
          const y = geo.yScale(v)
          return (
            <g key={`y${i}`}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} className="tv-grid" />
              <text x={PAD.left - 6} y={y + 3} className="tv-tick" textAnchor="end">{Math.round(v)}</text>
            </g>
          )
        })}
        {/* x ticks (lap-relative seconds) */}
        {Array.from({ length: xTicks + 1 }, (_, i) => {
          const t = geo.t0 + ((geo.t1 - geo.t0) * i) / xTicks
          const x = geo.xScale(t)
          return (
            <g key={`x${i}`}>
              <line x1={x} x2={x} y1={H - PAD.bottom} y2={H - PAD.bottom + 4} className="tv-grid" />
              <text x={x} y={H - PAD.bottom + 15} className="tv-tick" textAnchor="middle">{t.toFixed(0)}s</text>
            </g>
          )
        })}
        {/* measured deficit regions (reference faster than target) -
            contiguous shaded spans derived from the real samples */}
        {samples.reference_kmh && (() => {
          const spans: Array<[number, number]> = []
          let start: number | null = null
          for (let i = 0; i < n; i++) {
            const deficit = samples.reference_kmh[i] > samples.target_kmh[i]
            if (deficit && start === null) start = samples.t_s[i]
            if (!deficit && start !== null) {
              spans.push([start, samples.t_s[i]])
              start = null
            }
          }
          if (start !== null) spans.push([start, samples.t_s[n - 1]])
          return spans.map(([s, e], k) => (
            <rect
              key={k}
              x={geo.xScale(s)} y={PAD.top}
              width={Math.max(geo.xScale(e) - geo.xScale(s), 0.5)}
              height={H - PAD.top - PAD.bottom}
              className="tv-deficit-region"
            />
          ))
        })()}
        {/* reference trace */}
        {samples.reference_kmh && (
          <path
            d={buildPath(samples.t_s, samples.reference_kmh, geo.xScale, geo.yScale)}
            className="tv-trace tv-trace-ref"
          />
        )}
        {/* target trace */}
        <path
          d={buildPath(samples.t_s, samples.target_kmh, geo.xScale, geo.yScale)}
          className="tv-trace tv-trace-target"
        />
        {/* counterfactual trace */}
        {showCounterfactual && (
          <path
            d={buildPath(samples.t_s, samples.counterfactual_kmh, geo.xScale, geo.yScale)}
            className="tv-trace tv-trace-cf"
          />
        )}
        {/* crosshair */}
        {idx != null && (
          <g>
            <line
              x1={geo.xScale(samples.t_s[idx])} x2={geo.xScale(samples.t_s[idx])}
              y1={PAD.top} y2={H - PAD.bottom} className="tv-crosshair"
            />
            <circle cx={geo.xScale(samples.t_s[idx])} cy={geo.yScale(samples.target_kmh[idx])} r={3.5} className="tv-dot tv-dot-target" />
            {samples.reference_kmh && (
              <circle cx={geo.xScale(samples.t_s[idx])} cy={geo.yScale(samples.reference_kmh[idx])} r={3} className="tv-dot tv-dot-ref" />
            )}
            {showCounterfactual && (
              <circle cx={geo.xScale(samples.t_s[idx])} cy={geo.yScale(samples.counterfactual_kmh[idx])} r={3} className="tv-dot tv-dot-cf" />
            )}
          </g>
        )}
      </svg>
      {/* synchronized readout HUD - real samples at the hovered index */}
      <div className="tv-hud" aria-label="Trace readout">
        <span className="tv-hud-item">
          <span className="ctx-label">T</span>
          <span className="mono">{idx != null ? `${samples.t_s[idx].toFixed(2)} s` : '—'}</span>
        </span>
        <span className="tv-hud-item">
          <span className="tv-dot tv-dot-target" aria-hidden="true" />
          <span className="mono">{targetLabel || 'target'} {idx != null ? `${fmt(samples.target_kmh[idx])} km/h` : '—'}</span>
        </span>
        {samples.reference_kmh && (
          <span className="tv-hud-item">
            <span className="tv-dot tv-dot-ref" aria-hidden="true" />
            <span className="mono">{referenceLabel || 'reference'} {idx != null ? `${fmt(samples.reference_kmh[idx])} km/h` : '—'}</span>
          </span>
        )}
        {idx != null && samples.reference_kmh && (
          <span className="tv-hud-item tv-hud-delta">
            <span className="mono">
              Δv {fmt(samples.target_kmh[idx] - samples.reference_kmh[idx])} km/h
            </span>
          </span>
        )}
        {showCounterfactual && (
          <span className="tv-hud-item">
            <span className="tv-dot tv-dot-cf" aria-hidden="true" />
            <span className="mono">
              {counterfactualLabel || 'counterfactual'} {idx != null ? `${fmt(samples.counterfactual_kmh[idx])} km/h · ` : ''}MODELLED
            </span>
          </span>
        )}
      </div>
      {caption && <div className="tv-caption muted small">{caption}</div>}
    </div>
  )
}

/* ---------- comparability verdict (real 6E attribution status) ---------- */

interface AttributionStatus { status?: string; reason?: string }

export function ComparabilityChip({
  season, round, driverA, driverB, lap, sessionType,
}: {
  season: number
  round: number
  driverA: string
  driverB: string
  lap: number | null
  sessionType: string
}) {
  const [data, setData] = useState<AttributionStatus | null>(null)
  const key = `${season}-${round}-${driverA}-${driverB}-${lap}`
  useEffect(() => {
    if (sessionType !== 'RACE' || lap == null || lap < 1) return
    let cancelled = false
    setData(null)
    const params = new URLSearchParams({ driver_a: driverA, driver_b: driverB, lap: String(lap) })
    fetch(`/api/catalog/attribution/${season}/${round}?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: AttributionStatus) => { if (!cancelled) setData(j) })
      .catch(() => { if (!cancelled) setData({ status: 'UNAVAILABLE' }) })
    return () => { cancelled = true }
  }, [key, season, round, driverA, driverB, lap, sessionType])
  if (!data?.status) return null
  return (
    <div role="listitem">
      <span className="m-label">Comparability (6E)</span>
      <StateChip state={data.status} />
      {data.reason && <span className="m-sub">{data.reason}</span>}
    </div>
  )
}

/* ---------- degradation context (real 6G stint trend) ---------- */

interface StintEvidenceLite {
  status: string
  reason?: string
  stint_metadata?: {
    driver_a_stint?: { compound?: string | null; lap_range?: Array<number | null> } | null
    driver_b_stint?: { compound?: string | null; lap_range?: Array<number | null> } | null
    laps_selected?: number
  }
  performance?: {
    trend?: { status?: string; slope_per_stint_lap?: number; direction?: string }
    mean_delta_s?: number
    first_delta_s?: number
    last_delta_s?: number
  }
  residuals?: { cumulative_residual_s?: number }
}

export function DegradationContextPanel({
  season, round, driverA, driverB, stint,
}: {
  season: number
  round: number
  driverA: string
  driverB: string
  stint: number | null
}) {
  const [data, setData] = useState<StintEvidenceLite | null>(null)
  const key = `${season}-${round}-${driverA}-${driverB}-${stint}`
  useEffect(() => {
    let cancelled = false
    setData(null)
    const params = new URLSearchParams({ driver_a: driverA, driver_b: driverB })
    if (stint != null && stint >= 1) params.set('stint', String(stint))
    fetch(`/api/catalog/stint-evidence/${season}/${round}?${params.toString()}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: StintEvidenceLite) => { if (!cancelled) setData(j) })
      .catch(() => { if (!cancelled) setData({ status: 'UNAVAILABLE' }) })
    return () => { cancelled = true }
  }, [key, season, round, driverA, driverB])

  if (!data) return null
  const valid = data.status === 'VALID_COMPARISON' || data.status === 'VALID_WITH_CAVEATS'
  const a = data.stint_metadata?.driver_a_stint
  const b = data.stint_metadata?.driver_b_stint
  const trend = data.performance?.trend

  return (
    <section className="panel" aria-label="Degradation context">
      <h2>Degradation context — measured stint evidence (6G)</h2>
      {!valid ? (
        <div className="empty-state">
          {data.status}{data.reason ? ` — ${data.reason}` : ''}
          {' '}No stint trend is shown without measured comparable laps —
          a slope would be fabricated otherwise.
        </div>
      ) : (
        <div className="deg-grid">
          <div className="deg-item">
            <span className="t-microlabel">{shortDriver(driverA)} stint</span>
            <span className="mono">{a?.compound ?? '—'} · laps {a?.lap_range?.[0] ?? '—'}–{a?.lap_range?.[1] ?? '—'}</span>
          </div>
          <div className="deg-item">
            <span className="t-microlabel">{shortDriver(driverB)} stint</span>
            <span className="mono">{b?.compound ?? '—'} · laps {b?.lap_range?.[0] ?? '—'}–{b?.lap_range?.[1] ?? '—'}</span>
          </div>
          <div className="deg-item">
            <span className="t-microlabel">Delta trend (OLS)</span>
            {trend?.status === 'VALID' && trend.slope_per_stint_lap !== undefined ? (
              <span className="mono">{trend.slope_per_stint_lap >= 0 ? '+' : ''}{trend.slope_per_stint_lap} s / stint-lap</span>
            ) : (
              <StateChip state="INSUFFICIENT_EVIDENCE" />
            )}
          </div>
          <div className="deg-item">
            <span className="t-microlabel">Mean delta</span>
            <span className="mono">
              {data.performance?.mean_delta_s !== undefined ? `${data.performance.mean_delta_s} s` : '—'}
            </span>
          </div>
        </div>
      )}
      <p className="muted small">
        Compound, stint windows and slope come from the 6G stint-evidence engine for this
        exact scope. The cumulative residual stays unassigned; consistency over time is
        not causation.
      </p>
    </section>
  )
}
