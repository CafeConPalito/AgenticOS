import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import type { ServerCard, ServerDetail } from '@/api/connections'
import { createFakeBackend } from '@/test/fake-backend'
import { makeConnection } from '@/test/fake-connections'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const c = es.connections

const card = (overrides: Partial<ServerCard> = {}): ServerCard => ({
  source: 'smithery',
  ref: 'github',
  name: 'GitHub',
  description: 'Herramientas de GitHub.',
  author: 'github',
  uses: 6059,
  stars: null,
  updated_at: null,
  category: '',
  url: '',
  transport: 'http',
  verified: true,
  version: '',
  installed_connection_id: null,
  ...overrides,
})

const PG: ServerDetail = {
  card: card({
    source: 'official',
    ref: 'io.github.acme/pg-mcp',
    name: 'pg-mcp',
    author: 'io.github.acme',
    uses: null,
    transport: 'stdio',
    version: '1.0.0',
  }),
  options: [
    {
      index: 0,
      kind: 'npm',
      label: 'Paquete npm',
      package: '@acme/pg-mcp',
      version: 'latest',
      transport: 'stdio',
      url: '',
      oauth: false,
      command: 'npx -y @acme/pg-mcp@2.1.0',
      fields: [
        {
          key: 'PG_PASSWORD',
          label: 'PG_PASSWORD',
          where: 'env',
          name: 'PG_PASSWORD',
          secret: true,
          required: true,
          default: '',
          description: 'Contraseña de la base de datos',
        },
      ],
      requires: ['npx'],
      missing: ['npx'],
    },
    {
      index: 1,
      kind: 'pypi',
      label: 'Paquete PyPI',
      package: 'acme-pg-mcp',
      version: '0.4.0',
      transport: 'stdio',
      url: '',
      oauth: false,
      command: 'uvx acme-pg-mcp==0.4.0',
      fields: [],
      requires: ['uvx'],
      missing: [],
    },
  ],
  license: 'MIT',
  repo_url: 'https://github.com/acme/pg-mcp',
  website: '',
  tools: [],
  security: {},
  note: '',
  installed_as: null,
}

function explorer(extra = {}) {
  return createFakeBackend({
    connections: {
      connections: [],
      listing: {
        cards: [
          card(),
          card({
            source: 'official',
            ref: 'io.github.acme/pg-mcp',
            name: 'pg-mcp',
            author: 'io.github.acme',
            uses: null,
            transport: 'stdio',
            verified: false,
          }),
        ],
        errors: {},
      },
      detail: { 'official|io.github.acme/pg-mcp': PG },
      ...extra,
    },
  })
}

