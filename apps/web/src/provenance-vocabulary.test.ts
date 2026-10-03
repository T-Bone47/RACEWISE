import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  analyticalLayerCode,
  analyticalLayerLabel,
  formatAnalyticalChain,
} from './provenance'

/* Product invariant (mission §60): the user sees engineering concepts, never
   internal implementation history. The engine tags evidence with short layer
   codes ("6E", "6F", ...); those must never reach the screen verbatim. */
describe('provenance vocabulary', () => {
  it('maps known analytical layer codes to engineering language', () => {
    expect(analyticalLayerLabel('6E')).toBe('Telemetry attribution')
    expect(analyticalLayerLabel('6F')).toBe('Evidence fusion')
    expect(analyticalLayerLabel('6I')).toBe('Telemetry counterfactual')
    expect(analyticalLayerLabel('6K')).toBe('Performance regimes')
  })

  it('never leaks a raw phase code for any known layer', () => {
    const codes = ['6E', '6F', '6G', '6H', '6I', '6J', '6K', '6L', '6M', '6N', '6S']
    for (const code of codes) {
      const label = analyticalLayerLabel(code)
      expect(label).not.toMatch(/^6[A-Z]$/)
      expect(label).not.toContain('Phase')
      expect(label).toMatch(/^[A-Z]/)
      expect(label.length).toBeGreaterThan(0)
    }
  })

  /* Every layer code the engine can emit must have an engineering label.
     Asserting the full set (not a hand-picked subset) means adding a new
     analytical layer without a label fails here rather than leaking to the UI. */
  it('labels every layer code the engine emits', () => {
    const EMITTED = ['6E', '6F', '6G', '6H', '6I', '6J', '6K', '6L', '6M', '6N', '6S']
    for (const code of EMITTED) {
      expect(analyticalLayerLabel(code)).not.toBe(`Layer ${code}`)
    }
  })

  it('degrades honestly for unknown or missing codes instead of inventing a layer', () => {
    expect(analyticalLayerLabel('6Z')).toBe('Layer 6Z')
    expect(analyticalLayerLabel('')).toBe('Unattributed')
    expect(analyticalLayerLabel(undefined)).toBe('Unattributed')
    expect(analyticalLayerLabel(null)).toBe('Unattributed')
  })

  it('preserves the real code for provenance surfaces that legitimately need it', () => {
    expect(analyticalLayerCode('6E')).toBe('6E')
    expect(analyticalLayerCode(undefined)).toBe('')
  })

  it('renders the provenance chain in engineering vocabulary', () => {
    const rendered = formatAnalyticalChain(['6E', '6F', '6G', '6H'])
    expect(rendered).toBe(
      'Telemetry attribution → Evidence fusion → Stint evidence → Race gap decomposition',
    )
    expect(rendered).not.toMatch(/\b6[A-Z]\b/)
  })

  it('keeps every chain step - unknown ones are labelled, never dropped', () => {
    expect(formatAnalyticalChain(['6E', '9Z', '6K'])).toBe(
      'Telemetry attribution → Layer 9Z → Performance regimes',
    )
  })

  it('reports an honest empty chain instead of a blank line', () => {
    expect(formatAnalyticalChain([])).toBe('no analytical chain recorded')
    expect(formatAnalyticalChain(undefined)).toBe('no analytical chain recorded')
  })
})

/* Durable guard: new views are added constantly, and raw layer codes leaking
   into a heading or a caption is an easy regression to make. Rather than trust
   review, scan the view sources for the pattern in user-facing positions. */
describe('no internal layer codes reach the rendered UI (mission §60)', () => {
  const srcDir = join(process.cwd(), 'src')
  const viewFiles = readdirSync(srcDir).filter((f) => f.endsWith('.tsx') && !f.endsWith('.test.tsx'))

  it('finds view files to scan', () => {
    expect(viewFiles.length).toBeGreaterThan(5)
  })

  it('renders no bare phase code in JSX text', () => {
    const offenders: string[] = []

    for (const file of viewFiles) {
      // Strip comments (including JSX {/* ... */}) while preserving line count
      // so reported line numbers still point at the real source line.
      const source = readFileSync(join(srcDir, file), 'utf8')
      const noComments = source
        .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
        .replace(/\/\/[^\n]*/g, (m) => ' '.repeat(m.length))

      noComments.split('\n').forEach((line, i) => {
        const trimmed = line.trim()
        if (!trimmed) return
        // comparing source_phase against a code is legitimate layer logic
        if (line.includes('source_phase')) return
        // this file owns the code->label vocabulary itself
        if (file === 'provenance.ts') return
        // test fixtures carry legacy strings deliberately
        if (file === 'test-utils.ts') return

        // a code in user text: not wrapped in quotes, i.e. actually rendered
        const rendered = line.replace(/'[^']*'/g, "''").replace(/"[^"]*"/g, '""')
        if (/(?:^|[^A-Za-z0-9])(?:Phase\s+)?6[A-Z](?:[^A-Za-z0-9]|$)/.test(rendered)) {
          offenders.push(`${file}:${i + 1}  ${trimmed.slice(0, 90)}`)
        }
      })
    }

    expect(offenders).toEqual([])
  })
})