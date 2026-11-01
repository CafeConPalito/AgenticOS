/** The text of a dictation as it is spoken (phase 23, ADR 0029).
 *
 * While the person speaks, what was said since the last pause is transcribed every
 * `TICK_MS` and written into the field as provisional text, replacing the previous guess. At a
 * pause (or after `MAX_PIECE_SECONDS`) that piece is fixed: its text stays and the next guess
 * starts after it. So every request carries little audio and the text never jumps back. When
 * the recording stops (`end`: the microphone is released at once), what is left is transcribed
 * once more (`finish`) and the text is final.
 */

import { transcribe } from '@/api/dictation'
import { ApiError } from '@/lib/api'
import { insertText, shiftAnchor, spaced, type Anchor, type Field } from './insert'
import type { Recording } from './recorder'

export const TICK_MS = 1500
/** A pause this long fixes the piece said before it. */
export const PAUSE_MS = 600
/** A piece is fixed at this length even without a pause: the engine reads up to ~10 s. */
export const MAX_PIECE_SECONDS = 8
/** Below this level the microphone is taken as silent (the level goes from 0 to 1). */
export const QUIET_LEVEL = 0.04
/** Less audio than this is not worth a guess. */
const MIN_PIECE_SECONDS = 0.6

const joined = (...parts: string[]) => parts.filter(Boolean).join(' ')

export class LiveTranscript {
  /** The text of the pieces already fixed. */
  private fixed = ''
  /** The guess for the piece being said. */
  private guess = ''
  /** The sample where the piece being said starts. */
  private from = 0
  private busy: Promise<void> | null = null
  /** Where our text is in the field, and what it says there. */
  private range: Anchor
  private written = ''
  private last: string
  /** The person edited our text: from then on the rest is added after it. The fixed text at
   * that moment is what was already in the field for good. */
  private detached = false
  private fixedWhenDetached = ''
  private lastLoud = Date.now()
  private readonly onInput = () => this.followEdits()

  private readonly field: Field
  private readonly recording: Recording

  constructor(field: Field, anchor: Anchor, recording: Recording) {
    this.field = field
    this.recording = recording
    this.range = { start: anchor.start, end: anchor.end }
    this.last = field.value
    field.addEventListener('input', this.onInput)
  }

  /** The microphone's level, to tell the pauses. */
  level(value: number): void {
    if (value > QUIET_LEVEL) this.lastLoud = Date.now()
  }

  /** One turn of the clock while recording: a guess of what is being said. */
  tick(): void {
    if (this.busy || !this.recording.peek) return
    const { wav, end, rate } = this.recording.peek(this.from)
    const seconds = (end - this.from) / rate
    if (seconds < MIN_PIECE_SECONDS) return
    const fix = Date.now() - this.lastLoud >= PAUSE_MS || seconds >= MAX_PIECE_SECONDS
    this.busy = transcribe(wav, undefined, true)
      .then(({ text }) => {
        if (fix) {
          this.fixed = joined(this.fixed, text)
          this.guess = ''
          this.from = end
        } else this.guess = text
        this.show()
      })
      .catch((error: unknown) => {
        // A piece without words is left behind, so silence does not pile up; anything else
        // (the engine busy, the network) only loses this guess: the next turn tries again.
        if (fix && error instanceof ApiError && error.code === 'no_speech') this.from = end
      })
      .finally(() => {
        this.busy = null
      })
  }

  /** The person stopped: the recording ends and the microphone is released now, even if the
   * text comes later (its audio stays to be read by `finish`). */
  async end(): Promise<void> {
    await this.recording.stop()
  }

  /** After `end`: the rest is transcribed and the text is final ("" when nothing was said). */
  async finish(): Promise<string> {
    await this.busy
    const { wav, end, rate } = this.recording.peek!(this.from)
    if ((end - this.from) / rate >= MIN_PIECE_SECONDS) {
      try {
        const { text } = await transcribe(wav)
        this.fixed = joined(this.fixed, text)
      } catch (error) {
        // Nothing more was said after the last piece: what is fixed stays.
        if (!(error instanceof ApiError && error.code === 'no_speech')) throw error
      }
    }
    this.guess = ''
    return this.fixed
  }

  /** The last transcription failed: what was already fixed stays in the field, the guess goes. */
  keep(): string {
    this.guess = ''
    this.show()
    this.stop()
    return this.fixed
  }

  /** Writes the final text; false if it could not go into the field (it is gone). */
  deliver(text: string): boolean {
    this.stop()
    if (!this.field.isConnected) return false
    if (this.detached) {
      const known = this.fixedWhenDetached
      const rest = (text.startsWith(known) ? text.slice(known.length) : text).trim()
      if (rest) insertText(this.field, { start: this.range.end, end: this.range.end }, rest)
      return true
    }
    this.write(text)
    return true
  }

  /** The recording was thrown away: our provisional text goes too. */
  discard(): void {
    this.stop()
    if (!this.detached && this.field.isConnected && this.written) this.write('')
  }

  stop(): void {
    this.field.removeEventListener('input', this.onInput)
  }

  private show(): void {
    if (!this.detached && this.field.isConnected) this.write(joined(this.fixed, this.guess))
  }

  /** Our text in place of the one written before, with the spaces it needs around it. */
  private write(text: string): void {
    const value = this.field.value
    const piece = text
      ? spaced(
          value.slice(0, this.range.start) + value.slice(this.range.end),
          { start: this.range.start, end: this.range.start },
          text,
        )
      : ''
    this.field.setRangeText(piece, this.range.start, this.range.end, 'end')
    this.range = { start: this.range.start, end: this.range.start + piece.length }
    this.written = piece
    this.last = this.field.value
    this.field.dispatchEvent(new Event('input', { bubbles: true }))
  }

  /** An edit of the person: our range follows it; inside our text, we stop writing there. */
  private followEdits(): void {
    const value = this.field.value
    if (value === this.last) return // our own write
    this.range = shiftAnchor(this.last, value, this.range)
    this.last = value
    if (!this.detached && value.slice(this.range.start, this.range.end) !== this.written) {
      this.detached = true
      this.fixedWhenDetached = this.fixed
    }
  }
}
