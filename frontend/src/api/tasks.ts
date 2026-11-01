import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { agentKeys } from './agents'
import type {
  AgentQueue,
  BranchDecision,
  JoinClash,
  Priority,
  SchedulerState,
  Task,
  TaskEvent,
  TaskStatus,
  TreeNode,
} from './types'

export interface TaskFilters {
  projectId?: string
  agentId?: string
  status?: TaskStatus[]
  parentTaskId?: string
  /** Also the lanes of forked tasks, as tasks of their own (the board by stage). */
  lanes?: boolean
}

export const taskKeys = {
  all: ['tasks'] as const,
  list: (filters: TaskFilters) => ['tasks', 'list', filters] as const,
  detail: (id: string) => ['tasks', id] as const,
  events: (id: string) => ['tasks', id, 'events'] as const,
  queue: (agentId: string) => ['tasks', 'queue', agentId] as const,
  scheduler: ['tasks', 'scheduler'] as const,
}

/** Tasks the scheduler may still move: lists poll while one of them is shown. A task that
 * forked changes with its lanes, whatever the state it shows. */
export const isMoving = (task: Pick<Task, 'status'> & { phase?: Task['phase'] }) =>
  task.status === 'queued' || task.status === 'running' || Boolean(task.phase)

const POLL_MS = 2500

function query(filters: TaskFilters): string {
  const params = new URLSearchParams()
  if (filters.projectId) params.set('project_id', filters.projectId)
  if (filters.agentId) params.set('agent_id', filters.agentId)
  for (const status of filters.status ?? []) params.append('status', status)
  if (filters.lanes) params.set('lanes', 'include')
  const text = params.toString()
  return text ? `?${text}` : ''
}

export function useTasks(filters: TaskFilters = {}) {
  return useQuery({
    queryKey: taskKeys.list(filters),
    queryFn: () => api.get<Task[]>(`/api/tasks${query(filters)}`),
    refetchInterval: (q) => (q.state.data?.some(isMoving) ? POLL_MS : false),
  })
}

/** Ctrl+K: tasks whose title contains `q`, or with that `T-n` number. Nothing for an empty `q`. */
export function useTaskSearch(q: string) {
  const text = q.trim()
  return useQuery({
    queryKey: ['tasks', 'search', text] as const,
    queryFn: () => api.get<Task[]>(`/api/tasks?q=${encodeURIComponent(text)}&limit=14`),
    enabled: text.length > 0,
    placeholderData: keepPreviousData,
  })
}

export function useTask(id: string | undefined) {
  return useQuery({
    queryKey: taskKeys.detail(id ?? ''),
    queryFn: () => api.get<Task>(`/api/tasks/${id}`),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data && isMoving(q.state.data) ? POLL_MS : false),
  })
}

export function useTaskEvents(id: string, poll: boolean) {
  return useQuery({
    queryKey: taskKeys.events(id),
    queryFn: () => api.get<TaskEvent[]>(`/api/tasks/${id}/events`),
    refetchInterval: poll ? POLL_MS : false,
  })
}

export function useTaskTree(id: string, poll: boolean) {
  return useQuery({
    queryKey: [...taskKeys.detail(id), 'tree'],
    queryFn: () => api.get<TreeNode[]>(`/api/tasks/${id}/tree`),
    refetchInterval: poll ? POLL_MS : false,
  })
}

export function useSubtasks(parentId: string) {
  return useQuery({
    queryKey: taskKeys.list({ parentTaskId: parentId }),
    queryFn: () => api.get<Task[]>(`/api/tasks?parent_task_id=${parentId}`),
    refetchInterval: (q) => (q.state.data?.some(isMoving) ? POLL_MS : false),
  })
}

export function useAgentQueue(agentId: string) {
  return useQuery({
    queryKey: taskKeys.queue(agentId),
    queryFn: () => api.get<AgentQueue>(`/api/agents/${agentId}/queue`),
    refetchInterval: (q) =>
      q.state.data && (q.state.data.running.length || q.state.data.queued.length) ? POLL_MS : false,
  })
}

/** Everything that shows tasks (lists, queues, agents' counters, the scheduler) is refreshed. */
function useInvalidateTasks() {
  const queryClient = useQueryClient()
  return (task?: Task) => {
    if (task) queryClient.setQueryData(taskKeys.detail(task.id), task)
    void queryClient.invalidateQueries({ queryKey: agentKeys.all })
    return queryClient.invalidateQueries({ queryKey: taskKeys.all })
  }
}

export interface TaskCreate {
  project_id: string
  title: string
  description?: string
  priority?: Priority
  agent_id?: string | null
  enqueue?: boolean
  /** Branches fixed by hand: fork stage id → ids of its links (the decider is not asked). */
  preset_lanes?: Record<string, string[]>
}

