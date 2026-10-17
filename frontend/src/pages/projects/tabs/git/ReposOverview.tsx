import { FolderGit2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type BatchRequest, type RepoOverview, useBatch } from '@/api/git'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useGitJobs } from '@/stores/git-jobs'

type Ask = 'switch' | 'create_branch' | 'commit'

/** Every repository of the project with its state, and the actions that apply to several at
 * once (fetch, pull, push, the same branch or commit in all). */
export function ReposOverview({
  projectId,
  repos,
  selected,
  onSelect,
}: {
  projectId: string
  repos: RepoOverview[]
  selected: string
  onSelect: (repoId: string) => void
}) {
  const { t } = useTranslation()
  const batch = useBatch(projectId)
  const upsert = useGitJobs((state) => state.upsert)
  const [ticked, setTicked] = useState<ReadonlySet<string>>(new Set())
  const [asking, setAsking] = useState<Ask | null>(null)
  const [value, setValue] = useState('')

  const usable = repos.filter((r) => !r.missing)
  const chosen = ticked.size > 0 ? [...ticked] : usable.map((r) => r.repo_id)

  async function run(request: Omit<BatchRequest, 'repo_ids'>) {
    try {
      const items = await batch.mutateAsync({ ...request, repo_ids: chosen })
      for (const item of items) if (item.job) upsert(item.job)
      const failed = items.filter((item) => !item.ok)
      if (failed.length === 0) toast.success(t('git.batch.done', { count: items.length }))
      else
        toast.error(t('git.batch.failed', { count: failed.length }), {
          description: failed
            .map((item) => {
              const name = repos.find((r) => r.repo_id === item.repo_id)?.name ?? item.repo_id
              return `${name}: ${t(`git.errors.${item.error_code ?? 'git_failed'}`, { defaultValue: item.error ?? '' })}`
            })
            .join('\n'),
        })
    } catch {
      toast.error(t('git.batch.error'))
    }
  }

  function confirmAsk() {
    if (!asking) return
    const text = value.trim()
    setAsking(null)
    setValue('')
    void run(
      asking === 'commit' ? { action: 'commit', message: text } : { action: asking, name: text },
    )
  }

  return (
    <aside
      aria-label={t('git.repositories')}
      className="flex flex-col gap-3 border-r border-sep p-4"
    >
      <ul className="flex flex-col gap-1.5">
        {repos.map((repo) => {
          const status = repo.status
          return (
            <li key={repo.repo_id}>
              <div
                className={cn(
                  'flex items-start gap-2 rounded-lg border px-2.5 py-2 text-[13px]',
                  selected === repo.repo_id ? 'border-primary bg-accent' : 'border-sep bg-card',
                )}
              >
                <input
                  type="checkbox"
                  disabled={repo.missing}
                  checked={ticked.has(repo.repo_id)}
                  aria-label={`${t('git.batch.tick')} ${repo.name}`}
                  onChange={(e) =>
                    setTicked((previous) => {
                      const next = new Set(previous)
                      if (e.target.checked) next.add(repo.repo_id)
                      else next.delete(repo.repo_id)
                      return next
                    })
                  }
                  className="mt-1"
                />
                <button
                  type="button"
                  onClick={() => onSelect(repo.repo_id)}
                  aria-current={selected === repo.repo_id || undefined}
                  className="flex min-w-0 flex-1 flex-col gap-0.5 text-left"
                >
                  <span className="flex items-center gap-1.5 font-medium">
                    <FolderGit2 className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="truncate">{repo.name}</span>
                    {repo.linked && (
                      <Badge variant="secondary">{t('projects.repos.badgeLinked')}</Badge>
                    )}
                  </span>
                  {repo.missing ? (
                    <span className="text-xs text-status-failed">
                      {t('projects.repos.badgeMissing')}
                    </span>
                  ) : repo.error || !status ? (
                    <span className="text-xs text-status-failed">
                      {t(`git.errors.${repo.error ?? 'git_failed'}`, {
                        defaultValue: repo.error ?? '',
                      })}
                    </span>
                  ) : (
                    <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                      <span className="font-mono">{status.branch ?? status.head ?? '—'}</span>
                      {status.upstream && (
                        <span>
                          ↑{status.ahead} ↓{status.behind}
                        </span>
                      )}
                      {status.clean ? (
                        <span>{t('git.overview.clean')}</span>
                      ) : (
                        <span className="text-foreground">
                          {t('git.overview.changes', {
                            count:
                              status.staged.length +
                              status.unstaged.length +
                              status.conflicts.length,
                          })}
                        </span>
                      )}
                      {status.operation && (
                        <Badge variant="destructive">
                          {t(`git.operation.${status.operation}`)}
                        </Badge>
                      )}
                    </span>
                  )}
                </button>
              </div>
            </li>
          )
        })}
      </ul>

      <div role="group" aria-label={t('git.batch.title')} className="flex flex-col gap-1.5">
        <p className="text-xs text-muted-foreground">
          {ticked.size > 0
            ? t('git.batch.ticked', { count: ticked.size })
            : t('git.batch.all', { count: usable.length })}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {(['fetch', 'pull', 'push'] as const).map((action) => (
            <Button
              key={action}
              type="button"
              size="sm"
              variant="outline"
              disabled={batch.isPending}
              onClick={() => void run({ action })}
            >
              {t(`git.batch.${action}`)}
            </Button>
          ))}
          {(['switch', 'create_branch', 'commit'] as const).map((action) => (
            <Button
              key={action}
              type="button"
              size="sm"
              variant="outline"
              disabled={batch.isPending}
              onClick={() => setAsking(action)}
            >
              {t(`git.batch.${action}`)}
            </Button>
          ))}
        </div>
      </div>

      <Dialog open={asking !== null} onOpenChange={(open) => !open && setAsking(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{asking && t(`git.batch.ask.${asking}.title`)}</DialogTitle>
            <DialogDescription>
              {asking && t(`git.batch.ask.${asking}.description`, { count: chosen.length })}
            </DialogDescription>
          </DialogHeader>
          <Input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-label={asking ? t(`git.batch.ask.${asking}.title`) : ''}
            className={asking === 'commit' ? '' : 'font-mono'}
          />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setAsking(null)}>
              {t('common.cancel')}
            </Button>
            <Button type="button" disabled={!value.trim()} onClick={confirmAsk}>
              {t('git.batch.run')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  )
}
