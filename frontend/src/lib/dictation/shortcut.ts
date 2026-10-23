/** The hold-to-dictate shortcut: «Ctrl+Space», «Ctrl+Shift+D», «F9»… (Ajustes › Dictado). */

export interface Combo {
  ctrl: boolean
  alt: boolean
  shift: boolean
  meta: boolean
  /** `KeyboardEvent.code` of the main key, e.g. `Space`, `KeyD`, `F9`. */
  code: string
}

const NAMES: Record<string, string> = {
  space: 'Space',
  enter: 'Enter',
  tab: 'Tab',
  esc: 'Escape',
  escape: 'Escape',
  backquote: 'Backquote',
  '`': 'Backquote',
}

function codeOf(token: string): string {
  const lower = token.toLowerCase()
  if (NAMES[lower]) return NAMES[lower]
  if (/^f([1-9]|1[0-9]|2[0-4])$/.test(lower)) return lower.toUpperCase()
  if (/^[a-z]$/.test(lower)) return `Key${lower.toUpperCase()}`
  if (/^[0-9]$/.test(lower)) return `Digit${lower}`
  return token
}

export function parseShortcut(text: string): Combo | null {
  const combo: Combo = { ctrl: false, alt: false, shift: false, meta: false, code: '' }
  for (const raw of text.split('+')) {
    const token = raw.trim()
    if (!token) continue
    const lower = token.toLowerCase()
    if (lower === 'ctrl' || lower === 'control') combo.ctrl = true
    else if (lower === 'alt' || lower === 'option') combo.alt = true
    else if (lower === 'shift') combo.shift = true
    else if (lower === 'meta' || lower === 'cmd' || lower === 'win') combo.meta = true
    else combo.code = codeOf(token)
  }
  return combo.code ? combo : null
}

export function matches(combo: Combo, event: KeyboardEvent): boolean {
  return (
    event.code === combo.code &&
    event.ctrlKey === combo.ctrl &&
    event.altKey === combo.alt &&
    event.shiftKey === combo.shift &&
    event.metaKey === combo.meta
  )
}

/** The keycaps to show for a shortcut («Ctrl», «Espacio»…). */
export function keycaps(text: string, space = 'Space'): string[] {
  return text
    .split('+')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => (part.toLowerCase() === 'space' ? space : part))
}

/** The shortcut text for the pressed keys, or null while only modifiers are down. */
export function fromEvent(event: KeyboardEvent): string | null {
  if (['Control', 'Shift', 'Alt', 'Meta'].includes(event.key)) return null
  const names: string[] = []
  if (event.ctrlKey) names.push('Ctrl')
  if (event.altKey) names.push('Alt')
  if (event.shiftKey) names.push('Shift')
  if (event.metaKey) names.push('Meta')
  let main = event.code
  if (main.startsWith('Key')) main = main.slice(3)
  else if (main.startsWith('Digit')) main = main.slice(5)
  else if (main === 'Backquote') main = '`'
  return [...names, main].join('+')
}

/** Releasing any key of the combination ends a hold. */
export function releases(combo: Combo, event: KeyboardEvent): boolean {
  if (event.code === combo.code) return true
  return (
    (combo.ctrl && (event.key === 'Control' || !event.ctrlKey)) ||
    (combo.alt && (event.key === 'Alt' || !event.altKey)) ||
    (combo.shift && (event.key === 'Shift' || !event.shiftKey)) ||
    (combo.meta && (event.key === 'Meta' || !event.metaKey))
  )
}
