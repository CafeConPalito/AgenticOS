import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { safeStorage } from '@/lib/safe-storage'

export interface TaskTarget {
  projectId: string
  agentId: string
}

interface UiPrefsState {
  /** `N`, `?`… without a modifier (Ajustes → General). */
  singleKeyShortcuts: boolean
  /** The project and agent of the last task created: «Nueva tarea» starts there. */
  lastTaskTarget: TaskTarget | null
  /** CLI alerts postponed in this session (not persisted). */
  snoozedAlerts: string[]
  setSingleKeyShortcuts: (value: boolean) => void
  setLastTaskTarget: (target: TaskTarget) => void
  snoozeAlert: (id: string) => void
}

export const useUiPrefs = create<UiPrefsState>()(
  persist(
    (set) => ({
      singleKeyShortcuts: true,
      lastTaskTarget: null,
      snoozedAlerts: [],
      setSingleKeyShortcuts: (singleKeyShortcuts) => set({ singleKeyShortcuts }),
      setLastTaskTarget: (lastTaskTarget) => set({ lastTaskTarget }),
      snoozeAlert: (id) =>
        set((s) =>
          s.snoozedAlerts.includes(id) ? s : { snoozedAlerts: [...s.snoozedAlerts, id] },
        ),
    }),
    {
      name: 'agentic-os.ui-prefs',
      storage: createJSONStorage(() => safeStorage),
      partialize: (s) => ({
        singleKeyShortcuts: s.singleKeyShortcuts,
        lastTaskTarget: s.lastTaskTarget,
      }),
    },
  ),
)
