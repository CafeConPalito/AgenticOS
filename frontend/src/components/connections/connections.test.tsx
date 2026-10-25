import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeProject } from '@/test/fake-backend'
import { makeConnection, TOOLS } from '@/test/fake-connections'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const c = es.connections

function catalog() {
  return [
    makeConnection({
      id: 'gh',
      name: 'github',
      tested_at: new Date().toISOString(),
      tools: TOOLS,
      usage: {
        received_runs: 3,
        used_runs: 3,
        calls: 14,
        failed_calls: 1,
        last_used: new Date().toISOString(),
      },
    }),
    makeConnection({
      id: 'db',
      name: 'tienda-db',
      enabled: false,
      transport: 'stdio',
      command: 'npx',
      args: ['-y', 'pg'],
      headers: {},
      secrets: [{ key: 'PASSWORD', set: false }],
      assignments: [],
      origin: 'import',
    }),
  ]
}

describe('The connections catalog (phase 18, block 9)', () => {
  it('lists the cards with their state, usage and where each one is given', async () => {
    installFakeWebSocket()
    createFakeBackend({ connections: { connections: catalog() } })
    renderApp('/conexiones')
    const card = (await screen.findByRole('button', { name: 'Abrir github' })).closest('article')!
    expect(within(card).getByText(c.transport.http)).toBeVisible()
    expect(within(card).getByText(c.level.general)).toBeVisible()
    expect(within(card).getByText(/Probada · 2 herramientas/)).toBeVisible()
    expect(within(card).getByText(/3 ejecuciones · 14 llamadas/)).toBeVisible()
    const other = screen.getByRole('button', { name: 'Abrir tienda-db' }).closest('article')!
    expect(within(other).getByText(c.card.unassigned)).toBeVisible()
    expect(within(other).getByText(c.origin.import)).toBeVisible()
    expect(within(other).getByText('Falta 1 secreto')).toBeVisible()
    expect(within(other).getByText(c.card.untested)).toBeVisible()
    expect(screen.getByText('1 activas de 2')).toBeVisible()
  })

  it('switches a connection off from its card', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ connections: { connections: catalog() } })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('switch', { name: 'Activar github' }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/connections/gh')[0]?.body).toEqual({ enabled: false }),
    )
  })

  it('creates a local connection with a secret that is sent apart', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ connections: { connections: [] } })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: c.actions.new }))
    await user.type(screen.getByLabelText(c.form.name), 'postgres')
    await user.type(screen.getByLabelText(c.form.command), 'npx')
    await user.type(screen.getByLabelText(c.form.args), '-y{enter}pg-mcp')
    await user.click(screen.getByRole('button', { name: c.form.addRow }))
    await user.type(screen.getByLabelText('Variable 1'), 'PG_PASSWORD')
    await user.click(screen.getByRole('checkbox', { name: 'Secreto: PG_PASSWORD' }))
    // the secret shows up in its own list, as a password field
    await user.type(screen.getByLabelText('Valor secreto de PG_PASSWORD'), 'hunter2')
    expect(screen.getByLabelText('Valor secreto de PG_PASSWORD')).toHaveAttribute(
      'type',
      'password',
    )
    await user.click(screen.getByRole('button', { name: c.actions.save }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/connections')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/connections')[0].body).toMatchObject({
      name: 'postgres',
      transport: 'stdio',
      command: 'npx',
      args: ['-y', 'pg-mcp'],
      env: { PG_PASSWORD: '${secret:PG_PASSWORD}' },
      secrets: { PG_PASSWORD: 'hunter2' },
      auth: 'none',
    })
  })

  it('shows the backend’s reason when the name is taken', async () => {
    installFakeWebSocket()
    createFakeBackend({ connections: { connections: catalog() } })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: c.actions.new }))
    await user.type(screen.getByLabelText(c.form.name), 'github')
    await user.type(screen.getByLabelText(c.form.command), 'x')
    await user.click(screen.getByRole('button', { name: c.actions.save }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ya hay una conexión con ese nombre.',
    )
  })

  it('creates connections from a pasted JSON after reviewing it', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ connections: { connections: [] } })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: c.actions.new }))
    await user.click(screen.getByRole('tab', { name: c.editor.tabJson }))
    await user.click(screen.getByLabelText(c.paste.label))
    await user.paste('{"mcpServers": {"pasted-a": {"command": "npx"}}}')
    await user.click(screen.getByRole('button', { name: c.paste.review }))
    const preview = await screen.findByRole('list', { name: c.paste.preview })
    expect(within(preview).getByText('pasted-a')).toBeVisible()
    expect(within(preview).getByText('Secretos que guardará: PASSWORD')).toBeVisible()
    expect(within(preview).getByText('No importado: oauth')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Crear 1 conexión' }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/connections')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/connections')[0].body).toMatchObject({
      json_text: '{"mcpServers": {"pasted-a": {"command": "npx"}}}',
    })
  })

  it('creates a connection from a template asking only for its token', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ connections: { connections: [] } })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: c.actions.fromTemplate }))
    await user.click(await screen.findByRole('button', { name: /GitHub/ }))
    const token = screen.getByLabelText('Token personal de GitHub')
    expect(token).toHaveAttribute('type', 'password')
    await user.type(token, 'ghp_secret')
    await user.click(screen.getByRole('button', { name: c.templates.create }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/from-template')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/connections/from-template')[0].body).toMatchObject({
      template: 'github',
      values: { GITHUB_TOKEN: 'ghp_secret' },
    })
  })

  it('warns when the program a template needs is missing', async () => {
    installFakeWebSocket()
    createFakeBackend({
      connections: {
        connections: [],
        requirements: [{ program: 'npx', found: false, path: '' }],
      },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: c.actions.fromTemplate }))
    await user.click(await screen.findByRole('button', { name: /Playwright/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Para usarla necesitas instalar: npx.',
    )
  })

  it('imports the CLIs’ servers, each to the level the person picks', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      agents: [makeAgent({ id: 'a1', name: 'Dev' })],
      projects: [makeProject({ id: 'p1', name: 'Tienda' })],
      connections: {
        connections: [],
        found: [
          {
            id: 'f1',
            source: 'claude',
            origin: 'Claude Code (global)',
            name: 'excalidraw',
            transport: 'http',
            target: 'https://x.example.test/mcp',
            env_keys: [],
            header_keys: ['Authorization'],
            has_secrets: true,
            ignored: [],
            imported: false,
          },
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: c.actions.import }))
    await user.click(await screen.findByRole('checkbox', { name: 'Importar excalidraw' }))
    expect(screen.getByText(c.import.secrets)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Importar 1' }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/connections/import')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/connections/import')[0].body).toMatchObject({
      items: [{ id: 'f1', scope: 'general' }],
    })
  })
})

