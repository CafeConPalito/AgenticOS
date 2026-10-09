import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

describe('Agents list', () => {
  it('lists agents with CLI, model and status', async () => {
    createFakeBackend({
      agents: [
        makeAgent({ name: 'Ana', role: 'Analista' }),
        makeAgent({ name: 'Quique', role: 'QA', cli: 'agy', model: '', status: 'draft' }),
      ],
    })
    renderApp('/agentes')
    const ana = await screen.findByRole('row', { name: 'Abrir Ana' })
    expect(within(ana).getByText('Analista')).toBeVisible()
    expect(within(ana).getByText('sonnet')).toBeVisible()
    expect(within(ana).getByText(es.agents.status.active)).toBeVisible()
    const quique = screen.getByRole('row', { name: 'Abrir Quique' })
    expect(within(quique).getAllByText(es.cli.agy).length).toBeGreaterThan(0)
    expect(within(quique).getByText(es.cli.defaultModel)).toBeVisible()
    expect(within(quique).getByText(es.agents.status.draft)).toBeVisible()
  })

  it('creates an agent from a template in the empty state and opens its editor', async () => {
    const backend = createFakeBackend()
    const user = userEvent.setup()
    const { router } = renderApp('/agentes')
    expect(await screen.findByText(es.pages.agents.emptyTitle)).toBeVisible()

    await user.click(await screen.findByRole('button', { name: /Desarrollador/ }))
    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/agentes/agent-from-developer/general'),
    )
    expect(backend.callsTo('POST', '/api/agents')[0].body).toEqual({ template: 'developer' })
    expect(await screen.findByRole('heading', { name: /Desarrollador/ })).toBeVisible()
  })

  it('header button opens the template picker', async () => {
    createFakeBackend()
    const user = userEvent.setup()
    const { router } = renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: es.header.primary.newAgent }))
    expect(router.state.location.pathname).toBe('/agentes/nuevo')
    expect(
      await screen.findByRole('button', { name: new RegExp(es.agents.new.blank) }),
    ).toBeVisible()
  })
})

describe('Agent editor', () => {
  it('saves only the changed fields across tabs', async () => {
    const agent = makeAgent({ name: 'Dev', role: 'Desarrollador' })
    const backend = createFakeBackend({ agents: [agent] })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/general`)

    const name = await screen.findByLabelText(es.agents.fields.name)
    await user.clear(name)
    await user.type(name, 'Devi')

    await user.click(screen.getByRole('link', { name: es.agents.tabs.execution }))
    await user.click(
      await screen.findByRole('radio', { name: new RegExp(es.agents.permission.autonomous) }),
    )
    await user.click(screen.getByRole('checkbox', { name: es.agents.tool.terminal }))
    await user.click(screen.getByRole('button', { name: es.agents.fields.increase }))

    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() => expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)).toHaveLength(1))
    expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)[0].body).toEqual({
      name: 'Devi',
      permission_mode: 'autonomous',
      allowed_tools: ['terminal'],
      max_concurrency: 2,
    })
    expect(await screen.findByText(es.common.saved)).toBeVisible()
    expect(screen.getByRole('button', { name: es.common.save })).toBeDisabled()
  })

  it('validates the name before saving', async () => {
    const agent = makeAgent()
    const backend = createFakeBackend({ agents: [agent] })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/general`)
    await user.clear(await screen.findByLabelText(es.agents.fields.name))
    await user.click(screen.getByRole('button', { name: es.common.save }))
    expect(await screen.findByText(es.errors.name_required)).toBeVisible()
    expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)).toHaveLength(0)
  })

  it('asks before leaving with unsaved changes', async () => {
    const agent = makeAgent()
    createFakeBackend({ agents: [agent] })
    const user = userEvent.setup()
    const { router } = renderApp(`/agentes/${agent.id}/general`)
    await user.type(await screen.findByLabelText(es.agents.fields.role), ' senior')

    const nav = screen.getByRole('navigation', { name: es.nav.main })
    await user.click(within(nav).getByRole('link', { name: es.nav.projects }))
    expect(await screen.findByText(es.unsaved.title)).toBeVisible()
    expect(router.state.location.pathname).toBe(`/agentes/${agent.id}/general`)

    await user.click(screen.getByRole('button', { name: es.unsaved.discard }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/proyectos'))
  })

  it('switching tabs keeps the edits (one form for all tabs)', async () => {
    const agent = makeAgent({ instructions: '' })
    createFakeBackend({ agents: [agent] })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/instructions`)
    await user.type(await screen.findByLabelText(es.agents.fields.instructions), '# Hola')
    await user.click(screen.getByRole('link', { name: es.agents.tabs.general }))
    expect(screen.queryByText(es.unsaved.title)).not.toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: es.agents.tabs.instructions }))
    expect(await screen.findByLabelText(es.agents.fields.instructions)).toHaveValue('# Hola')
  })

  it('deletes after confirmation', async () => {
    const agent = makeAgent({ name: 'Rita' })
    const backend = createFakeBackend({ agents: [agent] })
    const user = userEvent.setup()
    const { router } = renderApp(`/agentes/${agent.id}/general`)
    await user.click(await screen.findByRole('button', { name: es.common.more }))
    await user.click(await screen.findByRole('menuitem', { name: es.common.delete }))
    const dialog = await screen.findByRole('alertdialog')
    expect(within(dialog).getByText('¿Borrar a Rita?')).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: es.common.delete }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/agentes'))
    expect(backend.callsTo('DELETE', `/api/agents/${agent.id}`)).toHaveLength(1)
  })

  it('shows CLI detection and model options', async () => {
    const agent = makeAgent()
    createFakeBackend({ agents: [agent] })
    renderApp(`/agentes/${agent.id}/execution`)
    const agy = await screen.findByRole('radio', { name: new RegExp(es.cli.agy) })
    expect(await within(agy).findByText(es.cli.notDetected)).toBeVisible()
    const claude = screen.getByRole('radio', { name: new RegExp(es.cli.claude) })
    expect(claude).toHaveAttribute('aria-checked', 'true')
    expect(await within(claude).findByText(/2\.1\.296/)).toBeVisible()
  })
})
