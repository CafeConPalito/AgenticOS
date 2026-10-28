import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import '@/i18n'
import { useDialogs } from '@/stores/dialogs'
import { useUiPrefs } from '@/stores/ui-prefs'
import { resetClientLog } from '@/lib/client-log'

const DIALOGS_INITIAL = useDialogs.getState()
const PREFS_INITIAL = useUiPrefs.getState()

// findBy*/waitFor default to 1 s, too short for whole-app renders on a busy machine.
configure({ asyncUtilTimeout: 3000 })

// jsdom lacks these browser APIs used by the sidebar and Radix primitives.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
})
// Radix Select relies on pointer capture and scrollIntoView.
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.releasePointerCapture ??= () => {}
Element.prototype.scrollIntoView ??= () => {}
globalThis.IntersectionObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
} as unknown as typeof IntersectionObserver
// React Flow (the pipeline editor) reads the zoom from the viewport's transform matrix.
globalThis.DOMMatrixReadOnly ??= class {
  m22 = 1
} as unknown as typeof DOMMatrixReadOnly
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
  // Module-level stores outlive each test's render: back to their start.
  useDialogs.setState(DIALOGS_INITIAL, true)
  useUiPrefs.setState(PREFS_INITIAL, true)
  // Phase 20: the interface errors a test left pending are not sent during the next one.
  resetClientLog()
  document.documentElement.className = ''
})
