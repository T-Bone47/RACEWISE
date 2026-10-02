import type { TargetAndTransition, Transition } from 'motion/react'

/* ============================================================
   RACEWISE MOTION SYSTEM — the single motion vocabulary
   ------------------------------------------------------------
   Mission: motion communicates state (what changed / where it
   came from / what is selected) — nothing decorative.

   Hard rules (docs/RACEWISE_DESIGN_SYSTEM.md §9):
   1. Engineering values NEVER animate (no number interpolation,
      no telemetry data motion). Only containers/highlights move.
   2. The telemetry crosshair is IMMEDIATE — never animated.
   3. OBSERVED traces stay static; only MODELLED layers may
      crossfade when the scenario changes.
   4. Everything here is gated globally by
      <MotionConfig reducedMotion="user">: users who prefer
      reduced motion get opacity-only / instant state changes.
   5. One easing family, one gentle (critically damped) spring.
      No bounce, no overshoot, no elastic.
   ============================================================ */

/** durations (ms) — aligned with the CSS token layer */
export const DUR = {
  /** micro feedback: color/opacity state changes */
  micro: 150,
  /** surfaces: inspector, drawer, palette, stage switch */
  panel: 200,
  /** layout: sidebar collapse, shared-element flight */
  layout: 320,
} as const

/** the one easing family: controlled deceleration (emphasized ease-out) */
export const EASE_OUT = [0.2, 0, 0, 1] as const

/** the one spring family — critically damped, zero overshoot */
export const SPRING = {
  type: 'spring',
  stiffness: 420,
  damping: 42,
} as const satisfies Transition

/** drawer-grade spring: slightly softer, still no overshoot */
export const SPRING_DRAWER = {
  type: 'spring',
  stiffness: 320,
  damping: 38,
} as const satisfies Transition

/** transition presets — the only transitions components may use */
export const T = {
  micro: { duration: DUR.micro, ease: EASE_OUT } satisfies Transition,
  panel: { duration: DUR.panel, ease: EASE_OUT } satisfies Transition,
  panelSpring: SPRING_DRAWER,
  layout: { duration: DUR.layout, ease: EASE_OUT } satisfies Transition,
  layoutSpring: SPRING,
} as const

/** shared variants — plain targets only (no resolver functions), so they
 *  typecheck directly against motion props */
export const V: Record<string, { initial: TargetAndTransition; animate: TargetAndTransition; exit?: TargetAndTransition }> = {
  /** container appears: opacity + 6px rise (transform auto-disabled under reduced motion) */
  fadeIn: {
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    exit: { opacity: 0 },
  },
  riseIn: {
    initial: { opacity: 0, y: 6 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0 },
  },
  /** workspace view change: short, interruptible */
  viewIn: {
    initial: { opacity: 0, y: 4 },
    animate: { opacity: 1, y: 0 },
  },
  /** right inspector: slides into position like a physical panel */
  inspectorIn: {
    initial: { opacity: 0, x: 14 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: 10 },
  },
  /** modal drawer: scale-anchored surface */
  drawerIn: {
    initial: { opacity: 0, x: 18 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: 12 },
  },
  /** palette: appear fast, keyboard-ready immediately */
  paletteIn: {
    initial: { opacity: 0, scale: 0.985, y: -4 },
    animate: { opacity: 1, scale: 1, y: 0 },
    exit: { opacity: 0, scale: 0.99, y: -2 },
  },
  /** overlay backdrop */
  backdrop: {
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    exit: { opacity: 0 },
  },
}

/** the MODELLED-layer crossfade key: only the counterfactual trace
 *  re-fades when the scenario parameter changes — OBSERVED stays put */
export function modelLayerKey(fraction: number | string | undefined): string {
  return `cf-${fraction ?? 'none'}`
}
