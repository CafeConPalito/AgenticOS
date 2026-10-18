import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAgent,
  makeInboxItem,
  makePipeline,
  makeProject,
  makeRun,
  makeTask,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

function seed() {
  const dev = makeAgent({ name: 'Dev', color: '#4FD1C5' })
  const qa = makeAgent({ name: 'QA', color: '#B5E061' })
  const tienda = makeProject({ name: 'Tienda online', color: '#7C9CFF' })
  const blog = makeProject({ name: 'Blog', color: '#F5B547' })
  return { dev, qa, tienda, blog }
}

describe('Board', () => {
  it('shows the tasks by status and filters them by project', async () => {
    const { dev, tienda, blog } = seed()
    const queued = makeTask({ title: 'Pasarela de pago', project_id: tienda.id, agent_id: dev.id })
    const running = makeTask({ title: 'Login con Google', status: 'running', agent_id: dev.id })
    const other = makeTask({
      title: 'Artículo',
      status: 'backlog',
      project_id: blog.id,
      project_name: 'Blog',
    })
    createFakeBackend({
      agents: [dev],
      projects: [tienda, blog],
      tasks: [queued, running, other],
    })
    const user = userEvent.setup()
    renderApp('/tablero')

    await screen.findByText('Pasarela de pago')
    const queuedColumn = screen.getByRole('region', { name: es.tasks.status.queued })
    expect(within(queuedColumn).getByText('Pasarela de pago')).toBeVisible()
    const runningColumn = screen.getByRole('region', { name: es.tasks.status.running })
    expect(within(runningColumn).getByText('Login con Google')).toBeVisible()
    expect(screen.getByText('Artículo')).toBeVisible()

    await user.click(screen.getByRole('button', { name: 'Tienda online' }))
    expect(screen.queryByText('Artículo')).toBeNull()
    expect(screen.getByText('Pasarela de pago')).toBeVisible()
  })

  it('reorders an agent queue and pauses the scheduler', async () => {
    const { dev, tienda } = seed()
    const first = makeTask({ title: 'Primera', agent_id: dev.id, queue_position: 0 })
    const second = makeTask({ title: 'Segunda', agent_id: dev.id, queue_position: 1 })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [first, second],
    })
    const user = userEvent.setup()
    renderApp('/tablero?vista=queues')

    const row = await screen.findByRole('region', { name: 'Dev' })
    const cards = within(row).getAllByRole('article')
    expect(cards.map((c) => c.getAttribute('aria-label'))).toEqual([
      `#1 ${first.code}`,
      `#2 ${second.code}`,
    ])
    await user.click(
      within(row).getByRole('button', { name: es.board.moveLater.replace('{{title}}', 'Primera') }),
    )
    await waitFor(() =>
      expect(backend.callsTo('PUT', `/api/agents/${dev.id}/queue`)).toHaveLength(1),
    )
    expect(backend.callsTo('PUT', `/api/agents/${dev.id}/queue`)[0].body).toEqual({
      task_ids: [second.id, first.id],
    })
    expect(await screen.findByText(/pasa a la posición #2/)).toBeVisible()

    await user.click(screen.getByRole('button', { name: es.board.pause }))
    await waitFor(() => expect(backend.scheduler.paused).toBe(true))
    expect(await screen.findByRole('button', { name: es.board.resume })).toBeVisible()
  })
})

