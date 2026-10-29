import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makePipeline, makeProject } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

function seed() {
  const dev = makeAgent({ name: 'Dev', role: 'Desarrollador' })
  const qa = makeAgent({ name: 'QA', role: 'Pruebas' })
  const tienda = makeProject({ name: 'Tienda online' })
  return { dev, qa, tienda }
}

const stagesNav = () => screen.findByRole('navigation', { name: es.pipeline.stages })

async function pick(user: ReturnType<typeof userEvent.setup>, name: string) {
  const nav = await stagesNav()
  await user.click(within(nav).getByRole('button', { name: new RegExp(name) }))
}

describe('Pipeline editor', () => {
  it('starts from the template, edits a stage and saves the graph', async () => {
    const { dev, qa, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev, qa], projects: [tienda] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)

    await user.click(await screen.findByRole('button', { name: es.pipeline.useTemplate }))
    const nav = await stagesNav()
    expect(within(nav).getAllByRole('listitem')).toHaveLength(3)

    await pick(user, 'Desarrollo')
    const name = screen.getByLabelText(es.pipeline.stageName.replace('{{n}}', '2'))
    await user.clear(name)
    await user.type(name, 'Implementación')
    await user.click(screen.getByRole('button', { name: es.common.save }))

    await waitFor(() =>
      expect(backend.callsTo('PUT', `/api/projects/${tienda.id}/pipeline`)).toHaveLength(1),
    )
    const body = backend.callsTo('PUT', `/api/projects/${tienda.id}/pipeline`)[0].body as {
      stages: { name: string; reject_to: number | null; reject_also: number[] }[]
      links: { source: number; target: number }[]
    }
    expect(body.stages.map((s) => [s.name, s.reject_to])).toEqual([
      ['Requisitos', null],
      ['Implementación', null],
      ['QA', 1],
    ])
    expect(body.links.map((l) => [l.source, l.target])).toEqual([
      [0, 1],
      [1, 2],
    ])
  })

  it('offers the split template and shows its fork, its branches and QA’s two rejection targets', async () => {
    const { dev, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)

    await user.click(await screen.findByRole('button', { name: es.pipeline.useTemplateSplit }))
    expect(backend.callsTo('POST', `/api/projects/${tienda.id}/pipeline/template`)[0].body).toEqual(
      {
        template: 'web_split',
      },
    )
    await pick(user, 'Requisitos')
    const panel = await screen.findByRole('region', {
      name: es.pipeline.stagePanel.replace('{{name}}', 'Requisitos'),
    })
    // Two outgoing links: it is a fork, and the person can ask to confirm the decision
    expect(within(panel).getByLabelText(es.pipeline.confirmDecision)).toBeVisible()
    expect(within(panel).getByRole('button', { name: /Backend → Dev backend/ })).toBeVisible()
    expect(within(panel).getByRole('button', { name: /Frontend → Dev frontend/ })).toBeVisible()

    await pick(user, 'QA')
    const qaPanel = await screen.findByRole('region', {
      name: es.pipeline.stagePanel.replace('{{name}}', 'QA'),
    })
    expect(within(qaPanel).getByRole('combobox', { name: es.pipeline.rejectTo })).toHaveTextContent(
      'Dev backend',
    )
    const also = within(qaPanel).getByRole('group', { name: es.pipeline.rejectAlso })
    expect(within(also).getByLabelText('Dev frontend')).toBeChecked()
  })

  it('edits a branch: name, condition and «always»', async () => {
    const { dev, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)
    await user.click(await screen.findByRole('button', { name: es.pipeline.useTemplateSplit }))

    await pick(user, 'Requisitos')
    const panel = await screen.findByRole('region', { name: /Etapa Requisitos/ })
    await user.click(within(panel).getByRole('button', { name: /Backend → Dev backend/ }))
    const branch = await screen.findByRole('region', { name: /Rama de Requisitos a Dev backend/ })
    const condition = within(branch).getByLabelText(es.pipeline.condition)
    await user.clear(condition)
    await user.type(condition, 'Toca la base de datos')
    await user.click(within(branch).getByLabelText(es.pipeline.branchName))
    await user.click(screen.getByRole('button', { name: es.common.save }))

    await waitFor(() =>
      expect(backend.callsTo('PUT', `/api/projects/${tienda.id}/pipeline`)).toHaveLength(1),
    )
    const body = backend.callsTo('PUT', `/api/projects/${tienda.id}/pipeline`)[0].body as {
      links: { source: number; target: number; condition: string; always: boolean }[]
    }
    expect(body.links.find((l) => l.source === 0 && l.target === 1)).toMatchObject({
      condition: 'Toca la base de datos',
      always: false,
    })
  })

  it('a branch without a condition is always taken and can be saved (phase 21)', async () => {
    const { dev, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)
    await user.click(await screen.findByRole('button', { name: es.pipeline.useTemplateSplit }))

    await pick(user, 'Requisitos')
    const panel = await screen.findByRole('region', { name: /Etapa Requisitos/ })
    await user.click(within(panel).getByRole('button', { name: /Backend → Dev backend/ }))
    const branch = await screen.findByRole('region', { name: /Rama de Requisitos a Dev backend/ })
    expect(within(branch).getByText(es.pipeline.conditionHelp)).toBeVisible()
    await user.clear(within(branch).getByLabelText(es.pipeline.condition))
    expect(within(branch).getByText(es.pipeline.alwaysHelp)).toBeVisible()

    expect(screen.queryByRole('list', { name: es.pipeline.problems })).toBeNull()
    await user.click(screen.getByRole('button', { name: es.common.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', `/api/projects/${tienda.id}/pipeline`)).toHaveLength(1),
    )
    const body = backend.callsTo('PUT', `/api/projects/${tienda.id}/pipeline`)[0].body as {
      links: { source: number; target: number; condition: string; always: boolean }[]
    }
    expect(body.links.find((l) => l.source === 0 && l.target === 1)).toMatchObject({
      condition: '',
      always: false,
    })
  })

  it('shows the problems of a graph that is not well built and goes to where they are', async () => {
    const { dev, tienda } = seed()
    createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)
    await user.click(await screen.findByRole('button', { name: es.pipeline.useTemplate }))

    // Requisitos → QA besides Requisitos → Desarrollo → QA: a branch with no stages of its own
    await pick(user, 'Requisitos')
    const panel = await screen.findByRole('region', { name: /Etapa Requisitos/ })
    await user.click(within(panel).getByRole('combobox', { name: es.pipeline.addLink }))
    await user.click(await screen.findByRole('option', { name: 'QA' }))
    const problems = await screen.findByRole('list', { name: es.pipeline.problems })
    await user.click(within(problems).getByText(/no tiene etapas propias/))
    // the problem is on that branch, so its panel opens
    expect(await screen.findByRole('region', { name: /Rama de Requisitos a QA/ })).toBeVisible()
    expect(screen.getByRole('button', { name: es.common.save })).toBeDisabled()
  })

  it('tries the conditions with an example task and shows what would be taken', async () => {
    const { dev, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)
    await user.click(await screen.findByRole('button', { name: es.pipeline.useTemplateSplit }))

    // With nothing selected the pipeline’s settings show the decider and «Probar»
    const nav = await stagesNav()
    expect(nav).toBeVisible()
    await user.click(await screen.findByRole('button', { name: es.pipeline.try }))
    const dialog = await screen.findByRole('dialog')
    await user.type(
      within(dialog).getByLabelText(es.pipeline.tryTask),
      'Nuevo endpoint de clientes',
    )
    await user.click(within(dialog).getByRole('button', { name: es.pipeline.tryRun }))

    const result = await within(dialog).findByRole('list', { name: es.pipeline.tryResult })
    const rows = within(result).getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('Backend')
    expect(rows[0]).toHaveTextContent('Encaja con la condición')
    expect(within(rows[0]).getByLabelText(es.pipeline.taken)).toBeVisible()
    expect(within(rows[1]).getByLabelText(es.pipeline.notTaken)).toBeVisible()
    const call = backend.callsTo('POST', `/api/projects/${tienda.id}/pipeline/decide-preview`)[0]
    expect(call.body).toMatchObject({
      title: 'Nuevo endpoint de clientes',
      branches: [
        { name: 'Backend', condition: 'Toca la API' },
        { name: 'Frontend', condition: 'Toca la UI' },
      ],
    })
  })

  it('does not remove a stage that has tasks, and says why', async () => {
    const { dev, tienda } = seed()
    const pipeline = makePipeline(tienda.id, [
      { id: 's1', name: 'Diseño', agent_id: dev.id, agent_name: 'Dev', agent_color: dev.color },
      { id: 's2', name: 'Código', active_tasks: 2 },
    ])
    createFakeBackend({ agents: [dev], projects: [tienda], pipelines: { [tienda.id]: pipeline } })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)

    await pick(user, 'Código')
    const remove = await screen.findByRole('button', { name: es.pipeline.remove })
    expect(remove).toBeDisabled()
    expect(remove).toHaveAttribute('title', '2 tareas en esta etapa')
    await pick(user, 'Diseño')
    expect(screen.getByRole('button', { name: es.pipeline.remove })).toBeEnabled()
  })

  it('warns that branches go one after the other in a direct folder', async () => {
    const { dev, tienda } = seed()
    createFakeBackend({ agents: [dev], projects: [{ ...tienda, workspace_mode: 'direct' }] })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)
    await user.click(await screen.findByRole('button', { name: es.pipeline.useTemplateSplit }))
    expect(await screen.findByRole('note')).toHaveTextContent(es.pipeline.directWarning)
  })
})

