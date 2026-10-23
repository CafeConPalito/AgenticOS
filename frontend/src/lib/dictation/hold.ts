import { useEffect } from 'react'
import { useDictationSettings, useDictationStatus } from '@/api/dictation'
import { useUiPrefs } from '@/stores/ui-prefs'
import { fieldIdOf, releaseHold, startDictation } from './controller'
import { matches, parseShortcut, releases } from './shortcut'

/** Hold the dictation shortcut in a field with a microphone, talk, let go (ADR 0023). Mounted
 * once, in the AppShell. The shortcut does not type anything into the field. */
export function useHoldToDictate() {
  const settings = useDictationSettings().data
  const status = useDictationStatus().data
  const deviceId = useUiPrefs((s) => s.microphoneId)
  const enabled = Boolean(status?.enabled)
  const shortcut = settings?.shortcut
  const maxSeconds = settings?.max_seconds ?? 300

  useEffect(() => {
    const combo = shortcut ? parseShortcut(shortcut) : null
    if (!enabled || !combo) return
    let held = false

    function onKeyDown(event: KeyboardEvent) {
      if (!combo || event.isComposing || !matches(combo, event)) return
      const fieldId = fieldIdOf(document.activeElement)
      if (!fieldId) return // not in a field with a microphone: the key keeps its usual job
      event.preventDefault() // also the repeats of a held key
      if (event.repeat || held) return
      held = true
      void startDictation(fieldId, { mode: 'hold', maxSeconds, deviceId: deviceId ?? undefined })
    }

    function onKeyUp(event: KeyboardEvent) {
      if (!held || !combo || !releases(combo, event)) return
      held = false
      releaseHold()
    }

    function onBlur() {
      if (!held) return
      held = false
      releaseHold()
    }

    window.addEventListener('keydown', onKeyDown, true)
    window.addEventListener('keyup', onKeyUp, true)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onKeyDown, true)
      window.removeEventListener('keyup', onKeyUp, true)
      window.removeEventListener('blur', onBlur)
    }
  }, [enabled, shortcut, maxSeconds, deviceId])
}
