import { useEffect, useRef } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { X as XIcon } from 'lucide-react'
import { stateChipClass } from './types'
import type { LedgerItem } from './types'

/* ============ shared primitives for the 6Q workspace ============ */

export function StateChip({ state, title }: { state: string | null | undefined; title?: string }) {
  if (!state) return <span className="muted">—</span>
  return (
    <span
      className={`ef-badge ${stateChipClass(state)}`}
      title={title || state}
      aria-label={`state ${state.replace(/_/g, ' ').toLowerCase()}`}
    >
      {state.replace(/_/g, ' ')}
    </span>
  )
}

export function ClaimTag({ claimClass }: { claimClass: string }) {
  return <span className={`claim-tag tag-${claimClass}`}>{claimClass}</span>
}

export function KV({ k, children }: { k: string; children: ReactNode }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{children}</dd>
    </>
  )
}

/* ---------- drawer shell (universal right-side surface) ---------- */

export function Drawer({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string
  subtitle?: string
  onClose: () => void
  children: ReactNode
}) {
  const backdropRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      ref={backdropRef}
      className="drawer-backdrop"
      onMouseDown={(e) => {
        if (e.target === backdropRef.current) onClose()
      }}
    >
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <button ref={closeRef} className="drawer-close" onClick={onClose} aria-label="Close panel">
          <XIcon size={15} strokeWidth={1.75} aria-hidden="true" />
        </button>
        <h3>{title}</h3>
        {subtitle && <p className="muted small">{subtitle}</p>}
        {children}
      </aside>
    </div>
  )
}

/* ---------- evidence detail drawer (§11) ---------- */

