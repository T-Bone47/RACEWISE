import { useEffect, useState } from 'react'
import type { SearchResponse } from './types'

/* ============ command palette: only real application actions ============
   Extracted from App.tsx so it can be tested in isolation. The palette
   combines real navigation commands with the /api/catalog/search
   structured search; it degrades silently when the API is unreachable
   (commands still work). Content renders INSIDE the Layer-4 .palette
   surface — a regression test pins this. */

export default function CommandPalette({
  onClose,
  onNavigate,
}: {
  onClose: () => void
  onNavigate: (v: string) => void
  currentView: string
}) {
  const [q, setQ] = useState('')
  const [idx, setIdx] = useState(0)
  const [search, setSearch] = useState<SearchResponse | null>(null)

  /* global search: exact/structured matching via /api/catalog/search —
     no semantic search, deterministic retrieval only */
  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) {
      setSearch(null)
      return
    }
    let cancelled = false
    const t = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/catalog/search?q=${encodeURIComponent(term)}`)
        if (resp.ok && !cancelled) setSearch(await resp.json())
      } catch {
        /* search stays silent on transport errors — commands still work */
      }
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [q])

  const commands = [
    { label: 'New investigation', view: 'command' },
    { label: 'Open active investigation', view: 'autonomous' },
    { label: 'Open investigation workspace', view: 'investigate' },
    { label: 'Open falsification matrix', view: 'falsification' },
    { label: 'Open investigation graph', view: 'graph' },
    { label: 'Compare investigations', view: 'compare' },
    { label: 'Open engineering memory', view: 'memory' },
    { label: 'Replay investigation', view: 'replay' },
    { label: 'Open data catalog', view: 'catalog' },
    { label: 'Open lap comparison', view: 'telemetry' },
    { label: 'Open lap attribution', view: 'attribution' },
    { label: 'Open evidence fusion', view: 'fusion' },
    { label: 'Open stint analysis', view: 'stint' },
    { label: 'Open race gap decomposition', view: 'racegap' },
    { label: 'Open counterfactual lab', view: 'counterfactual' },
    { label: 'Open performance envelope', view: 'envelope' },
    { label: 'Open regime timeline', view: 'regime' },
    { label: 'Open cross-race patterns', view: 'patterns' },
    { label: 'Open pattern evidence', view: 'patternevidence' },
  ]
  const filtered = commands.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()))
  /* keyboard selection spans commands first, then typed search results */
  const entries = [
    ...filtered.map((c) => ({ kind: 'COMMAND' as const, view: c.view, label: c.label, detail: '', type: 'COMMAND' })),
    ...(search?.results || []).map((r) => ({
      kind: 'RESULT' as const,
      view: r.result_type === 'RACE' || r.result_type === 'DRIVER'
        ? `investigate?season=${r.ref.season ?? 2023}&round=${r.ref.round ?? 1}&driver_a=${r.ref.driver_key ?? r.ref.hypothesis_id ?? ''}`
        : r.result_type === 'HYPOTHESIS'
          ? `investigate?question_type=HYPOTHESIS_EVALUATION&hypotheses=${r.ref.hypothesis_id ?? ''}&driver_a=max-verstappen&driver_b=sergio-perez&season=2023&round=1&lap_number=6`
          : r.result_type === 'INVESTIGATION' || r.result_type === 'MEMORY'
            ? `memory`
            : r.result_type === 'PATTERN'
              ? `patternevidence`
              : `investigate`,
      label: r.label,
      detail: r.detail,
      type: r.result_type,
    })),
  ]
  const active = Math.min(idx, Math.max(0, entries.length - 1))

  return (
    <div className="palette">
      <input
        autoFocus
        value={q}
        placeholder="Type a command…"
        aria-label="Command search"
        onChange={(e) => { setQ(e.target.value); setIdx(0) }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onClose()
          if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, filtered.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)) }
          if (e.key === 'Enter' && entries[active]) onNavigate(entries[active].view)
        }}
      />
      <div className="palette-list">
        {entries.length === 0 && (
          <div className="palette-empty">No command matches “{q}”.</div>
        )}
        {filtered.map((c, i) => (
          <button
            key={`cmd-${c.view}`}
            className={`palette-item ${i === active ? 'active' : ''}`}
            onMouseEnter={() => setIdx(i)}
            onClick={() => onNavigate(c.view)}
          >
            <span className="p-type">COMMAND</span>
            <span>{c.label}</span>
          </button>
        ))}
        {(search?.results || []).map((r, j) => {
          const i = filtered.length + j
          const view =
            r.result_type === 'RACE' && typeof r.ref.season === 'number'
              ? `investigate?season=${r.ref.season}&round=${r.ref.round ?? 1}`
              : r.result_type === 'DRIVER' && typeof r.ref.driver_key === 'string'
                ? `investigate?season=2023&round=1&driver_a=${encodeURIComponent(r.ref.driver_key)}&driver_b=sergio-perez&lap_number=6`
                : r.result_type === 'HYPOTHESIS'
                  ? `investigate?question_type=HYPOTHESIS_EVALUATION&hypotheses=${r.ref.hypothesis_id ?? ''}`
                  : r.result_type === 'INVESTIGATION' || r.result_type === 'MEMORY'
                    ? 'memory'
                    : r.result_type === 'PATTERN'
                      ? 'patternevidence'
                      : 'investigate'
          return (
            <button
              key={`res-${r.result_type}-${r.label}-${i}`}
              className={`palette-item ${i === active ? 'active' : ''}`}
              onMouseEnter={() => setIdx(i)}
              onClick={() => onNavigate(view)}
            >
              <span className="p-type">{r.result_type}</span>
              <span>{r.label}{r.detail ? <em className="muted"> — {r.detail}</em> : null}</span>
            </button>
          )
        })}
      </div>
      <div className="palette-hint">
        <span><kbd>↑↓</kbd> navigate</span>
        <span><kbd>Enter</kbd> run</span>
        <span><kbd>Esc</kbd> close</span>
        <span>search is also here — types: RACE / DRIVER / HYPOTHESIS / ids</span>
      </div>
    </div>
  )
}
