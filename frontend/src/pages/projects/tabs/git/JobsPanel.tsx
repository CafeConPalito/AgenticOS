import { Loader2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useCancelJob } from '@/api/git'
import { Button } from '@/components/ui/button'
import { useGitJobs } from '@/stores/git-jobs'

/** The fetch, pull and push running now, with their progress and a way to cancel them. */
export function JobsPanel({ repoIds }: { repoIds?: string[] }) {
  const { t } = useTranslation()
  const jobs = useGitJobs((state) => state.jobs)
  const cancel = useCancelJob()
  const shown = Object.values(jobs).filter(
    (job) => job.status === 'running' && (!repoIds || repoIds.includes(job.repo_id)),
  )
  if (shown.length === 0) return null
  return (
    <ul aria-label={t('git.jobs.title')} className="flex flex-col gap-1.5">
      {shown.map((job) => (
        <li
          key={job.id}
          className="flex items-center gap-3 rounded-lg border border-sep bg-card px-3 py-2 text-[13px]"
        >
          <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />
          <span className="font-medium">
            {t(`git.jobs.running.${job.kind}`, { defaultValue: job.kind })}
          </span>
          <span className="min-w-0 flex-1 truncate text-muted-foreground">
            {job.phase || job.message}
          </span>
          {job.percent !== null && (
            <span
              role="progressbar"
              aria-valuenow={job.percent}
              aria-valuemin={0}
              aria-valuemax={100}
              className="h-1.5 w-28 overflow-hidden rounded-full bg-accent"
            >
              <span
                className="block h-full bg-primary-action"
                style={{ width: `${job.percent}%` }}
              />
            </span>
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label={t('git.jobs.cancel')}
            onClick={() => cancel.mutate(job.id)}
          >
            <X />
          </Button>
        </li>
      ))}
    </ul>
  )
}
