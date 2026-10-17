import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type CommitDetail, useCreateBranch } from '@/api/git'
import {
  type OpResult,
  type ResetMode,
  useCherryPick,
  useReset,
  useRevert,
} from '@/api/git-integration'
import { InteractiveRebase } from '@/components/git/InteractiveRebase'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { gitErrorText } from './git-errors'

/** What can be done from a commit of the history: pick it, revert it, branch from it, move the
 * branch to it, or rewrite the commits that come after it. */
export function CommitActions({ repoId, commit }: { repoId: string; commit: CommitDetail }) {
  const { t } = useTranslation()
  const pick = useCherryPick(repoId)
  const revert = useRevert(repoId)
  const reset = useReset(repoId)
  const create = useCreateBranch(repoId)
  const [mode, setMode] = useState<ResetMode>('mixed')
  const [confirmReset, setConfirmReset] = useState(false)
  const [rewriting, setRewriting] = useState(false)
  const [branchName, setBranchName] = useState('')

  function report(result: OpResult, done: string) {
    if (result.status === 'conflicts') toast.warning(t('git.conflicts.more'))
    else if (result.status === 'up_to_date') toast.info(t('git.nothingToDo'))
    else toast.success(done)
  }

  async function run(action: Promise<OpResult>, done: string) {
    try {
      report(await action, done)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onBranch(event: React.FormEvent) {
    event.preventDefault()
    const name = branchName.trim()
    if (!name) return
    try {
      await create.mutateAsync({ name, start: commit.sha })
      toast.success(t('git.branches.created', { name }))
      setBranchName('')
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <div
      role="group"
      aria-label={t('git.commitActions.title')}
      className="flex flex-wrap items-center gap-2 rounded-lg border border-sep bg-card px-3 py-2"
    >
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={pick.isPending}
        onClick={() => void run(pick.mutateAsync([commit.sha]), t('git.commitActions.picked'))}
      >
        {t('git.commitActions.cherryPick')}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={revert.isPending}
        onClick={() => void run(revert.mutateAsync([commit.sha]), t('git.commitActions.reverted'))}
      >
        {t('git.commitActions.revert')}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={commit.parents.length === 0}
        onClick={() => setRewriting(true)}
      >
        {t('git.commitActions.rewrite')}
      </Button>
      <span className="flex items-center gap-1">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as ResetMode)}
          aria-label={t('git.commitActions.resetMode')}
          className="h-8 rounded-md border border-input bg-background px-2 text-[13px]"
        >
          {(['soft', 'mixed', 'hard'] as const).map((value) => (
            <option key={value} value={value}>
              {t(`git.commitActions.modes.${value}`)}
            </option>
          ))}
        </select>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={reset.isPending}
          onClick={() =>
            mode === 'hard'
              ? setConfirmReset(true)
              : void run(
                  reset.mutateAsync({ ref: commit.sha, mode }),
                  t('git.commitActions.resetDone'),
                )
          }
        >
          {t('git.commitActions.reset')}
        </Button>
      </span>
      <form onSubmit={(event) => void onBranch(event)} className="flex items-center gap-1">
        <Input
          value={branchName}
          onChange={(e) => setBranchName(e.target.value)}
          placeholder={t('git.commitActions.branchHere')}
          aria-label={t('git.commitActions.branchHere')}
          className="h-8 w-40 font-mono text-xs"
        />
        <Button type="submit" size="sm" variant="outline" disabled={!branchName.trim()}>
          {t('git.branches.create')}
        </Button>
      </form>

      <ConfirmDialog
        open={confirmReset}
        onOpenChange={setConfirmReset}
        title={t('git.commitActions.hardTitle', { sha: commit.short })}
        description={t('git.commitActions.hardDescription')}
        confirmLabel={t('git.commitActions.reset')}
        destructive
        onConfirm={() => {
          setConfirmReset(false)
          void run(
            reset.mutateAsync({ ref: commit.sha, mode: 'hard' }),
            t('git.commitActions.resetDone'),
          )
        }}
      />
      <Sheet open={rewriting} onOpenChange={setRewriting}>
        <SheetContent className="w-full gap-0 sm:max-w-3xl">
          <SheetHeader className="border-b">
            <SheetTitle>{t('git.rebase.title', { sha: commit.short })}</SheetTitle>
            <SheetDescription>{t('git.rebase.description')}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-auto p-4">
            {rewriting && (
              <InteractiveRebase
                repoId={repoId}
                base={commit.parents[0]}
                onDone={(result) => {
                  setRewriting(false)
                  report(result, t('git.rebase.done'))
                }}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
