import { useEffect } from 'react'
import { useDialogs } from '@/stores/dialogs'
import { useUiPrefs } from '@/stores/ui-prefs'

export type ShortcutId = 'palette' | 'newTask' | 'shortcuts' | 'dock' | 'close'

export interface Shortcut {
  id: ShortcutId
  /** What the person presses, for the help and the hints (one entry per key cap). */
  keys: string[]
  /** i18n key (under `shortcuts.`) of what it does. */
  label: string
  /** Handled by the global listener here (the dock and Esc have their own). */
  global: boolean
}

/** The single table of shortcuts: the listener, the help (`?`) and the Ctrl+K hints read it. */
export const SHORTCUTS: Shortcut[] = [
  { id: 'palette', keys: ['Ctrl', 'K'], label: 'palette', global: true },
  { id: 'newTask', keys: ['N'], label: 'newTask', global: true },
  { id: 'shortcuts', keys: ['?'], label: 'shortcuts', global: true },
  { id: 'dock', keys: ['Ctrl', '`'], label: 'dock', global: false },
  { id: 'close', keys: ['Esc'], label: 'close', global: false },
]

const FIELD = 'input, textarea, select, [contenteditable=""], [contenteditable="true"]'

/** The focus is in a terminal: xterm, or anywhere inside the dock. */
export function inTerminal(el: Element | null): boolean {
  return Boolean(el?.closest('.xterm, [data-terminal-dock]'))
}

function inField(el: Element | null): boolean {
  return Boolean(el?.closest(FIELD))
}

export interface ShortcutContext {
  singleKeyShortcuts: boolean
  /** Some dialog is open (Radix marks it role=dialog). */
  dialogOpen: boolean
}

/** Which shortcut a key event triggers, or null. Pure: the guards live here. */
export function shortcutFor(e: KeyboardEvent, ctx: ShortcutContext): ShortcutId | null {
  const target = e.target instanceof Element ? e.target : null

  // Ctrl+K is «kill line» in shells and CLIs: it never acts inside a terminal.
  if (e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey && e.key.toLowerCase() === 'k') {
    return inTerminal(target) ? null : 'palette'
  }

  if (!ctx.singleKeyShortcuts || e.ctrlKey || e.altKey || e.metaKey) return null
  if (inField(target) || inTerminal(target) || ctx.dialogOpen) return null
  if (e.key === '?') return 'shortcuts'
  if (e.key.toLowerCase() === 'n' && !e.shiftKey) return 'newTask'
  return null
}

/** One keydown listener for the whole app; mounted once, in the AppShell. */
export function useGlobalShortcuts() {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.isComposing) return
      const dialogs = useDialogs.getState()
      const id = shortcutFor(e, {
        singleKeyShortcuts: useUiPrefs.getState().singleKeyShortcuts,
        dialogOpen: Boolean(document.querySelector('[role="dialog"], [role="alertdialog"]')),
      })
      if (id === 'palette') {
        e.preventDefault()
        if (dialogs.palette) dialogs.closePalette()
        else dialogs.openPalette()
      } else if (id === 'newTask') {
        e.preventDefault()
        dialogs.openNewTask()
      } else if (id === 'shortcuts') {
        e.preventDefault()
        dialogs.openShortcuts()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
