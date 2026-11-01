import { encodeWav, level } from './wav'

export type MicrophoneProblem = 'permission' | 'no_device' | 'failed'

/** Why the microphone could not be used; `permission` is the one the person can fix. */
export class MicrophoneError extends Error {
  readonly problem: MicrophoneProblem

  constructor(problem: MicrophoneProblem, message: string) {
    super(message)
    this.name = 'MicrophoneError'
    this.problem = problem
  }
}

export interface Recording {
  /** Ends the recording and gives the WAV (16 kHz, mono, 16 bit), from sample `from` on. */
  stop(from?: number): Promise<Blob>
  /** Phase 23: the WAV recorded so far from sample `from`, while it goes on, and where it ends
   * (the next `from`). Without it a recording is transcribed only at the end. */
  peek?(from: number): { wav: Blob; end: number; rate: number }
  /** Throws the recording away and releases the microphone. */
  cancel(): void
}

export interface Recorder {
  start(options: { deviceId?: string; onLevel: (level: number) => void }): Promise<Recording>
}

function problemOf(error: unknown): MicrophoneError {
  const name = error instanceof DOMException || error instanceof Error ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return new MicrophoneError('permission', 'microphone permission denied')
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') {
    return new MicrophoneError('no_device', 'no microphone found')
  }
  return new MicrophoneError('failed', error instanceof Error ? error.message : String(error))
}

/** The real recorder: the system microphone through Web Audio. Closing the stream and the
 * context on stop or cancel is what turns off the recording indicator of the system. */
export const microphone: Recorder = {
  async start({ deviceId, onLevel }) {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new MicrophoneError('failed', 'this window cannot use the microphone')
    }
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: deviceId ? { exact: deviceId } : undefined,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
    } catch (error) {
      // The remembered microphone was unplugged: use the default one.
      if (deviceId && (error as Error).name === 'OverconstrainedError') {
        return microphone.start({ onLevel })
      }
      throw problemOf(error)
    }
    // 16 kHz asked of the browser, which resamples with a proper filter; elsewhere the device
    // rate is kept and `encodeWav` resamples.
    let context: AudioContext
    try {
      context = new AudioContext({ sampleRate: 16_000 })
    } catch {
      context = new AudioContext()
    }
    const chunks: Float32Array[] = []
    let closed = false
    let node: AudioWorkletNode | null = null
    let flushed: (() => void) | null = null
    const release = () => {
      if (closed) return
      closed = true
      for (const track of stream.getTracks()) track.stop()
      void context.close()
    }
    try {
      await context.audioWorklet.addModule('/dictation-worklet.js')
      const source = context.createMediaStreamSource(stream)
      const created = new AudioWorkletNode(context, 'dictation-processor', {
        numberOfInputs: 1,
        numberOfOutputs: 0,
      })
      node = created
      created.port.onmessage = (event: MessageEvent<Float32Array | { flushed: true }>) => {
        if (event.data instanceof Float32Array) {
          chunks.push(event.data)
          onLevel(level(event.data))
        } else flushed?.()
      }
      source.connect(created)
    } catch (error) {
      release()
      throw problemOf(error)
    }
    const joined = (from: number) => {
      const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
      const samples = new Float32Array(Math.max(0, total - from))
      let offset = 0
      let skip = from
      for (const chunk of chunks) {
        if (skip >= chunk.length) {
          skip -= chunk.length
          continue
        }
        const part = skip > 0 ? chunk.subarray(skip) : chunk
        skip = 0
        samples.set(part, offset)
        offset += part.length
      }
      return { samples, total }
    }
    return {
      peek(from) {
        const { samples, total } = joined(from)
        const rate = context.sampleRate
        return {
          wav: new Blob([encodeWav(samples, rate)], { type: 'audio/wav' }),
          end: total,
          rate,
        }
      },
      async stop(from = 0) {
        const rate = context.sampleRate
        // The end of the last word is still in the worklet: ask for it before closing.
        const pending = node
        if (pending && !closed) {
          await new Promise<void>((resolve) => {
            flushed = resolve
            pending.port.postMessage('flush')
            setTimeout(resolve, 300)
          })
        }
        release()
        return new Blob([encodeWav(joined(from).samples, rate)], { type: 'audio/wav' })
      },
      cancel: release,
    }
  },
}
