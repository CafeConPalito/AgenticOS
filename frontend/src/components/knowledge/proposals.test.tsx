import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { KnowledgeDoc, Provenance } from '@/api/knowledge'
import es from '@/i18n/es.json'
import {
  createFakeBackend,
  makeAgent,
  makeInboxItem,
  makeKnowledgeDoc,
  makeProject,
} from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const k = es.knowledge
const p = k.proposal

const provenance = (overrides: Partial<Provenance> = {}): Provenance => ({
  agent_id: 'agent-1',
  agent_name: 'Redactor',
  run_id: 'run-1',
  task_id: null,
  task_title: 'Documentar Celery',
  proposed_at: new Date().toISOString(),
  suggested_scope: 'general',
  replaces_id: null,
  decided_at: null,
  edited: false,
  ...overrides,
})

function celery() {
  return makeKnowledgeDoc({ id: 'pdf', title: 'Manual de Celery' })
}

function proposal(overrides: Partial<KnowledgeDoc> = {}) {
  return makeKnowledgeDoc({
    id: 'prop-1',
    title: 'Guía de reintentos',
    description: 'Cómo reintentar tareas',
    source_kind: 'markdown',
    origin: 'agent',
    review: 'proposed',
    path: null,
    file_name: null,
    extension: '',
    viewer: 'none',
    size: null,
    md_tokens: 300,
    summary: 'Cómo reintentar tareas',
    provenance: provenance(),
    sources: [{ id: 'pdf', title: 'Manual de Celery', removed: false }],
    ...overrides,
  })
}

const GUIDE = '# Reintentos\n\nUsa autoretry_for y retry_backoff.'

