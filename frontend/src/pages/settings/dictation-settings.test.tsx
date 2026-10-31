import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import es from '@/i18n/es.json'
import { resetDictation, setRecorder } from '@/lib/dictation/controller'
import { MicrophoneError } from '@/lib/dictation/recorder'
import { createFakeBackend, makeLocalModel } from '@/test/fake-backend'
import { installFakeWebSocket } from '@/test/fake-socket'
import { renderApp } from '@/test/render'

vi.mock('@/lib/notify', () => ({
  notify: vi.fn(async () => true),
  notificationPermission: async () => 'granted',
  askNotificationPermission: async () => 'granted',
}))

const d = es.settings.dictation

const whisper = (overrides = {}) =>
  makeLocalModel({
    id: 'whisper-small',
    kind: 'speech',
    title: 'Whisper small',
    size: 190_000_000,
    done: 190_000_000,
    total: 190_000_000,
    speed: 'medium',
    quality: 'good',
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
    ...overrides,
  })

async function section() {
  installFakeWebSocket()
  const found = await screen.findByRole('region', { name: d.title })
  await waitFor(() => expect(within(found).queryByRole('generic', { busy: true })).toBeNull())
  await within(found).findByLabelText(d.enabled)
  return found
}

beforeEach(() => {
  resetDictation()
  setRecorder({ start: vi.fn() })
})

