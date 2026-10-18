import { Archive } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type StashEntry,
  useApplyStash,
  useDropStash,
  usePushStash,
  useStashDiff,
  useStashes,
  useStashToBranch,
} from '@/api/git-more'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/time'
import { gitErrorText } from './git-errors'

/** The stash: put the work in progress aside, bring it back (keeping it or not), turn it into a
 * branch or drop it. */
export function StashSection({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const stashes = useStashes(repoId)
  const push = usePushStash(repoId)
  const apply = useApplyStash(repoId)
  const drop = useDropStash(repoId)
  const toBranch = useStashToBranch(repoId)
  const [message, setMessage] = useState('')
  const [untracked, setUntracked] = useState(true)
  const [dropping, setDropping] = useState<StashEntry | null>(null)
  const [viewing, setViewing] = useState<string | null>(null)
  const [branching, setBranching] = useState<{ ref: string; name: string } | null>(null)
  const diff = useStashDiff(repoId, viewing)

  async function run(action: Promise<unknown>, done?: string) {
    try {
      await action
      if (done) toast.success(done)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onPush(event: React.FormEvent) {
    event.preventDefault()
    try {
      const result = await push.mutateAsync({
        message: message.trim() || undefined,
        include_untracked: untracked,
      })
      if (result.stored) toast.success(t('git.stash.stored'))
      else toast.info(t('git.stash.nothing'))
      setMessage('')
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onApply(entry: StashEntry, pop: boolean) {
    try {
      const result = await apply.mutateAsync({ ref: entry.ref, drop: pop })
      if (result.status === 'conflicts') toast.warning(t('git.stash.conflicts'))
      else toast.success(t(pop ? 'git.stash.popped' : 'git.stash.applied'))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  if (stashes.isPending) return <Skeleton aria-busy className="m-6 h-40 rounded-lg" />

  return (
    <div className="flex flex-col gap-3 px-6 py-4">
      <form onSubmit={(event) => void onPush(event)} className="flex flex-wrap items-center gap-2">
        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={t('git.stash.message')}
          aria-label={t('git.stash.message')}
          className="h-8 w-64 text-xs"
        />
        <label className="flex items-center gap-1.5 text-xs">
          <input
            type="checkbox"
            checked={untracked}
            onChange={(e) => setUntracked(e.target.checked)}
          />
          {t('git.stash.untracked')}
        </label>
        <Button type="submit" size="sm" disabled={push.isPending}>
          <Archive />
          {t('git.stash.push')}
        </Button>
      </form>

      {(stashes.data ?? []).length === 0 ? (
        <EmptyState icon={Archive} title={t('git.stash.empty')} />
      ) : (
        <ul className="overflow-hidden rounded-lg border border-sep bg-card">
          {(stashes.data ?? []).map((entry) => (
            <li
              key={entry.ref}
              className="flex flex-col gap-2 border-b border-sep px-3 py-2 text-[13px] last:border-b-0"
            >
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono text-xs text-muted-foreground">{entry.ref}</span>
                <span className="min-w-0 flex-1 truncate" title={entry.message}>
                  {entry.message}
                </span>
                <span className="text-xs text-muted-foreground">{relativeTime(entry.date)}</span>
                <span className="flex gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setViewing(viewing === entry.ref ? null : entry.ref)}
                  >
                    {t('git.stash.view')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => void onApply(entry, false)}
                  >
                    {t('git.stash.apply')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => void onApply(entry, true)}
                  >
                    {t('git.stash.pop')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setBranching({ ref: entry.ref, name: '' })}
                  >
                    {t('git.stash.toBranch')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label={`${t('git.stash.drop')} ${entry.ref}`}
                    onClick={() => setDropping(entry)}
                  >
                    {t('git.stash.drop')}
                  </Button>
                </span>
              </div>
              {branching?.ref === entry.ref && (
                <form
                  className="flex gap-2"
                  onSubmit={(event) => {
                    event.preventDefault()
                    const name = branching.name.trim()
                    if (!name) return
                    void run(
                      toBranch.mutateAsync({ ref: entry.ref, name }),
                      t('git.stash.branchCreated', { name }),
                    ).then(() => setBranching(null))
                  }}
                >
                  <Input
                    value={branching.name}
                    onChange={(e) => setBranching({ ...branching, name: e.target.value })}
                    placeholder={t('git.branches.newName')}
                    aria-label={t('git.branches.newName')}
                    className="h-7 w-52 font-mono text-xs"
                  />
                  <Button type="submit" size="sm">
                    {t('git.branches.create')}
                  </Button>
                </form>
              )}
              {viewing === entry.ref && (
                <ul aria-label={t('git.stash.files')} className="font-mono text-xs">
                  {diff.isPending && <Skeleton aria-busy className="h-8 rounded" />}
                  {(diff.data?.repos.flatMap((r) => r.files) ?? []).map((file) => (
                    <li key={file.path} className="flex gap-3">
                      <span className="text-muted-foreground">{file.status}</span>
                      <span className="truncate">{file.path}</span>
                      <span className="ml-auto text-muted-foreground">
                        +{file.additions} −{file.deletions}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={dropping !== null}
        onOpenChange={(open) => !open && setDropping(null)}
        title={t('git.stash.dropTitle', { ref: dropping?.ref ?? '' })}
        description={t('git.stash.dropDescription')}
        confirmLabel={t('git.stash.drop')}
        destructive
        onConfirm={() => {
          const entry = dropping
          setDropping(null)
          if (entry) void run(drop.mutateAsync(entry.ref), t('git.stash.dropped'))
        }}
      />
    </div>
  )
}
