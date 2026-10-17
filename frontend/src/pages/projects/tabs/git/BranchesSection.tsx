import { GitBranch, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import {
  type BranchInfo,
  useBranches,
  useCreateBranch,
  useDeleteBranches,
  useRenameBranch,
  useSwitchBranch,
} from '@/api/git'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/time'
import { gitErrorText } from './git-errors'
import { MergeActions } from './MergeActions'

type Filter = 'all' | 'tasks' | 'open'

/** The branches of a repository: the ones of tasks with their task, how far each is from its
 * upstream and from the base, and the operations on them. */
export function BranchesSection({ repoId, base }: { repoId: string; base: string | null }) {
  const { t } = useTranslation()
  const branches = useBranches(repoId)
  const create = useCreateBranch(repoId)
  const switchTo = useSwitchBranch(repoId)
  const rename = useRenameBranch(repoId)
  const remove = useDeleteBranches(repoId)
  const [filter, setFilter] = useState<Filter>('all')
  const [name, setName] = useState('')
  const [renaming, setRenaming] = useState<{ old: string; value: string } | null>(null)
  const [deleting, setDeleting] = useState<BranchInfo | null>(null)
  const current = branches.data?.find((b) => b.current)?.name ?? null

  const shown = useMemo(() => {
    const all = branches.data ?? []
    if (filter === 'tasks') return all.filter((b) => b.task_code)
    if (filter === 'open') return all.filter((b) => !b.remote && !b.integrated && !b.current)
    return all
  }, [branches.data, filter])

  async function run(action: Promise<unknown>, done?: string) {
    try {
      await action
      if (done) toast.success(done)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onCreate(event: React.FormEvent) {
    event.preventDefault()
    const value = name.trim()
    if (!value) return
    await run(
      create.mutateAsync({ name: value, switch: true }),
      t('git.branches.created', { name: value }),
    )
    setName('')
  }

  async function onDelete(branch: BranchInfo, force: boolean) {
    try {
      const result = await remove.mutateAsync({ names: [branch.name], force })
      const reason = result.failed[branch.name]
      if (reason === 'not_merged') {
        setDeleting(branch) // asks again, this time knowing the work would be lost
        return
      }
      if (reason) toast.error(t(`git.errors.${reason}`, { defaultValue: reason }))
      else toast.success(t('git.branches.deleted', { name: branch.name }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  if (branches.isPending) return <Skeleton aria-busy className="m-6 h-40 rounded-lg" />

  return (
    <div className="flex flex-col gap-3 px-6 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label={t('git.branches.filter')} className="flex gap-1">
          {(['all', 'tasks', 'open'] as const).map((value) => (
            <Button
              key={value}
              type="button"
              size="sm"
              variant={filter === value ? 'default' : 'outline'}
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {t(`git.branches.filters.${value}`)}
            </Button>
          ))}
        </div>
        <form onSubmit={(event) => void onCreate(event)} className="flex gap-2">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('git.branches.newName')}
            aria-label={t('git.branches.newName')}
            className="h-8 w-48 font-mono text-xs"
          />
          <Button type="submit" size="sm" disabled={!name.trim() || create.isPending}>
            <GitBranch />
            {t('git.branches.create')}
          </Button>
        </form>
      </div>

      {shown.length === 0 ? (
        <EmptyState icon={GitBranch} title={t('git.branches.empty')} />
      ) : (
        <ul className="overflow-hidden rounded-lg border border-sep bg-card">
          {shown.map((branch) => (
            <li
              key={`${branch.remote}:${branch.name}`}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-sep px-3 py-2 text-[13px] last:border-b-0"
            >
              <span className="flex min-w-0 flex-1 items-center gap-2">
                <span className="truncate font-mono" title={branch.name}>
                  {branch.name}
                </span>
                {branch.current && <Badge>{t('git.branches.current')}</Badge>}
                {branch.remote && <Badge variant="secondary">{t('git.branches.remote')}</Badge>}
                {branch.name === base && <Badge variant="outline">{t('git.branches.base')}</Badge>}
                {branch.task_code && (
                  <Link
                    to={`/tablero/tareas/${branch.task_id}`}
                    className="text-xs text-primary hover:underline"
                  >
                    {branch.task_code} · {branch.task_title}
                  </Link>
                )}
                {branch.task_status && (
                  <Badge variant="outline">
                    {t(`tasks.status.${branch.task_status}`, branch.task_status)}
                  </Badge>
                )}
                {branch.integrated && !branch.current && branch.name !== base && (
                  <Badge variant="secondary">{t('git.branches.integrated')}</Badge>
                )}
              </span>
              <span className="text-xs text-muted-foreground">
                {branch.upstream && (
                  <span title={branch.upstream}>
                    ↑{branch.ahead} ↓{branch.behind}
                  </span>
                )}
                {branch.base_ahead !== null && branch.name !== base && (
                  <span className="ml-3" title={t('git.branches.vsBase', { base: base ?? '' })}>
                    {t('git.branches.aheadOfBase', {
                      ahead: branch.base_ahead,
                      behind: branch.base_behind ?? 0,
                    })}
                  </span>
                )}
                <span className="ml-3">{relativeTime(branch.last_commit)}</span>
              </span>
              {renaming?.old === branch.name ? (
                <form
                  className="flex gap-1"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void run(
                      rename.mutateAsync({ old: renaming.old, new: renaming.value.trim() }),
                    ).then(() => setRenaming(null))
                  }}
                >
                  <Input
                    value={renaming.value}
                    onChange={(e) => setRenaming({ ...renaming, value: e.target.value })}
                    aria-label={t('git.branches.renameTo')}
                    className="h-7 w-40 font-mono text-xs"
                  />
                  <Button type="submit" size="sm">
                    {t('common.save')}
                  </Button>
                </form>
              ) : (
                <span className="flex gap-1">
                  {!branch.current && current && (
                    <MergeActions repoId={repoId} branch={branch.name} current={current} />
                  )}
                  {!branch.current && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void run(switchTo.mutateAsync(branch.name))}
                    >
                      {t('git.branches.switch')}
                    </Button>
                  )}
                  {!branch.remote && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => setRenaming({ old: branch.name, value: branch.name })}
                    >
                      {t('git.branches.rename')}
                    </Button>
                  )}
                  {!branch.remote && !branch.current && (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      aria-label={`${t('git.branches.delete')} ${branch.name}`}
                      onClick={() => void onDelete(branch, false)}
                    >
                      <Trash2 />
                    </Button>
                  )}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={t('git.branches.forceTitle', { name: deleting?.name ?? '' })}
        description={t('git.branches.forceDescription')}
        confirmLabel={t('git.branches.forceConfirm')}
        destructive
        onConfirm={() => {
          const branch = deleting
          setDeleting(null)
          if (branch) void onDelete(branch, true)
        }}
      />
    </div>
  )
}
