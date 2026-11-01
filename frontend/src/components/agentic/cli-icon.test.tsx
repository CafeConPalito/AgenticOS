import { render, screen, within } from '@testing-library/react'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { renderApp } from '@/test/render'
import { CLI_COLORS } from '@/theme/palettes'
import { CliIcon } from './CliIcon'

const stops = (svg: Element) =>
  [...svg.querySelectorAll('stop')].map((stop) => stop.getAttribute('stop-color'))

describe('CliIcon (phase 23, CA5)', () => {
  it('an icon of its own per CLI, named, in its color; a generic one for any other', () => {
    render(
      <>
        <CliIcon cli="claude" label="Claude Code" />
        <CliIcon cli="agy" label="Antigravity CLI" />
        <CliIcon cli="codex" label="Codex" />
      </>,
    )
    const [claude, agy, other] = screen.getAllByRole('img')
    expect(claude).toHaveAccessibleName('Claude Code')
    expect(stops(claude)).toEqual([CLI_COLORS.claude.from, CLI_COLORS.claude.to])
    expect(stops(agy)).toEqual([CLI_COLORS.agy.from, CLI_COLORS.agy.to])
    expect(stops(other)).toEqual([CLI_COLORS.generic.from, CLI_COLORS.generic.to])
    // Each one its own gradient: two icons on a page do not share an id.
    const ids = [claude, agy].map((svg) => svg.querySelector('linearGradient')!.id)
    expect(new Set(ids).size).toBe(2)
  })

  it('CLIs y cuentas shows each CLI with its icon', async () => {
    createFakeBackend()
    renderApp('/clis')
    for (const cli of ['claude', 'agy'] as const) {
      const section = await screen.findByRole('region', {
        name: cli === 'claude' ? 'Claude Code' : 'Antigravity CLI',
      })
      expect(within(section).getByRole('img', { name: es.cli[cli] })).toBeInTheDocument()
    }
  })
})