describe('Board with forked tasks', () => {
  function forkedTasks() {
    const { dev, tienda } = seed()
    const mother = makeTask({
      title: 'Filtro de pedidos',
      code: 'T-9',
      project_id: tienda.id,
      status: 'running',
      phase: 'forked',
      agent_id: null,
      agent_name: null,
      stage_name: 'Requisitos',
      stage_index: 1,
      lanes: ['backend', 'frontend'].map((key) => ({
        id: `lane-${key}`,
        code: `T-9·${key}`,
        lane_key: key,
        name: key,
        status: 'running' as const,
        stage_id: null,
        stage_name: null,
        agent_name: null,
        agent_color: null,
        waiting_reason: null,
        link_id: null,
        fork_stage_id: null,
      })),
    })
    const back = makeTask({
      title: 'Filtro de pedidos',
      code: 'T-9·backend',
      project_id: tienda.id,
      status: 'running',
      lane_of_id: mother.id,
      lane_name: 'Backend',
      stage_name: 'Dev backend',
      stage_index: 2,
      agent_id: dev.id,
    })
    const front = makeTask({
      title: 'Filtro de pedidos',
      code: 'T-9·frontend',
      project_id: tienda.id,
      status: 'queued',
      lane_of_id: mother.id,
      lane_name: 'Frontend',
      stage_name: 'Dev frontend',
      stage_index: 3,
      agent_id: dev.id,
    })
    return { dev, tienda, mother, back, front }
  }

  it('by state a forked task counts once; by stage its lanes sit in their own columns', async () => {
    const { dev, tienda, mother, back, front } = forkedTasks()
    createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [mother, back, front],
    })
    const user = userEvent.setup()
    renderApp('/tablero')

    const running = await screen.findByRole('region', { name: es.tasks.status.running })
    expect(await within(running).findAllByRole('link')).toHaveLength(1) // the task, not its lanes
    expect(within(running).getByText('2 ramas')).toBeVisible()
    expect(screen.queryByText(/Rama Backend/)).toBeNull()

    await user.click(screen.getByRole('tab', { name: es.board.views.stage }))
    const backColumn = await screen.findByRole('region', { name: 'Dev backend' })
    expect(within(backColumn).getByText('Rama Backend')).toBeVisible()
    const frontColumn = screen.getByRole('region', { name: 'Dev frontend' })
    expect(within(frontColumn).getByText('Rama Frontend')).toBeVisible()
    // the task that forked is not repeated: its lanes stand for it
    expect(screen.queryByRole('region', { name: 'Requisitos' })).toBeNull()
  })

  it('an agent queue lists the lane it has to work on', async () => {
    const { dev, tienda, mother, back, front } = forkedTasks()
    createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [mother, back, front],
    })
    renderApp('/tablero?vista=queues')
    const row = await screen.findByRole('region', { name: 'Dev' })
    expect(within(row).getByText(/Rama Frontend/)).toBeVisible()
  })
})

describe('Board queues (code review)', () => {
  it('reorders with a project filter on by sending the whole queue', async () => {
    const { dev, tienda, blog } = seed()
    const a = makeTask({ title: 'A1', project_id: tienda.id, agent_id: dev.id, queue_position: 0 })
    const b = makeTask({ title: 'B1', project_id: blog.id, agent_id: dev.id, queue_position: 1 })
    const c = makeTask({ title: 'A2', project_id: tienda.id, agent_id: dev.id, queue_position: 2 })
    const high = makeTask({
      title: 'Urgente',
      project_id: tienda.id,
      agent_id: dev.id,
      priority: 'high',
      queue_position: 0,
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda, blog],
      tasks: [a, b, c, high],
    })
    const user = userEvent.setup()
    renderApp('/tablero?vista=queues')
    await user.click(await screen.findByRole('button', { name: 'Tienda online' }))
    const row = await screen.findByRole('region', { name: 'Dev' })
    expect(within(row).queryByText('B1')).toBeNull()

    // A high-priority task always goes first: A1 cannot move above it.
    const earlier = (title: string) =>
      within(row).getByRole('button', { name: es.board.moveEarlier.replace('{{title}}', title) })
    expect(earlier('A1')).toBeDisabled()

    await user.click(earlier('A2'))
    await waitFor(() =>
      expect(backend.callsTo('PUT', `/api/agents/${dev.id}/queue`)).toHaveLength(1),
    )
    expect(backend.callsTo('PUT', `/api/agents/${dev.id}/queue`)[0].body).toEqual({
      task_ids: [high.id, c.id, a.id, b.id],
    })
  })
})

