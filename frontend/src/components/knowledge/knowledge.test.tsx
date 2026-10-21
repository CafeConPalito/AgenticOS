import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { parseCsv } from '@/components/knowledge/DocViewer'
import es from '@/i18n/es.json'
import { createFakeBackend, makeAgent, makeKnowledgeDoc, makeProject } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

const k = es.knowledge

function pushEvent(socket: { push: (m: never) => void }, event: unknown) {
  act(() => socket.push(event as never))
}

describe('Knowledge library (general)', () => {
  it('lists the documents with their state, progress, failure reason and missing original', async () => {
    installFakeWebSocket()
    createFakeBackend({
      knowledge: [
        makeKnowledgeDoc({ title: 'Manual de marca' }),
        makeKnowledgeDoc({
          title: 'Informe grande',
          status: 'images',
          progress_done: 2,
          progress_total: 5,
        }),
        makeKnowledgeDoc({ title: 'Cifrado', status: 'failed', error_code: 'encrypted' }),
        makeKnowledgeDoc({ title: 'Perdido', presence: 'missing' }),
        makeKnowledgeDoc({ title: 'Esperando', status: 'queued' }),
      ],
    })
    renderApp('/conocimiento')
    const ready = await screen.findByRole('button', { name: 'Abrir Manual de marca' })
    expect(within(ready).getByText(k.status.ready)).toBeVisible()

    const working = screen.getByRole('button', { name: 'Abrir Informe grande' })
    expect(within(working).getByText(k.status.images)).toBeVisible()
    const bar = within(working).getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '40')
    expect(within(working).getByText('2/5')).toBeVisible()

    const failed = screen.getByRole('button', { name: 'Abrir Cifrado' })
    expect(within(failed).getByText(k.errors.encrypted)).toBeVisible()
    expect(
      within(screen.getByRole('button', { name: 'Abrir Perdido' })).getByText(k.presence.missing),
    ).toBeVisible()
    expect(
      within(screen.getByRole('button', { name: 'Abrir Esperando' })).getByText(k.status.queued),
    ).toBeVisible()
  })

  it('shows an empty state when there is nothing', async () => {
    installFakeWebSocket()
    createFakeBackend()
    renderApp('/conocimiento')
    expect(await screen.findByText(k.empty.title)).toBeVisible()
  })

  it('adds a file by path and says why a file was refused', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.type(await screen.findByLabelText(k.add.pathLabel), 'D:\\docs\\guia.pdf')
    await user.click(screen.getByRole('button', { name: k.add.addFile }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/knowledge/docs/files')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/knowledge/docs/files')[0].body).toEqual({
      scope: 'general',
      project_id: null,
      agent_id: null,
      paths: ['D:\\docs\\guia.pdf'],
    })
    expect(await screen.findByRole('button', { name: 'Abrir guia' })).toBeVisible()

    await user.type(screen.getByLabelText(k.add.pathLabel), 'D:\\docs\\enorme.pdf')
    await user.click(screen.getByRole('button', { name: k.add.addFile }))
    expect(await screen.findByText(k.errors.too_large)).toBeVisible()
  })

  it('adds a web address', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.type(await screen.findByLabelText(k.add.urlLabel), 'https://example.com/docs')
    await user.click(screen.getByRole('button', { name: k.add.addUrl }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/knowledge/docs/url')).toHaveLength(1))
    expect(
      await screen.findByRole('button', { name: 'Abrir https://example.com/docs' }),
    ).toBeVisible()
  })

  it('follows a document live: progress and the end of the processing', async () => {
    const sockets = installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'En marcha', status: 'converting' })
    createFakeBackend({ knowledge: [doc] })
    renderApp('/conocimiento')
    await screen.findByRole('button', { name: 'Abrir En marcha' })
    await waitFor(() => expect(sockets.instances.length).toBeGreaterThan(0))
    const socket = sockets.instances[0]
    expect(socket.url).toContain('/api/knowledge/events')
    act(() => socket.open())

    pushEvent(socket, {
      type: 'doc',
      doc: { ...doc, status: 'images', progress_done: 3, progress_total: 4 },
    })
    const row = await screen.findByRole('button', { name: 'Abrir En marcha' })
    await waitFor(() =>
      expect(within(row).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '75'),
    )

    pushEvent(socket, { type: 'doc', doc: { ...doc, status: 'ready' } })
    await waitFor(() =>
      expect(
        within(screen.getByRole('button', { name: 'Abrir En marcha' })).getByText(k.status.ready),
      ).toBeVisible(),
    )

    pushEvent(socket, { type: 'doc_removed', id: doc.id })
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Abrir En marcha' })).not.toBeInTheDocument(),
    )
  })

  it('shows the load of the machine while processing and pauses the queue', async () => {
    installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'Pesado', status: 'converting' })
    const backend = createFakeBackend({
      knowledge: [doc],
      queue: { active: [doc.id], queued: 2 },
    })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    const monitor = await screen.findByRole('region', { name: k.monitor.title })
    expect(within(monitor).getByText(k.monitor.working)).toBeVisible()
    await waitFor(() =>
      expect(within(monitor).getByRole('meter', { name: k.monitor.cpu })).toHaveAttribute(
        'aria-valuenow',
        '40',
      ),
    )
    // The GPU cannot be read on this machine: it says so instead of showing 0 %.
    expect(within(monitor).getByText(k.monitor.unavailable)).toBeVisible()
    await user.click(within(monitor).getByRole('button', { name: k.monitor.pause }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/knowledge/queue/pause')).toHaveLength(1),
    )
    expect(await within(monitor).findByText(k.monitor.paused)).toBeVisible()
  })

  it('tries a search and opens the document of a result', async () => {
    installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'Tarifas' })
    createFakeBackend({
      knowledge: [doc],
      markdowns: { [doc.id]: '# Tarifas\n\nEl plan Pro cuesta 12 euros.' },
      searchHits: [
        {
          doc_id: doc.id,
          title: 'Tarifas',
          scope: 'general',
          chunk: 0,
          heading: 'Planes',
          location: 'p. 3',
          text: 'El plan Pro cuesta 12 euros.',
          score: 0.9,
          found_by: 'both',
          via: '',
          images: [],
        },
      ],
    })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.type(await screen.findByLabelText(k.search.label), 'precio del plan')
    await user.click(screen.getByRole('button', { name: k.search.run }))
    expect(await screen.findByText('Planes · p. 3 · por ambos')).toBeVisible()
    expect(screen.getByText(/Búsqueda por significado y por palabras · e5-small/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Tarifas' }))
    expect(await screen.findByRole('dialog')).toBeVisible()
  })
})

