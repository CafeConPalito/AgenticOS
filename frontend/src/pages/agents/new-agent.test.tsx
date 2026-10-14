import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

describe('New agent dialog', () => {
  it('the header button opens it', async () => {
    createFakeBackend({ agents: [makeAgent()] })
    const user = userEvent.setup()
    renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: es.header.primary.newAgent }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: es.agents.new.title })).toBeVisible()
    expect(
      within(dialog).getByRole('button', { name: new RegExp(es.agents.new.blank) }),
    ).toBeVisible()
  })

  it('/agentes/nuevo still works: the list with the dialog open', async () => {
    createFakeBackend({ agents: [makeAgent()] })
    const { router } = renderApp('/agentes/nuevo')
    expect(await screen.findByRole('dialog')).toBeVisible()
    expect(router.state.location.pathname).toBe('/agentes')
  })

  it('creates the agent as a draft from a template, adjusted, and opens its page', async () => {
    const backend = createFakeBackend({ agents: [makeAgent()] })
    const user = userEvent.setup()
    const { router } = renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: es.header.primary.newAgent }))
    const dialog = await screen.findByRole('dialog')

    await user.click(await within(dialog).findByRole('button', { name: /Desarrollador/ }))
    const name = within(dialog).getByLabelText(es.agents.fields.name)
    expect(name).toHaveValue('Desarrollador')
    await user.clear(name)
    await user.type(name, 'Dev senior')
    await user.click(within(dialog).getByRole('radio', { name: es.agents.permission.autonomous }))
    await user.click(within(dialog).getByRole('button', { name: es.agents.new.submit }))

    await waitFor(() => expect(backend.callsTo('POST', '/api/agents')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/agents')[0].body).toMatchObject({
      template: 'developer',
      name: 'Dev senior',
      permission_mode: 'autonomous',
      status: 'draft',
    })
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/agentes\/agent-/))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('a blank agent needs a name', async () => {
    const backend = createFakeBackend({ agents: [makeAgent()] })
    const user = userEvent.setup()
    renderApp('/agentes')
    await user.click(await screen.findByRole('button', { name: es.header.primary.newAgent }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('button', { name: es.agents.new.submit })).toBeDisabled()
    await user.type(within(dialog).getByLabelText(es.agents.fields.name), 'Redactor')
    await user.click(within(dialog).getByRole('button', { name: es.agents.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/agents')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/agents')[0].body).toMatchObject({
      name: 'Redactor',
      status: 'draft',
    })
  })
})
