import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import es from '@/i18n/es.json'
import { resetDictation } from '@/lib/dictation/controller'
import { useDictation } from '@/stores/dictation'
import { createFakeBackend, makeLocalModel } from '@/test/fake-backend'
import { renderApp } from '@/test/render'

const D = es.dictation.download

const whisper = (overrides = {}) =>
  makeLocalModel({
    id: 'whisper-small',
    kind: 'speech',
    title: 'Whisper small',
    size: 190_000_000,
    done: 0,
    total: 190_000_000,
    state: 'absent',
    selected: false,
    ...overrides,
  })
const engine = (overrides = {}) =>
  makeLocalModel({
    id: 'whisper-cpp',
    kind: 'engine',
    title: 'whisper.cpp b5454 (CPU)',
    default: false,
    selected: false,
    size: 9_000_000,
    done: 0,
    total: 9_000_000,
    state: 'absent',
    ...overrides,
  })

beforeEach(() => resetDictation())

async function openDialog() {
  renderApp('/')
  await screen.findAllByRole('main')
  act(() => useDictation.getState().setDownloadOpen(true))
  return screen.findByRole('dialog', { name: D.title })
}

describe('downloading a speech model from the microphone', () => {
  it('offers the recommended engine and model with their total size and downloads both', async () => {
    const backend = createFakeBackend({
      dictation: { status: { ready: false, reason: 'engine_missing' } },
      localModels: [whisper(), engine()],
    })
    const user = userEvent.setup()
    const dialog = await openDialog()
    expect(within(dialog).getByText('Whisper small')).toBeVisible()
    expect(within(dialog).getByText('whisper.cpp b5454 (CPU)')).toBeVisible()
    expect(within(dialog).getByText(/Descarga total: 190 MB|Descarga total: 199 MB/)).toBeVisible()
    await user.click(within(dialog).getByRole('button', { name: D.start }))
    await waitFor(() => {
      expect(backend.callsTo('POST', '/api/local-models/whisper-cpp/download')).toHaveLength(1)
      expect(backend.callsTo('POST', '/api/local-models/whisper-small/download')).toHaveLength(1)
    })
    const bars = await within(dialog).findAllByRole('progressbar')
    expect(bars).toHaveLength(2)
    expect(within(dialog).getByRole('button', { name: D.downloading })).toBeDisabled()
  })

  it('starts using the model as soon as everything is downloaded, and closes', async () => {
    const backend = createFakeBackend({
      dictation: { status: { ready: false, reason: 'no_model' } },
      localModels: [whisper({ state: 'ready', done: 190_000_000 }), engine({ state: 'ready' })],
    })
    await openDialog()
    await waitFor(() => expect(useDictation.getState().downloadOpen).toBe(false))
    expect(backend.callsTo('PUT', '/api/settings/local-models')[0].body).toEqual({
      speech: 'whisper-small',
    })
  })

  it('"Elegir otro modelo" goes to the models in the settings', async () => {
    createFakeBackend({
      dictation: { status: { ready: false, reason: 'no_model' } },
      localModels: [whisper(), engine()],
    })
    const user = userEvent.setup()
    const dialog = await openDialog()
    await user.click(within(dialog).getByRole('button', { name: D.another }))
    await waitFor(() => expect(useDictation.getState().downloadOpen).toBe(false))
    expect(await screen.findByRole('region', { name: es.localModels.title })).toBeInTheDocument()
  })
})
