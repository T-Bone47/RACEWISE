import { useEffect, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { T, V } from './motion'
import type { SearchResponse } from './types'

/* ============ command palette: only real application actions ============
   Grouped navigation commands + the /api/catalog/search structured search,
   plus context actions built from the CURRENT route scope (mission §22).
   Degrades silently when the API is unreachable (commands still work).
   Keyboard spans every entry — commands AND search results (audit §7). */

interface CommandGroup { label: string; items: Array<{ label: string; view: string }> }

const COMMAND_GROUPS: CommandGroup[] = [
  {
    label: 'Investigation',
    items: [
      { label: 'New investigation', view: 'command' },
      { label: 'Open active investigation', view: 'investigate' },
      { label: 'Open falsification matrix', view: 'falsification' },
      { label: 'Open counterfactual lab', view: 'counterfactual' },
      { label: 'Autonomous query', view: 'autonomous' },
    ],
  },
  {
    label: 'Knowledge',
    items: [
      { label: 'Open investigation graph', view: 'graph' },
      { label: 'Open engineering memory', view: 'memory' },
      { label: 'Open cross-race patterns', view: 'patterns' },
      { label: 'Open pattern evidence', view: 'patternevidence' },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { label: 'Open lap comparison', view: 'telemetry' },
      { label: 'Open lap attribution', view: 'attribution' },
      { label: 'Open evidence fusion', view: 'fusion' },
      { label: 'Open stint analysis', view: 'stint' },
      { label: 'Open race gap decomposition', view: 'racegap' },
      { label: 'Open performance envelope', view: 'envelope' },
      { label: 'Open regime timeline', view: 'regime' },
    ],
  },
  {
    label: 'Data & workspace',
    items: [
      { label: 'Open data catalog', view: 'catalog' },
      { label: 'Compare investigations', view: 'compare' },
      { label: 'Replay investigation', view: 'replay' },
      { label: 'Toggle focus mode', view: 'zen' },
    ],
  },
]

export default function CommandPalette({
  onClose,
  onNavigate,
  currentView,
  currentParams,
}: {
  onClose: () => void
  onNavigate: (v: string) => void
  currentView: string
  currentParams?: URLSearchParams
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

  /* context actions: real commands built from the current route scope —
     the scope lives in the route params, so the actions are always real */
  const contextActions = useMemo(() => {
    const p = currentParams
    if (!p || [...p.keys()].length === 0) return []
    const has = (k: string) => p.get(k) != null
    const actions: Array<{ label: string; view: string }> = []
    if (has('season') && has('round')) {
      const cf = new URLSearchParams()
      cf.set('season', p.get('season') || '')
      cf.set('round', p.get('round') || '')
      if (p.get('driver_a')) cf.set('reference', p.get('driver_a') || '')
      if (p.get('driver_b')) cf.set('driver', p.get('driver_b') || '')
      if (has('lap_number')) cf.set('lap', p.get('lap_number') || '')
      actions.push({ label: 'Run counterfactual with this scope', view: `counterfactual?${cf.toString()}` })
    }
    if (has('driver_a') && has('driver_b') && has('season') && has('round')) {
      const scope = p.toString()
      actions.push({ label: 'Falsify this scope in the matrix', view: `falsification?${scope}` })
      actions.push({ label: 'Open graph for this scope', view: `graph?${scope}` })
      actions.push({ label: 'Open memory for this scope', view: `memory?${scope}` })
      actions.push({ label: 'Replay this scope', view: `replay?${scope}` })
    }
    if (currentView !== 'command') {
      actions.push({ label: 'Change context', view: 'command' })
    }
    return actions
  }, [currentParams, currentView])

  /* flattened command list with group headers for rendering */
  const commands = useMemo(() => {
    const out: Array<{ kind: 'header' | 'cmd'; label: string; view?: string }> = []
    if (contextActions.length > 0) {
      out.push({ kind: 'header', label: 'This scope' })
      for (const a of contextActions) out.push({ kind: 'cmd', label: a.label, view: a.view })
    }
    for (const g of COMMAND_GROUPS) {
      const items = g.items.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()))
      if (items.length === 0) continue
      out.push({ kind: 'header', label: g.label })
      for (const c of items) out.push({ kind: 'cmd', label: c.label, view: c.view })
    }
    return out
  }, [contextActions, q])

  const commandEntries = commands.filter((c) => c.kind === 'cmd')

  /* keyboard selection spans commands first, then typed search results —
     the index may reach every entry (audit fix) */
  const entries = [
    ...commandEntries.map((c) => ({ kind: 'COMMAND' as const, view: c.view as string, label: c.label, detail: '', type: 'COMMAND' })),
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

  let entryCursor = -1

  return (
    <motion.div
      className="palette"
      role="listbox"
      aria-label="Commands and structured search"
      initial={V.paletteIn.initial}
      animate={V.paletteIn.animate}
      transition={T.micro}
    >
      <input
        autoFocus
        value={q}
        placeholder="Type a command, or search races / drivers / hypotheses / ids…"
        aria-label="Command search"
        onChange={(e) => { setQ(e.target.value); setIdx(0) }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onClose()
          if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, entries.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)) }
          if (e.key === 'Enter' && entries[active]) onNavigate(entries[active].view)
        }}
      />
      <div className="palette-list">
        {entries.length === 0 && (
          <div className="palette-empty">No command matches “{q}”.</div>
        )}
        {commands.map((c, i) => {
          if (c.kind === 'header') {
            return <div key={`h-${i}`} className="palette-group">{c.label}</div>
          }
          entryCursor += 1
          const entryIndex = entryCursor
          return (
            <button
              key={`cmd-${c.view}-${i}`}
              role="option"
              aria-selected={entryIndex === active}
              className={`palette-item ${entryIndex === active ? 'active' : ''}`}
              onMouseEnter={() => setIdx(entryIndex)}
              onClick={() => c.view && onNavigate(c.view)}
            >
              <span className="p-type">COMMAND</span>
              <span>{c.label}</span>
            </button>
          )
        })}
        {(search?.results || []).map((r, j) => {
          const i = commandEntries.length + j
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
              role="option"
              aria-selected={i === active}
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
    </motion.div>
  )
}
