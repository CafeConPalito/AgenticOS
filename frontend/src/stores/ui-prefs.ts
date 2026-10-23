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
  /** The microphone used to dictate (a browser device id); null: the system's default. */
  microphoneId: string | null
  /** CLI alerts postponed in this session (not persisted). */
  snoozedAlerts: string[]
  setSingleKeyShortcuts: (value: boolean) => void
  setLastTaskTarget: (target: TaskTarget) => void
  setMicrophoneId: (id: string | null) => void
  snoozeAlert: (id: string) => void
}

export const useUiPrefs = create<UiPrefsState>()(
  persist(
    (set) => ({
      singleKeyShortcuts: true,
      lastTaskTarget: null,
      microphoneId: null,
      snoozedAlerts: [],
      setSingleKeyShortcuts: (singleKeyShortcuts) => set({ singleKeyShortcuts }),
      setLastTaskTarget: (lastTaskTarget) => set({ lastTaskTarget }),
      setMicrophoneId: (microphoneId) => set({ microphoneId }),
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
        microphoneId: s.microphoneId,
      }),
    },
  ),
)