describe('The registries explorer (phase 18, block 11)', () => {
  it('lists the most used with the permanent warning about third parties', async () => {
    installFakeWebSocket()
    explorer()
    renderApp('/conexiones?vista=explorar')
    expect(await screen.findByText(c.explore.mostUsed)).toBeVisible()
    const github = (await screen.findByRole('button', { name: 'Abrir GitHub' })).closest('article')!
    expect(within(github).getByText(/6\.?059 usos|6,1 mil usos/)).toBeVisible()
    expect(within(github).getByText(c.explore.verified)).toBeVisible()
    expect(within(github).getByText(c.explore.transport_http)).toBeVisible()
    expect(screen.getAllByText(c.explore.warning).length).toBeGreaterThan(0)
  })

  it('searches with the filters the person chose', async () => {
    installFakeWebSocket()
    const backend = explorer()
    const user = userEvent.setup()
    renderApp('/conexiones?vista=explorar')
    await screen.findByRole('button', { name: 'Abrir GitHub' })
    await user.type(screen.getByRole('textbox', { name: c.explore.search }), 'postgres')
    await user.click(screen.getByRole('combobox', { name: c.explore.kind }))
    await user.click(await screen.findByRole('option', { name: c.explore.transport_stdio }))
    await user.click(screen.getByRole('button', { name: c.explore.searchButton }))
    await waitFor(() =>
      expect(
        backend
          .callsTo('GET', '/api/connections/registries/search')
          .some((call) => call.query === '?query=postgres&transport=stdio'),
      ).toBe(true),
    )
  })

  it('says there is no connection and that the catalog still works', async () => {
    installFakeWebSocket()
    createFakeBackend({
      connections: {
        connections: [makeConnection({ id: 'x', name: 'mia' })],
        listing: { cards: [], errors: { official: 'offline', smithery: 'offline' } },
      },
    })
    renderApp('/conexiones?vista=explorar')
    expect(await screen.findByText(c.explore.offline)).toBeVisible()
  })

  it('names the source that failed and keeps the others’ results', async () => {
    installFakeWebSocket()
    createFakeBackend({
      connections: {
        connections: [],
        listing: { cards: [card()], errors: { smithery: 'unavailable' } },
      },
    })
    renderApp('/conexiones?vista=explorar')
    expect(await screen.findByText(/no responde \(no disponible\)\./i)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Abrir GitHub' })).toBeVisible()
  })

  it('shows the ficha with the exact command and what is missing, then installs', async () => {
    installFakeWebSocket()
    const backend = explorer()
    const user = userEvent.setup()
    renderApp('/conexiones?vista=explorar')
    await user.click(await screen.findByRole('button', { name: 'Abrir pg-mcp' }))
    expect(await screen.findByText('npx -y @acme/pg-mcp@2.1.0')).toBeVisible()
    expect(screen.getByText('MIT')).toBeVisible()
    expect(
      screen.getByText('En este equipo falta: npx. Instálalo antes de probar la conexión.'),
    ).toBeVisible()
    const secret = screen.getByLabelText(/PG_PASSWORD/)
    expect(secret).toHaveAttribute('type', 'password')
    await user.type(secret, 'pw')
    await user.click(screen.getByRole('checkbox', { name: c.explore.give }))
    await user.click(screen.getByRole('button', { name: c.explore.install }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/registries/install')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/connections/registries/install')[0].body).toMatchObject({
      source: 'official',
      ref: 'io.github.acme/pg-mcp',
      option: 0,
      values: { PG_PASSWORD: 'pw' },
      level: { scope: 'general', project_id: null, agent_id: null },
    })
  })

  it('lets the person pick another way to run it', async () => {
    installFakeWebSocket()
    const backend = explorer()
    const user = userEvent.setup()
    renderApp('/conexiones?vista=explorar')
    await user.click(await screen.findByRole('button', { name: 'Abrir pg-mcp' }))
    await user.click(await screen.findByRole('radio', { name: 'Paquete PyPI' }))
    expect(await screen.findByText('uvx acme-pg-mcp==0.4.0')).toBeVisible()
    await user.click(screen.getByRole('button', { name: c.explore.install }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/registries/install')[0]?.body).toMatchObject(
        {
          option: 1,
        },
      ),
    )
  })

  it('explains it when a server cannot be run from here', async () => {
    installFakeWebSocket()
    explorer({ detail: {} })
    const user = userEvent.setup()
    renderApp('/conexiones?vista=explorar')
    await user.click(await screen.findByRole('button', { name: 'Abrir pg-mcp' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No está en el registro')
  })

  it('checks for updates and says how many there are', async () => {
    installFakeWebSocket()
    const backend = explorer({
      updates: [{ connection_id: 'x', name: 'pg-mcp', version: '2.1.0', latest: '2.2.0' }],
    })
    const user = userEvent.setup()
    renderApp('/conexiones?vista=explorar')
    await user.click(await screen.findByRole('button', { name: c.explore.checkUpdates }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/updates/check')).toHaveLength(1),
    )
    expect(await screen.findByText('1 conexión tiene una versión nueva')).toBeVisible()
  })
})
