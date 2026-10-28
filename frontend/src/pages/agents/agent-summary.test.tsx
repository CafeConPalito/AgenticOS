import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { useDialogs } from '@/stores/dialogs'
import {
  createFakeBackend,
  makeAgent,
  makeInboxItem,
  makeProject,
  makeTask,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

describe('Agent page · Resumen', () => {
  it('is the default tab and shows requests, tasks, spend and folded settings', async () => {
    const agent = makeAgent({ name: 'Dev', role: 'Desarrollador', model: 'sonnet' })
    const project = makeProject()
    const open = makeTask({ agent_id: agent.id, project_id: project.id, title: 'Login con Google' })
    const done = makeTask({
      agent_id: agent.id,
      project_id: project.id,
      title: 'Ya hecha',
      status: 'done',
    })
    const other = makeTask({ agent_id: 'agent-x', project_id: project.id, title: 'De otro agente' })
    createFakeBackend({
      agents: [agent],
      projects: [project],
      tasks: [open, done, other],
      inbox: [
        makeInboxItem({ kind: 'question', title: '¿Qué base?', agent_id: agent.id }),
        makeInboxItem({ kind: 'question', title: 'De otro', agent_id: 'otro' }),
      ],
      usage: {
        breakdown: {
          group: 'agent',
          rows: [
            {
              id: agent.id,
              name: 'Dev',
              color: agent.color,
              cost_usd: 3.5,
              tokens: 1_200_000,
              sessions: 4,
              share: 1,
            },
          ],
        },
      },
    })
    const { router } = renderApp(`/agentes/${agent.id}`)

    expect(await screen.findByRole('heading', { name: /Dev/ })).toBeVisible()
    await waitFor(() => expect(router.state.location.pathname).toBe(`/agentes/${agent.id}/resumen`))

    const requests = await screen.findByRole('region', { name: es.agents.summary.requests })
    expect(within(requests).getByText('¿Qué base?')).toBeVisible()
    expect(screen.queryByText('De otro')).toBeNull()

    const tasks = screen.getByRole('region', { name: es.agents.summary.tasks })
    expect(await within(tasks).findByText('Login con Google')).toBeVisible()
    expect(within(tasks).queryByText('Ya hecha')).toBeNull()
    expect(within(tasks).queryByText('De otro agente')).toBeNull()

    const usage = screen.getByRole('region', { name: es.agents.summary.usage })
    expect(await within(usage).findByText('1,20 M')).toBeVisible()
    expect(within(usage).getByText('4')).toBeVisible()

    // The settings are folded away at the end.
    const config = screen.getByText(es.agents.summary.config).closest('details')!
    expect(config).not.toHaveAttribute('open')
    expect(within(config).getByText('sonnet')).toBeInTheDocument()
  })

  it('«Asignar tarea» opens the new-task dialog on this agent', async () => {
    const agent = makeAgent()
    createFakeBackend({ agents: [agent], projects: [makeProject()] })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/resumen`)
    await user.click(await screen.findByRole('button', { name: es.agents.assignTask }))
    expect(useDialogs.getState().newTask).toEqual({ agentId: agent.id })
    expect(await screen.findByRole('heading', { name: es.tasks.new.title })).toBeVisible()
  })

  it('«Activar» turns a draft into an active agent', async () => {
    const agent = makeAgent({ name: 'Nuevo', status: 'draft' })
    const backend = createFakeBackend({ agents: [agent] })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/resumen`)
    expect(await screen.findByRole('button', { name: es.agents.assignTask })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: es.agents.activate }))
    await waitFor(() => expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)).toHaveLength(1))
    expect(backend.callsTo('PATCH', `/api/agents/${agent.id}`)[0].body).toEqual({
      status: 'active',
    })
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: es.agents.activate })).toBeNull(),
    )
    expect(screen.getByRole('button', { name: es.agents.assignTask })).toBeEnabled()
  })

  it('Resumen only reads: no «Editar» nor «Guardar»; the General tab brings «Guardar» (phase 20)', async () => {
    const agent = makeAgent()
    createFakeBackend({ agents: [agent] })
    const user = userEvent.setup()
    const { router } = renderApp(`/agentes/${agent.id}/resumen`)
    await screen.findByRole('button', { name: es.agents.assignTask })
    expect(screen.queryByRole('button', { name: es.common.save })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Editar' })).toBeNull()
    await user.click(screen.getByRole('link', { name: es.agents.tabs.general }))
    expect(router.state.location.pathname).toBe(`/agentes/${agent.id}/general`)
    expect(await screen.findByRole('button', { name: es.common.save })).toBeVisible()
  })
})
