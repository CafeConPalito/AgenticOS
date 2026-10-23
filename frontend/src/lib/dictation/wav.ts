/** What the engine wants: 16 kHz, mono, 16-bit PCM in a WAV (ADR 0023). */
export const SAMPLE_RATE = 16_000

/** Linear resampling to 16 kHz. Speech needs nothing fancier; the browser has already filtered
 * the microphone signal. */
export function resample(samples: Float32Array, fromRate: number): Float32Array {
  if (fromRate === SAMPLE_RATE) return samples
  const length = Math.floor((samples.length * SAMPLE_RATE) / fromRate)
  const out = new Float32Array(length)
  const step = fromRate / SAMPLE_RATE
  for (let i = 0; i < length; i++) {
    const position = i * step
    const before = Math.floor(position)
    const after = Math.min(before + 1, samples.length - 1)
    const fraction = position - before
    out[i] = samples[before] * (1 - fraction) + samples[after] * fraction
  }
  return out
}

/** The bytes of a WAV file holding `samples` (floats in -1..1) recorded at `rate`. */
export function encodeWav(samples: Float32Array, rate: number): Uint8Array<ArrayBuffer> {
  const pcm = resample(samples, rate)
  const bytes = new Uint8Array(44 + pcm.length * 2)
  const view = new DataView(bytes.buffer)
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i))
  }
  text(0, 'RIFF')
  view.setUint32(4, 36 + pcm.length * 2, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  view.setUint32(16, 16, true) // size of the fmt chunk
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, SAMPLE_RATE, true)
  view.setUint32(28, SAMPLE_RATE * 2, true) // bytes per second
  view.setUint16(32, 2, true) // bytes per frame
  view.setUint16(34, 16, true) // bits per sample
  text(36, 'data')
  view.setUint32(40, pcm.length * 2, true)
  for (let i = 0; i < pcm.length; i++) {
    const clipped = Math.max(-1, Math.min(1, pcm[i]))
    view.setInt16(44 + i * 2, clipped < 0 ? clipped * 0x8000 : clipped * 0x7fff, true)
  }
  return bytes
}

/** Level of a chunk for the meter: RMS in 0..1, with some gain because speech is quiet. */
export function level(chunk: Float32Array): number {
  if (chunk.length === 0) return 0
  let sum = 0
  for (let i = 0; i < chunk.length; i++) sum += chunk[i] * chunk[i]
  return Math.min(1, Math.sqrt(sum / chunk.length) * 4)
}
