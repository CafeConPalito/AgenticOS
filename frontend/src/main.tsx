import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'
import './i18n'
import './styles/index.css'
import { installClientLog } from './lib/client-log'
import { Providers } from './providers'
import { routes } from './routes'

const router = createBrowserRouter(routes)
// Phase 20: the interface's errors go to the backend's log (and so to the logs to send).
installClientLog()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  </StrictMode>,
)