describe('Pipeline editor with several forks', () => {
  it('offers to try each fork on its own', async () => {
    const { dev, tienda } = seed()
    // A → (B | C) → D → (E | F) → G
    const stageIds = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
    const pipeline = makePipeline(
      tienda.id,
      stageIds.map((id) => ({ id, name: id.toUpperCase(), agent_id: dev.id })),
      {
        links: [
          ['a', 'b'],
          ['a', 'c'],
          ['b', 'd'],
          ['c', 'd'],
          ['d', 'e'],
          ['d', 'f'],
          ['e', 'g'],
          ['f', 'g'],
        ].map(([from, to], i) => ({
          id: `l${i}`,
          from_stage_id: from,
          to_stage_id: to,
          name: to.toUpperCase(),
          condition: 'x',
          always: false,
          position: i % 2,
        })),
      },
    )
    createFakeBackend({ agents: [dev], projects: [tienda], pipelines: { [tienda.id]: pipeline } })
    const user = userEvent.setup()
    renderApp(`/proyectos/${tienda.id}/pipeline`)

    const second = await screen.findByRole('button', {
      name: es.pipeline.tryFork.replace('{{name}}', 'D'),
    })
    expect(
      screen.getByRole('button', { name: es.pipeline.tryFork.replace('{{name}}', 'A') }),
    ).toBeVisible()
    await user.click(second)
    expect(await screen.findByRole('dialog')).toHaveTextContent('Probar las ramas de D')
  })
})
