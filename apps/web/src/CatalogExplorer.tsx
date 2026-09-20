import { useCallback, useEffect, useState } from 'react'

interface Capability {
  count?: number
  availability?: 'AVAILABLE' | 'PARTIAL' | 'UNAVAILABLE'
  available?: boolean
  status?: string
  note?: string
}

function capAvailability(cap: Capability | undefined): 'AVAILABLE' | 'PARTIAL' | 'UNAVAILABLE' {
  if (!cap) return 'UNAVAILABLE'
  if (cap.availability) return cap.availability
  if (cap.available === true) return 'AVAILABLE'
  return 'UNAVAILABLE'
}

function capCount(cap: Capability | undefined): number | undefined {
  return cap && typeof cap.count === 'number' ? cap.count : undefined
}

interface CatalogSession {
  session_id: string
  season: number
  round: number
  race_name: string | null
  circuit: string | null
  country: string | null
  date: string | null
  session_type: string
  capabilities: Record<string, Capability & { status?: string; note?: string }>
  providers?: string[]
  provenance?: { source_provider: string | null; catalog_updated_at: string | null }
}

interface CatalogResponse {
  total: number
  page: number
  pages: number
  sessions: CatalogSession[]
}

const CAPABILITY_LABELS: Record<string, string> = {
  results: 'Results',
  qualifying: 'Qualifying',
  pit_stops: 'Pit Stops',
  laps: 'Lap Data',
  stints: 'Stints',
  weather: 'Weather',
  race_control: 'Race Control',
  telemetry: 'Telemetry',
}

function CapabilityMark({ availability }: { availability: string }) {
  if (availability === 'AVAILABLE') return <span className="cap-available" title="AVAILABLE">✓</span>
  if (availability === 'PARTIAL') return <span className="cap-partial" title="PARTIAL">◐</span>
  return <span className="cap-unavailable" title="UNAVAILABLE">—</span>
}

interface Props {
  onInvestigate: (session: CatalogSession) => void
}

export default function CatalogExplorer({ onInvestigate }: Props) {
  const [data, setData] = useState<CatalogResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<CatalogSession | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // filters
  const [search, setSearch] = useState('')
  const [season, setSeason] = useState('')
  const [sessionType, setSessionType] = useState('')
  const [capability, setCapability] = useState('')
  const [page, setPage] = useState(1)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (search.trim()) params.set('search', search.trim())
      if (season) params.set('season', season)
      if (sessionType) params.set('session_type', sessionType)
      if (capability) params.set('capability', capability)
      params.set('page', String(page))
      params.set('page_size', '25')
      const resp = await fetch(`/api/catalog/sessions?${params.toString()}`)
      if (!resp.ok) throw new Error(`Catalog request failed (${resp.status})`)
      setData(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [search, season, sessionType, capability, page])

  useEffect(() => {
    load()
  }, [load])

  async function openDetail(s: CatalogSession) {
    setDetailLoading(true)
    setDetail(null)
    try {
      const resp = await fetch(`/api/catalog/sessions/${s.season}/${s.round}/${s.session_type}`)
      if (!resp.ok) throw new Error(`Detail request failed (${resp.status})`)
      setDetail(await resp.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="catalog">
      <h2>Data Catalog</h2>
      <p className="muted small">
        Every capability below is derived from actual canonical record counts — nothing is assumed
        from the season or provider marketing.
      </p>

      <div className="catalog-filters">
        <input
          placeholder='Search "2023 Bahrain", "Monaco", "2018"...'
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
        />
        <select value={season} onChange={(e) => { setSeason(e.target.value); setPage(1) }}>
          <option value="">All seasons</option>
          {[...Array(27)].map((_, i) => {
            const y = 2026 - i
            return <option key={y} value={y}>{y}</option>
          })}
        </select>
        <select value={sessionType} onChange={(e) => { setSessionType(e.target.value); setPage(1) }}>
          <option value="">All session types</option>
          {['RACE', 'QUALIFYING', 'SPRINT', 'SPRINT_QUALIFYING'].map((t) => (
            <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
          ))}
        </select>
        <select value={capability} onChange={(e) => { setCapability(e.target.value); setPage(1) }}>
          <option value="">Any capability</option>
          {Object.keys(CAPABILITY_LABELS).map((c) => (
            <option key={c} value={c}>has {CAPABILITY_LABELS[c]}</option>
          ))}
        </select>
        <button onClick={() => load()}>Refresh</button>
      </div>

      {error && <div className="catalog-error">Error: {error}</div>}
      {loading && <div className="catalog-loading">Loading catalog…</div>}
      {!loading && data && data.sessions.length === 0 && (
        <div className="catalog-empty">No sessions match these filters.</div>
      )}

      {!loading && data && data.sessions.length > 0 && (
        <>
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Season</th>
                <th>Round</th>
                <th>Race</th>
                <th>Session</th>
                {Object.entries(CAPABILITY_LABELS).map(([key, label]) => (
                  <th key={key} title={label}>{label.split(' ').map((w) => w[0]).join('')}</th>
                ))}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.sessions.map((s) => (
                <tr key={s.session_id} className={detail?.session_id === s.session_id ? 'selected' : ''}>
                  <td>{s.season}</td>
                  <td>{s.round}</td>
                  <td className="race-name" title={s.race_name || ''}>{s.race_name || '—'}</td>
                  <td>{s.session_type.replace(/_/g, ' ')}</td>
                  {Object.keys(CAPABILITY_LABELS).map((cap) => (
                    <td key={cap} className="cap-cell">
                      <CapabilityMark availability={capAvailability(s.capabilities[cap])} />
                    </td>
                  ))}
                  <td>
                    <button onClick={() => openDetail(s)}>Detail</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="catalog-pagination">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>‹ Prev</button>
            <span>Page {data.page} of {data.pages} — {data.total} sessions</span>
            <button disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Next ›</button>
          </div>
        </>
      )}

      {detailLoading && <div className="catalog-loading">Loading session detail…</div>}

      {detail && (
        <div className="catalog-detail">
          <h3>{detail.race_name || `${detail.season} Round ${detail.round}`}</h3>
          <div className="detail-meta">
            {detail.date} · {detail.circuit} · {detail.country} · {detail.session_type.replace(/_/g, ' ')}
          </div>
          <div className="detail-providers">
            Providers: {(detail.providers || []).join(', ') || detail.provenance?.source_provider || '—'}
          </div>
          <ul className="capability-list">
            {Object.entries(CAPABILITY_LABELS).map(([key, label]) => {
              const cap = detail.capabilities[key]
              const availability = capAvailability(cap)
              const count = capCount(cap)
              return (
                <li key={key}>
                  <CapabilityMark availability={availability} />
                  <span className={availability === 'UNAVAILABLE' ? 'muted' : ''}>
                    {label}
                    {count !== undefined && availability !== 'UNAVAILABLE' ? ` — ${count} rows` : ''}
                    {key === 'telemetry' && cap?.note ? ` — ${cap.note}` : ''}
                  </span>
                </li>
              )
            })}
          </ul>
          <button
            className="investigate-btn"
            onClick={() => onInvestigate(detail)}
            disabled={detail.capabilities.results?.availability !== 'AVAILABLE'}
            title={detail.capabilities.results?.availability !== 'AVAILABLE'
              ? 'Investigation requires classification data (UNAVAILABLE for this session)'
              : 'Open this session in the investigation workspace'}
          >
            Investigate Session →
          </button>
        </div>
      )}
    </div>
  )
}
