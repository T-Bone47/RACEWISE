import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

/* Single source of truth for the backend origin so `dev` and `preview` cannot
   drift. The production build must be runnable against the real engine -
   a build you cannot exercise is a build you cannot claim is fast. */
const API_TARGET = process.env.RACEWISE_API ?? 'http://localhost:8000'

/* ---------- build identity ----------
   RACEWISE routes on the URL hash (`#/investigate`). Hash changes never
   re-execute JavaScript, so a tab left open across a rebuild keeps running the
   bundle it loaded while the server is already serving a different one. The
   symptom is the worst kind: stale numbers, no error, no error boundary.

   One stamp, emitted into both halves of the page, makes that detectable:
     - `<meta name="x-rw-build">` in index.html, served `no-cache`
     - `__RW_BUILD__`, inlined into the JS bundle
   src/build-version.ts compares the two and reloads on disagreement. If the
   two ever drift apart the guard simply never fires — it cannot produce a
   false positive, which is why the meta tag and the define come from the same
   constant. This is a build *identifier*, not a content hash. */
const BUILD_STAMP = new Date().toISOString()

function buildStamp(stamp: string): Plugin {
  return {
    name: 'racewise-build-stamp',
    transformIndexHtml(html) {
      return html.replace('<!--RW_BUILD_STAMP-->', `<meta name="x-rw-build" content="${stamp}" />`)
    },
  }
}

const apiProxy = {
  '/api': {
    target: API_TARGET,
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react(), buildStamp(BUILD_STAMP)],
  /* Same constant, injected into the bundle itself. */
  define: {
    __RW_BUILD__: JSON.stringify(BUILD_STAMP),
  },
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
  build: {
    /* Modern evergreen baseline: lets esbuild emit native ESM and avoid
       downlevelling syntax the shipped browsers already support. */
    target: 'es2022',
    cssTarget: 'chrome111',
    reportCompressedSize: true,
  },
})