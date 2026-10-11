import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { taskKeys } from './tasks'
import type { InboxItem, InboxSummary, NotificationSettings } from './types'

export const inboxKeys = {
  all: ['inbox'] as const,
  list: (status: 'pending' | 'resolved') => ['inbox', 'list', status] as const,
  summary: ['inbox', 'summary'] as const,
  settings: ['settings', 'notifications'] as const,
}

const POLL_MS = 3000

export function useInbox(status: 'pending' | 'resolved') {
  return useQuery({
    queryKey: inboxKeys.list(status),
    queryFn: () => api.get<InboxItem[]>(`/api/inbox?status=${status}`),
    refetchInterval: status === 'pending' ? POLL_MS : false,
  })
}

/** Counter for the sidebar and the notifier; polled while the app is open. */
export function useInboxSummary() {
  return useQuery({
    queryKey: inboxKeys.summary,
    queryFn: () => api.get<InboxSummary>('/api/inbox/summary'),
    refetchInterval: POLL_MS,
    // Notifications must keep coming while the window is in the background.
    refetchIntervalInBackground: true,
  })
}

function useInboxMutation<T>(fn: (vars: T) => Promise<InboxItem>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: taskKeys.all })
      return queryClient.invalidateQueries({ queryKey: inboxKeys.all })
    },
  })
}

export const useAnswerItem = () =>
  useInboxMutation(({ id, text }: { id: string; text: string }) =>
    api.post<InboxItem>(`/api/inbox/${id}/answer`, { text }),
  )

export const usePermissionItem = () =>
  useInboxMutation(({ id, approve }: { id: string; approve: boolean }) =>
    api.post<InboxItem>(`/api/inbox/${id}/${approve ? 'approve' : 'reject'}`),
  )

export const useReviewItem = () =>
  useInboxMutation(({ id, approve, reason }: { id: string; approve: boolean; reason?: string }) =>
    api.post<InboxItem>(`/api/inbox/${id}/review`, { approve, reason: reason ?? '' }),
  )

export const useDismissItem = () =>
  useInboxMutation((id: string) => api.post<InboxItem>(`/api/inbox/${id}/dismiss`))

export function markNotified(id: string) {
  return api.post<InboxItem>(`/api/inbox/${id}/notified`)
}

export function useNotificationSettings() {
  return useQuery({
    queryKey: inboxKeys.settings,
    queryFn: () => api.get<NotificationSettings>('/api/settings/notifications'),
  })
}

export function useSaveNotificationSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (values: NotificationSettings) =>
      api.put<NotificationSettings>('/api/settings/notifications', values),
    onSuccess: (values) => queryClient.setQueryData(inboxKeys.settings, values),
  })
}
