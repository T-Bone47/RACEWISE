import type { TargetAndTransition, Transition } from 'motion/react'

/** Motion's `initial` also accepts `false` ("do not run an entrance
 *  animation") in addition to a target object. */
type VariantInitial = TargetAndTransition | false

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

/** Durations, in MILLISECONDS, for authoring and for the CSS token layer.
 *
 *  ⚠ These are milliseconds. Motion's `duration` is expressed in SECONDS
 *  (see `Transition.duration` in motion-dom: "The visual duration is a time,
 *  set in seconds"). Handing Motion `duration: 140` therefore means *140
 *  seconds*, not 140ms — which is exactly what happened here: every view
 *  transition resolved to a multi-minute fade, so a navigated workspace sat at
 *  `opacity: 0` and looked permanently blank.
 *
 *  `T` below converts to seconds once, at the boundary, so no call site can
 *  repeat the mistake. */
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

/** ms -> s. The single conversion point between our token layer and Motion. */
const secs = (ms: number) => ms / 1000

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

/** transition presets — the only transitions components may use.
 *  Durations are converted ms -> s here; components never do it themselves. */
export const T = {
  micro: { duration: secs(DUR.micro), ease: EASE_OUT } satisfies Transition,
  panel: { duration: secs(DUR.panel), ease: EASE_OUT } satisfies Transition,
  /** exits resolve faster than entrances (asymmetric timing) */
  exitMicro: { duration: secs(DUR.exitMicro), ease: EASE_OUT } satisfies Transition,
  exitPanel: { duration: secs(DUR.exitPanel), ease: EASE_OUT } satisfies Transition,
  panelSpring: SPRING_DRAWER,
  layout: { duration: secs(DUR.layout), ease: EASE_OUT } satisfies Transition,
  layoutSpring: SPRING,
} as const

/** shared variants — plain targets only (no resolver functions), so they
 *  typecheck directly against motion props.
 *
 *  Exit variants exist so `AnimatePresence` can resolve them under the
 *  faster `T.exitPanel` transition instead of replaying the entrance. */
export const V: Record<string, { initial: VariantInitial; animate: TargetAndTransition; exit?: TargetAndTransition }> = {
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
  /** workspace view change.
   *
   *  Deliberately INSTANT. An engineering workstation must never withhold
   *  content behind an animation: an entrance fade means the evidence is
   *  technically absent for its duration, so the operator's eye arrives at
   *  something that isn't there yet. View switches therefore do not animate
   *  in — the new view is present on the first frame it can be painted.
   *
   *  Motion still runs where it carries meaning the operator actually reads:
   *  the nav selection cursor (layoutId), inspectors, drawers, the palette,
   *  and the modelled/observed crossfade. Those describe relationships
   *  (what opened, what is selected, what came from where) rather than
   *  decorating an arrival. */
  viewIn: {
    initial: false,
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
