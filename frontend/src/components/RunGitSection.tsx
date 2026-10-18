import { GitCommitHorizontal, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { hasGitActivity, type RunRepoGit, useRunGit, useUndoRunGit } from '@/api/run-git'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { gitErrorText } from '@/pages/projects/tabs/git/git-errors'

/** «Git» of a run: the commits, branches, tags and pushes it made in each repository, and
 * «Deshacer lo que hizo esta ejecución». Hidden when the run did nothing with git. */
export function RunGitSection({ runId }: { runId: string }) {
  const { t } = useTranslation()
  const git = useRunGit(runId)
  const undo = useUndoRunGit(runId)
  const [confirming, setConfirming] = useState(false)

  if (!hasGitActivity(git.data)) return null
  const repos = (git.data ?? []).filter((r) => r.activity)
  const undoable = repos.some((r) => r.can_undo)
  const pushed = repos.some((r) => r.pushed)

  async function onUndo() {
    try {
      const report = await undo.mutateAsync()
      const items = Object.values(report.repos).flatMap((r) => r.items)
      const skipped = items.filter((i) => i.result === 'skipped')
      if (skipped.length)
        toast.warning(
          t('runs.git.undoneWithSkipped', {
            skipped: skipped
              .map(
                (i) =>
                  `${i.branch} (${t(`runs.git.reason.${i.reason ?? 'other'}`, { defaultValue: t('runs.git.reason.other') })})`,
              )
              .join(', '),
          }),
        )
      else toast.success(t('runs.git.undone'))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <section
      aria-labelledby="run-git-title"
      className="rounded-[10px] border bg-subtle px-3.5 py-3"
    >
      <header className="mb-2 flex items-center justify-between gap-2">
        <h2 id="run-git-title" className="flex items-center gap-1.5 text-[12.5px] font-medium">
          <GitCommitHorizontal className="size-3.5" aria-hidden />
          {t('runs.git.title')}
        </h2>
        {undoable && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={undo.isPending}
            onClick={() => setConfirming(true)}
          >
            <Undo2 />
            {t('runs.git.undo')}
          </Button>
        )}
      </header>
      <div className="flex flex-col gap-3">
        {repos.map((repo) => (
          <RepoActivity key={repo.repo_id ?? repo.path} repo={repo} />
        ))}
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('runs.git.undoTitle')}
        description={t(pushed ? 'runs.git.undoDescriptionPushed' : 'runs.git.undoDescription')}
        confirmLabel={t('runs.git.undo')}
        destructive
        onConfirm={() => {
          setConfirming(false)
          void onUndo()
        }}
      />
    </section>
  )
}

function RepoActivity({ repo }: { repo: RunRepoGit }) {
  const { t } = useTranslation()
  const found = repo.activity
  if (!found) return null
  return (
    <div className="flex flex-col gap-1 text-[13px]">
      <div className="flex items-center gap-2">
        <span className="font-medium">{repo.name}</span>
        {found.undone && <Badge variant="outline">{t('runs.git.undoneBadge')}</Badge>}
      </div>
      {found.commits.length > 0 && (
        <ul aria-label={t('runs.git.commits', { name: repo.name })} className="text-xs">
          {found.commits.map((commit) => (
            <li key={commit.sha} className="flex gap-2">
              <span className="font-mono text-muted-foreground">{commit.sha.slice(0, 7)}</span>
              <span className="min-w-0 truncate">{commit.subject}</span>
              {commit.kind !== 'commit' && (
                <Badge variant="secondary">{t(`runs.git.kind.${commit.kind}`)}</Badge>
              )}
            </li>
          ))}
        </ul>
      )}
      {found.branches.length > 0 && (
        <ul aria-label={t('runs.git.branches', { name: repo.name })} className="text-xs">
          {found.branches.map((branch) => (
            <li key={branch.name}>
              <span className="font-mono">{branch.name}</span>{' '}
              <span className="text-muted-foreground">
                {branch.start === null
                  ? t('runs.git.created')
                  : branch.end === null
                    ? t('runs.git.deleted')
                    : t('runs.git.moved')}
              </span>
            </li>
          ))}
        </ul>
      )}
      {found.tags.length > 0 && (
        <p className="text-xs">
          {t('runs.git.tags')}:{' '}
          <span className="font-mono">{found.tags.map((x) => x.name).join(', ')}</span>
        </p>
      )}
      {found.pushes.length > 0 && (
        <ul aria-label={t('runs.git.pushes', { name: repo.name })} className="text-xs">
          {found.pushes.map((push) => (
            <li key={`${push.remote}/${push.branch}`} className="flex items-center gap-2">
              <span className="font-mono">
                {push.remote}/{push.branch}
              </span>
              {push.forced && <Badge variant="destructive">{t('runs.git.forced')}</Badge>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
