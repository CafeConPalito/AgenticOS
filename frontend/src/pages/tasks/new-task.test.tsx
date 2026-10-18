import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { useUiPrefs } from '@/stores/ui-prefs'
import { createFakeBackend, makeAgent, makePipeline, makeProject } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

function seed() {
  const dev = makeAgent({ name: 'Dev', role: 'Desarrollador' })
  const qa = makeAgent({ name: 'QA', role: 'Pruebas' })
  const draft = makeAgent({ name: 'Borrador', status: 'draft' })
  const tienda = makeProject({ name: 'Tienda online' })
  const blog = makeProject({ name: 'Blog', path: 'D:\\blog' })
  return { dev, qa, draft, tienda, blog }
}

async function openWithN(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('navigation', { name: es.nav.main })
  await user.keyboard('n')
  return screen.findByRole('dialog')
}

describe('Nueva tarea dialog', () => {
  it('opens with N, focuses «Qué hay que hacer» and queues the task on the first agent', async () => {
    const { dev, qa, draft, tienda } = seed()
    const backend = createFakeBackend({ agents: [draft, dev, qa], projects: [tienda] })
    const user = userEvent.setup()
    renderApp('/tablero')

    const dialog = await openWithN(user)
    const title = within(dialog).getByLabelText(es.tasks.new.what)
    await waitFor(() => expect(title).toHaveFocus())
    await user.type(title, 'Filtro por precio')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.submit }))

    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/tasks')[0].body).toEqual({
      project_id: tienda.id,
      title: 'Filtro por precio',
      description: '',
      priority: 'normal',
      agent_id: dev.id, // drafts are not offered
      enqueue: true,
    })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(await screen.findByText(/en la cola de/)).toBeVisible()
    expect(screen.getByRole('button', { name: es.tasks.new.view })).toBeVisible()
  })

  it('does not offer draft agents', async () => {
    const { dev, draft, tienda } = seed()
    createFakeBackend({ agents: [draft, dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openWithN(user)
    await user.click(await within(dialog).findByRole('combobox', { name: es.tasks.new.agent }))
    const options = await screen.findAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['Dev · Desarrollador'])
  })

  it('«Guardar en backlog» creates it without queueing', async () => {
    const { dev, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openWithN(user)
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'Idea para más adelante')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.saveBacklog }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/tasks')[0].body).toMatchObject({ enqueue: false })
    expect(await screen.findByText(/guardada en el backlog/)).toBeVisible()
  })

  it('needs a title', async () => {
    const { dev, tienda } = seed()
    createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openWithN(user)
    expect(within(dialog).getByRole('button', { name: es.tasks.new.submit })).toBeDisabled()
    expect(within(dialog).getByRole('button', { name: es.tasks.new.saveBacklog })).toBeDisabled()
  })

  it('the description is folded away until asked for', async () => {
    const { dev, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openWithN(user)
    expect(within(dialog).queryByLabelText(es.tasks.new.descriptionField)).toBeNull()
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'Con detalle')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.addDescription }))
    await user.type(within(dialog).getByLabelText(es.tasks.new.descriptionField), 'Criterios…')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/tasks')[0].body).toMatchObject({
      description: 'Criterios…',
    })
  })

  it('starts on the agent of the card whose «+» opened it', async () => {
    const { dev, qa, tienda } = seed()
    const backend = createFakeBackend({ agents: [dev, qa], projects: [tienda] })
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderApp('/')
    const card = await screen.findByRole('link', { name: /^QA, Pruebas/ })
    await user.click(within(card).getByRole('button', { name: 'Asignar tarea a QA' }))

    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'Probar el carrito')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/tasks')[0].body).toMatchObject({ agent_id: qa.id })
  })

  it('with a pipeline the stage decides the agent: says so and remembers the one used', async () => {
    const { dev, qa, tienda } = seed()
    const pipeline = makePipeline(
      tienda.id,
      [
        {
          id: 'st-1',
          name: 'Diseño',
          agent_id: dev.id,
          agent_name: 'Dev',
          agent_color: dev.color,
        },
      ],
      { id: 'pl-1', name: 'Desarrollo web' },
    )
    const backend = createFakeBackend({
      agents: [dev, qa],
      projects: [tienda],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderApp('/')
    const card = await screen.findByRole('link', { name: /^QA, Pruebas/ })
    await user.click(within(card).getByRole('button', { name: 'Asignar tarea a QA' }))

    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText(/El pipeline decide el agente/)).toHaveTextContent('QA')
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'Con pipeline')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/tasks')[0].body).toMatchObject({ agent_id: null })
    expect(useUiPrefs.getState().lastTaskTarget).toEqual({
      projectId: tienda.id,
      agentId: dev.id,
    })
  })

  it('remembers the last project and agent for the next one', async () => {
    const { dev, qa, tienda, blog } = seed()
    useUiPrefs.setState({ lastTaskTarget: { projectId: blog.id, agentId: qa.id } })
    const backend = createFakeBackend({ agents: [dev, qa], projects: [tienda, blog] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openWithN(user)
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'De nuevo')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/tasks')[0].body).toMatchObject({
      project_id: blog.id,
      agent_id: qa.id,
    })
    expect(useUiPrefs.getState().lastTaskTarget).toEqual({ projectId: blog.id, agentId: qa.id })
  })

  it('N does nothing while typing in a field', async () => {
    const { dev, tienda } = seed()
    createFakeBackend({ agents: [dev], projects: [tienda] })
    const user = userEvent.setup()
    renderApp('/tablero')
    const dialog = await openWithN(user)
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'nnn')
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(within(dialog).getByLabelText(es.tasks.new.what)).toHaveValue('nnn')
  })
})

describe('Nueva tarea con un pipeline que bifurca', () => {
  function forked() {
    const { dev, tienda } = seed()
    const pipeline = makePipeline(
      tienda.id,
      [
        { id: 'req', name: 'Requisitos', agent_id: dev.id, agent_name: 'Dev' },
        { id: 'back', name: 'Dev backend' },
        { id: 'front', name: 'Dev frontend' },
      ],
      {
        links: [
          ['l-back', 'req', 'back', 'Backend', 0],
          ['l-front', 'req', 'front', 'Frontend', 1],
        ].map(([id, from, to, name, position]) => ({
          id: String(id),
          from_stage_id: String(from),
          to_stage_id: String(to),
          name: String(name),
          condition: 'x',
          always: false,
          position: Number(position),
        })),
      },
    )
    return { dev, tienda, pipeline }
  }

  it('can fix the branches by hand, and sends nothing when left alone', async () => {
    const { dev, tienda, pipeline } = forked()
    const backend = createFakeBackend({
      agents: [dev],
      projects: [tienda],
      pipelines: { [tienda.id]: pipeline },
    })
    const user = userEvent.setup()
    renderApp('/tablero')

    let dialog = await openWithN(user)
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'Sin elegir')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/tasks')[0].body).not.toHaveProperty('preset_lanes')

    dialog = await openWithN(user)
    await user.type(within(dialog).getByLabelText(es.tasks.new.what), 'Solo el backend')
    await user.click(within(dialog).getByRole('button', { name: es.tasks.lanes.manual }))
    const fork = await within(dialog).findByRole('group', { name: 'Requisitos' })
    await user.click(within(fork).getByLabelText('Backend'))
    await user.click(within(dialog).getByRole('button', { name: es.tasks.new.submit }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/tasks')).toHaveLength(2))
    expect(backend.callsTo('POST', '/api/tasks')[1].body).toMatchObject({
      preset_lanes: { req: ['l-back'] },
    })
  })
})
