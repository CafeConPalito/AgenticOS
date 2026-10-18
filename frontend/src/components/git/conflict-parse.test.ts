import {
  applyChoices,
  conflictCount,
  hasMarkers,
  newlineOf,
  parseConflicts,
} from './conflict-parse'

const FILE = [
  'antes',
  '<<<<<<< main',
  'nuestra 1',
  'nuestra 2',
  '=======',
  'suya',
  '>>>>>>> clash',
  'entre',
  '<<<<<<< main',
  'otra nuestra',
  '=======',
  'otra suya',
  '>>>>>>> clash',
  'después',
].join('\n')

describe('parseConflicts', () => {
  it('splits a file into text and conflict blocks, keeping their labels', () => {
    const segments = parseConflicts(FILE)
    expect(segments.map((s) => s.type)).toEqual(['text', 'conflict', 'text', 'conflict', 'text'])
    expect(conflictCount(segments)).toBe(2)
    expect(segments[1]).toMatchObject({
      ours: ['nuestra 1', 'nuestra 2'],
      theirs: ['suya'],
      base: null,
      oursLabel: 'main',
      theirsLabel: 'clash',
    })
  })

  it('reads the common ancestor of a diff3 conflict', () => {
    const [, block] = parseConflicts(
      ['a', '<<<<<<< HEAD', 'x', '||||||| base', 'orig', '=======', 'y', '>>>>>>> otra', 'b'].join(
        '\n',
      ),
    )
    expect(block).toMatchObject({ ours: ['x'], base: ['orig'], theirs: ['y'] })
  })

  it('treats a block that never closes as plain text', () => {
    const segments = parseConflicts('a\n<<<<<<< main\nx\n=======\ny\nb')
    expect(conflictCount(segments)).toBe(0)
    expect(applyChoices(segments, {})).toBe('a\n<<<<<<< main\nx\n=======\ny\nb')
  })

  it('does not take a line of equal signs for a marker outside a conflict', () => {
    const segments = parseConflicts('título\n=======\nTexto')
    expect(conflictCount(segments)).toBe(0)
    expect(applyChoices(segments, {})).toBe('título\n=======\nTexto')
  })
})

describe('applyChoices', () => {
  const segments = parseConflicts(FILE)

  it('replaces each block by the side chosen', () => {
    expect(applyChoices(segments, { 0: 'ours', 1: 'theirs' })).toBe(
      'antes\nnuestra 1\nnuestra 2\nentre\notra suya\ndespués',
    )
    expect(applyChoices(segments, { 0: 'both', 1: 'ours' })).toBe(
      'antes\nnuestra 1\nnuestra 2\nsuya\nentre\notra nuestra\ndespués',
    )
  })

  it('takes a text written by hand', () => {
    expect(applyChoices(segments, { 0: { custom: 'a mano\ndos' }, 1: 'ours' })).toBe(
      'antes\na mano\ndos\nentre\notra nuestra\ndespués',
    )
  })

  it('keeps the markers of the blocks nobody has settled', () => {
    const text = applyChoices(segments, { 0: 'ours' })
    expect(hasMarkers(text)).toBe(true)
    expect(text).toContain('<<<<<<< main\notra nuestra\n=======\notra suya\n>>>>>>> clash')
    expect(hasMarkers(applyChoices(segments, { 0: 'ours', 1: 'ours' }))).toBe(false)
  })

  it('keeps the line endings of the file', () => {
    const crlf = FILE.replaceAll('\n', '\r\n')
    expect(newlineOf(crlf)).toBe('\r\n')
    expect(applyChoices(parseConflicts(crlf), { 0: 'ours', 1: 'ours' }, newlineOf(crlf))).toBe(
      'antes\r\nnuestra 1\r\nnuestra 2\r\nentre\r\notra nuestra\r\ndespués',
    )
  })
})
