import { screen } from '@testing-library/react'
import es from '@/i18n/es.json'
import { mockHealth, renderApp } from '@/test/render'

describe('backend status', () => {
  it('shows "Conectado" with the backend version', async () => {
    const fetchMock = mockHealth('ok', '0.1.0')
    renderApp('/')
    expect(await screen.findByText('Conectado · v0.1.0')).toBeVisible()
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/api/health', undefined)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows "Conectando" while the first request is in flight', async () => {
    mockHealth('pending')
    renderApp('/')
    expect(await screen.findByText(es.backend.connecting)).toBeVisible()
  })

  it('shows the offline banner when the backend is unreachable', async () => {
    mockHealth('error')
    renderApp('/')
    expect(await screen.findByText(es.backend.disconnected)).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent(es.backend.offlineTitle)
    expect(screen.getByRole('button', { name: es.backend.retry })).toBeEnabled()
    expect(screen.getByRole('alert')).toHaveTextContent('http://127.0.0.1:8765')
  })
})
