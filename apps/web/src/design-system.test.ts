import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

/* ============ Stitch design-system contract tests ============
   The Stitch design is the visual source of truth. These tests pin the
   token layer and the component-class contract so the design system
   cannot silently drift back to the pre-Stitch palette. */

const here = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(join(here, 'App.css'), 'utf-8')

describe('Stitch token layer', () => {
  it('keeps the Stitch surface ladder as the source of truth', () => {
    expect(css).toContain('--st-canvas: #0b0e12')
    expect(css).toContain('--st-surface: #111418')
    expect(css).toContain('--st-element: #171b22')
    expect(css).toContain('--st-hover: #1e232c')
  })

  it('uses the Stitch signal accents', () => {
    expect(css).toContain('--st-primary: #00e5ff')
    expect(css).toContain('--st-secondary: #3875ff')
    expect(css).toContain('--st-secondary-text: #b3c5ff')
  })

  it('aliases every legacy token to a Stitch value (no orphan palettes)', () => {
    expect(css).toMatch(/--bg:\s*var\(--st-canvas\)/)
    expect(css).toMatch(/--panel:\s*var\(--st-surface\)/)
    expect(css).toMatch(/--accent:\s*var\(--st-primary\)/)
    expect(css).toMatch(/--radius:\s*var\(--st-radius-panel\)/)
    expect(css).toMatch(/--radius-sm:\s*var\(--st-radius-el\)/)
  })

  it('keeps the F1-red accent out of the design system', () => {
    expect(css).not.toContain('#e10600')
  })

  it('keeps the epistemic state engine', () => {
    expect(css).toContain('--ep-fact: #3b82f6')
    expect(css).toContain('--ep-calc: #06b6d4')
    expect(css).toContain('--ep-infer: #f59e0b')
    expect(css).toContain('--ep-cf: #8b5cf6')
    expect(css).toContain('--ep-assume: #64748b')
  })

  it('enforces Stitch geometry: 0px panels, 4px interactive elements', () => {
    expect(css).toContain('--st-radius-panel: 0px')
    expect(css).toContain('--st-radius-el: 4px')
  })

  it('prescribes Inter for UI and JetBrains Mono for metrics', () => {
    expect(css).toContain("--font-ui: 'Inter Variable'")
    expect(css).toContain("--font-metric: 'JetBrains Mono Variable'")
  })

  it('carries the reduced-motion accessibility rule', () => {
    expect(css).toContain('prefers-reduced-motion')
  })
})

describe('Stitch flagship component classes', () => {
  it('has the investigation hero (dominant question)', () => {
    expect(css).toContain('.inv-hero')
    expect(css).toContain('.inv-question')
  })

  it('has the metric strip and phase timeline', () => {
    expect(css).toContain('.metric-strip')
    expect(css).toContain('.m-value')
    expect(css).toContain('.phase-timeline')
    expect(css).toContain('.phase.active')
  })

  it('has the telemetry-evidence cross-highlight contract', () => {
    expect(css).toContain('.catalog-table tr.linked')
  })

  it('keeps the orchestrator-vs-engine distinction in the autonomous view', () => {
    expect(css).toContain('.auto-orchestration')
    expect(css).toContain('.auto-engine')
  })
})
