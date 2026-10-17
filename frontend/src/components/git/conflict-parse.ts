/** Conflict markers of a file git could not merge, as editable blocks (phase 12).
 *
 * git leaves `<<<<<<< ours`, `=======` and `>>>>>>> theirs` in the file (with `|||||||` and the
 * common ancestor in between when it merges in the `diff3` style). The text between conflicts
 * is kept as it is. */

export type Segment =
  | { type: 'text'; lines: string[] }
  | {
      type: 'conflict'
      ours: string[]
      base: string[] | null
      theirs: string[]
      oursLabel: string
      theirsLabel: string
    }

export type Choice = 'ours' | 'theirs' | 'both' | { custom: string }

const START = /^<{7}(?: (.*))?$/
const BASE = /^\|{7}(?: (.*))?$/
const MIDDLE = /^={7}$/
const END = /^>{7}(?: (.*))?$/

export const newlineOf = (text: string): string => (text.includes('\r\n') ? '\r\n' : '\n')

export function parseConflicts(text: string): Segment[] {
  const lines = text.split(/\r?\n/)
  const segments: Segment[] = []
  let plain: string[] = []
  let index = 0
  while (index < lines.length) {
    const start = START.exec(lines[index])
    if (!start) {
      plain.push(lines[index])
      index += 1
      continue
    }
    const ours: string[] = []
    let base: string[] | null = null
    const theirs: string[] = []
    let part: 'ours' | 'base' | 'theirs' = 'ours'
    let theirsLabel = ''
    let closed = false
    let cursor = index + 1
    for (; cursor < lines.length; cursor += 1) {
      const line = lines[cursor]
      if (part === 'ours' && BASE.test(line)) {
        part = 'base'
        base = []
      } else if (part !== 'theirs' && MIDDLE.test(line)) {
        part = 'theirs'
      } else if (part === 'theirs' && END.test(line)) {
        theirsLabel = END.exec(line)?.[1] ?? ''
        closed = true
        break
      } else if (part === 'ours') {
        ours.push(line)
      } else if (part === 'base') {
        base?.push(line)
      } else {
        theirs.push(line)
      }
    }
    if (!closed) {
      // A block that never closes is just text: the file is not what git left.
      plain.push(lines[index])
      index += 1
      continue
    }
    if (plain.length > 0) segments.push({ type: 'text', lines: plain })
    plain = []
    segments.push({ type: 'conflict', ours, base, theirs, oursLabel: start[1] ?? '', theirsLabel })
    index = cursor + 1
  }
  if (plain.length > 0) segments.push({ type: 'text', lines: plain })
  return segments
}

/** How many conflict blocks the text has. */
export const conflictCount = (segments: Segment[]): number =>
  segments.filter((segment) => segment.type === 'conflict').length

/** The file with each block replaced by what was chosen for it. A block with no choice keeps
 * its markers, so the file still says it is unresolved. */
export function applyChoices(
  segments: Segment[],
  choices: Record<number, Choice | undefined>,
  newline = '\n',
): string {
  const out: string[] = []
  let block = 0
  for (const segment of segments) {
    if (segment.type === 'text') {
      out.push(...segment.lines)
      continue
    }
    const choice = choices[block]
    block += 1
    if (choice === undefined) {
      out.push(`<<<<<<< ${segment.oursLabel}`.trimEnd(), ...segment.ours)
      if (segment.base) out.push('||||||| base', ...segment.base)
      out.push('=======', ...segment.theirs, `>>>>>>> ${segment.theirsLabel}`.trimEnd())
    } else if (choice === 'ours') {
      out.push(...segment.ours)
    } else if (choice === 'theirs') {
      out.push(...segment.theirs)
    } else if (choice === 'both') {
      out.push(...segment.ours, ...segment.theirs)
    } else {
      out.push(...choice.custom.split(/\r?\n/))
    }
  }
  return out.join(newline)
}

/** The text still has conflict markers. */
export const hasMarkers = (text: string): boolean =>
  text.split(/\r?\n/).some((line) => START.test(line) || END.test(line) || MIDDLE.test(line))
