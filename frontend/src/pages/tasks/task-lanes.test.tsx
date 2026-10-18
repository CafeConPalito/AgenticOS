import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { BranchDecision, Lane, Pipeline } from '@/api/types'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAgent,
  makePipeline,
  makeProject,
  makeTask,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

function seed() {
  const dev = makeAgent({ name: 'Dev' })
  const tienda = makeProject({ name: 'Tienda online' })
  // Requisitos → (Backend | Frontend) → QA
  const pipeline: Pipeline = makePipeline(
    tienda.id,
    [
      { id: 'req', name: 'Requisitos', agent_id: dev.id, agent_name: 'Dev', x: 0, y: 80 },
      { id: 'back', name: 'Dev backend', agent_id: dev.id, agent_name: 'Dev', x: 300, y: 0 },
      { id: 'front', name: 'Dev frontend', agent_id: dev.id, agent_name: 'Dev', x: 300, y: 160 },
      { id: 'qa', name: 'QA', agent_id: dev.id, agent_name: 'Dev', x: 600, y: 80 },
    ],
    {
      links: [
        ['l-back', 'req', 'back', 'Backend', 'Toca la API'],
        ['l-front', 'req', 'front', 'Frontend', 'Toca la UI'],
        ['b-qa', 'back', 'qa', 'QA', ''],
        ['f-qa', 'front', 'qa', 'QA', ''],
      ].map(([id, from, to, name, condition], i) => ({
        id,
        from_stage_id: from,
        to_stage_id: to,
        name,
        condition,
        always: false,
        position: i % 2,
      })),
    },
  )
  return { dev, tienda, pipeline }
}

const lane = (overrides: Partial<Lane>): Lane => ({
  id: 'lane-1',
  code: 'T-7·backend',
  lane_key: 'backend',
  name: 'Backend',
  status: 'running',
  stage_id: 'back',
  stage_name: 'Dev backend',
  agent_name: 'Dev',
  agent_color: '#4FD1C5',
  waiting_reason: null,
  link_id: 'l-back',
  fork_stage_id: 'req',
  ...overrides,
})

const decision = (overrides: Partial<BranchDecision>): BranchDecision => ({
  id: 'd1',
  at: '2026-10-18T10:00:00Z',
  fork_stage_id: 'req',
  decided_by: 'model',
  proposed: false,
  chosen: ['l-back'],
  reasons: { 'l-back': 'Añade un endpoint', 'l-front': 'No hay pantallas' },
  error: null,
  run_id: null,
  ...overrides,
})

