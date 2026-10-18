import { ArrowDown, ArrowUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type OpResult,
  type TodoAction,
  useInteractiveRebase,
  useRebasePlan,
} from '@/api/git-integration'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { gitErrorText } from '@/pages/projects/tabs/git/git-errors'

const ACTIONS: TodoAction[] = ['pick', 'reword', 'squash', 'fixup', 'edit', 'drop']

interface Row {
  sha: string
  short: string
  subject: string
  action: TodoAction
  message: string
}

/** The list of an interactive rebase: the commits from `base` to the tip, oldest first, that the
 * person reorders, squashes, rewords, edits or drops before replaying them. */
export function InteractiveRebase({
  repoId,
  base,
  onDone,
}: {
  repoId: string
  base: string
  onDone: (result: OpResult) => void
}) {
  const { t } = useTranslation()
  const plan = useRebasePlan(repoId, base)
  const rebase = useInteractiveRebase(repoId)
  const [edited, setEdited] = useState<Row[] | null>(null)
  const initial = useMemo<Row[]>(
    () =>
      (plan.data ?? []).map((commit) => ({
        sha: commit.sha,
        short: commit.short,
        subject: commit.subject,
        action: 'pick',
        message: commit.subject,
      })),
    [plan.data],
  )
  const rows = edited ?? initial

  if (plan.isPending) return <Skeleton aria-busy className="h-32 rounded-lg" />
  if (plan.isError)
    return (
      <p role="alert" className="text-[13px] text-status-failed">
        {gitErrorText(plan.error, t)}
      </p>
    )
  if (rows.length === 0)
    return <p className="text-[13px] text-muted-foreground">{t('git.rebase.nothing')}</p>

  const change = (index: number, patch: Partial<Row>) =>
    setEdited(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  const move = (index: number, by: -1 | 1) => {
    const next = [...rows]
    const [row] = next.splice(index, 1)
    next.splice(index + by, 0, row)
    setEdited(next)
  }
  const kept = rows.filter((row) => row.action !== 'drop')
  const firstIsFold = kept[0] && (kept[0].action === 'squash' || kept[0].action === 'fixup')
  const dropped = rows.filter((row) => row.action === 'drop').length

  async function start() {
    try {
      const result = await rebase.mutateAsync({
        base,
        items: rows.map((row) => ({
          action: row.action,
          sha: row.sha,
          ...(row.action === 'reword' ? { message: row.message } : {}),
        })),
      })
      onDone(result)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[13px] text-muted-foreground">{t('git.rebase.help')}</p>
      <ol
        aria-label={t('git.rebase.list')}
        className="overflow-hidden rounded-lg border border-sep bg-card"
      >
        {rows.map((row, index) => (
          <li
            key={row.sha}
            className={cn(
              'flex flex-wrap items-center gap-2 border-b border-sep px-3 py-1.5 text-[13px] last:border-b-0',
              row.action === 'drop' && 'opacity-50',
            )}
          >
            <span className="flex gap-0.5">
              <Button
                type="button"
                size="icon"
                variant="ghost"
                disabled={index === 0}
                aria-label={`${t('git.rebase.up')} ${row.short}`}
                onClick={() => move(index, -1)}
              >
                <ArrowUp />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                disabled={index === rows.length - 1}
                aria-label={`${t('git.rebase.down')} ${row.short}`}
                onClick={() => move(index, 1)}
              >
                <ArrowDown />
              </Button>
            </span>
            <select
              value={row.action}
              onChange={(e) => change(index, { action: e.target.value as TodoAction })}
              aria-label={`${t('git.rebase.action')} ${row.short}`}
              className="h-8 rounded-md border border-input bg-background px-2 text-[13px]"
            >
              {ACTIONS.map((action) => (
                <option key={action} value={action}>
                  {t(`git.rebase.actions.${action}`)}
                </option>
              ))}
            </select>
            <span className="font-mono text-xs text-muted-foreground">{row.short}</span>
            {row.action === 'reword' ? (
              <Input
                value={row.message}
                onChange={(e) => change(index, { message: e.target.value })}
                aria-label={`${t('git.rebase.message')} ${row.short}`}
                className="h-8 min-w-0 flex-1"
              />
            ) : (
              <span className="min-w-0 flex-1 truncate">{row.subject}</span>
            )}
          </li>
        ))}
      </ol>
      {firstIsFold && (
        <p role="note" className="text-xs text-status-failed">
          {t('git.rebase.firstFold')}
        </p>
      )}
      {dropped > 0 && (
        <p role="note" className="text-xs text-muted-foreground">
          {t('git.rebase.dropping', { count: dropped })}
        </p>
      )}
      <Button
        type="button"
        disabled={Boolean(firstIsFold) || kept.length === 0 || rebase.isPending}
        onClick={() => void start()}
        className="self-end bg-primary-action text-white hover:bg-primary-action-hover"
      >
        {t('git.rebase.start')}
      </Button>
    </div>
  )
}
