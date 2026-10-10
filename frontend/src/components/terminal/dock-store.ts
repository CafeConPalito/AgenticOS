import { create } from 'zustand'
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware'

export type DockPosition = 'bottom' | 'right'

interface DockState {
  open: boolean
  position: DockPosition
  activeRunId: string | null
  toggle: () => void
  setOpen: (open: boolean) => void
  swapPosition: () => void
  /** Opens the dock on a run's tab. */
  show: (runId: string) => void
  setActive: (runId: string) => void
}

export const DOCK_DEFAULTS = { open: false, position: 'bottom', activeRunId: null } as const

// Storage can be unavailable (private mode, blocked site data): the dock then just forgets.
const safeStorage: StateStorage = {
  getItem: (name) => {
    try {
      return localStorage.getItem(name)
    } catch {
      return null
    }
  },
  setItem: (name, value) => {
    try {
      localStorage.setItem(name, value)
    } catch {
      // ignore
    }
  },
  removeItem: (name) => {
    try {
      localStorage.removeItem(name)
    } catch {
      // ignore
    }
  },
}

export const useDock = create<DockState>()(
  persist(
    (set) => ({
      ...DOCK_DEFAULTS,
      toggle: () => set((s) => ({ open: !s.open })),
      setOpen: (open) => set({ open }),
      swapPosition: () => set((s) => ({ position: s.position === 'bottom' ? 'right' : 'bottom' })),
      show: (runId) => set({ open: true, activeRunId: runId }),
      setActive: (runId) => set({ activeRunId: runId }),
    }),
    { name: 'agentic-os.dock', storage: createJSONStorage(() => safeStorage) },
  ),
)
