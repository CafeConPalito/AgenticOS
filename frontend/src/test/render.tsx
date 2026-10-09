import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { resetApiBaseUrl } from '@/lib/api'
import { Providers } from '@/providers'
import { routes } from '@/routes'

/** Renders the whole app at `path` with a fresh query client and router. */
export function renderApp(path = '/') {
  resetApiBaseUrl()
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const result = render(
    <Providers>
      <RouterProvider router={router} />
    </Providers>,
  )
  return { ...result, router }
}

export function mockHealth(response: 'ok' | 'error' | 'pending', version = '0.1.0') {
  const fetchMock = vi.fn(() => {
    if (response === 'pending') return new Promise<Response>(() => {})
    if (response === 'error') return Promise.reject(new TypeError('Failed to fetch'))
    return Promise.resolve(
      new Response(JSON.stringify({ status: 'ok', name: 'Agentic OS', version }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
