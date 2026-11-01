import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeProject, makeTask } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

const W = es.tasks.workMode

function seed(overrides: Parameters<typeof makeTask>[0] = {}) {
  const dev = makeAgent({ name: 'Dev' })
  const tienda = makeProject({ name: 'Tienda online' })
  const task = makeTask({
    project_id: tienda.id,
    project_name: tienda.name,
    title: 'Login con Google',
    status: 'review',
    stage_name: 'Validación de requisitos',
    work_mode: 'sdd',
    work_mode_reason: 'Toca la interfaz, la API y la base de datos',
    spec_path: 'specs/003-login',
    ...overrides,
  })
  return { dev, tienda, task }
}

describe('The working mode of a task (phase 24, CA5)', () => {
  it('shows the mode, why and where the spec is, and changes it', async () => {
    const { dev, tienda, task } = seed()
    const backend = createFakeBackend({ agents: [dev], projects: [tienda], tasks: [task] })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    const section = await screen.findByRole('region', { name: W.title })
    expect(within(section).getByText(W.sdd)).toBeVisible()
    expect(within(section).getByText(/Toca la interfaz/)).toBeVisible()
    expect(within(section).getByText('specs/003-login')).toBeVisible()
    const button = within(section).getByRole('button', { name: W.changeTo.direct })
    expect(button).toHaveAttribute('title', W.changeHelp)
    await user.click(button)
    await waitFor(() =>
      expect(backend.callsTo('PUT', `/api/tasks/${task.id}/work-mode`)[0]?.body).toEqual({
        mode: 'direct',
      }),
    )
    expect(await screen.findByText(W.changed)).toBeVisible()
  })

  it('cannot be changed once the task forked, and says why', async () => {
    const { dev, tienda, task } = seed({ status: 'running', phase: 'forked' })
    createFakeBackend({ agents: [dev], projects: [tienda], tasks: [task] })
    renderApp(`/tablero/tareas/${task.id}`)
    const section = await screen.findByRole('region', { name: W.title })
    const button = within(section).getByRole('button', { name: W.changeTo.direct })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', W.locked.forked)
  })

  it('a task without a mode yet shows nothing, and the card shows the tag', async () => {
    const { dev, tienda, task } = seed()
    const plain = makeTask({ project_id: tienda.id, title: 'Sin decidir', status: 'queued' })
    createFakeBackend({ agents: [dev], projects: [tienda], tasks: [task, plain] })
    renderApp('/tablero')
    const card = (await screen.findByText('Login con Google')).closest('a')
    expect(card).toHaveTextContent(W.tag.sdd)
    expect((await screen.findByText('Sin decidir')).closest('a')).not.toHaveTextContent(
      W.tag.direct,
    )
  })
})
