import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { IntegrationCheck, RepoCheck } from '@/api/integration'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeProject, makeRun, makeTask } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))
vi.mock('@xterm/xterm', () => import('@/test/fake-xterm'))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))

function repo(overrides: Partial<RepoCheck> = {}): RepoCheck {
  return {
    repo_id: 'r1',
    name: 'backend',
    branch: 'agentic/T-9',
    base: 'main',
    ahead: 2,
    behind: 0,
    state: 'clean',
    conflicts: [],
    active_in: null,
    dirty: [],
    integrated_at: null,
    integrated_sha: null,
    ...overrides,
  }
}

function setup(repos: RepoCheck[], extra: Parameters<typeof createFakeBackend>[0] = {}) {
  const project = makeProject()
  const dev = makeAgent({ name: 'Dev' })
  const task = makeTask({
    title: 'Login',
    status: 'done',
    project_id: project.id,
    agent_id: dev.id,
  })
  const check: IntegrationCheck = {
    task_id: task.id,
    repos,
    pending: repos.filter((r) => ['clean', 'conflicts', 'blocked'].includes(r.state)).length,
    can_integrate: repos.every((r) => r.state === 'clean' || r.state === 'integrated'),
  }
  const backend = createFakeBackend({
    projects: [project],
    agents: [dev],
    tasks: [task],
    runs: [makeRun({ task_id: task.id, project_id: project.id })],
    integrations: { [task.id]: check },
    ...extra,
  })
  installFakeWebSocket()
  return { project, task, backend, dev }
}

function block() {
  return screen.findByRole('region', { name: es.tasks.integration.title })
}

describe('Integration block of a task', () => {
  it('integrates the branches with the chosen way, pushing, and says what happened', async () => {
    const { task, backend } = setup([repo(), repo({ repo_id: 'r2', name: 'frontend' })])
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    const section = await block()
    expect(within(section).getByText('backend')).toBeVisible()
    expect(within(section).getByText('frontend')).toBeVisible()
    expect(within(section).getAllByText(es.tasks.integration.state.clean)).toHaveLength(2)

    await user.selectOptions(
      within(section).getByRole('combobox', { name: es.tasks.integration.mode }),
      'squash',
    )
    await user.click(within(section).getByRole('checkbox', { name: es.tasks.integration.push }))
    await user.click(within(section).getByRole('button', { name: es.tasks.integration.integrate }))

    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/integrate`)[0].body).toEqual({
        mode: 'squash',
        push: true,
        delete_branches: false,
      }),
    )
    expect(await screen.findByText('Integrado en 2 repositorios')).toBeVisible()
  })

  it('without a chosen way the project decides', async () => {
    const { task, backend } = setup([repo()])
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)
    const section = await block()
    await user.click(within(section).getByRole('button', { name: es.tasks.integration.integrate }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/integrate`)[0].body).toEqual({
        mode: undefined,
        push: false,
        delete_branches: false,
      }),
    )
  })

  it('lists the conflicts, blocks integrating and offers the ways out', async () => {
    const { task, backend, dev } = setup([
      repo({ state: 'clean' }),
      repo({ repo_id: 'r2', name: 'frontend', state: 'conflicts', conflicts: ['b.txt', 'c.txt'] }),
    ])
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)
    const section = await block()

    expect(within(section).getByText(/Conflictos en 2 ficheros/)).toBeVisible()
    expect(within(section).getByText('b.txt, c.txt')).toBeVisible()
    expect(
      within(section).getByRole('button', { name: es.tasks.integration.integrate }),
    ).toBeDisabled()

    await user.selectOptions(
      within(section).getByRole('combobox', { name: es.tasks.integration.agent }),
      dev.id,
    )
    await user.click(
      within(section).getByRole('button', { name: es.tasks.integration.handToAgent }),
    )
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/resolve-conflicts`)[0].body).toEqual({
        agent_id: dev.id,
      }),
    )
    expect(await within(section).findByText(/Tarea T-\d+ creada/)).toBeVisible()
  })

  it('resolves here: shows the folder and files, then marks it resolved', async () => {
    const { task, backend } = setup([repo({ state: 'conflicts', conflicts: ['a.txt'] })], {
      resolution: {
        repo_id: 'r1',
        name: 'backend',
        path: 'D:\\web.wt\\merge-T-9\\backend',
        conflicts: ['a.txt'],
      },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)
    const section = await block()

    await user.click(
      within(section).getByRole('button', { name: `${es.tasks.integration.resolveHere} backend` }),
    )
    expect(await within(section).findByText('D:\\web.wt\\merge-T-9\\backend')).toBeVisible()
    await user.click(
      within(section).getByRole('button', { name: es.tasks.integration.markResolved }),
    )
    await waitFor(() =>
      expect(
        backend.callsTo('POST', `/api/tasks/${task.id}/integration/resolution/finish`)[0].body,
      ).toEqual({ repo_id: 'r1' }),
    )
  })

  it('tells why a base folder blocks it', async () => {
    const { task } = setup([repo({ state: 'blocked', active_in: 'D:\\web', dirty: ['a.txt'] })])
    renderApp(`/tablero/tareas/${task.id}`)
    const section = await block()
    expect(within(section).getByText(/tiene cambios sin commit/)).toBeVisible()
    expect(within(section).getByText('a.txt')).toBeVisible()
  })

  it('undoes what was integrated, after confirming', async () => {
    const { task, backend } = setup([
      repo({ state: 'integrated', ahead: 0, integrated_at: new Date().toISOString() }),
    ])
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)
    const section = await block()

    await user.click(within(section).getByRole('button', { name: es.tasks.integration.undo }))
    expect(backend.callsTo('POST', `/api/tasks/${task.id}/integration/undo`)).toHaveLength(0)
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.integration.undo }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/integration/undo`)).toHaveLength(1),
    )
  })

  it('is not shown when the task left nothing to integrate', async () => {
    const { task } = setup([repo({ state: 'nothing', ahead: 0 })])
    renderApp(`/tablero/tareas/${task.id}`)
    await screen.findByRole('heading', { name: new RegExp(task.title) })
    expect(
      screen.queryByRole('region', { name: es.tasks.integration.title }),
    ).not.toBeInTheDocument()
  })
})

