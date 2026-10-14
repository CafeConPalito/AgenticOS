import { create } from 'zustand'

export interface NewTaskInit {
  agentId?: string
  projectId?: string
  stageId?: string
}

interface DialogsState {
  /** Non-null while «Nueva tarea» is open; holds what the opener preselects. */
  newTask: NewTaskInit | null
  newAgent: boolean
  newProject: boolean
  palette: boolean
  shortcuts: boolean
  openNewTask: (init?: NewTaskInit) => void
  openNewAgent: () => void
  openNewProject: () => void
  openPalette: () => void
  openShortcuts: () => void
  closeNewTask: () => void
  closeNewAgent: () => void
  closeNewProject: () => void
  closePalette: () => void
  closeShortcuts: () => void
}

/** Which global dialog is open. They are mounted once, in the AppShell. */
export const useDialogs = create<DialogsState>()((set) => ({
  newTask: null,
  newAgent: false,
  newProject: false,
  palette: false,
  shortcuts: false,
  openNewTask: (init = {}) => set({ newTask: init, palette: false }),
  openNewAgent: () => set({ newAgent: true, palette: false }),
  openNewProject: () => set({ newProject: true, palette: false }),
  openPalette: () => set({ palette: true }),
  openShortcuts: () => set({ shortcuts: true, palette: false }),
  closeNewTask: () => set({ newTask: null }),
  closeNewAgent: () => set({ newAgent: false }),
  closeNewProject: () => set({ newProject: false }),
  closePalette: () => set({ palette: false }),
  closeShortcuts: () => set({ shortcuts: false }),
}))
