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

/* ============ Stitch-integration component contracts ============
   The new screen-pattern components (context strip, telemetry canvas,
   falsification matrix, counterfactual lab, command-center templates)
   must stay in the design system, and the fabricated Stitch content must
   never leak into the product source. */

import { readdirSync, statSync } from 'node:fs'

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = `${dir}/${f}`
    if (statSync(p).isDirectory()) return sourceFiles(p)
    /* production sources only — test fixtures describe fabrications to
       assert their absence; they are not rendered by the product */
    if (/\.test\.(ts|tsx)$/.test(f)) return []
    return /\.(tsx?|css)$/.test(f) ? [p] : []
  })
}

const src = sourceFiles(join(here))
const allSource = src.map((f) => readFileSync(f, 'utf-8')).join('\n')

describe('Stitch integration component classes', () => {
  it('styles the measured context strip', () => {
    expect(css).toContain('.ctx-strip')
    expect(css).toContain('.ctx-chip')
    expect(css).toContain('.ctx-compound')
  })

  it('styles the aligned telemetry canvas (traces, crosshair, HUD)', () => {
    expect(css).toContain('.tv-canvas')
    expect(css).toContain('.tv-trace-target')
    expect(css).toContain('.tv-crosshair')
    expect(css).toContain('.tv-hud')
    expect(css).toContain('.tv-deficit-region')
  })

  it('styles the falsification matrix pattern', () => {
    expect(css).toContain('.fm-table')
    expect(css).toContain('.fm-ev-chip')
    expect(css).toContain('.fm-trace-step')
    expect(css).toContain('.fm-synthesis')
  })

  it('styles the counterfactual lab ribbons and sweep', () => {
    expect(css).toContain('.cf-ribbons')
    expect(css).toContain('.cf-ribbon')
    expect(css).toContain('.cf-sweep')
  })

  it('styles the command-center templates, console and focused preview', () => {
    expect(css).toContain('.template-pill')
    expect(css).toContain('.nl-console')
    expect(css).toContain('.nl-stage')
    expect(css).toContain('.focus-bar')
    expect(css).toContain('.recent-hyps')
  })

  it('styles the synthesis action row (real actions only)', () => {
    expect(css).toContain('.synth-actions')
  })
})

describe('Fabrication guard (§7, §9, §10, §11, §17, §19 of the mission)', () => {
  it('never claims 100 Hz telemetry — the real grid is 0.25 s', () => {
    expect(allSource).not.toMatch(/100\s?Hz/i)
    /* the honest grid label is present in the rendered sources */
    expect(allSource).toContain('0.25 s')
    expect(allSource).toContain('aligned telemetry')
  })

  it('never renders fabricated confidence values', () => {
    expect(allSource).not.toContain('94.2%')
    expect(allSource).not.toContain('P=0.')
    expect(allSource).not.toContain('99.4%')
    expect(allSource).not.toContain('99.8%')
  })

  it('never renders fabricated solver/branding content', () => {
    expect(allSource).not.toContain('AeroDelta')
    expect(allSource).not.toContain('8-CORE')
    expect(allSource).not.toContain('42k slices')
    expect(allSource).not.toContain('solved investigations indexed')
    expect(allSource).not.toContain('Dr. H. Vance')
    expect(allSource).not.toContain('Sakhir Pitlane LAN')
  })

  it('never offers unsupported actions or telemetry channels', () => {
    expect(allSource).not.toContain('PUBLISH CONSENSUS')
    expect(allSource).not.toContain('Publish Verdict')
    expect(allSource).not.toContain('Publish verdict')
    expect(allSource).not.toContain('SIGN OFF')
    expect(allSource).not.toContain('Sign off')
    expect(allSource).not.toContain('Falsify Claim')
    expect(allSource).not.toMatch(/MGU-[kK]/)
    expect(allSource).not.toContain('state of charge')
    expect(allSource).not.toMatch(/tyre (carcass|surface) temperature/i)
    expect(allSource).not.toContain('steering lock')
    expect(allSource).not.toContain('lateral acceleration')
    expect(allSource).not.toContain('slip ratio')
  })

  it('never labels the 6P graph as causal', () => {
    expect(allSource).not.toMatch(/causal (graph|dag)/i)
    expect(allSource).toContain('Investigation Graph')
  })

  it('always labels modelled counterfactuals', () => {
    expect(allSource).toContain('MODELLED')
    expect(allSource).toContain('NOT HISTORICAL')
  })

  it('keeps the canonical hypothesis-state vocabulary in the chip contract', () => {
    for (const state of ['SUPPORTED', 'PARTIALLY_SUPPORTED', 'NOT_SUPPORTED', 'CONTRADICTED',
      'NOT_TESTABLE', 'INSUFFICIENT_EVIDENCE', 'MIXED_EVIDENCE', 'NOT_REQUESTED']) {
      expect(readFileSync(join(here, 'types.ts'), 'utf-8')).toContain(`case '${state}'`)
    }
  })
})