describe('A task that forked', () => {
  it('shows its lanes, the path through the pipeline and cancels one', async () => {
    const { dev, tienda, pipeline } = seed()
    const task = makeTask({
      project_id: tienda.id,
      status: 'running',
      stage_id: 'req',
      phase: 'forked',
      lanes: [
        lane({}),
        lane({
          id: 'lane-2',
          name: 'Frontend',
          link_id: 'l-front',
          status: 'done',
          stage_id: 'front',
        }),
      ],
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
      decisions: { [task.id]: [decision({ chosen: ['l-back', 'l-front'] })] },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    expect(await screen.findByText(es.tasks.lanes.phase.forked)).toBeVisible()
    expect(await screen.findByRole('img', { name: es.tasks.lanes.pathLabel })).toBeVisible()
    const section = await screen.findByRole('region', { name: es.tasks.lanes.title })
    expect(within(section).getByRole('link', { name: 'Backend' })).toHaveAttribute(
      'href',
      '/tablero/tareas/lane-1',
    )
    // only the lane that is still going can be cancelled
    expect(within(section).getAllByRole('button', { name: /Cancelar la rama/ })).toHaveLength(1)

    await user.click(
      within(section).getByRole('button', {
        name: es.tasks.lanes.cancelLane.replace('{{name}}', 'Backend'),
      }),
    )
    await user.click(await screen.findByRole('button', { name: es.tasks.lanes.cancelConfirm }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks/lane-1/cancel')).toHaveLength(1))
  })

  it('adds a branch the decision left out', async () => {
    const { dev, tienda, pipeline } = seed()
    const task = makeTask({
      project_id: tienda.id,
      status: 'running',
      stage_id: 'req',
      phase: 'forked',
      lanes: [lane({})],
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    await user.click(await screen.findByRole('combobox', { name: es.tasks.lanes.add }))
    await user.click(await screen.findByRole('option', { name: 'Frontend' }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/lanes`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/tasks/${task.id}/lanes`)[0].body).toEqual({
      link_id: 'l-front',
    })
  })

  it('lets the person choose the branches when nobody could, and cannot finish it by hand', async () => {
    const { dev, tienda, pipeline } = seed()
    const task = makeTask({
      project_id: tienda.id,
      status: 'waiting_human',
      waiting_reason: 'choose_branch',
      waiting_detail: 'la cuenta no está disponible',
      stage_id: 'req',
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    expect(await screen.findByText(es.tasks.waiting.choose_branch)).toBeVisible()
    expect(screen.queryByRole('button', { name: es.tasks.actions.complete })).toBeNull()
    expect(screen.getByRole('button', { name: es.tasks.actions.retry })).toBeVisible()

    const group = await screen.findByRole('group', { name: es.tasks.lanes.choose })
    const take = within(group).getByRole('button', { name: es.tasks.lanes.take })
    expect(take).toBeDisabled()
    expect(within(group).getByText('Toca la API')).toBeVisible() // the condition guides the choice
    await user.click(within(group).getByLabelText(/Backend/))
    await user.click(within(group).getByLabelText(/Frontend/))
    await user.click(take)
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/decision`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/tasks/${task.id}/decision`)[0].body).toEqual({
      chosen: ['l-back', 'l-front'],
    })
  })

  it('shows the branches the model proposes with their reasons and accepts or changes them', async () => {
    const { dev, tienda, pipeline } = seed()
    const task = makeTask({
      project_id: tienda.id,
      status: 'review',
      stage_id: 'req',
      requires_review: false,
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
      decisions: { [task.id]: [decision({ proposed: true })] },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    const group = await screen.findByRole('group', { name: es.tasks.lanes.confirm })
    expect(within(group).getByText('Añade un endpoint')).toBeVisible()
    expect(within(group).getByLabelText(/Backend/)).toBeChecked()
    expect(within(group).getByLabelText(/Frontend/)).not.toBeChecked()
    // untouched: accept; touched: it becomes a choice of the person
    await user.click(within(group).getByLabelText(/Frontend/))
    await user.click(within(group).getByRole('button', { name: es.tasks.lanes.take }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/decision`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/tasks/${task.id}/decision`)[0].body).toEqual({
      chosen: ['l-back', 'l-front'],
    })
  })

  it('keeps who decided what and why', async () => {
    const { dev, tienda, pipeline } = seed()
    const task = makeTask({
      project_id: tienda.id,
      status: 'running',
      stage_id: 'req',
      phase: 'forked',
      lanes: [lane({})],
    })
    createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
      decisions: { [task.id]: [decision({})] },
    })
    renderApp(`/tablero/tareas/${task.id}`)
    const past = await screen.findByRole('list', { name: es.tasks.lanes.decisions })
    expect(within(past).getByText(es.tasks.lanes.by.model)).toBeVisible()
    expect(within(past).getByText(/Añade un endpoint/)).toBeVisible()
    expect(within(past).getByText(/No hay pantallas/)).toBeVisible()
  })

  it('offers to resolve the conflicts of the join here or with an agent', async () => {
    const { dev, tienda, pipeline } = seed()
    const task = makeTask({
      project_id: tienda.id,
      status: 'waiting_human',
      waiting_reason: 'join_conflict',
      stage_id: 'req',
      phase: 'forked',
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
      join: [{ repo_id: 'r1', name: 'web', lane: 'frontend', files: ['src/app.ts'] }],
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    const block = await screen.findByRole('region', { name: es.tasks.lanes.joinTitle })
    expect(await within(block).findByText('src/app.ts')).toBeVisible()
    await user.click(within(block).getByRole('button', { name: es.tasks.lanes.resolveHere }))
    expect(await within(block).findByText(/join-web/)).toBeVisible()
    await user.click(within(block).getByRole('button', { name: es.tasks.lanes.markResolved }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/join/editor/finish`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/tasks/${task.id}/join/editor/finish`)[0].body).toEqual({
      repo_id: 'r1',
    })

    await user.selectOptions(within(block).getByLabelText(es.tasks.lanes.agent), dev.id)
    await user.click(within(block).getByRole('button', { name: es.tasks.lanes.handToAgent }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/join/agent`)).toHaveLength(1),
    )
    expect(backend.callsTo('POST', `/api/tasks/${task.id}/join/agent`)[0].body).toEqual({
      agent_id: dev.id,
    })
  })

  it('a lane links back to the task that forked', async () => {
    const { dev, tienda, pipeline } = seed()
    const mother = makeTask({ project_id: tienda.id, code: 'T-7', status: 'running' })
    const child = makeTask({
      project_id: tienda.id,
      code: 'T-7·backend',
      lane_of_id: mother.id,
      lane_name: 'Backend',
      fork_stage_id: 'req',
      stage_id: 'back',
    })
    createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [mother, child],
      pipelines: { [tienda.id]: pipeline },
    })
    renderApp(`/tablero/tareas/${child.id}`)
    const link = await screen.findByRole('link', {
      name: es.tasks.lanes.lanePrefix.replace('{{code}}', 'T-7'),
    })
    expect(link).toHaveAttribute('href', `/tablero/tareas/${mother.id}`)
  })
})

describe('Actions of a task that forked', () => {
  it('are done on its lanes: the task itself offers none of the stage actions', async () => {
    const { dev, tienda, pipeline } = seed()
    const task = makeTask({
      project_id: tienda.id,
      status: 'review', // the state of its lane in review
      stage_id: 'req',
      phase: 'forked',
      lanes: [lane({ status: 'review' })],
    })
    createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
    })
    renderApp(`/tablero/tareas/${task.id}`)
    await screen.findByText(es.tasks.lanes.phase.forked)
    for (const name of [
      es.tasks.actions.approve,
      es.tasks.actions.reject,
      es.tasks.actions.retry,
      es.tasks.actions.complete,
    ])
      expect(screen.queryByRole('button', { name })).toBeNull()
    expect(screen.getByRole('button', { name: es.tasks.actions.cancel })).toBeVisible()
  })
})
