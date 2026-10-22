import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { KnowledgeGraph, SearchHit } from '@/api/knowledge'
import es from '@/i18n/es.json'
import { createFakeBackend, makeKnowledgeDoc } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const s = es.knowledge.search
const g = es.knowledge.graph

const hit = (overrides: Partial<SearchHit>): SearchHit => ({
  doc_id: 'pdf',
  title: 'Manual de Celery',
  scope: 'general',
  chunk: 0,
  heading: 'Tareas',
  location: 'p. 3',
  text: 'Celery es una cola de tareas.',
  score: 0.9,
  found_by: 'both',
  via: '',
  images: [],
  ...overrides,
})

const docs = () => [
  makeKnowledgeDoc({ id: 'pdf', title: 'Manual de Celery' }),
  makeKnowledgeDoc({ id: 'guide', title: 'Guía de reintentos', origin: 'agent' }),
]

async function open(seed: Parameters<typeof createFakeBackend>[0] = {}) {
  installFakeWebSocket()
  const backend = createFakeBackend({ knowledge: docs(), ...seed })
  const user = userEvent.setup()
  renderApp('/conocimiento')
  await screen.findByRole('group', { name: s.mode.label })
  return { backend, user }
}

describe('Search tester · búsqueda', () => {
  it('marks what came from the graph and how it was reached', async () => {
    const { user } = await open({
      searchHits: [
        hit({}),
        hit({
          doc_id: 'guide',
          title: 'Guía de reintentos',
          chunk: 1,
          score: 0,
          found_by: 'graph',
          via: 'deriva de «Manual de Celery»',
          text: 'Usa autoretry_for.',
        }),
      ],
    })
    await user.type(screen.getByLabelText(s.label), 'reintentos')
    await user.click(screen.getByRole('button', { name: s.run }))
    const text = await screen.findByText('Usa autoretry_for.')
    const result = text.closest('li')!
    expect(within(result).getByText(/por el grafo/)).toBeVisible()
    expect(within(result).getByText(/vecino: deriva de «Manual de Celery»/)).toBeVisible()
  })
})