describe('Pull requests of a task', () => {
  it('opens one per repository and links to them, saying what failed', async () => {
    const created = {
      number: 4,
      title: 'T',
      state: 'open' as const,
      draft: true,
      author: 'ana',
      head: 'agentic/T-9',
      base: 'main',
      url: 'https://github.com/ana/shop/pull/4',
      created_at: null,
      updated_at: null,
      mergeable: null,
    }
    const { task, backend } = setup([repo(), repo({ repo_id: 'r2', name: 'frontend' })], {
      taskPulls: [
        {
          repo_id: 'r1',
          name: 'backend',
          status: 'created',
          pull: created,
          error_code: null,
          message: '',
        },
        {
          repo_id: 'r2',
          name: 'frontend',
          status: 'failed',
          pull: null,
          error_code: 'auth_failed',
          message: '',
        },
      ],
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)
    const section = await block()

    await user.click(within(section).getByRole('checkbox', { name: es.git.pulls.asDraft }))
    await user.click(within(section).getByRole('button', { name: es.tasks.integration.openPull }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/pulls`)[0].body).toEqual({
        draft: true,
        push: true,
      }),
    )
    const list = await within(section).findByRole('list', { name: es.tasks.integration.pulls })
    expect(within(list).getByRole('link', { name: 'backend · #4' })).toHaveAttribute(
      'href',
      'https://github.com/ana/shop/pull/4',
    )
    expect(within(list).getByText(/frontend:/)).toBeVisible()
  })
})

describe('Git settings of a project', () => {
  it('saves the way of integrating, what happens on approval and the agents’ git', async () => {
    const project = makeProject({ workspace_mode: 'worktree' })
    const backend = createFakeBackend({ projects: [project], repos: { [project.id]: [] } })
    installFakeWebSocket()
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/settings`)

    const section = await screen.findByRole('region', { name: es.projects.gitSettings.title })
    await user.selectOptions(
      within(section).getByRole('combobox', { name: es.projects.gitSettings.mode }),
      'rebase',
    )
    await waitFor(() =>
      expect(backend.callsTo('PATCH', `/api/projects/${project.id}`)[0].body).toEqual({
        integration_mode: 'rebase',
      }),
    )
    await user.selectOptions(
      within(section).getByRole('combobox', { name: es.projects.gitSettings.onApprove }),
      'integrate_push',
    )
    await waitFor(() =>
      expect(backend.callsTo('PATCH', `/api/projects/${project.id}`)[1].body).toEqual({
        on_approve: 'integrate_push',
      }),
    )
    await user.click(
      within(section).getByRole('switch', { name: new RegExp(es.projects.gitSettings.agentsGit) }),
    )
    await waitFor(() =>
      expect(backend.callsTo('PATCH', `/api/projects/${project.id}`)[2].body).toEqual({
        agents_git_authorized: false,
      }),
    )
  })
})
