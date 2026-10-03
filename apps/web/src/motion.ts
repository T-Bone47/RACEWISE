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

/** durations (ms) — aligned with the CSS token layer.
 *
 * Tuned for an instrument, not a marketing page. An engineering workstation
 * must feel like a tool: the operator's next action has to already be
 * available by the time their eyes arrive. Every value here is deliberately at
 * the fast end of the comfortable band.
 *
 * Asymmetry is the single biggest perceived-speed lever: exits resolve faster
 * than entrances, so dismissing something never feels like waiting on it. */
export const DUR = {
  /** micro feedback: color/opacity state changes */
  micro: 110,
  /** surfaces: inspector, drawer, palette, stage switch */
  panel: 140,
  /** layout: sidebar collapse, shared-element flight */
  layout: 200,
  /** exits — uniformly faster than their matching entrance (asymmetric timing) */
  exitMicro: 90,
  exitPanel: 110,
} as const

/** the one easing family: controlled deceleration (emphasized ease-out) */
export const EASE_OUT = [0.2, 0, 0, 1] as const

/** the one spring family — critically damped, zero overshoot.
 *
 *  Stiffness is what makes motion feel fast; damping must rise with it or the
 *  spring overshoots and the interface reads as bouncy/cheap. The invariant
 *  this project holds is `damping / stiffness >= 0.09` (enforced by
 *  motion-system.test.ts), so stiffness is raised only as far as damping can
 *  follow. Raising stiffness without that is what produces the "slow but
 *  springy" float people describe as sluggish. */
export const SPRING = {
  type: 'spring',
  stiffness: 540,
  damping: 50, // 50/540 = 0.0926 — critically damped
} as const satisfies Transition

/** drawer-grade spring: settles fast, still no overshoot */
export const SPRING_DRAWER = {
  type: 'spring',
  stiffness: 620,
  damping: 64, // 64/620 = 0.1032 — drawer surfaces hold the stricter ratio
} as const satisfies Transition

/** transition presets — the only transitions components may use */
export const T = {
  micro: { duration: DUR.micro, ease: EASE_OUT } satisfies Transition,
  panel: { duration: DUR.panel, ease: EASE_OUT } satisfies Transition,
  /** exits resolve faster than entrances (asymmetric timing) */
  exitMicro: { duration: DUR.exitMicro, ease: EASE_OUT } satisfies Transition,
  exitPanel: { duration: DUR.exitPanel, ease: EASE_OUT } satisfies Transition,
  panelSpring: SPRING_DRAWER,
  layout: { duration: DUR.layout, ease: EASE_OUT } satisfies Transition,
  layoutSpring: SPRING,
} as const

/** shared variants — plain targets only (no resolver functions), so they
 *  typecheck directly against motion props.
 *
 *  Exit variants exist so `AnimatePresence` can resolve them under the
 *  faster `T.exitPanel` transition instead of replaying the entrance. */
export const V: Record<string, { initial: TargetAndTransition; animate: TargetAndTransition; exit?: TargetAndTransition }> = {
  /** container appears: opacity + 6px rise (transform auto-disabled under reduced motion) */
  fadeIn: {
    initial: { opacity: 0 },
    animate: { opacity: 1 },
    exit: { opacity: 0 },
  },
  riseIn: {
    initial: { opacity: 0, y: 4 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0 },
  },
  /** workspace view change: short, interruptible, and symmetric-free
   (the 4px rise is the only movement — a view swap must never feel like a
   transition the operator has to wait out) */
  viewIn: {
    initial: { opacity: 0, y: 3 },
    animate: { opacity: 1, y: 0 },
  },
  /** right inspector: slides into position like a physical panel */
  inspectorIn: {
    initial: { opacity: 0, x: 10 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: 6 },
  },
  /** modal drawer: scale-anchored surface */
  drawerIn: {
    initial: { opacity: 0, x: 14 },
    animate: { opacity: 1, x: 0 },
    exit: { opacity: 0, x: 8 },
  },
  /** palette: appear fast, keyboard-ready immediately */
  paletteIn: {
    initial: { opacity: 0, scale: 0.99, y: -3 },
    animate: { opacity: 1, scale: 1, y: 0 },
    exit: { opacity: 0, scale: 0.995, y: -2 },
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