describe('One connection: tools, login and levels (phase 18, block 9)', () => {
  it('tests the connection and lists what it found', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      connections: { connections: [makeConnection({ id: 'gh', name: 'github' })] },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: 'Abrir github' }))
    await user.click(await screen.findByRole('tab', { name: c.sheet.tools }))
    expect(screen.getByText(c.tools.none)).toBeVisible()
    await user.click(screen.getByRole('button', { name: c.tools.test }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/connections/gh/test')).toHaveLength(1))
    expect(await screen.findByText('read_note')).toBeVisible()
    expect(screen.getByText('write_note')).toBeVisible()
    expect(screen.getByText(c.tools.readOnly)).toBeVisible()
    expect(screen.getByText(c.tools.destructive)).toBeVisible()
    expect(screen.getByRole('status')).toHaveTextContent('Funciona: 2 herramientas (1.2 s)')
  })

  it('says in words why a test failed', async () => {
    installFakeWebSocket()
    createFakeBackend({
      connections: {
        connections: [makeConnection({ id: 'gh', name: 'github' })],
        testResult: {
          ok: false,
          seconds: 0.3,
          server: {},
          tools: [],
          resources: [],
          prompts: [],
          error: {
            code: 'command_not_found',
            message: 'No se encuentra «npx». Falta Node.js: instálalo desde nodejs.org.',
            detail: '',
          },
        },
      },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: 'Abrir github' }))
    await user.click(await screen.findByRole('tab', { name: c.sheet.tools }))
    await user.click(screen.getByRole('button', { name: c.tools.test }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Falta Node.js')
  })

  it('chooses which tools the agents get and which ask nothing', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      connections: {
        connections: [
          makeConnection({
            id: 'gh',
            name: 'github',
            tools: TOOLS,
            tested_at: new Date().toISOString(),
          }),
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: 'Abrir github' }))
    await user.click(await screen.findByRole('tab', { name: c.sheet.tools }))
    expect(screen.queryByRole('checkbox', { name: 'Permitir read_note' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: c.tools.mode_selected }))
    await user.click(screen.getByRole('checkbox', { name: 'Permitir read_note' }))
    await user.click(screen.getByRole('checkbox', { name: 'Sin preguntar: read_note' }))
    // a tool that is not allowed cannot be pre-approved
    expect(screen.getByRole('checkbox', { name: 'Sin preguntar: write_note' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: c.tools.save }))
    await waitFor(() => expect(backend.callsTo('PATCH', '/api/connections/gh')).toHaveLength(1))
    expect(backend.callsTo('PATCH', '/api/connections/gh')[0].body).toEqual({
      id: undefined,
      tool_mode: 'selected',
      allowed_tools: ['read_note'],
      preapproved_tools: ['read_note'],
    })
  })

  it('warns about new tools until the person has seen them', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      connections: {
        connections: [
          makeConnection({ id: 'gh', name: 'github', tools: TOOLS, tools_changed: true }),
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    const card = (await screen.findByRole('button', { name: 'Abrir github' })).closest('article')!
    expect(within(card).getByText(c.card.newTools)).toBeVisible()
    await user.click(within(card).getByRole('button', { name: 'Abrir github' }))
    await user.click(await screen.findByRole('tab', { name: c.sheet.tools }))
    await user.click(screen.getByRole('button', { name: c.tools.seen }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', '/api/connections/gh')[0]?.body).toMatchObject({
        tools_changed: false,
      }),
    )
  })

  it('connects an account: opens the login in the browser and waits for it', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      connections: {
        connections: [
          makeConnection({
            id: 'ln',
            name: 'linear',
            auth: 'oauth',
            headers: {},
            secrets: [],
            oauth: null,
          }),
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    const card = (await screen.findByRole('button', { name: 'Abrir linear' })).closest('article')!
    expect(within(card).getByText(c.card.connect)).toBeVisible()
    await user.click(within(card).getByRole('button', { name: 'Abrir linear' }))
    const panel = await screen.findByRole('region', { name: c.oauth.title })
    expect(within(panel).getByText(c.oauth.status_disconnected)).toBeVisible()
    await user.click(within(panel).getByRole('button', { name: c.oauth.connect }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/ln/oauth/start')).toHaveLength(1),
    )
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/oauth/flows/flow-1/open')).toHaveLength(1),
    )
    expect(await within(panel).findByRole('status')).toHaveTextContent(c.oauth.waiting)
    // the flow ends: the account shows as connected
    expect(
      await within(panel).findByText(c.oauth.status_connected, undefined, { timeout: 5000 }),
    ).toBeVisible()
    expect(within(panel).getByText(/Cuenta: Linear · mcp.linear.app/)).toBeVisible()
  })

  it('asks for the client id and shows the address to register when the service needs one', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      connections: {
        connections: [
          makeConnection({
            id: 'gh2',
            name: 'github-remoto',
            auth: 'oauth',
            headers: {},
            secrets: [],
          }),
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: 'Abrir github-remoto' }))
    const panel = await screen.findByRole('region', { name: c.oauth.title })
    await user.click(within(panel).getByRole('checkbox', { name: c.oauth.own }))
    expect(within(panel).getByText(/http:\/\/127\.0\.0\.1:53682\/callback/)).toBeVisible()
    await user.type(within(panel).getByLabelText(c.oauth.clientId), 'Iv1.abc')
    await user.click(within(panel).getByRole('button', { name: c.oauth.connect }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/gh2/oauth/start')[0]?.body).toEqual({
        client_id: 'Iv1.abc',
        client_secret: '',
      }),
    )
  })

  it('gives a connection to a project and takes it away', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      projects: [makeProject({ id: 'p1', name: 'Tienda' })],
      connections: { connections: [makeConnection({ id: 'gh', name: 'github' })] },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: 'Abrir github' }))
    await user.click(await screen.findByRole('tab', { name: c.sheet.where }))
    await user.click(screen.getByRole('combobox', { name: es.skills.level.label }))
    await user.click(await screen.findByRole('option', { name: es.skills.level.project }))
    await user.click(screen.getByRole('button', { name: c.assign.add }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/gh/assignments')[0]?.body).toEqual({
        scope: 'project',
        project_id: 'p1',
        agent_id: null,
      }),
    )
    await user.click(await screen.findByRole('button', { name: `Quitar de ${c.level.general}` }))
    await waitFor(() =>
      expect(backend.callsTo('DELETE', '/api/connections/gh/assignments/github-a1')).toHaveLength(
        1,
      ),
    )
  })

  it('shows what an update changes and applies it only when asked', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      connections: {
        connections: [
          makeConnection({
            id: 'pg',
            name: 'pg-mcp',
            origin: 'registry',
            registry: {
              source: 'official',
              ref: 'io.github.acme/pg-mcp',
              package_type: 'npm',
              package: '@acme/pg-mcp',
              version: '2.1.0',
              repo_url: 'https://github.com/acme/pg-mcp',
              license: '',
              official: true,
              latest_version: '2.2.0',
              update_available: true,
            },
          }),
        ],
        updatePreview: {
          from: '2.1.0',
          to: '2.2.0',
          changes: [
            {
              field: 'command',
              label: 'Comando',
              from: 'npx -y @acme/pg-mcp@2.1.0',
              to: 'npx -y @acme/pg-mcp@2.2.0',
            },
          ],
        },
      },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    const card = (await screen.findByRole('button', { name: 'Abrir pg-mcp' })).closest('article')!
    expect(within(card).getByText(c.card.update)).toBeVisible()
    await user.click(within(card).getByRole('button', { name: 'Abrir pg-mcp' }))
    await user.click(await screen.findByRole('tab', { name: c.sheet.usage }))
    expect(await screen.findByText('Hay una versión nueva: 2.1.0 → 2.2.0')).toBeVisible()
    expect(screen.getByText(/@acme\/pg-mcp@2\.2\.0/)).toBeVisible()
    expect(backend.callsTo('POST', '/api/connections/pg/update')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: c.update.apply }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/connections/pg/update')).toHaveLength(1),
    )
  })

  it('deletes a connection after confirming', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      connections: { connections: [makeConnection({ id: 'gh', name: 'github' })] },
    })
    const user = userEvent.setup()
    renderApp('/conexiones')
    await user.click(await screen.findByRole('button', { name: 'Abrir github' }))
    await user.click(await screen.findByRole('tab', { name: c.sheet.usage }))
    await user.click(screen.getByRole('button', { name: es.common.delete }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText('¿Borrar la conexión github?')).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: es.common.delete }))
    await waitFor(() => expect(backend.callsTo('DELETE', '/api/connections/gh')).toHaveLength(1))
  })
})
