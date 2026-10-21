import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { GraphNode, KnowledgeGraph } from '@/api/knowledge'
import es from '@/i18n/es.json'
import { createFakeBackend, makeKnowledgeDoc, makeProject } from '@/test/fake-backend'
import { FakeWebSocket, installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const g = es.knowledge.graph

function node(id: string, title: string, overrides: Partial<GraphNode> = {}): GraphNode {
  return {
    id,
    title,
    summary: '',
    ghost: false,
    origin: 'user',
    source_kind: 'file',
    review: 'none',
    scope: 'general',
    project_id: null,
    agent_id: null,
    mode: 'auto',
    status: 'ready',
    presence: 'ok',
    md_tokens: 1200,
    topic: 0,
    ...overrides,
  }
}

const graph: KnowledgeGraph = {
  version: 3,
  nodes: [
    node('pdf', 'Manual de Celery'),
    node('web', 'Docs de Redis', { source_kind: 'url', topic: 0 }),
    node('shot', 'Captura de error', { source_kind: 'image', topic: 1 }),
    node('guide', 'Guía de reintentos', {
      origin: 'agent',
      source_kind: 'markdown',
      topic: 0,
    }),
    node('draft', 'Guía de colas', {
      origin: 'agent',
      source_kind: 'markdown',
      review: 'proposed',
      topic: 0,
    }),
    node('gone', 'Guía antigua', { ghost: true, scope: null, topic: null, md_tokens: 0 }),
    node('off', 'Apagado', { mode: 'off', topic: 1 }),
  ],
  edges: [
    { kind: 'derived', source: 'pdf', target: 'guide', weight: 1 },
    { kind: 'derived', source: 'guide', target: 'draft', weight: 1 },
    { kind: 'derived', source: 'gone', target: 'draft', weight: 1 },
    { kind: 'related', source: 'pdf', target: 'web', weight: 0.7 },
    { kind: 'related', source: 'shot', target: 'off', weight: 0.4 },
  ],
  topics: [
    { id: 0, name: 'Celery · broker', size: 4, loose: false, central: ['pdf'], neighbors: [1] },
    { id: 1, name: 'Errores', size: 2, loose: false, central: ['shot'], neighbors: [0] },
  ],
}

async function openGraph(seed: Parameters<typeof createFakeBackend>[0] = {}) {
  installFakeWebSocket()
  const backend = createFakeBackend({
    knowledge: [makeKnowledgeDoc({ id: 'pdf', title: 'Manual de Celery' })],
    graph,
    ...seed,
  })
  const user = userEvent.setup()
  renderApp('/conocimiento')
  await user.click(await screen.findByRole('tab', { name: es.knowledge.views.graph }))
  await screen.findByRole('group', { name: g.canvas })
  return { backend, user }
}

// Nodes are driven with plain DOM events: React Flow listens to them with d3, which needs a real
// window in `event.view` that user-event's pointer events in jsdom do not carry.
// React Flow measures nodes with a ResizeObserver, which jsdom does not drive: it keeps them
// `visibility: hidden`, and a hidden element has no accessible name, so they are found by label.
const nodeButton = (title: string) => screen.getByLabelText(g.node.open.replace('{{title}}', title))
const queryNode = (title: string) =>
  screen.queryByLabelText(g.node.open.replace('{{title}}', title))

describe('The knowledge graph', () => {
  it('draws a node for every document, each looking like where it came from', async () => {
    await openGraph()
    expect(nodeButton('Manual de Celery')).toHaveAttribute('data-kind', 'file')
    expect(nodeButton('Docs de Redis')).toHaveAttribute('data-kind', 'url')
    expect(nodeButton('Captura de error')).toHaveAttribute('data-kind', 'image')
    expect(nodeButton('Guía de reintentos')).toHaveAttribute('data-kind', 'agent')
    expect(nodeButton('Guía de colas')).toHaveAttribute('data-kind', 'proposed')
    // The source that was deleted is a ghost, not a document that can be opened.
    expect(
      screen.getByLabelText(g.node.ghost.replace('{{title}}', 'Guía antigua')),
    ).toHaveAttribute('data-kind', 'ghost')
  })

  it('summarises it, explains the shapes and lists the topics', async () => {
    await openGraph()
    expect(screen.getByText('7 documentos · 5 vínculos')).toBeVisible()
    const legend = screen.getByRole('region', { name: g.legend.title })
    for (const label of [
      g.legend.file,
      g.legend.url,
      g.legend.image,
      g.legend.agent,
      g.legend.proposed,
      g.legend.removed,
      g.legend.derived,
      g.legend.related,
    ])
      expect(within(legend).getByText(label)).toBeVisible()
    const topics = screen.getByRole('region', { name: g.topics.title })
    expect(within(topics).getByText(/Celery · broker/)).toBeVisible()
    expect(within(topics).getByText(/Errores/)).toBeVisible()
  })

  it('opens the document of a node with a click', async () => {
    await openGraph({
      knowledge: [makeKnowledgeDoc({ id: 'pdf', title: 'Manual de Celery' })],
      markdowns: { pdf: '# Manual\n\nCelery es una cola.' },
    })
    fireEvent.click(nodeButton('Manual de Celery'))
    const sheet = await screen.findByRole('dialog')
    expect(await within(sheet).findByText(/Celery es una cola/)).toBeVisible()
  })

  it('opens it from the keyboard too, and a ghost opens nothing', async () => {
    await openGraph({
      knowledge: [makeKnowledgeDoc({ id: 'pdf', title: 'Manual de Celery' })],
      markdowns: { pdf: '# Manual\n\nCelery es una cola.' },
    })
    fireEvent.click(screen.getByLabelText(g.node.ghost.replace('{{title}}', 'Guía antigua')))
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.keyDown(nodeButton('Manual de Celery'), { key: 'Enter' })
    expect(await screen.findByRole('dialog')).toBeVisible()
  })

  it('filters by origin, state and topic', async () => {
    const { user } = await openGraph()
    await user.click(screen.getByRole('combobox', { name: g.filters.origin }))
    await user.click(await screen.findByRole('option', { name: g.filters.byAgent }))
    expect(nodeButton('Guía de reintentos')).toBeInTheDocument()
    expect(queryNode('Manual de Celery')).toBeNull()

    await user.click(screen.getByRole('button', { name: g.filters.reset }))
    await user.click(screen.getByRole('combobox', { name: g.filters.state }))
    await user.click(await screen.findByRole('option', { name: g.filters.pending }))
    expect(nodeButton('Guía de colas')).toBeInTheDocument()
    expect(queryNode('Docs de Redis')).toBeNull()

    await user.click(screen.getByRole('button', { name: g.filters.reset }))
    await user.click(screen.getByRole('combobox', { name: g.filters.topic }))
    await user.click(await screen.findByRole('option', { name: 'Errores' }))
    expect(nodeButton('Captura de error')).toBeInTheDocument()
    expect(nodeButton('Apagado')).toBeInTheDocument()
    expect(queryNode('Manual de Celery')).toBeNull()
  })

  it('shows only the neighbourhood of a document on a double click, and all again', async () => {
    const { user } = await openGraph()
    fireEvent.doubleClick(nodeButton('Manual de Celery'))
    expect(await screen.findByText(/Vecindario de Manual de Celery/)).toBeVisible()
    expect(nodeButton('Docs de Redis')).toBeInTheDocument()
    expect(nodeButton('Guía de reintentos')).toBeInTheDocument()
    expect(queryNode('Captura de error')).toBeNull()
    await user.click(screen.getByRole('button', { name: g.unfocus }))
    expect(nodeButton('Captura de error')).toBeInTheDocument()
  })

  it('highlights the documents that answer a question and fades the rest', async () => {
    const { backend, user } = await openGraph({
      searchHits: [
        {
          doc_id: 'guide',
          title: 'Guía de reintentos',
          scope: 'general',
          chunk: 0,
          heading: '',
          location: '',
          text: 'autoretry',
          score: 0.9,
          found_by: 'both',
          via: '',
          images: [],
        },
        {
          doc_id: 'pdf',
          title: 'Manual de Celery',
          scope: 'general',
          chunk: 1,
          heading: '',
          location: '',
          text: 'tareas',
          score: 0,
          found_by: 'graph',
          via: 'origen de «Guía de reintentos»',
          images: [],
        },
      ],
    })
    await user.type(screen.getByLabelText(g.search.label), 'reintentos')
    await user.click(screen.getByRole('button', { name: g.search.run }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/knowledge/search')).toHaveLength(1))
    expect(await screen.findByText('2 documentos resaltados')).toBeVisible()
    expect(nodeButton('Guía de reintentos')).toHaveAttribute('data-matched', 'true')
    expect(nodeButton('Manual de Celery')).toHaveAttribute('data-matched', 'true')
    expect(nodeButton('Captura de error')).toHaveAttribute('data-matched', 'false')
    await user.click(screen.getByRole('button', { name: g.search.clear }))
    expect(nodeButton('Captura de error')).not.toHaveAttribute('data-matched')
  })

  it('says when nothing answers the question', async () => {
    const { user } = await openGraph({ searchHits: [] })
    await user.type(screen.getByLabelText(g.search.label), 'nada de nada')
    await user.click(screen.getByRole('button', { name: g.search.run }))
    expect(await screen.findByText(g.search.none)).toBeVisible()
  })

  it('shows the whole library on demand', async () => {
    const { backend, user } = await openGraph()
    await user.click(screen.getByRole('switch', { name: g.scope.all }))
    await waitFor(() =>
      expect(
        backend.calls.some((c) => c.path === '/api/knowledge/graph' && c.query === '?all=true'),
      ).toBe(true),
    )
  })

  it('asks for the graph of the project it is opened from', async () => {
    installFakeWebSocket()
    const project = makeProject({ id: 'p1', name: 'Blog' })
    const backend = createFakeBackend({
      projects: [project],
      knowledge: [makeKnowledgeDoc({ scope: 'project', project_id: 'p1', title: 'Guía' })],
      graph,
    })
    const user = userEvent.setup()
    renderApp('/proyectos/p1/knowledge')
    await user.click(await screen.findByRole('tab', { name: es.knowledge.views.graph }))
    await waitFor(() =>
      expect(
        backend.calls.some(
          (c) => c.path === '/api/knowledge/graph' && c.query === '?project_id=p1',
        ),
      ).toBe(true),
    )
  })

  it('says so when there is nothing to draw', async () => {
    installFakeWebSocket()
    createFakeBackend({
      knowledge: [makeKnowledgeDoc({ title: 'Manual' })],
      graph: { version: 1, nodes: [], edges: [], topics: [] },
    })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('tab', { name: es.knowledge.views.graph }))
    expect(await screen.findByText(g.empty)).toBeVisible()
  })

  it('reads the graph again when the backend says the links changed', async () => {
    const { backend } = await openGraph()
    const reads = () => backend.calls.filter((c) => c.path === '/api/knowledge/graph').length
    const before = reads()
    await waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThan(0))
    const socket = FakeWebSocket.instances[0]
    act(() => socket.open())
    act(() => socket.push({ type: 'graph', version: 4 } as never))
    await waitFor(() => expect(reads()).toBeGreaterThan(before))
  })
})