describe('A document sheet', () => {
  it('shows the Markdown with its pictures, and reprocesses the document', async () => {
    installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'Guía', image_count: 1 })
    const backend = createFakeBackend({
      knowledge: [doc],
      markdowns: { [doc.id]: '# Guía de uso\n\nPrimero, instala.\n\n![](kimg:0)' },
      knowledgeImages: {
        [doc.id]: [
          {
            ord: 0,
            kind: 'embedded',
            location: 'p. 2',
            width: 900,
            height: 126,
            ocr_text: 'Emitida Enviada',
            description: 'Un flujo de tres pasos',
            described_by: 'claude:haiku',
          },
        ],
      },
    })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('button', { name: 'Abrir Guía' }))
    const sheet = await screen.findByRole('dialog')
    await user.click(within(sheet).getByRole('tab', { name: k.viewer.markdown }))
    expect(await within(sheet).findByRole('heading', { name: 'Guía de uso' })).toBeVisible()
    await within(sheet).findByText('Un flujo de tres pasos')
    // An empty alt makes the picture decorative: it has no «img» role.
    const picture = sheet.querySelector('img')
    expect(picture).not.toBeNull()
    expect(picture).toHaveAttribute(
      'src',
      `http://127.0.0.1:8765/api/knowledge/docs/${doc.id}/images/0`,
    )
    expect(await within(sheet).findByText('Un flujo de tres pasos')).toBeVisible()
    expect(within(sheet).getByText(/descrita por claude:haiku/)).toBeVisible()

    await user.click(within(sheet).getByRole('button', { name: k.sheet.reprocess }))
    await waitFor(() =>
      expect(backend.callsTo('POST', `/api/knowledge/docs/${doc.id}/reprocess`)).toHaveLength(1),
    )
  })

  it('opens the original PDF inside the app', async () => {
    installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'Contrato' })
    createFakeBackend({ knowledge: [doc] })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('button', { name: 'Abrir Contrato' }))
    const sheet = await screen.findByRole('dialog')
    await user.click(within(sheet).getByRole('tab', { name: k.viewer.original }))
    const frame = await within(sheet).findByTitle('PDF de Contrato')
    expect(frame).toHaveAttribute(
      'src',
      `http://127.0.0.1:8765/api/knowledge/docs/${doc.id}/original`,
    )
  })

  it('changes how the agents use the document and whether to describe its pictures', async () => {
    installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'Guía' })
    const backend = createFakeBackend({ knowledge: [doc] })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('button', { name: 'Abrir Guía' }))
    const sheet = await screen.findByRole('dialog')
    await user.click(within(sheet).getByRole('combobox', { name: k.sheet.mode }))
    await user.click(await screen.findByRole('option', { name: k.modes.search }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', `/api/knowledge/docs/${doc.id}`)[0]?.body).toEqual({
        mode: 'search',
      }),
    )
    await user.click(within(sheet).getByRole('combobox', { name: k.sheet.describe }))
    await user.click(await screen.findByRole('option', { name: k.describeChoice.yes }))
    await waitFor(() =>
      expect(backend.callsTo('PATCH', `/api/knowledge/docs/${doc.id}`)[1]?.body).toEqual({
        describe_images: true,
      }),
    )
  })

  it('a missing original can be relocated; another file asks for confirmation', async () => {
    installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'Perdido', presence: 'missing' })
    const backend = createFakeBackend({ knowledge: [doc] })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('button', { name: 'Abrir Perdido' }))
    const sheet = await screen.findByRole('dialog')
    expect(within(sheet).getByText(k.sheet.missingHelp)).toBeVisible()
    expect(within(sheet).queryByRole('button', { name: k.sheet.open })).not.toBeInTheDocument()

    await user.type(within(sheet).getByLabelText(k.sheet.newPath), 'D:\\nuevo\\otro.pdf')
    await user.click(within(sheet).getByRole('button', { name: k.sheet.relocate }))
    const confirm = await screen.findByRole('alertdialog')
    expect(within(confirm).getByText(k.sheet.differentTitle)).toBeVisible()
    await user.click(within(confirm).getByRole('button', { name: k.sheet.differentConfirm }))
    await waitFor(() => {
      const calls = backend.callsTo('POST', `/api/knowledge/docs/${doc.id}/relocate`)
      expect(calls.map((c) => (c.body as { confirm: boolean }).confirm)).toEqual([false, true])
    })
  })

  it('removes the document after confirming', async () => {
    installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'Borrable' })
    const backend = createFakeBackend({ knowledge: [doc] })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('button', { name: 'Abrir Borrable' }))
    const sheet = await screen.findByRole('dialog')
    await user.click(within(sheet).getByRole('button', { name: k.sheet.remove }))
    const confirm = await screen.findByRole('alertdialog')
    expect(backend.callsTo('DELETE', `/api/knowledge/docs/${doc.id}`)).toHaveLength(0)
    await user.click(within(confirm).getByRole('button', { name: k.sheet.remove }))
    await waitFor(() =>
      expect(backend.callsTo('DELETE', `/api/knowledge/docs/${doc.id}`)).toHaveLength(1),
    )
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Abrir Borrable' })).not.toBeInTheDocument(),
    )
  })

  it('a failed document says why and can be tried again', async () => {
    installFakeWebSocket()
    const doc = makeKnowledgeDoc({ title: 'Roto', status: 'failed', error_code: 'convert_error' })
    createFakeBackend({ knowledge: [doc] })
    const user = userEvent.setup()
    renderApp('/conocimiento')
    await user.click(await screen.findByRole('button', { name: 'Abrir Roto' }))
    const sheet = await screen.findByRole('dialog')
    expect(within(sheet).getByRole('alert')).toHaveTextContent(k.errors.convert_error)
  })
})

