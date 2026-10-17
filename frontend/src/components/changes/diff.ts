import type { Hunk } from '@/api/changes'

/** Lines of context «Mostrar más» reveals per click. */
export const CONTEXT_STEP = 20
/** A file with more changed lines than this starts folded (its diff loads when opened). */
export const LARGE_DIFF = 800

/**
 * Where a hunk sits in the old and the new file. A hunk with no lines on one side (a pure
 * addition or deletion) is written by git with the line *before* it, so its first line is the
 * next one.
 */
export function hunkBounds(hunk: Hunk) {
  const newFirst = hunk.new_lines === 0 ? hunk.new_start + 1 : hunk.new_start
  const oldFirst = hunk.old_lines === 0 ? hunk.old_start + 1 : hunk.old_start
  return {
    newFirst,
    newAfter: newFirst + hunk.new_lines,
    oldFirst,
    oldAfter: oldFirst + hunk.old_lines,
  }
}

/** How far the old line numbers are from the new ones just before the hunk. */
export function offsetBefore(hunk: Hunk): number {
  const { newFirst, oldFirst } = hunkBounds(hunk)
  return oldFirst - newFirst
}

/** The same, just after the hunk (the next hunk's offset when no hunk is in between). */
export function offsetAfter(hunk: Hunk): number {
  const { newAfter, oldAfter } = hunkBounds(hunk)
  return oldAfter - newAfter
}
