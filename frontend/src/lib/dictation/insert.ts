/** Putting the dictated text into a field without losing what the person has written, even if
 * they kept typing while it was being transcribed (ADR 0023). */

export type Field = HTMLInputElement | HTMLTextAreaElement

export interface Anchor {
  start: number
  end: number
}

/** Where position `x` of `before` ends up in `after`, found from what changed between them:
 * the common start and the common end are untouched, only the middle was replaced. */
export function shiftPosition(before: string, after: string, x: number): number {
  let prefix = 0
  const shortest = Math.min(before.length, after.length)
  while (prefix < shortest && before[prefix] === after[prefix]) prefix++
  let suffix = 0
  while (
    suffix < shortest - prefix &&
    before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
  ) {
    suffix++
  }
  if (x <= prefix) return x
  if (x >= before.length - suffix) return x + (after.length - before.length)
  return after.length - suffix // inside the replaced part: right after the new text
}

export function shiftAnchor(before: string, after: string, anchor: Anchor): Anchor {
  return {
    start: shiftPosition(before, after, anchor.start),
    end: shiftPosition(before, after, anchor.end),
  }
}

/** The text with a space before it when it would otherwise stick to the word on the left, and
 * after it when it would stick to the word on the right. */
export function spaced(value: string, anchor: Anchor, text: string): string {
  const left = value[anchor.start - 1]
  const right = value[anchor.end]
  const before = left !== undefined && !/\s/.test(left) && !/^[\s.,;:!?)\]]/.test(text)
  const after = right !== undefined && !/\s/.test(right) && !/[.,;:!?)\]]/.test(right)
  return `${before ? ' ' : ''}${text}${after && !/\s$/.test(text) ? ' ' : ''}`
}

/** Follows the field's edits so the anchor stays where the cursor was when the recording began. */
export function trackAnchor(
  field: Field,
  initial: Anchor,
): { read: () => Anchor; stop: () => void } {
  let anchor = initial
  let last = field.value
  const onInput = () => {
    anchor = shiftAnchor(last, field.value, anchor)
    last = field.value
  }
  field.addEventListener('input', onInput)
  return { read: () => anchor, stop: () => field.removeEventListener('input', onInput) }
}

/** Writes `text` at the anchor (replacing what was selected there), in a way the field's owner
 * hears about (the `input` event) and that Ctrl+Z can undo where the browser supports it.
 * Leaves the cursor after the text. */
export function insertText(field: Field, anchor: Anchor, text: string): void {
  const value = field.value
  const start = Math.min(anchor.start, value.length)
  const end = Math.min(Math.max(anchor.end, start), value.length)
  const piece = spaced(value, { start, end }, text)
  const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
  field.focus({ preventScroll: true })
  field.setSelectionRange(start, end)
  // `insertText` goes through the browser's editing machinery: the undo stack and the `input`
  // event come for free. Where it does not exist (or refuses) the same is done by hand.
  const done =
    typeof document.execCommand === 'function' && document.execCommand('insertText', false, piece)
  if (!done) {
    field.setRangeText(piece, start, end, 'end')
    field.dispatchEvent(new Event('input', { bubbles: true }))
  }
  if (previous && previous !== field && previous.isConnected) {
    previous.focus({ preventScroll: true })
  }
}
