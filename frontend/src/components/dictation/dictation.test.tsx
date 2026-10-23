import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Textarea } from '@/components/ui/textarea'
import es from '@/i18n/es.json'
import { resetDictation, setRecorder, WARNING_SECONDS } from '@/lib/dictation/controller'
import { useHoldToDictate } from '@/lib/dictation/hold'
import { MicrophoneError, type Recorder } from '@/lib/dictation/recorder'
import { Providers } from '@/providers'
import { useDictation } from '@/stores/dictation'
import { createFakeBackend } from '@/test/fake-backend'

const MIC = es.dictation

function fakeRecorder(failWith?: MicrophoneError) {
  const cancels = vi.fn()
  const start = vi.fn(async ({ onLevel }: { onLevel: (level: number) => void }) => {
    if (failWith) throw failWith
    onLevel(0.6)
    return { stop: async () => new Blob(['wav'], { type: 'audio/wav' }), cancel: cancels }
  })
  const recorder: Recorder = { start }
  setRecorder(recorder)
  return { start, cancels }
}

function Harness({ initial = '' }: { initial?: string }) {
  const [value, setValue] = useState(initial)
  useHoldToDictate()
  return (
    <Textarea
      aria-label="campo"
      dictation
      value={value}
      onChange={(event) => setValue(event.target.value)}
    />
  )
}

function mount(seed: Parameters<typeof createFakeBackend>[0] = { dictation: {} }, text = '') {
  const backend = createFakeBackend(seed)
  const view = render(
    <Providers>
      <Harness initial={text} />
    </Providers>,
  )
  const field = screen.getByLabelText('campo') as HTMLTextAreaElement
  return { backend, field, ...view }
}

const mic = () => screen.findByRole('button', { name: MIC.start })
const transcriptions = (backend: ReturnType<typeof createFakeBackend>) =>
  backend.callsTo('POST', '/api/dictation/transcribe')

async function dictate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await mic())
  await user.click(await screen.findByRole('button', { name: MIC.stop }))
}

beforeEach(() => {
  resetDictation()
  setRecorder({ start: vi.fn() })
})

