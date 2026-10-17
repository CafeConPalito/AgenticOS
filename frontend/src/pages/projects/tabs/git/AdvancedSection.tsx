import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type SubmoduleInfo,
  type WorktreeInfo,
  useAddSubmodule,
  useLfs,
  useLfsPattern,
  useLfsPull,
  usePruneWorktrees,
  useRemoveSubmodule,
  useRemoveWorktree,
  useSubmodules,
  useUpdateSubmodules,
  useWorktrees,
} from '@/api/git-more'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useGitJobs } from '@/stores/git-jobs'
import { gitErrorText } from './git-errors'

/** Submodules, Git LFS and the worktrees of the repository. */
export function AdvancedSection({ repoId }: { repoId: string }) {
  return (
    <div className="flex flex-col gap-4 px-6 py-4">
      <SubmodulesPanel repoId={repoId} />
      <LfsPanel repoId={repoId} />
      <WorktreesPanel repoId={repoId} />
    </div>
  )
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-2 rounded-lg border border-sep p-3">
      <h3 className="text-[13px] font-medium">{title}</h3>
      {children}
    </section>
  )
}

function useRunner() {
  const { t } = useTranslation()
  return async (action: Promise<unknown>, done?: string) => {
    try {
      await action
      if (done) toast.success(done)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }
}

function SubmodulesPanel({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const run = useRunner()
  const submodules = useSubmodules(repoId)
  const update = useUpdateSubmodules(repoId)
  const add = useAddSubmodule(repoId)
  const remove = useRemoveSubmodule(repoId)
  const upsert = useGitJobs((state) => state.upsert)
  const [url, setUrl] = useState('')
  const [path, setPath] = useState('')
  const [removing, setRemoving] = useState<SubmoduleInfo | null>(null)

  async function onUpdate(target?: string) {
    try {
      upsert(await update.mutateAsync(target))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <Panel title={t('git.advanced.submodules')}>
      {(submodules.data ?? []).length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('git.advanced.noSubmodules')}</p>
      ) : (
        <>
          <ul className="text-[13px]">
            {(submodules.data ?? []).map((sub) => (
              <li key={sub.path} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1">
                <span className="font-mono">{sub.path}</span>
                <Badge variant={sub.state === 'ok' ? 'secondary' : 'outline'}>
                  {t(`git.advanced.submoduleState.${sub.state}`)}
                </Badge>
                <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground">
                  {sub.sha.slice(0, 7)} {sub.describe}
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  aria-label={`${t('git.advanced.update')} ${sub.path}`}
                  onClick={() => void onUpdate(sub.path)}
                >
                  {t('git.advanced.update')}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  aria-label={`${t('git.advanced.removeSubmodule')} ${sub.path}`}
                  onClick={() => setRemoving(sub)}
                >
                  {t('git.advanced.removeSubmodule')}
                </Button>
              </li>
            ))}
          </ul>
          <div>
            <Button type="button" size="sm" variant="outline" onClick={() => void onUpdate()}>
              {t('git.advanced.updateAll')}
            </Button>
          </div>
        </>
      )}
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (!url.trim() || !path.trim()) return
          void run(add.mutateAsync({ url: url.trim(), path: path.trim() })).then(() => {
            setUrl('')
            setPath('')
          })
        }}
      >
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder={t('git.advanced.submoduleUrl')}
          aria-label={t('git.advanced.submoduleUrl')}
          className="h-8 w-72 font-mono text-xs"
        />
        <Input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder={t('git.advanced.submodulePath')}
          aria-label={t('git.advanced.submodulePath')}
          className="h-8 w-48 font-mono text-xs"
        />
        <Button type="submit" size="sm" disabled={!url.trim() || !path.trim() || add.isPending}>
          {t('git.advanced.addSubmodule')}
        </Button>
      </form>
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={t('git.advanced.removeSubmoduleTitle', { path: removing?.path ?? '' })}
        description={t('git.advanced.removeSubmoduleDescription')}
        confirmLabel={t('git.advanced.removeSubmodule')}
        destructive
        onConfirm={() => {
          const sub = removing
          setRemoving(null)
          if (sub) void run(remove.mutateAsync(sub.path))
        }}
      />
    </Panel>
  )
}