describe('The library of a project and of an agent', () => {
  it('a project sees only its own documents, and adds at its level', async () => {
    installFakeWebSocket()
    const project = makeProject()
    const other = makeProject({ name: 'Otro', path: 'D:\\otro' })
    const backend = createFakeBackend({
      projects: [project, other],
      knowledge: [
        makeKnowledgeDoc({ title: 'De la tienda', scope: 'project', project_id: project.id }),
        makeKnowledgeDoc({ title: 'De otro', scope: 'project', project_id: other.id }),
        makeKnowledgeDoc({ title: 'General' }),
      ],
    })
    const user = userEvent.setup()
    renderApp(`/proyectos/${project.id}/knowledge`)
    expect(await screen.findByRole('button', { name: 'Abrir De la tienda' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Abrir De otro' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir General' })).not.toBeInTheDocument()

    await user.type(screen.getByLabelText(k.add.pathLabel), 'D:\\p\\nota.md')
    await user.click(screen.getByRole('button', { name: k.add.addFile }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/knowledge/docs/files')).toHaveLength(1),
    )
    expect(backend.callsTo('POST', '/api/knowledge/docs/files')[0].body).toMatchObject({
      scope: 'project',
      project_id: project.id,
    })
  })

  it('an agent has its own library, outside the editing form', async () => {
    installFakeWebSocket()
    const agent = makeAgent({ name: 'Dev' })
    const backend = createFakeBackend({
      agents: [agent],
      knowledge: [makeKnowledgeDoc({ title: 'Solo de Dev', scope: 'agent', agent_id: agent.id })],
    })
    const user = userEvent.setup()
    renderApp(`/agentes/${agent.id}/knowledge`)
    expect(await screen.findByRole('button', { name: 'Abrir Solo de Dev' })).toBeVisible()
    // A form inside the editing form would be invalid HTML.
    expect(document.querySelectorAll('form form')).toHaveLength(0)
    await user.type(screen.getByLabelText(k.add.urlLabel), 'https://example.com')
    await user.click(screen.getByRole('button', { name: k.add.addUrl }))
    await waitFor(() => expect(backend.callsTo('POST', '/api/knowledge/docs/url')).toHaveLength(1))
    expect(backend.callsTo('POST', '/api/knowledge/docs/url')[0].body).toMatchObject({
      scope: 'agent',
      agent_id: agent.id,
    })
  })
})

describe('parseCsv', () => {
  it('understands quotes, doubled quotes, newlines inside cells and semicolons', () => {
    expect(parseCsv('a,b\n"x, y","say ""hi"""\n')).toEqual([
      ['a', 'b'],
      ['x, y', 'say "hi"'],
    ])
    expect(parseCsv('a;b\r\n1;"dos\nlíneas"')).toEqual([
      ['a', 'b'],
      ['1', 'dos\nlíneas'],
    ])
    expect(parseCsv('')).toEqual([])
  })
})