describe('Proposed knowledge in the library', () => {
  it('shows a proposal apart and filters by «Propuestos»', async () => {
    installFakeWebSocket()
    createFakeBackend({ knowledge: [celery(), proposal()] })
    const user = userEvent.setup()
    renderApp('/conocimiento')

    const row = await screen.findByRole('button', { name: 'Abrir Guía de reintentos' })
    expect(within(row).getByText(k.origin.proposed)).toBeVisible()
    expect(within(row).getByText(/Propuesto por Redactor/)).toBeVisible()
    expect(within(row).getByText(/Derivado de Manual de Celery/)).toBeVisible()
    // A proposal has no processing state: it waits for a person.
    expect(within(row).queryByText(k.status.ready)).not.toBeInTheDocument()

    const filters = screen.getByRole('group', { name: k.filters.label })
    await user.click(within(filters).getByRole('button', { name: /Propuestos \(1\)/ }))
    expect(screen.getByRole('button', { name: 'Abrir Guía de reintentos' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Abrir Manual de Celery' })).not.toBeInTheDocument()
  })

  it('has no filters until an agent has contributed', async () => {
    installFakeWebSocket()
    createFakeBackend({ knowledge: [celery()] })
    renderApp('/conocimiento')
    await screen.findByRole('button', { name: 'Abrir Manual de Celery' })
    expect(screen.queryByRole('group', { name: k.filters.label })).not.toBeInTheDocument()
  })

  it('marks accepted documents «Generado por agente» and shows their provenance', async () => {
    installFakeWebSocket()
    const accepted = proposal({
      review: 'none',
      provenance: provenance({
        decided_at: new Date().toISOString(),
        edited: true,
        task_title: 'Documentar Celery',
      }),
      sources: [
        { id: 'pdf', title: 'Manual de Celery', removed: false },
        { id: null, title: 'Guía antigua', removed: true },
      ],
    })
    createFakeBackend({ knowledge: [celery(), accepted], markdowns: { [accepted.id]: GUIDE } })
    const user = userEvent.setup()
    renderApp('/conocimiento')

    const row = await screen.findByRole('button', { name: 'Abrir Guía de reintentos' })
    expect(within(row).getByText(k.origin.agent)).toBeVisible()
    await user.click(row)

    const sheet = await screen.findByRole('dialog')
    expect(await within(sheet).findByText(k.provenance.title)).toBeVisible()
    expect(within(sheet).getByText('Redactor')).toBeVisible()
    expect(within(sheet).getByText('Documentar Celery')).toBeVisible()
    expect(within(sheet).getByText(new RegExp(k.provenance.edited))).toBeVisible()
    expect(within(sheet).getByRole('button', { name: 'Manual de Celery' })).toBeVisible()
    expect(within(sheet).getByText('Guía antigua')).toBeVisible()
    expect(within(sheet).getByText(new RegExp(p.sourceRemoved))).toBeVisible()
    // The Markdown stays clean: the provenance is not part of it.
    expect(await within(sheet).findByText(/Usa autoretry_for/)).toBeVisible()
  })

  it('opens the document a derived one was built on', async () => {
    installFakeWebSocket()
    const accepted = proposal({ review: 'none' })
    createFakeBackend({ knowledge: [celery(), accepted], markdowns: { pdf: '# Manual' } })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('button', { name: 'Abrir Guía de reintentos' }))
    const sheet = await screen.findByRole('dialog')
    await user.click(await within(sheet).findByRole('button', { name: 'Manual de Celery' }))
    expect(await screen.findByRole('heading', { name: 'Manual de Celery' })).toBeVisible()
  })
})

describe('Reviewing a proposal', () => {
  async function open(proposalDoc = proposal(), extra: KnowledgeDoc[] = []) {
    installFakeWebSocket()
    const backend = createFakeBackend({
      knowledge: [celery(), proposalDoc, ...extra],
      markdowns: { [proposalDoc.id]: GUIDE },
      projects: [makeProject({ id: 'p1', name: 'Blog' })],
      agents: [makeAgent({ id: 'a1', name: 'Redactor' })],
    })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('button', { name: 'Abrir Guía de reintentos' }))
    const sheet = await screen.findByRole('dialog')
    await within(sheet).findByLabelText(p.titleLabel)
    return { backend, user, sheet }
  }

  it('shows who proposed it, what it is based on and its text', async () => {
    const { sheet } = await open()
    expect(within(sheet).getByText(p.title)).toBeVisible()
    expect(within(sheet).getByText(/Redactor propone este documento/)).toBeVisible()
    expect(within(sheet).getByText(/Documentar Celery/)).toBeVisible()
    expect(within(sheet).getByRole('button', { name: 'Manual de Celery' })).toBeVisible()
    expect(within(sheet).getByLabelText(p.titleLabel)).toHaveValue('Guía de reintentos')
    expect(within(sheet).getByLabelText(p.textLabel)).toHaveValue(GUIDE)
    expect(within(sheet).getByText(/El agente sugiere: General/)).toBeVisible()
  })

  it('accepts it as it is', async () => {
    const { backend, user, sheet } = await open()
    await user.click(within(sheet).getByRole('button', { name: p.accept }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/accept')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/accept')[0].body).toMatchObject({
      title: 'Guía de reintentos',
      markdown: GUIDE,
      scope: 'general',
      replace: false,
    })
    expect(await screen.findByText(p.accepted)).toBeVisible()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('accepts it with the title, the text and the level the person chose', async () => {
    const { backend, user, sheet } = await open()
    const title = within(sheet).getByLabelText(p.titleLabel)
    await user.clear(title)
    await user.type(title, 'Reintentos en Celery')
    const text = within(sheet).getByLabelText(p.textLabel)
    await user.clear(text)
    await user.type(text, 'Texto corregido')
    await user.click(within(sheet).getByRole('combobox', { name: p.level }))
    await user.click(await screen.findByRole('option', { name: p.scope.project }))
    // A project level needs a project: accepting is not possible until one is chosen.
    expect(within(sheet).getByRole('button', { name: p.accept })).toBeDisabled()
    expect(within(sheet).getByRole('alert')).toHaveTextContent(p.missingOwner)
    await user.click(within(sheet).getByRole('combobox', { name: p.project }))
    await user.click(await screen.findByRole('option', { name: 'Blog' }))
    await user.click(within(sheet).getByRole('button', { name: p.accept }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/accept')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/accept')[0].body).toEqual({
      title: 'Reintentos en Celery',
      description: 'Cómo reintentar tareas',
      markdown: 'Texto corregido',
      scope: 'project',
      project_id: 'p1',
      agent_id: null,
      replace: false,
    })
  })

  it('cannot be accepted with an empty text', async () => {
    const { user, sheet } = await open()
    await user.clear(within(sheet).getByLabelText(p.textLabel))
    expect(within(sheet).getByRole('button', { name: p.accept })).toBeDisabled()
  })

  it('rejects it, with a reason for the agent', async () => {
    const { backend, user, sheet } = await open()
    await user.click(within(sheet).getByRole('button', { name: p.reject }))
    const dialog = await screen.findByRole('alertdialog')
    await user.type(within(dialog).getByLabelText(p.reason), 'Ya lo sabemos')
    await user.click(within(dialog).getByRole('button', { name: p.reject }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/reject')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/reject')[0].body).toEqual({
      reason: 'Ya lo sabemos',
    })
    expect(await screen.findByText(p.rejected)).toBeVisible()
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Abrir Guía de reintentos' })).toBeNull(),
    )
  })

  it('offers to replace the version it improves on, and the two live together otherwise', async () => {
    const old = proposal({
      id: 'old-1',
      title: 'Guía de reintentos v1',
      review: 'none',
      provenance: provenance({ decided_at: new Date().toISOString() }),
    })
    const next = proposal({
      id: 'prop-1',
      title: 'Guía de reintentos',
      provenance: provenance({ replaces_id: 'old-1' }),
      sources: [{ id: 'old-1', title: 'Guía de reintentos v1', removed: false }],
    })
    const { backend, user, sheet } = await open(next, [old])
    expect(
      await within(sheet).findByText(/Es una versión nueva de «Guía de reintentos v1»/),
    ).toBeVisible()
    expect(within(sheet).getByText(p.replaceHelp)).toBeVisible()
    await user.click(within(sheet).getByRole('switch', { name: p.replaceOption }))
    await user.click(within(sheet).getByRole('button', { name: p.accept }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/accept')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/accept')[0].body).toMatchObject({
      replace: true,
    })
  })
})

describe('Proposals in the Inbox', () => {
  it('lists the request and opens the same review', async () => {
    installFakeWebSocket()
    const doc = proposal()
    const item = makeInboxItem({
      kind: 'knowledge',
      title: 'Conocimiento propuesto: Guía de reintentos',
      detail: 'Basado en Manual de Celery.',
      agent_name: 'Redactor',
      knowledge_doc_id: doc.id,
      notified_at: '2026-10-11T10:00:00Z',
    })
    const backend = createFakeBackend({
      knowledge: [celery(), doc],
      markdowns: { [doc.id]: GUIDE },
      inbox: [item],
    })
    const user = userEvent.setup()
    renderApp('/inbox')
    const card = await screen.findByRole('article', {
      name: `${es.inbox.kinds.knowledge}: Conocimiento propuesto: Guía de reintentos`,
    })
    await user.click(within(card).getByRole('button', { name: es.inbox.reviewProposal }))
    const sheet = await screen.findByRole('dialog')
    expect(await within(sheet).findByLabelText(p.titleLabel)).toHaveValue('Guía de reintentos')
    await user.click(within(sheet).getByRole('button', { name: p.accept }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/knowledge/docs/prop-1/accept')).toHaveLength(1),
    )
  })
})

describe('Settings for proposals and the graph', () => {
  it('saves the switch and the limits', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const proposals = await screen.findByRole('switch', { name: es.settings.knowledge.proposals })
    expect(proposals).toBeChecked()
    const perRun = screen.getByLabelText(es.settings.knowledge.fields.proposals_per_run)
    await user.clear(perRun)
    await user.type(perRun, '2')
    const threshold = screen.getByLabelText(es.settings.knowledge.fields.graph_threshold)
    await user.clear(threshold)
    await user.type(threshold, '0.3')
    await user.click(
      within(document.getElementById('knowledge')!).getByRole('button', { name: es.common.save }),
    )
    await waitFor(() => expect(backend.callsTo('PUT', '/api/settings/knowledge')).toHaveLength(1))
    expect(backend.callsTo('PUT', '/api/settings/knowledge')[0].body).toMatchObject({
      proposals_enabled: true,
      proposals_per_run: 2,
      graph_threshold: 0.3,
    })
  })

  it('hides the proposal limits while proposals are off', async () => {
    installFakeWebSocket()
    createFakeBackend({ knowledgeSettings: { proposals_enabled: false } })
    renderApp('/ajustes')
    await screen.findByRole('switch', { name: es.settings.knowledge.proposals })
    expect(
      screen.queryByLabelText(es.settings.knowledge.fields.proposals_per_run),
    ).not.toBeInTheDocument()
  })

  it('refuses a threshold outside its range', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const threshold = await screen.findByLabelText(es.settings.knowledge.fields.graph_threshold)
    await user.clear(threshold)
    await user.type(threshold, '5')
    await user.click(
      within(document.getElementById('knowledge')!).getByRole('button', { name: es.common.save }),
    )
    expect(await screen.findByText('Entre 0.05 y 0.9')).toBeVisible()
    expect(backend.callsTo('PUT', '/api/settings/knowledge')).toHaveLength(0)
  })
})

describe('The «Propuestos» filter', () => {
  it('stops filtering when the last proposal has been decided', async () => {
    installFakeWebSocket()
    createFakeBackend({
      knowledge: [celery(), proposal()],
      markdowns: { 'prop-1': GUIDE },
    })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    const filters = await screen.findByRole('group', { name: k.filters.label })
    await user.click(within(filters).getByRole('button', { name: /Propuestos \(1\)/ }))
    await user.click(await screen.findByRole('button', { name: 'Abrir Guía de reintentos' }))
    const sheet = await screen.findByRole('dialog')
    await user.click(await within(sheet).findByRole('button', { name: p.reject }))
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: p.reject }),
    )
    // Nothing is left to filter by: the whole library is back, not an empty list.
    expect(await screen.findByRole('button', { name: 'Abrir Manual de Celery' })).toBeVisible()
  })
})