export function useCreateTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (body: TaskCreate) => api.post<Task>('/api/tasks', body),
    onSuccess: (task) => invalidate(task),
  })
}

export function useUpdateTask(id: string) {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (body: Partial<Pick<Task, 'title' | 'description' | 'priority' | 'agent_id'>>) =>
      api.patch<Task>(`/api/tasks/${id}`, body),
    onSuccess: (task) => invalidate(task),
  })
}

export type TaskAction =
  | { action: 'enqueue' }
  | { action: 'retry' }
  | { action: 'cancel' }
  | { action: 'complete'; summary: string }
  | { action: 'review'; approve: true }
  | { action: 'review'; approve: false; reason: string; target_stage_id: string | null }

function actionRequest(id: string, action: TaskAction): Promise<Task> {
  switch (action.action) {
    case 'complete':
      return api.post<Task>(`/api/tasks/${id}/complete`, { summary: action.summary })
    case 'review':
      return api.post<Task>(
        `/api/tasks/${id}/review`,
        action.approve
          ? { action: 'approve' }
          : { action: 'reject', reason: action.reason, target_stage_id: action.target_stage_id },
      )
    default:
      return api.post<Task>(`/api/tasks/${id}/${action.action}`)
  }
}

export function useTaskAction(id: string) {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (action: TaskAction) => actionRequest(id, action),
    onSuccess: (task) => invalidate(task),
  })
}

export function useOpenWorktree() {
  return useMutation({
    mutationFn: (id: string) => api.post<void>(`/api/tasks/${id}/open-worktree`),
  })
}

export function useReorderQueue(agentId: string) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (taskIds: string[]) =>
      api.put<AgentQueue>(`/api/agents/${agentId}/queue`, { task_ids: taskIds }),
    onSuccess: (queue) => {
      queryClient.setQueryData(taskKeys.queue(agentId), queue)
      return invalidate()
    },
  })
}

export function useScheduler() {
  return useQuery({
    queryKey: taskKeys.scheduler,
    queryFn: () => api.get<SchedulerState>('/api/scheduler'),
  })
}

export function useSetSchedulerPaused() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (paused: boolean) =>
      api.post<SchedulerState>(`/api/scheduler/${paused ? 'pause' : 'resume'}`),
    onSuccess: (state) => queryClient.setQueryData(taskKeys.scheduler, state),
  })
}

// ------------------------------------------------------------ forks and lanes (phase 13)
export function useTaskDecisions(id: string, enabled = true) {
  return useQuery({
    queryKey: [...taskKeys.detail(id), 'decisions'],
    queryFn: () => api.get<BranchDecision[]>(`/api/tasks/${id}/decisions`),
    enabled,
  })
}

/** The person picks the branches of a fork (or changes the ones proposed). */
export function useDecide(id: string) {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (chosen: string[]) => api.post<Task>(`/api/tasks/${id}/decision`, { chosen }),
    onSuccess: (task) => invalidate(task),
  })
}

/** Phase 24: «Seguir con el pipeline» for a task that ended at an exit. */
export function useContinueTask(id: string) {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: () => api.post<Task>(`/api/tasks/${id}/continue`),
    onSuccess: (task) => invalidate(task),
  })
}

export function useAddLane(id: string) {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (linkId: string) => api.post<Task>(`/api/tasks/${id}/lanes`, { link_id: linkId }),
    onSuccess: () => invalidate(),
  })
}

export const joinKey = (id: string) => [...taskKeys.detail(id), 'join'] as const

/** What keeps the branches of a forked task from being merged. */
export function useJoin(id: string, enabled: boolean) {
  return useQuery({
    queryKey: joinKey(id),
    queryFn: () => api.get<JoinClash[]>(`/api/tasks/${id}/join`),
    enabled,
    staleTime: 0,
  })
}

export interface JoinResolution {
  repo_id: string
  name: string
  path: string
  conflicts: string[]
}

export function useStartJoinEditor(id: string) {
  return useMutation({
    mutationFn: () => api.post<JoinResolution[]>(`/api/tasks/${id}/join/editor`),
  })
}

export function useFinishJoinEditor(id: string) {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (repoId: string) =>
      api.post<{ conflicts: string[]; joined: boolean }>(`/api/tasks/${id}/join/editor/finish`, {
        repo_id: repoId,
      }),
    onSuccess: () => invalidate(),
  })
}

export function useJoinAgent(id: string) {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (agentId: string) =>
      api.post<Task>(`/api/tasks/${id}/join/agent`, { agent_id: agentId }),
    onSuccess: () => invalidate(),
  })
}
