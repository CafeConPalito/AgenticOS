import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Listing, RegistryCard, RegistryPreview } from '@/api/skills'
import es from '@/i18n/es.json'
import { createFakeBackend } from '@/test/fake-backend'
import { skillFile } from '@/test/fake-skills'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const x = es.skills.explore

const card = (overrides: Partial<RegistryCard> = {}): RegistryCard => ({
  source: 'skills_sh',
  ref: 'mattpocock/skills/code-review',
  name: 'code-review',
  description: 'Review a branch.',
  author: 'mattpocock',
  installs: 785110,
  stars: null,
  updated_at: null,
  category: 'dev',
  url: 'https://skills.sh/mattpocock/skills/code-review',
  installed_skill_id: null,
  ...overrides,
})

const popular: Listing = {
  cards: [
    card(),
    card({ source: 'anthropic', ref: 'skills/pdf', name: 'pdf', installs: null, category: '' }),
  ],
  errors: {},
  attribution: 'Clasificación: Best Skills by Linkly AI (CC BY 4.0)',
}

const preview: RegistryPreview = {
  id: 'p'.repeat(32),
  card: card(),
  revision: 'bb3048304e5c00',
  repo_url: 'https://github.com/mattpocock/skills',
  path: 'code-review',
  license: 'MIT',
  security: { skills_sh: { snyk: { risk: 'medium' }, socket: { risk: 'safe' } } },
  name: 'code-review',
  body: '# Two-axis review',
  header: { name: 'code-review', description: 'Review a branch.' },
  files: [skillFile('SKILL.md'), skillFile('scripts/check.sh', true)],
  executables: ['scripts/check.sh'],
}

describe('The registry explorer (CA16, CA18)', () => {
  it('lists the most used with their source and installs, and the attribution', async () => {
    installFakeWebSocket()
    createFakeBackend({ skills: { popular } })
    renderApp('/conocimiento?vista=explorar')
    const review = await screen.findByRole('button', { name: 'Ver code-review' })
    expect(within(review).getByText('785.110 instalaciones')).toBeVisible()
    expect(within(review).getByText('skills.sh')).toBeVisible()
    expect(screen.getByText(popular.attribution)).toBeVisible()
    expect(screen.getByRole('note')).toHaveTextContent(x.warning)
  })

  it('says it is offline and that a source failed', async () => {
    installFakeWebSocket()
    createFakeBackend({
      skills: {
        popular: {
          cards: [],
          errors: { ranking: 'offline', anthropic: 'offline' },
          attribution: '',
        },
      },
    })
    renderApp('/conocimiento?vista=explorar')
    expect(await screen.findByRole('alert')).toHaveTextContent(x.offline)
  })

  it('installs only after opening the scripts, at the chosen level', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ skills: { popular, preview } })
    const user = userEvent.setup()
    renderApp('/conocimiento?vista=explorar')
    await user.click(await screen.findByRole('button', { name: 'Ver code-review' }))
    expect(await screen.findByText('snyk: medium')).toBeVisible()
    expect(screen.getByText('MIT')).toBeVisible()
    const install = screen.getByRole('button', { name: x.preview.install })
    expect(install).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Abrir scripts/check.sh' }))
    await waitFor(() => expect(install).toBeEnabled())
    await user.click(install)
    await waitFor(() => expect(backend.skills.installed).toHaveLength(1))
    expect(backend.skills.installed[0]).toMatchObject({
      preview_id: preview.id,
      opened_files: ['scripts/check.sh'],
      scope: 'general',
    })
  })
})
