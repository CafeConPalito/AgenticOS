import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import es from '@/i18n/es.json'
import { createFakeBackend, makeLocalModel } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

const s = es.settings.knowledge
const m = es.localModels

/** The models section once its list has loaded (it first shows a skeleton). */
async function loadedSection() {
  const section = await screen.findByRole('region', { name: m.title })
  await waitFor(() => expect(within(section).queryByRole('generic', { busy: true })).toBeNull())
  await within(section).findByText(/libres en el disco/)
  return section
}

describe('Settings · Conocimiento', () => {
  it('shows the data folder split into library and models', async () => {
    installFakeWebSocket()
    createFakeBackend()
    renderApp('/ajustes')
    expect(await screen.findByText(/biblioteca 40 MB · modelos 118 MB/)).toBeVisible()
  })

  it('reads the settings and saves a change', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const budget = await screen.findByLabelText(s.fields.context_budget)
    expect(budget).toHaveValue(8000)
    await user.clear(budget)
    await user.type(budget, '12000')
    await user.click(screen.getAllByRole('button', { name: es.common.save })[0])
    await waitFor(() => expect(backend.callsTo('PUT', '/api/settings/knowledge')).toHaveLength(1))
    expect(backend.callsTo('PUT', '/api/settings/knowledge')[0].body).toMatchObject({
      context_budget: 12000,
      small_doc_tokens: 2000,
    })
  })

  it('refuses a value out of range without sending it', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const concurrency = await screen.findByLabelText(s.fields.concurrency)
    await user.clear(concurrency)
    await user.type(concurrency, '9')
    await user.click(screen.getAllByRole('button', { name: es.common.save })[0])
    expect(await screen.findByText('Entre 1 y 4')).toBeVisible()
    expect(backend.callsTo('PUT', '/api/settings/knowledge')).toHaveLength(0)
  })

  it('describing pictures is optional: it shows its options only when on', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend()
    const user = userEvent.setup()
    renderApp('/ajustes')
    const toggle = await screen.findByRole('switch', { name: s.describe })
    expect(toggle).not.toBeChecked()
    expect(screen.queryByLabelText(s.describer)).not.toBeInTheDocument()
    await user.click(toggle)
    expect(await screen.findByLabelText(s.model)).toBeVisible()
    await user.click(screen.getByRole('combobox', { name: s.describer }))
    await user.click(await screen.findByRole('option', { name: s.describers.local }))
    expect(await screen.findByText(s.localHelp)).toBeVisible()
    await user.click(screen.getAllByRole('button', { name: es.common.save })[0])
    await waitFor(() => expect(backend.callsTo('PUT', '/api/settings/knowledge')).toHaveLength(1))
    expect(backend.callsTo('PUT', '/api/settings/knowledge')[0].body).toMatchObject({
      describe_images: true,
      describer: 'local',
    })
  })
})

describe('Settings · Modelos locales', () => {
  const catalogue = () => [
    makeLocalModel(),
    makeLocalModel({
      id: 'bge-m3',
      title: 'bge-m3',
      default: false,
      selected: false,
      state: 'absent',
      done: 0,
      size: 600_000_000,
    }),
    makeLocalModel({
      id: 'ocr-latin',
      kind: 'ocr',
      title: 'RapidOCR',
      bundled: true,
      size: 18_000_000,
    }),
    makeLocalModel({
      id: 'gemma-4-e2b',
      kind: 'vision',
      title: 'Gemma 4 E2B',
      default: true,
      selected: false,
      state: 'downloading',
      done: 500_000_000,
      total: 2_000_000_000,
      size: 2_000_000_000,
      needs_account: true,
    }),
    makeLocalModel({
      id: 'llama-cpp',
      kind: 'engine',
      title: 'llama.cpp b11720 (CPU)',
      default: false,
      selected: false,
      state: 'error',
      error_code: 'network',
    }),
  ]

  it('lists the models by job with their state', async () => {
    installFakeWebSocket()
    createFakeBackend({ localModels: catalogue() })
    renderApp('/ajustes')
    const section = await loadedSection()
    expect(within(section).getByText(m.kinds.embedding.title)).toBeVisible()
    expect(within(section).getByText(m.kinds.engine.title)).toBeVisible()
    // The embedding model and the OCR are the ones in use.
    expect(within(section).getAllByText(m.inUse)).toHaveLength(2)
    expect(within(section).getByText(m.bundled)).toBeVisible()
    // A bundled model cannot be removed.
    expect(
      within(section).queryByRole('button', { name: 'Borrar RapidOCR' }),
    ).not.toBeInTheDocument()
    const bar = within(section).getByRole('progressbar', { name: 'Descarga de Gemma 4 E2B' })
    expect(bar).toHaveAttribute('aria-valuenow', '25')
    expect(within(section).getByText(m.errors.network)).toBeVisible()
    expect(within(section).getByText(/libres en el disco/)).toBeVisible()
  })

  it('downloads, cancels and removes after confirming', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ localModels: catalogue() })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const section = await loadedSection()

    await user.click(within(section).getByRole('button', { name: 'Descargar bge-m3' }))
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/local-models/bge-m3/download')).toHaveLength(1),
    )
    await user.click(
      await within(section).findByRole('button', { name: 'Cancelar la descarga de bge-m3' }),
    )
    await waitFor(() =>
      expect(backend.callsTo('POST', '/api/local-models/bge-m3/cancel')).toHaveLength(1),
    )

    await user.click(within(section).getByRole('button', { name: 'Borrar multilingual-e5-small' }))
    const confirm = await screen.findByRole('alertdialog')
    expect(backend.callsTo('DELETE', '/api/local-models/e5-small')).toHaveLength(0)
    await user.click(within(confirm).getByRole('button', { name: m.removeShort }))
    await waitFor(() =>
      expect(backend.callsTo('DELETE', '/api/local-models/e5-small')).toHaveLength(1),
    )
  })

  it('chooses another downloaded model for a job', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({
      localModels: [
        makeLocalModel(),
        makeLocalModel({ id: 'bge-m3', title: 'bge-m3', default: false, selected: false }),
      ],
    })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const section = await loadedSection()
    await user.click(within(section).getByRole('button', { name: 'Usar bge-m3' }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/local-models')[0]?.body).toEqual({
        embedding: 'bge-m3',
      }),
    )
    expect(await screen.findByText(m.reindexing)).toBeVisible()
  })

  it('asks for the Hugging Face token only when a model needs an account', async () => {
    installFakeWebSocket()
    const backend = createFakeBackend({ localModels: catalogue() })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const section = await loadedSection()
    await user.type(within(section).getByLabelText(m.token.label), 'hf_secreto')
    await user.click(within(section).getByRole('button', { name: m.token.save }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/huggingface-token')[0]?.body).toEqual({
        token: 'hf_secreto',
      }),
    )
    expect(await within(section).findByText(/Token configurado/)).toBeVisible()
  })

  it('has no token field when every model is already downloaded', async () => {
    installFakeWebSocket()
    createFakeBackend({ localModels: [makeLocalModel()] })
    renderApp('/ajustes')
    const section = await loadedSection()
    await within(section).findByText(m.inUse)
    expect(within(section).queryByLabelText(m.token.label)).not.toBeInTheDocument()
  })
})
