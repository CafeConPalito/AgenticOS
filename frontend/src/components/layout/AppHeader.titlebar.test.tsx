import { screen } from '@testing-library/react'
import es from '@/i18n/es.json'
import { isMacDesktop } from '@/lib/platform'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

vi.mock('@/lib/platform', () => ({ isMacDesktop: vi.fn() }))

// Phase 20, amendment 1 (CA18): on macOS the header is the title bar.
describe('AppHeader as the title bar', () => {
  beforeEach(() => createFakeBackend({}))

  it('leaves room for the system buttons and drags the window on macOS', async () => {
    vi.mocked(isMacDesktop).mockReturnValue(true)
    renderApp('/')
    const header = (await screen.findByRole('navigation', { name: es.nav.main })).closest('header')!
    expect(header).toHaveAttribute('data-tauri-drag-region')
    expect(header.className).toContain('pl-[84px]')
  })

  it('stays as it was everywhere else', async () => {
    vi.mocked(isMacDesktop).mockReturnValue(false)
    renderApp('/')
    const header = (await screen.findByRole('navigation', { name: es.nav.main })).closest('header')!
    expect(header).not.toHaveAttribute('data-tauri-drag-region')
    expect(header.className).not.toContain('pl-[84px]')
  })
})