function LfsPanel({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const run = useRunner()
  const lfs = useLfs(repoId)
  const pattern = useLfsPattern(repoId)
  const pull = useLfsPull(repoId)
  const upsert = useGitJobs((state) => state.upsert)
  const [value, setValue] = useState('')
  const state = lfs.data

  if (state && !state.installed)
    return (
      <Panel title={t('git.advanced.lfs')}>
        <p role="status" className="text-xs text-muted-foreground">
          {t('git.advanced.lfsMissing')}
        </p>
      </Panel>
    )

  return (
    <Panel title={t('git.advanced.lfs')}>
      <ul className="font-mono text-[13px]">
        {(state?.patterns ?? []).map((item) => (
          <li key={item} className="flex items-center gap-3 py-0.5">
            <span>{item}</span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              aria-label={`${t('git.advanced.untrack')} ${item}`}
              onClick={() => void run(pattern.mutateAsync({ action: 'untrack', pattern: item }))}
            >
              {t('git.advanced.untrack')}
            </Button>
          </li>
        ))}
      </ul>
      {state && state.patterns.length === 0 && (
        <p className="text-xs text-muted-foreground">{t('git.advanced.noLfs')}</p>
      )}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (!value.trim()) return
          void run(pattern.mutateAsync({ action: 'track', pattern: value.trim() })).then(() =>
            setValue(''),
          )
        }}
      >
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t('git.advanced.lfsPattern')}
          aria-label={t('git.advanced.lfsPattern')}
          className="h-8 w-48 font-mono text-xs"
        />
        <Button type="submit" size="sm" disabled={!value.trim()}>
          {t('git.advanced.track')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() =>
            void pull
              .mutateAsync()
              .then(upsert)
              .catch((error: unknown) => toast.error(gitErrorText(error, t)))
          }
        >
          {t('git.advanced.lfsPull')}
        </Button>
      </form>
    </Panel>
  )
}

function WorktreesPanel({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const run = useRunner()
  const trees = useWorktrees(repoId)
  const remove = useRemoveWorktree(repoId)
  const prune = usePruneWorktrees(repoId)
  const [removing, setRemoving] = useState<WorktreeInfo | null>(null)

  return (
    <Panel title={t('git.advanced.worktrees')}>
      <ul className="text-[13px]">
        {(trees.data ?? []).map((tree) => (
          <li key={tree.path} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1">
            <span className="min-w-0 flex-1 truncate font-mono text-xs" title={tree.path}>
              {tree.path}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {tree.branch ?? tree.head?.slice(0, 7)}
            </span>
            {tree.main && <Badge variant="secondary">{t('git.advanced.mainTree')}</Badge>}
            {tree.task && <Badge variant="outline">{t('git.advanced.taskTree')}</Badge>}
            {tree.prunable && <Badge variant="outline">{t('git.advanced.gone')}</Badge>}
            {!tree.main && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={`${t('git.advanced.removeTree')} ${tree.path}`}
                onClick={() => setRemoving(tree)}
              >
                {t('git.advanced.removeTree')}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void run(prune.mutateAsync(), t('git.advanced.pruned'))}
        >
          {t('git.advanced.prune')}
        </Button>
      </div>
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={t('git.advanced.removeTreeTitle', { path: removing?.path ?? '' })}
        description={t('git.advanced.removeTreeDescription')}
        confirmLabel={t('git.advanced.removeTree')}
        destructive
        onConfirm={() => {
          const tree = removing
          setRemoving(null)
          if (tree) void run(remove.mutateAsync({ path: tree.path, force: tree.prunable }))
        }}
      />
    </Panel>
  )
}
