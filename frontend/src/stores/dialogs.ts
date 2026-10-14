import { create } from 'zustand'
import type { Team } from '@/api/types'

export interface NewTaskInit {
  agentId?: string
  projectId?: string
  stageId?: string
}

export interface NewAgentInit {
  teamId?: string
}

interface DialogsState {
  /** Non-null while «Nueva tarea» is open; holds what the opener preselects. */
  newTask: NewTaskInit | null
  newAgent: boolean
  /** What «Nuevo agente» starts with when opened from a team's «+ Agente». */
  newAgentInit: NewAgentInit | null
  newProject: boolean
  newTeam: Team | 'new' | null
  palette: boolean
  shortcuts: boolean
  openNewTask: (init?: NewTaskInit) => void
  openNewAgent: (init?: NewAgentInit) => void
  openNewProject: () => void
  /** «Nuevo equipo» (no argument) or the edition of a team. */
  openTeam: (team?: Team) => void
  closeTeam: () => void
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
  newAgentInit: null,
  newProject: false,
  newTeam: null,
  palette: false,
  shortcuts: false,
  openNewTask: (init = {}) => set({ newTask: init, palette: false }),
  // Used as a click handler too: anything that is not a team id is ignored.
  openNewAgent: (init) =>
    set({
      newAgent: true,
      newAgentInit: typeof init?.teamId === 'string' ? { teamId: init.teamId } : null,
      palette: false,
    }),
  openNewProject: () => set({ newProject: true, palette: false }),
  openTeam: (team) => set({ newTeam: team ?? 'new', palette: false }),
  closeTeam: () => set({ newTeam: null }),
  openPalette: () => set({ palette: true }),
  openShortcuts: () => set({ shortcuts: true, palette: false }),
  closeNewTask: () => set({ newTask: null }),
  closeNewAgent: () => set({ newAgent: false, newAgentInit: null }),
  closeNewProject: () => set({ newProject: false }),
  closePalette: () => set({ palette: false }),
  closeShortcuts: () => set({ shortcuts: false }),
}))
