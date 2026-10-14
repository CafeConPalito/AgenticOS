import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { safeStorage } from '@/lib/safe-storage'

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
