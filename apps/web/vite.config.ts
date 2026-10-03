import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/* Single source of truth for the backend origin so `dev` and `preview` cannot
   drift. The production build must be runnable against the real engine -
   a build you cannot exercise is a build you cannot claim is fast. */
const API_TARGET = process.env.RACEWISE_API ?? 'http://localhost:8000'

const apiProxy = {
  '/api': {
    target: API_TARGET,
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
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