/* ============ RACEWISE motion system contract tests (mission §44) ============
   Pins the motion vocabulary: one duration scale, one easing family,
   critically damped springs (no overshoot), reduced-motion honored via
   MotionConfig, and — above all — the rule that ENGINEERING VALUES never
   animate (no numeric interpolation in the motion surface). */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { DUR, EASE_OUT, SPRING, SPRING_DRAWER, T, V, modelLayerKey } from './motion'

const here = dirname(fileURLToPath(import.meta.url))

describe('motion tokens', () => {
  it('keeps one duration scale aligned with the CSS token layer', () => {
    expect(DUR.micro).toBe(150)
    expect(DUR.panel).toBe(200)
    expect(DUR.layout).toBe(320)
    const css = readFileSync(join(here, 'App.css'), 'utf-8')
    expect(css).toContain('--motion-fast: 150ms')
    expect(css).toContain('--motion-normal: 200ms')
    expect(css).toContain('--motion-slow: 320ms')
  })

  it('uses one easing family: controlled deceleration', () => {
    expect(EASE_OUT).toEqual([0.2, 0, 0, 1])
    /* every time-based preset uses it; springs are separate */
    expect(T.micro.ease).toEqual(EASE_OUT)
    expect(T.panel.ease).toEqual(EASE_OUT)
    expect(T.layout.ease).toEqual(EASE_OUT)
  })

  it('springs are critically damped — no bounce, no overshoot', () => {
    expect(SPRING.type).toBe('spring')
    expect(SPRING.damping / SPRING.stiffness).toBeGreaterThanOrEqual(0.09)
    expect(SPRING_DRAWER.type).toBe('spring')
    expect(SPRING_DRAWER.damping / SPRING_DRAWER.stiffness).toBeGreaterThanOrEqual(0.1)
    /* hard ceiling on durations — nothing may exceed the layout scale */
    expect(DUR.layout).toBeLessThanOrEqual(350)
  })

  it('exposes entrance variants for every motion surface', () => {
    for (const name of ['fadeIn', 'riseIn', 'viewIn', 'inspectorIn', 'drawerIn', 'paletteIn', 'backdrop']) {
      expect(V[name]).toBeDefined()
      expect(V[name].initial).toBeDefined()
      expect(V[name].animate).toBeDefined()
    }
  })
})

describe('reduced motion (mission §40 — mandatory)', () => {
  it('the shell mounts MotionConfig with reducedMotion="user"', () => {
    const app = readFileSync(join(here, 'App.tsx'), 'utf-8')
    expect(app).toContain('MotionConfig reducedMotion="user"')
  })

  it('the CSS layer keeps the prefers-reduced-motion rules', () => {
    const css = readFileSync(join(here, 'App.css'), 'utf-8')
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*transition-duration: 0ms/)
  })
})

describe('the motion floor (no animated truth, no decoration)', () => {
  it('never animates engineering values — no number interpolation utilities exist', () => {
    const motionSrc = readFileSync(join(here, 'motion.ts'), 'utf-8')
    for (const banned of ['animate(', 'useSpring', 'useTransform', 'useMotionValue', 'useAnimationFrame']) {
      expect(motionSrc).not.toContain(banned)
    }
  })

  it('the telemetry crosshair stays immediate — no transition on the crosshair class', () => {
    const css = readFileSync(join(here, 'App.css'), 'utf-8')
    expect(css).not.toMatch(/\.tv-crosshair[^{]*\{[^}]*transition/)
  })

  it('the MODELLED layer has a deterministic crossfade key per scenario', () => {
    expect(modelLayerKey(0.5)).toBe('cf-0.5')
    expect(modelLayerKey(1)).toBe('cf-1')
    expect(modelLayerKey(undefined)).toBe('cf-none')
    expect(modelLayerKey(0.25)).not.toBe(modelLayerKey(0.5))
  })

  it('no banned spectacle exists anywhere in the app source', () => {
    const files = ['App.tsx', 'InvestigationView.tsx', 'workspace.tsx', 'stitch.tsx', 'CounterfactualView.tsx', 'motion.ts']
    const all = files.map((f) => readFileSync(join(here, f), 'utf-8')).join('\n')
    for (const banned of ['confetti', 'parallax', 'repeat: Infinity', 'whileHover={{']) {
      expect(all).not.toContain(banned)
    }
    /* drag is ALLOWED only for chart region selection (§38) — assert the
       only drag usage is the canvas drag-to-region */
    const stitch = readFileSync(join(here, 'stitch.tsx'), 'utf-8')
    const dragMentions = (stitch.match(/drag/g) ?? []).length
    expect(dragMentions).toBeGreaterThan(0)      /* the canvas region gesture exists */
    expect(stitch).not.toContain('dragConstraints') /* but nothing is freely draggable */
  })
})
