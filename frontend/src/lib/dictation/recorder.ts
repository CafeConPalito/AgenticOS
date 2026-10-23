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
  /** Ends the recording and gives the WAV (16 kHz, mono, 16 bit). */
  stop(): Promise<Blob>
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
    const context = new AudioContext()
    const chunks: Float32Array[] = []
    let closed = false
    const release = () => {
      if (closed) return
      closed = true
      for (const track of stream.getTracks()) track.stop()
      void context.close()
    }
    try {
      await context.audioWorklet.addModule('/dictation-worklet.js')
      const source = context.createMediaStreamSource(stream)
      const node = new AudioWorkletNode(context, 'dictation-processor', {
        numberOfInputs: 1,
        numberOfOutputs: 0,
      })
      node.port.onmessage = (event: MessageEvent<Float32Array>) => {
        chunks.push(event.data)
        onLevel(level(event.data))
      }
      source.connect(node)
    } catch (error) {
      release()
      throw problemOf(error)
    }
    return {
      async stop() {
        const rate = context.sampleRate
        release()
        const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
        const samples = new Float32Array(total)
        let offset = 0
        for (const chunk of chunks) {
          samples.set(chunk, offset)
          offset += chunk.length
        }
        return new Blob([encodeWav(samples, rate)], { type: 'audio/wav' })
      },
      cancel: release,
    }
  },
}