describe('the microphone of a field', () => {
  it('is not shown when dictation is turned off', async () => {
    const { backend } = mount({})
    await waitFor(() => expect(backend.callsTo('GET', '/api/dictation/status')).toHaveLength(1))
    expect(screen.queryByRole('button', { name: MIC.start })).not.toBeInTheDocument()
  })

  it('records on a click, shows the level and the time, and inserts the text at the cursor', async () => {
    const user = userEvent.setup()
    fakeRecorder()
    const { field, backend } = mount({ dictation: { answers: ['a todos'] } }, 'hola mundo')
    field.focus()
    field.setSelectionRange(4, 4)
    await user.click(await mic())
    const stop = await screen.findByRole('button', { name: MIC.stop })
    expect(stop).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('dictation-level')).toBeInTheDocument()
    expect(screen.getByText('0:00')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(MIC.recording)
    await user.click(stop)
    await waitFor(() => expect(field.value).toBe('hola a todos mundo'))
    expect(transcriptions(backend)).toHaveLength(1)
    expect(backend.callsTo('POST', '/api/dictation/warmup')).toHaveLength(1)
    expect(await mic()).toBeEnabled()
  })

  it('replaces the selection and leaves the rest of the text alone', async () => {
    const user = userEvent.setup()
    fakeRecorder()
    const { field } = mount({ dictation: { answers: ['esto'] } }, 'cambia ESTO ahora')
    field.focus()
    field.setSelectionRange(7, 11)
    await dictate(user)
    await waitFor(() => expect(field.value).toBe('cambia esto ahora'))
  })

  it('puts the text where the cursor was even if the person kept writing meanwhile', async () => {
    const user = userEvent.setup()
    fakeRecorder()
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    const { field } = mount(
      { dictation: { answers: ['dictado'], gate: () => gate } },
      'primero segundo',
    )
    field.focus()
    field.setSelectionRange(8, 8)
    await dictate(user)
    expect(await screen.findByRole('button', { name: MIC.transcribing })).toBeDisabled()
    // Typing at the start while it transcribes.
    field.setSelectionRange(0, 0)
    await user.keyboard('>> ')
    release()
    await waitFor(() => expect(field.value).toBe('>> primero dictado segundo'))
  })

  it('cancels with Esc: nothing is sent and the field stays as it was', async () => {
    const user = userEvent.setup()
    const recorder = fakeRecorder()
    const { field, backend } = mount({ dictation: {} }, 'intacto')
    await user.click(await mic())
    await screen.findByRole('button', { name: MIC.stop })
    await user.keyboard('{Escape}')
    await waitFor(() => expect(useDictation.getState().recording).toBeNull())
    expect(recorder.cancels).toHaveBeenCalledTimes(1)
    expect(transcriptions(backend)).toHaveLength(0)
    expect(field.value).toBe('intacto')
    expect(await mic()).toBeEnabled()
  })

  it('cuts at the maximum duration, warns before and transcribes what was said', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      fakeRecorder()
      const { field, backend } = mount(
        { dictation: { settings: { max_seconds: 40 }, answers: ['cortado'] } },
        '',
      )
      fireEvent.click(await mic())
      await screen.findByRole('button', { name: MIC.stop })
      await act(async () => {
        await vi.advanceTimersByTimeAsync((40 - WARNING_SECONDS) * 1000 + 100)
      })
      expect(screen.getByText(MIC.nearLimit)).toBeInTheDocument()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(WARNING_SECONDS * 1000)
      })
      await waitFor(() => expect(field.value).toBe('cortado'))
      expect(transcriptions(backend)).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not lose what was in the field when the microphone cannot be used', async () => {
    const user = userEvent.setup()
    fakeRecorder(new MicrophoneError('permission', 'denied'))
    const { field } = mount({ dictation: {} }, 'no se pierde')
    await user.click(await mic())
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(MIC.errors.permission))
    expect(field.value).toBe('no se pierde')
    expect(useDictation.getState().recording).toBeNull()
  })

  it.each([
    ['no_speech', 422, MIC.errors.no_speech],
    ['request_failed', 502, MIC.errors.request_failed],
    ['not_enough_memory', 503, MIC.errors.not_enough_memory],
  ])('says what happened when the transcription fails (%s)', async (code, status, text) => {
    const user = userEvent.setup()
    fakeRecorder()
    const { field } = mount({ dictation: { answers: [{ error: { status, code } }] } }, 'sigue')
    await dictate(user)
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(text))
    expect(field.value).toBe('sigue')
    // Trying again clears the error.
    await user.click(await screen.findByRole('button', { name: MIC.start }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(MIC.recording))
  })

  it('offers to download a model when there is none', async () => {
    const user = userEvent.setup()
    const recorder = fakeRecorder()
    mount({
      dictation: { status: { ready: false, reason: 'no_model' } },
      localModels: [],
    })
    await user.click(await mic())
    expect(useDictation.getState().downloadOpen).toBe(true)
    expect(recorder.start).not.toHaveBeenCalled()
  })

  it('copies the text to the clipboard when the field is gone before it arrives', async () => {
    const user = userEvent.setup()
    fakeRecorder()
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    const { field, unmount } = mount({ dictation: { answers: ['perdido'], gate: () => gate } })
    field.focus()
    await dictate(user)
    unmount()
    release()
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('perdido'))
  })

  it('transcribes one recording after the other, each into its own field', async () => {
    const user = userEvent.setup()
    fakeRecorder()
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    const backend = createFakeBackend({
      dictation: { answers: ['uno', 'dos'], gate: () => gate },
    })
    render(
      <Providers>
        <Harness />
        <Textarea aria-label="otro" dictation />
      </Providers>,
    )
    const [first, second] = [screen.getByLabelText('campo'), screen.getByLabelText('otro')]
    const [firstMic, secondMic] = await screen.findAllByRole('button', { name: MIC.start })
    await user.click(firstMic)
    await user.click(await screen.findByRole('button', { name: MIC.stop }))
    await user.click(secondMic)
    await user.click(await screen.findByRole('button', { name: MIC.stop }))
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: MIC.queued }).length).toBeGreaterThan(0),
    )
    release()
    await waitFor(() => expect((first as HTMLTextAreaElement).value).toBe('uno'))
    await waitFor(() => expect((second as HTMLTextAreaElement).value).toBe('dos'))
    expect(transcriptions(backend)).toHaveLength(2)
  })
})

