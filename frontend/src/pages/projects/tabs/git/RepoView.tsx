import { ArrowDown, ArrowUp, CloudDownload, GitMerge } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type JobState,
  type RepoOverview,
  useBranches,
  useFetch,
  usePull,
  usePush,
  useRepoStatus,
  useSwitchBranch,
} from '@/api/git'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/time'
import { useGitJobs } from '@/stores/git-jobs'
import { BranchesSection } from './BranchesSection'
import { ChangesSection } from './ChangesSection'
import { gitErrorText } from './git-errors'
import { HistorySection } from './HistorySection'
import { JobsPanel } from './JobsPanel'

export const SECTIONS = ['changes', 'history', 'branches'] as const
export type Section = (typeof SECTIONS)[number]

/** One repository: its branch and how far it is from its remote, the network buttons and the
 * sections (changes, history, branches). */
export function RepoView({
  repo,
  section,
  onSection,
}: {
  repo: RepoOverview
  section: Section
  onSection: (section: Section) => void
}) {
  const { t } = useTranslation()
  const status = useRepoStatus(repo.repo_id)
  const branches = useBranches(repo.repo_id)
  const fetchRemote = useFetch(repo.repo_id)
  const pull = usePull(repo.repo_id)
  const push = usePush(repo.repo_id)
  const switchTo = useSwitchBranch(repo.repo_id)
  const upsert = useGitJobs((state) => state.upsert)
  const info = status.data

  async function start(action: Promise<JobState>) {
    try {
      upsert(await action)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  if (repo.missing)
    return (
      <p role="alert" className="px-6 py-4 text-[13px] text-status-failed">
        {t('git.repoMissing', { name: repo.name })}
      </p>
    )

  const local = (branches.data ?? []).filter((b) => !b.remote)
  return (
    <div className="flex min-w-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-sep px-6 py-3">
        <h2 className="text-[15px] font-medium">{repo.name}</h2>
        {!info ? (
          <Skeleton className="h-6 w-40" />
        ) : (
          <>
            <label className="flex items-center gap-1.5 text-[13px]">
              <span className="sr-only">{t('git.branch')}</span>
              <select
                aria-label={t('git.branch')}
                value={info.branch ?? ''}
                onChange={(e) =>
                  void switchTo.mutateAsync(e.target.value).catch((error: unknown) => {
                    toast.error(gitErrorText(error, t))
                  })
                }
                className="h-8 max-w-56 rounded-md border border-input bg-background px-2 font-mono text-[12.5px]"
              >
                {info.branch === null && (
                  <option value="">{t('git.detached', { sha: info.head ?? '' })}</option>
                )}
                {local.map((branch) => (
                  <option key={branch.name} value={branch.name}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </label>
            {info.upstream && (
              <span
                className="flex items-center gap-1 text-xs text-muted-foreground"
                title={info.upstream}
              >
                <ArrowUp className="size-3" aria-hidden />
                <span aria-label={t('git.ahead')}>{info.ahead}</span>
                <ArrowDown className="size-3" aria-hidden />
                <span aria-label={t('git.behind')}>{info.behind}</span>
              </span>
            )}
            {info.last_fetch && (
              <span className="text-xs text-muted-foreground">
                {t('git.lastFetch', { when: relativeTime(info.last_fetch) })}
              </span>
            )}
          </>
        )}
        <span className="ml-auto flex gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={fetchRemote.isPending}
            onClick={() => void start(fetchRemote.mutateAsync())}
          >
            <CloudDownload />
            {t('git.fetch')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={pull.isPending}
            onClick={() => void start(pull.mutateAsync(undefined))}
          >
            <ArrowDown />
            {t('git.pull')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={push.isPending}
            onClick={() => void start(push.mutateAsync())}
          >
            <ArrowUp />
            {t('git.push')}
          </Button>
        </span>
      </header>

      {info?.operation && (
        <p
          role="status"
          className="mx-6 mt-3 flex items-center gap-2 rounded-md border border-status-waiting/40 bg-status-waiting/10 px-3 py-2 text-[13px]"
        >
          <GitMerge className="size-4" aria-hidden />
          {t(`git.operation.${info.operation}`)}
        </p>
      )}
      <div className="px-6 pt-3 empty:hidden">
        <JobsPanel repoIds={[repo.repo_id]} />
      </div>

      <nav aria-label={t('git.sections')} className="flex gap-1 px-6 pt-3">
        {SECTIONS.map((id) => (
          <Button
            key={id}
            type="button"
            size="sm"
            variant={section === id ? 'default' : 'ghost'}
            aria-current={section === id || undefined}
            onClick={() => onSection(id)}
          >
            {t(`git.section.${id}`)}
            {id === 'changes' && info && !info.clean ? (
              <span className="ml-1.5 rounded-full bg-accent px-1.5 text-[11px]">
                {info.staged.length + info.unstaged.length + info.conflicts.length}
              </span>
            ) : null}
          </Button>
        ))}
      </nav>

      {section === 'changes' && <ChangesSection repoId={repo.repo_id} />}
      {section === 'history' && <HistorySection repoId={repo.repo_id} />}
      {section === 'branches' && <BranchesSection repoId={repo.repo_id} base={repo.base_branch} />}
    </div>
  )
}
