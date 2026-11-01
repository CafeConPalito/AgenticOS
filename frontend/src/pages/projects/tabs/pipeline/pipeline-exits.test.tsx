import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Pipeline } from '@/api/types'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAgent,
  makePipeline,
  makeProject,
  makeTask,
} from '@/test/fake-backend'
import { renderApp } from '@/test/render'

const X = es.pipeline.exit
const T = es.tasks.exit

function seed(exit: string | null = null) {
  const dev = makeAgent({ name: 'Dev' })
  const tienda = makeProject({ name: 'Tienda online' })
  const pipeline: Pipeline = makePipeline(tienda.id, [
    { id: 'req', name: 'Requisitos', agent_id: dev.id, agent_name: 'Dev', exit_condition: exit },
    { id: 'code', name: 'Código', agent_id: dev.id, agent_name: 'Dev' },
  ])
  return { dev, tienda, pipeline }
}

async function pick(user: ReturnType<typeof userEvent.setup>, name: string) {
  const nav = await screen.findByRole('navigation', { name: es.pipeline.stages })
  await user.click(within(nav).getByRole('button', { name: new RegExp(name) }))
}

describe('«Terminar aquí» in the pipeline editor (phase 24, CA2)', () => {
  it('adds an exit with its condition, saves it and removes it', async () => {
    const { dev, tienda, pipeline } = seed()
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)

    await pick(user, 'Código')
    // The last stage is already a final one.
    expect(await screen.findByRole('button', { name: X.add })).toBeDisabled()

    await pick(user, 'Requisitos')
    await user.click(await screen.findByRole('button', { name: X.add }))
    // Without a condition the graph says what is missing.
    expect(
      await screen.findByText(X.condition.replace('…', ''), { exact: false }),
    ).toBeInTheDocument()
    expect(
      await screen.findByText(
        es.pipeline.issues.exit_no_condition.replace('{{stage}}', 'Requisitos'),
      ),
    ).toBeInTheDocument()
    await user.type(screen.getByLabelText(X.condition), 'La tarea solo pide requisitos')
    // A stage with an exit can ask to confirm its decision too.
    expect(screen.getByLabelText(es.pipeline.confirmDecision)).toBeVisible()
    await user.click(screen.getByRole('button', { name: es.common.save }))

    await waitFor(() =>
      expect(backend.callsTo('PUT', `/api/projects/${tienda.id}/pipeline`)).toHaveLength(1),
    )
    const body = backend.callsTo('PUT', `/api/projects/${tienda.id}/pipeline`)[0].body as {
      stages: { name: string; exit_condition: string | null }[]
    }
    expect(body.stages.map((s) => [s.name, s.exit_condition])).toEqual([
      ['Requisitos', 'La tarea solo pide requisitos'],
      ['Código', null],
    ])

    await pick(user, 'Requisitos')
    await user.click(await screen.findByRole('button', { name: X.remove }))
    expect(screen.getByRole('button', { name: X.add })).toBeEnabled()
  })

  it('tries the exit with an example task', async () => {
    const { dev, tienda, pipeline } = seed('La tarea solo pide requisitos')
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)

    await user.click(
      await screen.findByRole('button', { name: X.try.replace('{{name}}', 'Requisitos') }),
    )
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(es.pipeline.tryTask), 'Requisitos del login')
    await user.click(within(dialog).getByRole('button', { name: es.pipeline.tryRun }))
    const result = await within(dialog).findByRole('list', { name: es.pipeline.tryResult })
    expect(within(result).getAllByRole('listitem')[0]).toHaveTextContent('Terminar aquí')
    const call = backend.callsTo('POST', `/api/projects/${tienda.id}/pipeline/decide-preview`)[0]
    expect(call.body).toMatchObject({
      branches: [],
      exit_condition: 'La tarea solo pide requisitos',
      stage_name: 'Requisitos',
    })
  })
})

describe('«Terminar aquí» in a task (phase 24, CA2)', () => {
  it('lets the person end the task at a stage with an exit', async () => {
    const { dev, tienda, pipeline } = seed('La tarea solo pide requisitos')
    const task = makeTask({
      project_id: tienda.id,
      status: 'waiting_human',
      waiting_reason: 'choose_branch',
      stage_id: 'req',
      stage_name: 'Requisitos',
      stage_exit_condition: 'La tarea solo pide requisitos',
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    const choice = await screen.findByRole('group', { name: T.choose })
    const end = within(choice).getByRole('checkbox', { name: new RegExp(T.option) })
    const goOn = within(choice).getByRole('checkbox', {
      name: new RegExp(T.goOn.replace('{{stage}}', 'Código')),
    })
    await user.click(goOn)
    await user.click(end) // ending drops going on
    expect(goOn).not.toBeChecked()
    await user.click(within(choice).getByRole('button', { name: T.end }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/decision`)[0]?.body).toEqual({
        chosen: ['exit'],
      }),
    )
  })

  it('shows where a task ended and goes on with the pipeline', async () => {
    const { dev, tienda, pipeline } = seed('La tarea solo pide requisitos')
    const task = makeTask({
      project_id: tienda.id,
      status: 'done',
      stage_id: 'req',
      stage_name: 'Requisitos',
      exit_stage_id: 'req',
      exit_stage_name: 'Requisitos',
    })
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup()
    renderApp(`/tablero/tareas/${task.id}`)

    expect(
      await screen.findByText(T.endedAt.replace('{{stage}}', 'Requisitos')),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: T.continue }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/tasks/${task.id}/continue`)).toHaveLength(1),
    )
    expect(await screen.findByText(T.continued)).toBeVisible()
  })

  it('the board card says where the task ended', async () => {
    const { dev, tienda, pipeline } = seed('La tarea solo pide requisitos')
    const task = makeTask({
      project_id: tienda.id,
      project_name: tienda.name,
      status: 'done',
      stage_name: 'Requisitos',
      exit_stage_id: 'req',
      exit_stage_name: 'Requisitos',
    })
    createFakeBackend({
      agents: [dev],
      projects: [tienda],
      tasks: [task],
      pipelines: { [tienda.id]: pipeline },
    })
    renderApp('/tablero')
    const card = (await screen.findByText(task.title)).closest('a')
    expect(card).toHaveTextContent(T.endedAt.replace('{{stage}}', 'Requisitos'))
  })
})
