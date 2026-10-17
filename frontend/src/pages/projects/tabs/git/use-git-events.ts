import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { invalidateRepo } from '@/api/git'
import { GitEventsSocket } from '@/lib/git-events'
import { useGitJobs } from '@/stores/git-jobs'

/** How long a finished job stays in the panel. */
const LINGER_MS = 6000

/**
 * Listens to the backend's Git events while the Git tab is open: a repository that changed
 * (by this app or by an agent) is read again, and the progress of fetch/pull/push shows.
 */
export function useGitEvents() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  useEffect(() => {
    const finished = new Set<string>()
    const socket = new GitEventsSocket((event) => {
      if (event.type === 'repo_changed') {
        invalidateRepo(queryClient, event.repo_id)
        return
      }
      const { job } = event
      useGitJobs.getState().upsert(job)
      if (job.status === 'running' || finished.has(job.id)) return
      finished.add(job.id)
      if (job.status === 'failed')
        toast.error(t(`git.jobs.failed.${job.kind}`, { defaultValue: job.message }), {
          description: t(`git.errors.${job.error_code ?? 'git_failed'}`, {
            defaultValue: job.message,
          }),
        })
      else if (job.status === 'succeeded')
        toast.success(t(`git.jobs.done.${job.kind}`, { defaultValue: job.kind }))
      setTimeout(() => useGitJobs.getState().dismiss(job.id), LINGER_MS)
    })
    void socket.connect()
    return () => socket.close()
  }, [queryClient, t])
}
