import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.tsx', 'src/**/*.test.ts'],
    /* See src/test-setup.ts: these views settle asynchronously, and the default
       1s async ceiling was tight enough to fail on a loaded machine. */
    setupFiles: ['./src/test-setup.ts'],
  },
})