export function EvidenceDetailDrawer({
  item,
  onClose,
  onTraceToSource,
}: {
  item: LedgerItem
  onClose: () => void
  onTraceToSource?: (item: LedgerItem) => void
}) {
  return (
    <Drawer
      title={`Evidence ${item.evidence_id}`}
      subtitle="Every field below is imported from the investigation ledger — nothing is derived for display."
      onClose={onClose}
    >
      <dl className="drawer-kv">
        <KV k="claim">{item.claim}</KV>
        <KV k="claim class">{item.claim_class}</KV>
        <KV k="evidence type">{item.evidence_type}</KV>
        <KV k="measured value">
          {item.measured_value != null
            ? `${typeof item.measured_value === 'number' ? item.measured_value : JSON.stringify(item.measured_value)} ${item.units ?? ''}`
            : '—'}
        </KV>
        <KV k="state">{item.state ? <StateChip state={item.state} /> : '—'}</KV>
        <KV k="hypotheses">
          {item.hypothesis_ids.length > 0 ? item.hypothesis_ids.join(', ') : '—'}
        </KV>
        <KV k="support">
          {item.supports ? 'supports the hypothesis (evidence-consistency, not causation)' : 'no'}
        </KV>
        <KV k="contradiction">
          {item.contradicts ? 'contradicts the hypothesis' : 'no'}
        </KV>
        <KV k="assumptions">
          {item.assumptions.length > 0 ? (
            <ul className="assumptions-list">{item.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
          ) : '—'}
        </KV>
        <KV k="limitations">
          {item.limitations.length > 0 ? (
            <ul className="assumptions-list">{item.limitations.map((a, i) => <li key={i}>{a}</li>)}</ul>
          ) : '—'}
        </KV>
      </dl>

      <h4>Provenance</h4>
      <dl className="drawer-kv">
        <KV k="source phase">{item.source_phase}</KV>
        <KV k="source tool">{item.source_tool}</KV>
        <KV k="source hash">
          <code className="small">{item.source_hash}</code>
        </KV>
        <KV k="canonical scope">
          <code className="small">{JSON.stringify(item.source_reference)}</code>
        </KV>
      </dl>

      {onTraceToSource && (
        <button className="primary" onClick={() => onTraceToSource(item)}>
          Trace to source →
        </button>
      )}
    </Drawer>
  )
}

/* ---------- universal provenance drawer (§21) ---------- */

export interface ProvenanceTarget {
  kind: string
  id: string
  provenance: Record<string, unknown>
  canonicalReference?: Record<string, unknown>
  assumptions?: string[]
  limitations?: string[]
  extra?: Array<{ k: string; v: ReactNode }>
}

export function ProvenanceDrawer({
  target,
  onClose,
}: {
  target: ProvenanceTarget | null
  onClose: () => void
}) {
  if (!target) return null
  return (
    <Drawer
      title={`Provenance — ${target.kind} ${target.id}`}
      subtitle="The universal “show me why” surface: where this object came from and what bounds its interpretation."
      onClose={onClose}
    >
      <dl className="drawer-kv">
        <KV k="source">
          <code className="small">{JSON.stringify(target.provenance)}</code>
        </KV>
        {target.canonicalReference && Object.keys(target.canonicalReference).length > 0 && (
          <KV k="canonical scope">
            <code className="small">{JSON.stringify(target.canonicalReference)}</code>
          </KV>
        )}
        {(target.extra || []).map((e) => (
          <KV key={e.k} k={e.k}>{e.v}</KV>
        ))}
      </dl>
      {target.assumptions && target.assumptions.length > 0 && (
        <>
          <h4>Assumptions</h4>
          <ul className="assumptions-list">
            {target.assumptions.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </>
      )}
      {target.limitations && target.limitations.length > 0 && (
        <>
          <h4>Limitations</h4>
          <ul className="assumptions-list">
            {target.limitations.map((a, i) => <li key={i}>{a}</li>)}
          </ul>
        </>
      )}
    </Drawer>
  )
}

/* ---------- structured error surface (§24) ---------- */

const ERROR_TITLES: Record<string, string> = {
  INVALID: 'Invalid request',
  UNAVAILABLE: 'Data unavailable',
  INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
  NOT_TESTABLE: 'Not testable',
  TELEMETRY_UNAVAILABLE: 'Telemetry unavailable',
  UNSUPPORTED_MODEL: 'Unsupported model',
  TOOL_FAILURE: 'Tool failure',
  DATA_UNAVAILABLE: 'Data unavailable',
  NETWORK: 'Request failed',
}

export function StructuredError({
  code,
  message,
  hint,
}: {
  code: string
  message: string
  hint?: string
}) {
  const title = ERROR_TITLES[code] || 'Investigation error'
  return (
    <div className="falsification-banner" role="alert">
      <strong>{title}</strong>{' '}
      <span className="st-chip st-untestable">{code.replace(/_/g, ' ')}</span>
      <div className="muted small" style={{ marginTop: 4 }}>{message}</div>
      {hint && <div className="muted small">{hint}</div>}
    </div>
  )
}

/* ---------- context-specific loading line (§22) ---------- */

export function LoadingLine({ label }: { label: string }) {
  return <div className="loading-line" role="status">{label}</div>
}

/* ---------- structural skeleton loaders (§36): shapes mirror the real
   workspace layout, so the page never jumps when data lands ---------- */

export function Skeleton({ style }: { style?: CSSProperties }) {
  return <span className="skeleton" style={style} aria-hidden="true" />
}

export function WorkspaceSkeleton() {
  return (
    <div className="ws-skeleton" role="status" aria-label="Preparing investigation">
      <div className="sk-row">
        <Skeleton style={{ width: 150, height: 14 }} />
        <Skeleton style={{ width: 110, height: 20 }} />
        <span style={{ flex: 1 }} />
        <Skeleton style={{ width: 96, height: 28 }} />
      </div>
      <Skeleton style={{ width: '70%', height: 11 }} />
      <div className="sk-block">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="sk-row">
            <Skeleton style={{ width: 60, height: 11 }} />
            <Skeleton style={{ width: '30%', height: 11 }} />
            <Skeleton style={{ width: '18%', height: 11 }} />
            <Skeleton style={{ width: 56, height: 11 }} />
            <Skeleton style={{ width: 44, height: 11 }} />
          </div>
        ))}
      </div>
      <div className="sk-block">
        <Skeleton style={{ width: '45%', height: 11 }} />
        <Skeleton style={{ width: '90%', height: 11 }} />
        <Skeleton style={{ width: '82%', height: 11 }} />
      </div>
    </div>
  )
}
