import { useEffect, useRef } from 'react'
import type { CSSProperties, ReactNode } from 'react'
/* One icon family only (tabler) - lucide was a second competing family used
   for two glyphs, which split visual language and added a dependency. */
import { IconArrowLeft as ArrowLeft, IconX as XIcon } from '@tabler/icons-react'
import { analyticalLayerLabel } from './provenance'
import { AnimatePresence, motion } from 'motion/react'
import { T, V } from './motion'
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

/* ---------- drawer shell (universal right-side surface) ----------
   NOTE: the motion implementation lives at the SECOND Drawer definition
   below (kept adjacent to the drawer-adjacent consumers); this file exports
   exactly one Drawer. */

/* ---------- evidence details (shared by overlay drawer AND contextual inspector) ---------- */

export function EvidenceDetails({
  item,
  onTraceToSource,
}: {
  item: LedgerItem
  onTraceToSource?: (item: LedgerItem) => void
}) {
  return (
    <>
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
        <KV k="analytical layer">{analyticalLayerLabel(item.source_phase)}</KV>
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
    </>
  )
}

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
      <EvidenceDetails item={item} onTraceToSource={onTraceToSource} />
    </Drawer>
  )
}

/* motion: the modal drawer surfaces settle into position (spring, no
   overshoot); the backdrop fades. Reduced motion is honored globally. */
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
    <motion.div
      ref={backdropRef}
      className="drawer-backdrop"
      initial={V.backdrop.initial}
      animate={V.backdrop.animate}
      exit={V.backdrop.exit}
      transition={T.micro}
      onMouseDown={(e) => {
        if (e.target === backdropRef.current) onClose()
      }}
    >
      <motion.aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        initial={V.drawerIn.initial}
        animate={V.drawerIn.animate}
        exit={V.drawerIn.exit}
        transition={T.panelSpring}
      >
        <button ref={closeRef} className="drawer-close" onClick={onClose} aria-label="Close panel">
          <XIcon size={15} strokeWidth={1.75} aria-hidden="true" />
        </button>
        <h3>{title}</h3>
        {subtitle && <p className="muted small">{subtitle}</p>}
        {children}
      </motion.aside>
    </motion.div>
  )
}

/* ---------- universal provenance details (§21) ---------- */

export interface ProvenanceTarget {
  kind: string
  id: string
  provenance: Record<string, unknown>
  canonicalReference?: Record<string, unknown>
  assumptions?: string[]
  limitations?: string[]
  extra?: Array<{ k: string; v: ReactNode }>
}

export function ProvenanceDetails({ target }: { target: ProvenanceTarget }) {
  return (
    <>
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
    </>
  )
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
      <ProvenanceDetails target={target} />
    </Drawer>
  )
}

/* ---------- contextual inspector: evidence/hypothesis/provenance open
   BESIDE the workspace (sticky right column) instead of over it; a back
   stack keeps evidence → trace-to-source → back navigable ---------- */

/* hypothesis drawer payload — every field is real engine output */
export interface HypothesisDetail {
  hypothesis_id: string
  label: string
  statement: string
  criterion: { required: string; rule: string }
  aggregate_state: string
  falsification_status: string
  supporting: LedgerItem[]
  contradicting: LedgerItem[]
  non_decisive: LedgerItem[]
  limitations: string[]
}

export type InspectorEntry =
  | { kind: 'evidence'; item: LedgerItem }
  | { kind: 'provenance'; target: ProvenanceTarget }
  | { kind: 'hypothesis'; hyp: HypothesisDetail }

/* the scientific test, disclosed (mission: prediction → observed →
   criterion → result, never ranked, never guessed) */
