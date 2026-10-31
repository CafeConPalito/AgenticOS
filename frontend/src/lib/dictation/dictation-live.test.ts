import { ApiError } from '@/lib/api'
import { LiveTranscript, MAX_PIECE_SECONDS, PAUSE_MS } from './live'
import type { Recording } from './recorder'

const api = vi.hoisted(() => ({
  transcribe: vi.fn<(wav: Blob, signal?: AbortSignal, partial?: boolean) => Promise<unknown>>(),
}))
vi.mock('@/api/dictation', () => ({ transcribe: api.transcribe }))

const RATE = 16_000

/** A recording where the test says how many samples there are. */
function fakeRecording() {
  const state = { samples: 0, stoppedFrom: -1 }
  const recording: Recording = {
    peek: (from) => ({
      wav: new Blob([`${from}-${state.samples}`]),
      end: state.samples,
      rate: RATE,
    }),
    stop: async (from = 0) => {
      state.stoppedFrom = from
      return new Blob([`${from}-${state.samples}`])
    },
    cancel: () => {},
  }
  return { recording, state }
}

function field(value: string, at = value.length) {
  const textarea = document.createElement('textarea')
  document.body.append(textarea)
  textarea.value = value
  textarea.setSelectionRange(at, at)
  return textarea
}

const answer = (text: string) =>
  api.transcribe.mockResolvedValueOnce({ text, seconds: 1, model: 'm' })

async function turn(live: LiveTranscript) {
  live.tick()
  await vi.waitFor(() => expect(live['busy']).toBeNull())
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  api.transcribe.mockReset()
})
afterEach(() => vi.useRealTimers())

describe('LiveTranscript (phase 23, CA8)', () => {
  it('writes a guess of what is being said and replaces it with the next one', async () => {
    const textarea = field('Nota:')
    const { recording, state } = fakeRecording()
    const live = new LiveTranscript(textarea, { start: 5, end: 5 }, recording)
    live.level(0.5) // speaking
    state.samples = RATE * 1
    answer('hola')
    await turn(live)
    expect(textarea.value).toBe('Nota: hola')
    expect(api.transcribe).toHaveBeenLastCalledWith(expect.any(Blob), undefined, true)

    state.samples = RATE * 2
    answer('hola mundo')
    await turn(live)
    expect(textarea.value).toBe('Nota: hola mundo')
  })

  it('fixes a piece at a pause, and the next guess starts after it', async () => {
    const textarea = field('')
    const { recording, state } = fakeRecording()
    const live = new LiveTranscript(textarea, { start: 0, end: 0 }, recording)
    live.level(0.5)
    vi.setSystemTime(Date.now() + PAUSE_MS + 50) // silence since
    state.samples = RATE * 2
    answer('primera frase.')
    await turn(live)
    expect(live['from']).toBe(RATE * 2)

    live.level(0.5)
    state.samples = RATE * 3
    answer('segunda')
    await turn(live)
    // Only the audio after the fixed piece was sent.
    expect(await (api.transcribe.mock.lastCall![0] as Blob).text()).toBe(`${RATE * 2}-${RATE * 3}`)
    expect(textarea.value).toBe('primera frase. segunda')
  })

  it('fixes a piece that grows too long without a pause', async () => {
    const textarea = field('')
    const { recording, state } = fakeRecording()
    const live = new LiveTranscript(textarea, { start: 0, end: 0 }, recording)
    live.level(0.5)
    state.samples = RATE * MAX_PIECE_SECONDS
    answer('un trozo largo')
    await turn(live)
    expect(live['from']).toBe(RATE * MAX_PIECE_SECONDS)
  })

  it('finishes with the rest of the audio and leaves the final text', async () => {
    const textarea = field('Asunto: ')
    const { recording, state } = fakeRecording()
    const live = new LiveTranscript(textarea, { start: 8, end: 8 }, recording)
    vi.setSystemTime(Date.now() + PAUSE_MS + 50)
    state.samples = RATE * 2
    answer('reunión del lunes.')
    await turn(live)
    state.samples = RATE * 3
    answer('A las diez.')
    const text = await live.finish()
    expect(state.stoppedFrom).toBe(RATE * 2)
    expect(api.transcribe).toHaveBeenLastCalledWith(expect.any(Blob))
    expect(text).toBe('reunión del lunes. A las diez.')
    expect(live.deliver(text)).toBe(true)
    expect(textarea.value).toBe('Asunto: reunión del lunes. A las diez.')
  })

  it('a busy engine skips that turn', async () => {
    const textarea = field('')
    const { recording, state } = fakeRecording()
    const live = new LiveTranscript(textarea, { start: 0, end: 0 }, recording)
    live.level(0.5)
    state.samples = RATE
    api.transcribe.mockRejectedValueOnce(new ApiError(409, 'busy', 'busy'))
    await turn(live)
    expect(textarea.value).toBe('')
  })

  it('what the person types is never overwritten', async () => {
    const textarea = field('Hola')
    const { recording, state } = fakeRecording()
    const live = new LiveTranscript(textarea, { start: 4, end: 4 }, recording)
    vi.setSystemTime(Date.now() + PAUSE_MS + 50)
    state.samples = RATE * 2
    answer('qué tal.')
    await turn(live)
    expect(textarea.value).toBe('Hola qué tal.')

    // Typed before our text: it moves along, and is still ours.
    textarea.setRangeText('¡', 0, 0)
    textarea.dispatchEvent(new Event('input'))
    state.samples = RATE * 3
    answer('Bien')
    await turn(live)
    expect(textarea.value).toBe('¡Hola qué tal. Bien')

    // Edited inside our text: from now on the rest goes after it, nothing is replaced.
    textarea.setRangeText('QUÉ', 6, 9)
    textarea.dispatchEvent(new Event('input'))
    state.samples = RATE * 4
    answer('ya no se escribe')
    await turn(live)
    expect(textarea.value).toBe('¡Hola QUÉ tal. Bien')
    // The final text is the fixed one plus the rest: only the rest is added.
    expect(live.deliver('qué tal. Bien y adiós.')).toBe(true)
    expect(textarea.value).toBe('¡Hola QUÉ tal. Bien y adiós.')
  })

  it('a dictation thrown away takes its provisional text with it', async () => {
    const textarea = field('Antes')
    const { recording, state } = fakeRecording()
    const live = new LiveTranscript(textarea, { start: 5, end: 5 }, recording)
    live.level(0.5)
    state.samples = RATE
    answer('esto no')
    await turn(live)
    expect(textarea.value).toBe('Antes esto no')
    live.discard()
    expect(textarea.value).toBe('Antes')
  })
})