describe('Search tester · explorar', () => {
  const exploration = {
    message: '',
    nodes: [
      {
        id: 'pdf',
        title: 'Manual de Celery',
        depth: 0,
        strength: 1,
        path: ['Manual de Celery'],
        reasons: [],
      },
      {
        id: 'guide',
        title: 'Guía de reintentos',
        depth: 1,
        strength: 1,
        path: ['Manual de Celery', 'Guía de reintentos'],
        reasons: ['origen de'],
      },
      {
        id: 'tuning',
        title: 'Ajustes finos',
        depth: 2,
        strength: 0.62,
        path: ['Manual de Celery', 'Guía de reintentos', 'Ajustes finos'],
        reasons: ['origen de', 'relacionado 0,52'],
      },
    ],
  }

  it('walks the graph from a question and shows how each document was reached', async () => {
    const { backend, user } = await open({ exploration })
    await user.click(screen.getByRole('button', { name: s.mode.explore }))
    await user.type(screen.getByLabelText(s.explore.label), 'reintentos en celery')
    await user.click(screen.getByRole('button', { name: s.explore.run }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/knowledge/explore')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/knowledge/explore')[0].body).toEqual({
      document: 'reintentos en celery',
      query: 'reintentos en celery',
      hops: 2,
      project_id: null,
      agent_id: null,
    })
    const start = await screen.findByText(s.explore.start)
    const items = within(start.closest('ol')!).getAllByRole('listitem')
    expect(within(items[0]).getByText(s.explore.start)).toBeVisible()
    expect(within(items[1]).getByText(/a 1 saltos|a 1 salto/)).toBeVisible()
    const far = items[2]
    expect(within(far).getByText(/a 2 saltos/)).toBeVisible()
    expect(within(far).getByText(/fuerza 0,62/)).toBeVisible()
    expect(far).toHaveTextContent(
      'Manual de Celery —origen de→ Guía de reintentos —relacionado 0,52→ Ajustes finos',
    )
  })

  it('asks for the number of hops', async () => {
    const { backend, user } = await open({ exploration })
    await user.click(screen.getByRole('button', { name: s.mode.explore }))
    await user.click(screen.getByRole('combobox', { name: s.explore.hops }))
    await user.click(await screen.findByRole('option', { name: '3' }))
    await user.type(screen.getByLabelText(s.explore.label), 'celery')
    await user.click(screen.getByRole('button', { name: s.explore.run }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/knowledge/explore')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/knowledge/explore')[0].body).toMatchObject({ hops: 3 })
  })

  it('shows the reached documents highlighted in the graph', async () => {
    const graph: KnowledgeGraph = {
      version: 1,
      nodes: ['pdf', 'guide', 'tuning', 'other'].map((id) => ({
        id,
        title: id,
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
        md_tokens: 100,
        topic: null,
      })),
      edges: [],
      topics: [],
    }
    const { user } = await open({ exploration, graph })
    await user.click(screen.getByRole('button', { name: s.mode.explore }))
    await user.type(screen.getByLabelText(s.explore.label), 'celery')
    await user.click(screen.getByRole('button', { name: s.explore.run }))
    await user.click(await screen.findByRole('button', { name: s.explore.highlight }))
    expect(await screen.findByRole('group', { name: g.canvas })).toBeVisible()
    expect(await screen.findByText('3 documentos resaltados')).toBeVisible()
    expect(screen.getByLabelText('Abrir pdf')).toHaveAttribute('data-matched', 'true')
    expect(screen.getByLabelText('Abrir other')).toHaveAttribute('data-matched', 'false')
    await user.click(screen.getByRole('button', { name: g.search.clear }))
    expect(screen.getByLabelText('Abrir other')).not.toHaveAttribute('data-matched')
  })

  it('says why nothing was explored', async () => {
    const { user } = await open({
      exploration: { nodes: [], message: 'No encontré nada en el conocimiento para «zzz».' },
    })
    await user.click(screen.getByRole('button', { name: s.mode.explore }))
    await user.type(screen.getByLabelText(s.explore.label), 'zzz')
    await user.click(screen.getByRole('button', { name: s.explore.run }))
    expect(await screen.findByText(/No encontré nada en el conocimiento para «zzz»/)).toBeVisible()
  })

  it('opens a reached document', async () => {
    const { user } = await open({ exploration, markdowns: { guide: '# Reintentos\n\nTexto.' } })
    await user.click(screen.getByRole('button', { name: s.mode.explore }))
    await user.type(screen.getByLabelText(s.explore.label), 'celery')
    await user.click(screen.getByRole('button', { name: s.explore.run }))
    await user.click(await screen.findByRole('button', { name: 'Guía de reintentos' }))
    expect(await screen.findByRole('dialog')).toBeVisible()
  })
})

describe('Search tester · mapa', () => {
  it('lists the topics an agent of this context would see', async () => {
    const { user } = await open({
      graph: {
        version: 1,
        nodes: [],
        edges: [],
        topics: [
          { id: 0, name: 'Celery · broker', size: 4, loose: false, central: [], neighbors: [1] },
          { id: 1, name: 'Docker', size: 3, loose: false, central: [], neighbors: [0] },
          { id: 2, name: 'Sueltos', size: 1, loose: true, central: [], neighbors: [] },
        ],
      },
    })
    await user.click(screen.getByRole('button', { name: s.mode.map }))
    expect(await screen.findByText(s.map.intro)).toBeVisible()
    const topics = screen.getByText(s.map.intro).parentElement!
    const items = within(topics).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Celery · broker')
    expect(items[0]).toHaveTextContent('4 documentos')
    expect(items[0]).toHaveTextContent('Cerca de: Docker')
    expect(items[2]).toHaveTextContent(s.map.loose)
  })

  it('says so when there are no topics yet', async () => {
    const { user } = await open()
    await user.click(screen.getByRole('button', { name: s.mode.map }))
    expect(await screen.findByText(s.map.empty)).toBeVisible()
  })

  it('switches between the three ways to try it', async () => {
    const { user } = await open()
    const modes = screen.getByRole('group', { name: s.mode.label })
    expect(within(modes).getByRole('button', { name: s.mode.search })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await user.click(within(modes).getByRole('button', { name: s.mode.explore }))
    expect(within(modes).getByRole('button', { name: s.mode.explore })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.queryByLabelText(s.label)).toBeNull()
  })
})