describe('Task page', () => {
  it('explains why a task waits and retries it', async () => {
    const { dev, tienda } = seed()
    const task = makeTask({
      status: 'waiting_human',
      waiting_reason: 'run_exited',
      waiting_detail: 'exit code 3',
      agent_id: dev.id,
      project_id: tienda.id,
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      taskEvents: {
        [task.id]: [
          {
            id: 'e1',
            at: new Date().toISOString(),
            kind: 'rejected',
            stage_name: 'QA',
            agent_name: 'Quique',
            run_id: null,
            detail: 'Falta el test del callback',
          },
        ],
      },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(es.tasks.waiting.run_exited)
    expect(alert).toHaveTextContent('exit code 3')
    expect(await screen.findByText('Falta el test del callback')).toBeVisible()
    expect(screen.getByText(es.tasks.detail.noRun)).toBeVisible()

    await user.click(screen.getByRole('button', { name: es.tasks.actions.retry }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/retry`)).toHaveLength(1),
    )
  })

  it('shows the session facts under the live output, not in the side column', async () => {
    const { dev, tienda } = seed()
    const task = makeTask({
      status: 'running',
      agent_id: dev.id,
      project_id: tienda.id,
      branch: 'agentic/T-7',
      worktree_path: 'C:/code/web-wt',
    })
    const run = makeRun({
      task_id: task.id,
      agent_id: dev.id,
      cli_session_id: 'cc-7f3a91',
      cwd: 'C:/code/web',
      usage: { ...makeRun().usage, cost_usd: 2.84, status: 'final' },
    })
    task.active_run_id = run.id
    task.last_run_id = run.id
    createFakeBackend({ agents: [dev], projects: [tienda], tasks: [task], runs: [run] })
    renderApp(`/tablero/tareas/${task.id}`)

    const facts = await screen.findByRole('group', { name: es.tasks.facts.label }).catch(() => null)
    const line = facts ?? (await screen.findByLabelText(es.tasks.facts.label))
    expect(within(line).getByText('cc-7f3a91')).toBeVisible()
    expect(within(line).getByText('agentic/T-7')).toBeVisible()
    expect(within(line).getByText('C:/code/web')).toBeVisible()
    expect(within(line).getByText(/2,84/)).toBeVisible()
    expect(within(line).getByText(es.tasks.facts.duration)).toBeVisible()
  })

  it('answers the task requests right there', async () => {
    const { dev, tienda } = seed()
    const task = makeTask({ status: 'waiting_human', agent_id: dev.id, project_id: tienda.id })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      inbox: [
        makeInboxItem({
          kind: 'approval',
          command: 'npm test',
          task_id: task.id,
          agent_id: dev.id,
        }),
      ],
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)
    await user.click(await screen.findByRole('button', { name: es.inbox.approve }))
    await waitFor(() => expect(backend.calls.some((c) => c.path.endsWith('/approve'))).toBe(true))
  })

  it('resumes the session of an interrupted task', async () => {
    const { dev, tienda } = seed()
    const task = makeTask({
      status: 'waiting_human',
      waiting_reason: 'interrupted',
      agent_id: dev.id,
      project_id: tienda.id,
    })
    const run = makeRun({ task_id: task.id, status: 'interrupted', resumable: true })
    task.last_run_id = run.id
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      runs: [run],
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    await user.click(await screen.findByRole('button', { name: es.runs.resume.button }))

    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/runs/${run.id}/resume`)).toHaveLength(1),
    )
    expect(await screen.findByText(es.tasks.status.running)).toBeVisible()
  })

  it('rejects a task in review back to an earlier stage', async () => {
    const { dev, tienda } = seed()
    const pipeline = makePipeline(
      tienda.id,
      [
        {
          id: 's1',
          name: 'Desarrollo',
          agent_id: dev.id,
          agent_name: 'Dev',
          agent_color: '#4FD1C5',
          requires_review: true,
          active_tasks: 1,
        },
      ],
      { id: 'p1', name: 'Web' },
    )
    const task = makeTask({ status: 'review', stage_id: 's1', project_id: tienda.id })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    await user.click(await screen.findByRole('button', { name: es.tasks.actions.reject }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(es.tasks.actions.reason), 'Falta móvil')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.actions.reject }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/review`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/tasks/${task.id}/review`)[0].body).toEqual({
      action: 'reject',
      reason: 'Falta móvil',
      target_stage_id: 's1',
    })
  })
})

describe('New task', () => {
  it('needs an agent when the project has no pipeline', async () => {
    const { dev, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/tasks`)

    await user.click(await screen.findByRole('button', { name: es.tasks.new.title }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'Carrito')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/tasks')[0].body).toEqual({
      project_id: tienda.id,
      title: 'Carrito',
      description: '',
      priority: 'normal',
      agent_id: dev.id, // the only agent is picked by default
      enqueue: true,
    })
    expect(await screen.findByRole('row', { name: /Carrito/ })).toBeVisible()
  })
})