export function HypothesisDetails({
  hyp,
  onOpenEvidence,
}: {
  hyp: HypothesisDetail
  onOpenEvidence?: (item: LedgerItem) => void
}) {
  const evidenceChip = (item: LedgerItem, tone: 'sup' | 'con' | 'neu') => (
    <button
      key={item.evidence_id}
      className={`fm-ev-chip`}
      onClick={() => onOpenEvidence?.(item)}
      title={item.claim}
    >
      {item.evidence_id}
      {tone === 'sup' && <span className="hd-arrow" aria-hidden="true">→</span>}
      {tone === 'con' && <span className="hd-arrow hd-arrow-con" aria-hidden="true">↮</span>}
    </button>
  )
  return (
    <div className="hyp-drawer">
      <div className="fm-detail-sec">
        <span className="t-microlabel">Prediction (engine statement)</span>
        <span className="small">{hyp.statement}</span>
      </div>
      <div className="fm-detail-sec">
        <span className="t-microlabel">Observed evidence</span>
        <span className="small muted">
          {hyp.supporting.length + hyp.contradicting.length + hyp.non_decisive.length} evaluated —{' '}
          {hyp.supporting.length} supporting · {hyp.contradicting.length} contradicting ·{' '}
          {hyp.non_decisive.length} non-decisive
        </span>
        {hyp.supporting.length > 0 && (
          <div className="fm-ev-chips fm-supporting">
            {hyp.supporting.map((it) => evidenceChip(it, 'sup'))}
          </div>
        )}
        {hyp.contradicting.length > 0 && (
          <div className="fm-ev-chips fm-contradicting">
            {hyp.contradicting.map((it) => evidenceChip(it, 'con'))}
          </div>
        )}
        {hyp.non_decisive.length > 0 && (
          <div className="fm-ev-chips fm-non-decisive">
            {hyp.non_decisive.map((it) => evidenceChip(it, 'neu'))}
          </div>
        )}
        {hyp.supporting.length + hyp.contradicting.length + hyp.non_decisive.length === 0 && (
          <span className="small muted">
            No evaluated evidence — the state stays honest (NOT_TESTABLE / INSUFFICIENT_EVIDENCE), never guessed.
          </span>
        )}
      </div>
      <div className="fm-detail-sec">
        <span className="t-microlabel">Falsification criterion</span>
        <span className="small muted">
          requires: {hyp.criterion.required} — {hyp.criterion.rule}
        </span>
      </div>
      <div className="fm-detail-sec">
        <span className="t-microlabel">Result</span>
        <span className="small">
          <StateChip state={hyp.aggregate_state} /> · gate: {hyp.falsification_status.toLowerCase()}
        </span>
      </div>
      {hyp.limitations.length > 0 && (
        <div className="fm-detail-sec">
          <span className="t-microlabel">Limitations</span>
          <ul className="assumptions-list small">
            {hyp.limitations.map((l, i) => <li key={i}>{l}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}

export function ContextInspector({
  entry,
  history,
  onBack,
  onClose,
  onTraceToSource,
  onOpenEvidence,
}: {
  entry: InspectorEntry | null
  history: InspectorEntry[]
  onBack: () => void
  onClose: () => void
  onTraceToSource?: (item: LedgerItem) => void
  onOpenEvidence?: (item: LedgerItem) => void
}) {
  /* the PARENT owns both the current entry and the history list; this
     component renders it and routes Esc/BACK to the parent, so evidence →
     trace-to-source → BACK truly returns to the evidence */
  const headRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (!entry) return
    headRef.current?.focus()
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      if (history.length > 1) onBack()
      else onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [entry, history.length, onBack, onClose])

  const current = entry

  const title = current?.kind === 'evidence'
    ? `Evidence ${current.item.evidence_id}`
    : current?.kind === 'hypothesis'
      ? current.hyp.label
      : current
        ? `Provenance — ${current.target.kind} ${current.target.id}`
        : ''
  const subtitle = current?.kind === 'evidence'
    ? 'Every field below is imported from the investigation ledger — nothing is derived for display.'
    : current?.kind === 'hypothesis'
      ? 'The scientific test: prediction, evaluated evidence, falsification criterion, result — exactly as the engine classified them.'
      : current
        ? 'The universal “show me why” surface: where this object came from and what bounds its interpretation.'
        : ''
  /* identity key for the interruptible content fade — the panel head stays
     stable across Evidence A → B so the surface never rebuilds */
  const entryKey = current
    ? current.kind === 'evidence'
      ? `ev-${current.item.evidence_id}`
      : current.kind === 'hypothesis'
        ? `hyp-${current.hyp.hypothesis_id}`
        : `prov-${current.target.kind}-${current.target.id}`
    : ''

  return (
    <AnimatePresence>
      {current && (
        <motion.aside
          className="context-inspector"
          role="complementary"
          aria-label="Contextual inspector"
          initial={V.inspectorIn.initial}
          animate={V.inspectorIn.animate}
          exit={V.inspectorIn.exit}
          transition={T.panelSpring}
        >
          <div className="inspector-head">
            {history.length > 1 && (
              <button
                className="inspector-back"
                onClick={onBack}
                aria-label="Back to previous panel"
              >
                <ArrowLeft size={15} strokeWidth={1.75} aria-hidden="true" />
              </button>
            )}
            {current.kind === 'hypothesis' && (
              /* shared element: this badge is the same object as the row
                 badge the user clicked — it flies into the inspector head
                 (Motion layoutId) and returns on close */
              <motion.span
                layoutId={`hyp-${current.hyp.hypothesis_id}`}
                className={`ef-badge ${stateChipClass(current.hyp.aggregate_state)}`}
                transition={T.layoutSpring}
              >
                {current.hyp.hypothesis_id.split('_')[0]}
              </motion.span>
            )}
            <h3 ref={headRef} tabIndex={-1}>{title}</h3>
            <button className="drawer-close" onClick={onClose} aria-label="Close inspector">
              <XIcon size={15} strokeWidth={1.75} aria-hidden="true" />
            </button>
          </div>
          <p className="muted small">{subtitle}</p>
          <div aria-live="polite">
            <motion.div
              key={entryKey}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={T.micro}
            >
              {current.kind === 'evidence'
                ? <EvidenceDetails item={current.item} onTraceToSource={onTraceToSource} />
                : current.kind === 'hypothesis'
                  ? <HypothesisDetails hyp={current.hyp} onOpenEvidence={onOpenEvidence} />
                  : <ProvenanceDetails target={current.target} />}
            </motion.div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
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

/* ---------- unified honest-state panel (audit §12, mission §23) ----------
   One component for every non-success surface: loading, empty, insufficient
   evidence, unavailable, error. States name the condition, the reason and
   the recovery — AVAILABLE/MISSING lists come from real engine facts. */

export type StatePanelKind = 'loading' | 'empty' | 'insufficient' | 'unavailable' | 'error'

const STATE_PANEL_META: Record<StatePanelKind, { cls: string; label: string }> = {
  loading: { cls: 'sp-loading', label: 'LOADING' },
  empty: { cls: 'sp-empty', label: 'EMPTY' },
  insufficient: { cls: 'sp-insufficient', label: 'INSUFFICIENT EVIDENCE' },
  unavailable: { cls: 'sp-unavailable', label: 'UNAVAILABLE' },
  error: { cls: 'sp-error', label: 'ERROR' },
}

export function StatePanel({
  kind,
  title,
  reason,
  available,
  missing,
  action,
}: {
  kind: StatePanelKind
  title: string
  reason?: string
  available?: string[]
  missing?: string[]
  action?: ReactNode
}) {
  const meta = STATE_PANEL_META[kind]
  return (
    <div
      className={`state-panel ${meta.cls}`}
      role={kind === 'error' ? 'alert' : 'status'}
      aria-live={kind === 'error' ? 'assertive' : undefined}
    >
      <div className="sp-head">
        <span className={`sp-dot ${meta.cls}`} aria-hidden="true" />
        <span className="sp-kind mono">{meta.label}</span>
        <span className="sp-title">{title}</span>
      </div>
      {reason && <p className="sp-reason muted small">{reason}</p>}
      {(available && available.length > 0) || (missing && missing.length > 0) ? (
        <div className="sp-lists">
          {available && available.length > 0 && (
            <div className="sp-list sp-list-available">
              <span className="t-microlabel">Available</span>
              <ul>
                {available.map((a) => <li key={a}>{a}</li>)}
              </ul>
            </div>
          )}
          {missing && missing.length > 0 && (
            <div className="sp-list sp-list-missing">
              <span className="t-microlabel">Missing</span>
              <ul>
                {missing.map((m) => <li key={m}>{m}</li>)}
              </ul>
            </div>
          )}
        </div>
      ) : null}
      {action && <div className="sp-action">{action}</div>}
    </div>
  )
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
