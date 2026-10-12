import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { settingsKeys } from './settings'

/** Cleanup (phase 08): task branches and the retention of the runs' terminal logs. */
export interface TaskBranch {
  name: string
  task_id: string | null
  task_code: string | null
  task_status: string | null
  /** Merged into the project's base branch. */
  merged: boolean
  last_commit: string
  /** Its task is still open, or a worktree has it checked out. */
  in_use: boolean
}

export interface ProjectBranches {
  project_id: string
  project_name: string
  branches: TaskBranch[]
  error: string | null
}

export interface MaintenanceSettings {
  log_retention_days: number | null
}

export const maintenanceKeys = {
  branches: ['maintenance', 'branches'] as const,
  settings: ['maintenance', 'settings'] as const,
}

export function useTaskBranches() {
  return useQuery({
    queryKey: maintenanceKeys.branches,
    queryFn: () => api.get<ProjectBranches[]>('/api/maintenance/branches'),
  })
}

export function useDeleteBranches() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { project_id: string; branches: string[]; force?: boolean }) =>
      api.post<{ deleted: string[] }>('/api/maintenance/branches/delete', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: maintenanceKeys.branches }),
  })
}

export function useMaintenanceSettings() {
  return useQuery({
    queryKey: maintenanceKeys.settings,
    queryFn: () => api.get<MaintenanceSettings>('/api/settings/maintenance'),
  })
}

export function useSaveMaintenanceSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: MaintenanceSettings) =>
      api.put<MaintenanceSettings>('/api/settings/maintenance', body),
    onSuccess: (data) => queryClient.setQueryData(maintenanceKeys.settings, data),
  })
}

export function useCleanLogs() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.post<{ runs: number; freed_bytes: number }>('/api/maintenance/logs/cleanup'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: settingsKeys.dataDir }),
  })
}
