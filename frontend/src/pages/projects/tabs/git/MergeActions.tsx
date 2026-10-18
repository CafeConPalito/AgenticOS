import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type MergeMode, type OpResult, useMerge, useRebase } from '@/api/git-integration'
import { ConfirmDialog } from '@/components/ConfirmDialog'
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
import { gitErrorText } from './git-errors'

/** «Merge» and «Rebase» of another branch into / onto the current one, from a branch's row. */
export function MergeActions({
  repoId,
  branch,
  current,
}: {
  repoId: string
  branch: string
  current: string
}) {
  const { t } = useTranslation()
  const merge = useMerge(repoId)
  const rebase = useRebase(repoId)
  const [merging, setMerging] = useState(false)
  const [rebasing, setRebasing] = useState(false)
  const [mode, setMode] = useState<MergeMode>('no_ff')
  const [message, setMessage] = useState('')

  function report(result: OpResult) {
    if (result.status === 'conflicts') toast.warning(t('git.conflicts.more'))
    else if (result.status === 'up_to_date') toast.info(t('git.nothingToDo'))
    else if (result.status === 'squashed') toast.success(t('git.merge.squashed'))
    else toast.success(t('git.merge.done', { branch, current }))
  }

  async function onMerge() {
    setMerging(false)
    try {
      report(
        await merge.mutateAsync({
          ref: branch,
          mode,
          ...(mode === 'no_ff' && message.trim() ? { message: message.trim() } : {}),
        }),
      )
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onRebase() {
    setRebasing(false)
    try {
      report(await rebase.mutateAsync(branch))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        aria-label={`${t('git.merge.merge')} ${branch}`}
        onClick={() => {
          setMessage(t('git.merge.defaultMessage', { branch, current }))
          setMerging(true)
        }}
      >
        {t('git.merge.merge')}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        aria-label={`${t('git.merge.rebase')} ${branch}`}
        onClick={() => setRebasing(true)}
      >
        {t('git.merge.rebase')}
      </Button>

      <Dialog open={merging} onOpenChange={setMerging}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('git.merge.title', { branch, current })}</DialogTitle>
            <DialogDescription>{t('git.merge.description')}</DialogDescription>
          </DialogHeader>
          <fieldset className="flex flex-col gap-1.5 text-[13px]">
            {(['no_ff', 'ff', 'squash'] as const).map((value) => (
              <div key={value} className="flex items-start gap-2">
                <input
                  id={`merge-mode-${value}`}
                  type="radio"
                  name="merge-mode"
                  checked={mode === value}
                  onChange={() => setMode(value)}
                  className="mt-1"
                />
                <label htmlFor={`merge-mode-${value}`}>
                  <span className="font-medium">{t(`git.merge.modes.${value}`)}</span>
                  <span className="block text-xs text-muted-foreground">
                    {t(`git.merge.modesHelp.${value}`)}
                  </span>
                </label>
              </div>
            ))}
          </fieldset>
          {mode === 'no_ff' && (
            <Input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              aria-label={t('git.merge.message')}
            />
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setMerging(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="button" onClick={() => void onMerge()}>
              {t('git.merge.merge')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={rebasing}
        onOpenChange={setRebasing}
        title={t('git.merge.rebaseTitle', { current, branch })}
        description={t('git.merge.rebaseDescription')}
        confirmLabel={t('git.merge.rebase')}
        onConfirm={() => void onRebase()}
      />
    </>
  )
}