describe('Ajustes › Dictado', () => {
  it('shows the settings and saves each change as it is made', async () => {
    const backend = createFakeBackend({ dictation: {}, localModels: [whisper(), engine()] })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const region = await section()
    expect(within(region).getByRole('status')).toHaveTextContent(d.status.ready)
    expect(within(region).getByText('Whisper small')).toBeVisible()

    await user.click(within(region).getByLabelText(d.enabled))
    await waitFor(() => expect(backend.callsTo('PUT', '/api/settings/dictation')).toHaveLength(1))
    expect(backend.callsTo('PUT', '/api/settings/dictation')[0].body).toEqual({ enabled: false })

    await user.click(within(region).getByRole('combobox', { name: d.language }))
    await user.click(await screen.findByRole('option', { name: d.languages.en }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/dictation').at(-1)?.body).toEqual({
        language: 'en',
      }),
    )
  })

  it('says what is missing when there is no model', async () => {
    createFakeBackend({
      dictation: { status: { ready: false, reason: 'no_model' } },
      localModels: [whisper({ state: 'absent', done: 0 }), engine()],
    })
    renderApp('/ajustes')
    const region = await section()
    expect(within(region).getByRole('status')).toHaveTextContent(d.status.no_model)
    expect(within(region).getByText(d.modelNone)).toBeVisible()
  })

  it('keeps the maximum duration within its limits', async () => {
    const backend = createFakeBackend({ dictation: {}, localModels: [] })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const region = await section()
    const field = within(region).getByLabelText(d.maxSeconds)
    await user.clear(field)
    await user.type(field, '5')
    await user.tab()
    expect(field).toHaveValue(300) // out of range: back to what it was
    expect(backend.callsTo('PUT', '/api/settings/dictation')).toHaveLength(0)
    await user.clear(field)
    await user.type(field, '120')
    await user.tab()
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/dictation')[0].body).toEqual({
        max_seconds: 120,
      }),
    )
  })

  it('adds and removes terms of the vocabulary, without repeats', async () => {
    const backend = createFakeBackend({
      dictation: { settings: { vocabulary: ['Kestrel'] } },
      localModels: [],
    })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const region = await section()
    const field = within(region).getByPlaceholderText(d.vocabularyPlaceholder)
    await user.type(field, 'Zafiro{Enter}')
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/dictation').at(-1)?.body).toEqual({
        vocabulary: ['Kestrel', 'Zafiro'],
      }),
    )
    await user.type(field, 'kestrel{Enter}') // already there, whatever the case
    expect(backend.callsTo('PUT', '/api/settings/dictation')).toHaveLength(1)
    await user.click(within(region).getByRole('button', { name: `Quitar Kestrel` }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/dictation').at(-1)?.body).toEqual({
        vocabulary: ['Zafiro'],
      }),
    )
  })

  it('changes the shortcut by pressing it, and refuses one that would type', async () => {
    const backend = createFakeBackend({ dictation: {}, localModels: [] })
    const user = userEvent.setup()
    renderApp('/ajustes')
    const region = await section()
    await user.click(within(region).getByRole('button', { name: d.shortcutChange }))
    expect(within(region).getByText(d.shortcutListening)).toBeVisible()
    fireEvent.keyDown(window, { code: 'KeyA', key: 'a' })
    expect(await within(region).findByRole('alert')).toHaveTextContent(d.shortcutInvalid)
    fireEvent.keyDown(window, { code: 'KeyA', key: 'A', shiftKey: true }) // would type a capital
    fireEvent.keyDown(window, { code: 'KeyK', key: 'k', ctrlKey: true, altKey: true }) // AltGr
    expect(backend.callsTo('PUT', '/api/settings/dictation')).toHaveLength(0)
    fireEvent.keyDown(window, { code: 'KeyD', key: 'd', ctrlKey: true, shiftKey: true })
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/dictation')[0].body).toEqual({
        shortcut: 'Ctrl+Shift+D',
      }),
    )
    // It can go back to the default one.
    await user.click(await within(region).findByRole('button', { name: d.shortcutReset }))
    await waitFor(() =>
      expect(backend.callsTo('PUT', '/api/settings/dictation').at(-1)?.body).toEqual({
        shortcut: 'Ctrl+Space',
      }),
    )
  })

  it('tests the microphone and says whether it heard anything', async () => {
    createFakeBackend({ dictation: {}, localModels: [] })
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      setRecorder({
        start: vi.fn(async ({ onLevel }: { onLevel: (level: number) => void }) => {
          onLevel(0.4)
          return { stop: async () => new Blob(), cancel: vi.fn() }
        }),
      })
      renderApp('/ajustes')
      const region = await section()
      fireEvent.click(within(region).getByRole('button', { name: d.microphoneTest }))
      expect(await within(region).findByRole('meter')).toHaveAttribute('aria-valuenow', '40')
      await vi.advanceTimersByTimeAsync(3500)
      expect(await within(region).findByText(d.microphoneOk)).toBeVisible()
    } finally {
      vi.useRealTimers()
    }
  })

  it('explains how to grant the permission when the microphone is blocked', async () => {
    createFakeBackend({ dictation: {}, localModels: [] })
    const user = userEvent.setup()
    setRecorder({
      start: vi.fn(async () => {
        throw new MicrophoneError('permission', 'denied')
      }),
    })
    renderApp('/ajustes')
    const region = await section()
    await user.click(within(region).getByRole('button', { name: d.microphoneTest }))
    expect(await within(region).findByRole('alert')).toHaveTextContent(d.permission)
  })

  it('asks for the microphone to list the ones of Windows by name (phase 21, CA7)', async () => {
    createFakeBackend({ dictation: {}, localModels: [] })
    let allowed = false
    const hidden = { deviceId: '', label: '', kind: 'audioinput', groupId: '' }
    const named = [
      { deviceId: 'default', label: 'Predeterminado', kind: 'audioinput', groupId: 'g' },
      { deviceId: 'mic-1', label: 'Micrófono (Realtek)', kind: 'audioinput', groupId: 'g' },
    ]
    const stop = vi.fn()
    const getUserMedia = vi.fn(async () => {
      allowed = true
      return { getTracks: () => [{ stop }] }
    })
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: {
        enumerateDevices: async () => (allowed ? named : [hidden]),
        getUserMedia,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    })
    try {
      const user = userEvent.setup()
      renderApp('/ajustes')
      const region = await section()
      await user.click(await within(region).findByRole('button', { name: d.microphoneAllow }))
      expect(getUserMedia).toHaveBeenCalledWith({ audio: true })
      expect(stop).toHaveBeenCalled() // the permission only: nothing keeps recording
      await waitFor(() =>
        expect(within(region).queryByRole('button', { name: d.microphoneAllow })).toBeNull(),
      )
      await user.click(within(region).getByRole('combobox', { name: d.microphone }))
      expect(await screen.findByRole('option', { name: 'Micrófono (Realtek)' })).toBeVisible()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('shows speed and quality of the speech models in «Modelos locales»', async () => {
    createFakeBackend({ dictation: {}, localModels: [whisper(), engine()] })
    renderApp('/ajustes')
    await section()
    const models = await screen.findByRole('region', { name: es.localModels.title })
    expect(await within(models).findByText(es.localModels.kinds.speech.title)).toBeVisible()
    expect(within(models).getByText(/Equilibrado · Buena calidad/)).toBeVisible()
  })
})
