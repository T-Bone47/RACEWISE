/* ============ build identity: a stale tab must not silently run an old bundle ============
   RACEWISE routes on the URL hash (`#/investigate`). A hash change never
   re-executes JavaScript, so a tab left open across a rebuild keeps running the
   bundle it loaded — while the server is already serving a different one. There
   is no error and no error boundary; the screen just quietly shows numbers from
   a build that no longer exists.

   The fix is to make build identity observable. Vite stamps one value into both
   halves of the page:

     index.html  <meta name="x-rw-build" content="...">   served `no-cache`
     bundle      __RW_BUILD__                             inlined by `define`

   If the tab's running stamp and the server's stamp disagree, the tab is
   provably running an old build, so it reloads. Nothing else triggers a
   reload — no timers, no version polling, no surprise navigation.

   Failure policy: a failed probe is never fatal. If the stamp cannot be read,
   or the two are equal, the app proceeds untouched. The worst outcome is that a
   stale tab stays stale, which is where it already was; the app must never go
   blank because a check could not run. */

declare const __RW_BUILD__: string | undefined

/** Stamp compiled into the running bundle. `null` when not defined (tests, exotic hosts). */
export function runningStamp(): string | null {
  return typeof __RW_BUILD__ === 'undefined' ? null : __RW_BUILD__
}

/** Stamp advertised by the server, read from the no-cache index.html. */
export function parseServerStamp(html: string): string | null {
  const tag = /<meta\b[^>]*\bx-rw-build\b[^>]*>/i.exec(html)?.[0]
  if (!tag) return null
  return /content=["']([^"']*)["']/i.exec(tag)?.[1] ?? null
}

/**
 * Should this tab hard-reload? Pure, so the policy is testable without a browser
 * and without a reload ever actually happening during a test run.
 *
 *   reload — the server is demonstrably on a different build
 *   hold   — the build is current, the stamp is unreadable, or we already
 *            reloaded for this exact server build (loop guard)
 */
export function staleDecision(input: {
  running: string | null
  server: string | null
  /** Server stamp this tab already force-reloaded for, from sessionStorage. */
  alreadyReloadedFor: string | null
}): 'reload' | 'hold' {
  const { running, server, alreadyReloadedFor } = input
  if (!server || !running) return 'hold'
  if (server === running) return 'hold'
  if (server === alreadyReloadedFor) return 'hold'
  return 'reload'
}

const STORAGE_KEY = 'rw:reloaded-for'
/** Don't re-probe on every focus event; the tab could be focused constantly. */
const MIN_PROBE_INTERVAL_MS = 15_000

function lastReloadedFor(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null // private mode / storage disabled — the loop guard degrades, nothing breaks
  }
}

function rememberReload(server: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, server)
  } catch {
    /* non-fatal: worst case one extra reload */
  }
}

/** Fetch index.html bypassing the cache and read its build stamp. Never throws. */
export async function probeServerStamp(signal?: AbortSignal): Promise<string | null> {
  try {
    const res = await fetch('/index.html', {
      cache: 'no-cache',
      headers: { 'x-rw-build-probe': '1' },
      signal,
    })
    if (!res.ok) return null
    return parseServerStamp(await res.text())
  } catch {
    return null
  }
}

/** Make the running build inspectable from devtools without rendering UI chrome. */
function markDocument(running: string | null): void {
  try {
    if (running) document.documentElement.dataset.rwBuild = running
  } catch {
    /* no document (SSR/test) — nothing to mark */
  }
}

/**
 * Run the check once now and again whenever the tab is used again (a tab left
 * open overnight is the exact failure this exists for). Returns a teardown.
 */
export function installBuildGuard(): () => void {
  /* In dev there is no meta tag and no meaningful stamp — the guard would be
     dead weight, and a stale-meta artefact could fight the dev server. */
  if (import.meta.env.DEV) return () => {}

  const running = runningStamp()
  markDocument(running)

  let lastProbe = 0
  let inFlight: AbortController | null = null

  const check = async () => {
    const now = Date.now()
    if (now - lastProbe < MIN_PROBE_INTERVAL_MS) return
    lastProbe = now
    inFlight?.abort()
    const ac = new AbortController()
    inFlight = ac
    const server = await probeServerStamp(ac.signal)
    if (ac.signal.aborted) return
    if (staleDecision({ running, server, alreadyReloadedFor: lastReloadedFor() }) !== 'reload') return
    /* Record before reloading: if the reload somehow did not pick up the new
       build, this tab must not reload again on every focus event. */
    if (server) rememberReload(server)
    location.reload()
  }

  const onVisible = () => {
    if (document.visibilityState === 'visible') void check()
  }

  document.addEventListener('visibilitychange', onVisible)
  window.addEventListener('focus', check)
  void check()

  return () => {
    inFlight?.abort()
    document.removeEventListener('visibilitychange', onVisible)
    window.removeEventListener('focus', check)
  }
}