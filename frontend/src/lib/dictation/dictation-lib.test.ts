import { describe, expect, it } from 'vitest'
import { insertText, shiftAnchor, shiftPosition, spaced, trackAnchor } from './insert'
import { fromEvent, keycaps, matches, parseShortcut, releases } from './shortcut'
import { encodeWav, level, resample, SAMPLE_RATE } from './wav'

describe('wav', () => {
  it('writes a 16 kHz mono 16-bit WAV header and the samples', () => {
    const bytes = encodeWav(new Float32Array([0, 0.5, -0.5, 1, -1, 2]), SAMPLE_RATE)
    const view = new DataView(bytes.buffer)
    const tag = (at: number) => String.fromCharCode(...bytes.slice(at, at + 4))
    expect([tag(0), tag(8), tag(12), tag(36)]).toEqual(['RIFF', 'WAVE', 'fmt ', 'data'])
    expect(view.getUint16(20, true)).toBe(1) // PCM
    expect(view.getUint16(22, true)).toBe(1) // mono
    expect(view.getUint32(24, true)).toBe(16_000)
    expect(view.getUint16(34, true)).toBe(16)
    expect(view.getUint32(40, true)).toBe(12) // six samples of two bytes
    expect(view.getUint32(4, true)).toBe(bytes.length - 8)
    expect(bytes.length).toBe(44 + 12)
    expect(view.getInt16(44 + 2, true)).toBeCloseTo(0.5 * 0x7fff, -1)
    expect(view.getInt16(44 + 4, true)).toBeCloseTo(-0.5 * 0x8000, -1)
    expect(view.getInt16(44 + 10, true)).toBe(0x7fff) // 2.0 is clipped, not wrapped
    expect(view.getInt16(44 + 8, true)).toBe(-0x8000)
  })

  it('resamples from the microphone rate to 16 kHz', () => {
    const second = new Float32Array(48_000).fill(0.25)
    expect(resample(second, 48_000)).toHaveLength(16_000)
    expect(resample(new Float32Array(44_100), 44_100)).toHaveLength(16_000)
    const same = new Float32Array(10)
    expect(resample(same, 16_000)).toBe(same)
    const ramp = Float32Array.from({ length: 30 }, (_, i) => i / 30)
    const down = resample(ramp, 48_000)
    expect(down[1]).toBeCloseTo(ramp[3], 5) // every third sample
  })

  it('measures a level between 0 and 1', () => {
    expect(level(new Float32Array(0))).toBe(0)
    expect(level(new Float32Array(100))).toBe(0)
    expect(level(new Float32Array(100).fill(0.1))).toBeCloseTo(0.4)
    expect(level(new Float32Array(100).fill(1))).toBe(1)
  })
})