describe('review fixes', () => {
  it('closing the field while recording releases the microphone', async () => {
    const user = userEvent.setup()
    const recorder = fakeRecorder()
    const { unmount, backend } = mount({ dictation: {} })
    await user.click(await mic())
    await screen.findByRole('button', { name: MIC.stop })
    unmount()
    expect(recorder.cancels).toHaveBeenCalledTimes(1)
    expect(useDictation.getState().recording).toBeNull()
    expect(transcriptions(backend)).toHaveLength(0)
  })

  it('holding the shortcut without a model offers the download and does not record', async () => {
    const recorder = fakeRecorder()
    const { field } = mount({ dictation: { status: { ready: false, reason: 'no_model' } } })
    await mic()
    await act(async () => new Promise((resolve) => setTimeout(resolve, 60)))
    field.focus()
    fireEvent.keyDown(field, { code: 'Space', key: ' ', ctrlKey: true })
    expect(useDictation.getState().downloadOpen).toBe(true)
    expect(recorder.start).not.toHaveBeenCalled()
  })
})

describe('the hold-to-dictate shortcut', () => {
  const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

  async function ready() {
    await mic()
    await act(async () => wait(60)) // the settings arrive too
  }

  it('records while the keys are down and transcribes when they are released', async () => {
    fakeRecorder()
    const { field, backend } = mount({ dictation: { answers: ['por voz'] } }, 'hola')
    await ready()
    field.focus()
    field.setSelectionRange(4, 4)
    const down = fireEvent.keyDown(field, { code: 'Space', key: ' ', ctrlKey: true })
    expect(down).toBe(false) // preventDefault: no character is typed
    await waitFor(() => expect(useDictation.getState().recording?.mode).toBe('hold'))
    fireEvent.keyDown(field, { code: 'Space', key: ' ', ctrlKey: true, repeat: true })
    await act(async () => wait(350)) // longer than an accidental tap
    fireEvent.keyUp(field, { code: 'Space', key: ' ' })
    await waitFor(() => expect(field.value).toBe('hola por voz'))
    expect(transcriptions(backend)).toHaveLength(1)
  })

  it('ignores a tap that is too short to be a dictation', async () => {
    const recorder = fakeRecorder()
    const { field, backend } = mount({ dictation: {} }, 'hola')
    await ready()
    field.focus()
    fireEvent.keyDown(field, { code: 'Space', key: ' ', ctrlKey: true })
    await waitFor(() => expect(useDictation.getState().recording).not.toBeNull())
    fireEvent.keyUp(field, { code: 'Space', key: ' ' })
    await waitFor(() => expect(useDictation.getState().recording).toBeNull())
    expect(recorder.cancels).toHaveBeenCalled()
    expect(transcriptions(backend)).toHaveLength(0)
  })

  it('stops when the window loses the focus while held', async () => {
    fakeRecorder()
    const { field, backend } = mount({ dictation: { answers: ['x'] } })
    await ready()
    field.focus()
    fireEvent.keyDown(field, { code: 'Space', key: ' ', ctrlKey: true })
    await waitFor(() => expect(useDictation.getState().recording).not.toBeNull())
    await act(async () => wait(350))
    fireEvent.blur(window)
    await waitFor(() => expect(transcriptions(backend)).toHaveLength(1))
  })

  it('does nothing outside a field with a microphone', async () => {
    const recorder = fakeRecorder()
    mount({ dictation: {} })
    await ready()
    const prevented = fireEvent.keyDown(document.body, { code: 'Space', key: ' ', ctrlKey: true })
    expect(prevented).toBe(true)
    expect(recorder.start).not.toHaveBeenCalled()
  })

  it('the microphone has an accessible name in each state', async () => {
    const user = userEvent.setup()
    fakeRecorder()
    mount({ dictation: {} })
    const button = await mic()
    expect(within(button.parentElement!).getByRole('status')).toBeEmptyDOMElement()
    await user.click(button)
    expect(await screen.findByRole('button', { name: MIC.stop })).toBeInTheDocument()
  })
})
