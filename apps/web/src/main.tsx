import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { installBuildGuard } from './build-version.ts'

/* Before the first render, not after: a tab running an old bundle should reload
   before it paints anything, not after. No-op in dev and in tests. */
installBuildGuard()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
