/**
 * Analytical-layer provenance vocabulary.
 *
 * The engine tags each evidence item with the analytical layer that produced
 * it, using internal short codes ("6E", "6F", ...). Those codes are build
 * history, not engineering meaning, so they are never shown to the user as-is
 * (docs/RACEWISE_DESIGN_SYSTEM.md §4b: no internal implementation language in
 * the product).
 *
 * This lives outside `workspace.tsx` deliberately: it contains no components,
 * so it does not degrade that module's fast-refresh boundary.
 *
 * The underlying value is still real and still recorded in the payload and the
 * provenance inspector — only the label the user reads changes.
 */

const ANALYTICAL_LAYER_LABELS: Record<string, string> = {
  '6E': 'Telemetry attribution',
  '6F': 'Evidence fusion',
  '6G': 'Stint evidence',
  '6H': 'Race gap decomposition',
  '6I': 'Telemetry counterfactual',
  '6J': 'Performance envelope',
  '6K': 'Performance regimes',
  '6L': 'Cross-race pattern',
  '6M': 'Cross-race evidence',
  '6N': 'Investigation synthesis',
  '6S': 'Engineering validation',
}

/** Human-readable name for the analytical layer behind an evidence item. */
export function analyticalLayerLabel(sourcePhase: string | undefined | null): string {
  const code = (sourcePhase ?? '').trim()
  if (!code) return 'Unattributed'
  return ANALYTICAL_LAYER_LABELS[code] ?? `Layer ${code}`
}

/** The raw engine code, for provenance surfaces that legitimately need it. */
export function analyticalLayerCode(sourcePhase: string | undefined | null): string {
  return (sourcePhase ?? '').trim()
}

/**
 * Render the provenance chain in engineering vocabulary.
 *
 * The engine records the exact analytical chain it executed ("6E", "6F", ...).
 * That is genuine provenance, but the inline summary line reads as build
 * history if shown verbatim. Unknown steps pass through as `Layer X` rather
 * than being dropped, so no step is ever silently hidden.
 */
export function formatAnalyticalChain(chain: string[] | undefined | null): string {
  if (!chain || chain.length === 0) return 'no analytical chain recorded'
  return chain.map((step) => analyticalLayerLabel(step)).join(' → ')
}