describe('insert', () => {
  it('follows a position through an edit', () => {
    expect(shiftPosition('hola mundo', 'hola grande mundo', 5)).toBe(5) // before the edit
    expect(shiftPosition('hola mundo', 'hola grande mundo', 10)).toBe(17) // after it
    expect(shiftPosition('abc', 'aXXc', 2)).toBe(3) // inside the replaced part: after the new text
    expect(shiftAnchor('uno dos', 'uno dos tres', { start: 3, end: 3 })).toEqual({
      start: 3,
      end: 3,
    })
  })

  it('adds a space only where the text would stick to a word', () => {
    expect(spaced('hola', { start: 4, end: 4 }, 'mundo')).toBe(' mundo')
    expect(spaced('hola ', { start: 5, end: 5 }, 'mundo')).toBe('mundo')
    expect(spaced('', { start: 0, end: 0 }, 'mundo')).toBe('mundo')
    expect(spaced('hola', { start: 4, end: 4 }, ', adiós')).toBe(', adiós')
    expect(spaced('línea\n', { start: 6, end: 6 }, 'otra')).toBe('otra')
  })

  function field(value: string, start: number, end = start) {
    const textarea = document.createElement('textarea')
    document.body.append(textarea)
    textarea.value = value
    textarea.setSelectionRange(start, end)
    return textarea
  }

  it('inserts at the cursor, tells the owner, and leaves the cursor after the text', () => {
    const textarea = field('hola mundo', 4)
    let inputs = 0
    textarea.addEventListener('input', () => inputs++)
    insertText(textarea, { start: 4, end: 4 }, 'amigos')
    expect(textarea.value).toBe('hola amigos mundo')
    expect(inputs).toBe(1)
    expect(textarea.selectionStart).toBe(11)
  })

  it('replaces what was selected', () => {
    const textarea = field('borra esto ahora', 6, 10)
    insertText(textarea, { start: 6, end: 10 }, 'aquello')
    expect(textarea.value).toBe('borra aquello ahora')
  })

  it('keeps the place of the cursor while the person keeps typing', () => {
    const textarea = field('hola mundo', 4)
    const anchor = trackAnchor(textarea, { start: 4, end: 4 })
    textarea.value = 'ESCRITO hola mundo' // typed at the start while transcribing
    textarea.dispatchEvent(new Event('input'))
    textarea.value = 'ESCRITO hola mundo!'
    textarea.dispatchEvent(new Event('input'))
    expect(anchor.read()).toEqual({ start: 12, end: 12 })
    insertText(textarea, anchor.read(), 'a todos')
    expect(textarea.value).toBe('ESCRITO hola a todos mundo!')
    anchor.stop()
  })

  it('does not touch the focus of another field', () => {
    const other = document.createElement('input')
    document.body.append(other)
    other.focus()
    const textarea = field('abc', 3)
    insertText(textarea, { start: 3, end: 3 }, 'd')
    expect(textarea.value).toBe('abc d')
    expect(document.activeElement).toBe(other)
  })
})

describe('shortcut', () => {
  const press = (init: KeyboardEventInit) => new KeyboardEvent('keydown', init)

  it('reads «Ctrl+Space» and matches the physical key', () => {
    const combo = parseShortcut('Ctrl+Space')!
    expect(combo).toEqual({ ctrl: true, alt: false, shift: false, meta: false, code: 'Space' })
    expect(matches(combo, press({ code: 'Space', ctrlKey: true }))).toBe(true)
    expect(matches(combo, press({ code: 'Space' }))).toBe(false) // a plain space types a space
    expect(matches(combo, press({ code: 'Space', ctrlKey: true, shiftKey: true }))).toBe(false)
    expect(parseShortcut('ctrl+shift+d')!.code).toBe('KeyD')
    expect(parseShortcut('F9')!.code).toBe('F9')
    expect(parseShortcut('Ctrl+')).toBeNull()
  })

  it('ends the hold when any key of the combination is released', () => {
    const combo = parseShortcut('Ctrl+Shift+D')!
    expect(releases(combo, press({ code: 'KeyD', key: 'd', ctrlKey: true, shiftKey: true }))).toBe(
      true,
    )
    expect(releases(combo, press({ code: 'ControlLeft', key: 'Control', shiftKey: true }))).toBe(
      true,
    )
    expect(releases(combo, press({ code: 'KeyX', key: 'x', ctrlKey: true, shiftKey: true }))).toBe(
      false,
    )
  })

  it('names the combination for the settings, and the keys for the help', () => {
    expect(fromEvent(press({ code: 'KeyD', key: 'd', ctrlKey: true, shiftKey: true }))).toBe(
      'Ctrl+Shift+D',
    )
    expect(fromEvent(press({ code: 'Space', key: ' ', ctrlKey: true }))).toBe('Ctrl+Space')
    expect(fromEvent(press({ code: 'ControlLeft', key: 'Control', ctrlKey: true }))).toBeNull()
    expect(keycaps('Ctrl+Space', 'Espacio')).toEqual(['Ctrl', 'Espacio'])
  })
})
