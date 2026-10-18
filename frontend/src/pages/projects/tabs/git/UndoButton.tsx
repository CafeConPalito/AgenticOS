import { Undo2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useOperations, useUndo } from '@/api/git-integration'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { gitErrorText } from './git-errors'

/** «Deshacer» the last thing the app did to this repository (a merge, a reset, a deleted
 * branch…), if it can be undone without touching work done since. */
export function UndoButton({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const operations = useOperations(repoId)
  const undo = useUndo(repoId)
  const [asking, setAsking] = useState(false)
  const last = operations.data?.find((operation) => !operation.undone && !operation.in_progress)
  if (!last) return null

  const blocked = last.blocked_by !== null
  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        disabled={blocked || undo.isPending}
        title={
          blocked ? t(`git.undo.blocked.${last.blocked_by}`, { defaultValue: '' }) : last.label
        }
        onClick={() => setAsking(true)}
      >
        <Undo2 />
        {t('git.undo.button', { label: last.label })}
      </Button>
      <ConfirmDialog
        open={asking}
        onOpenChange={setAsking}
        title={t('git.undo.title', { label: last.label })}
        description={last.lost_files ? t('git.undo.withFiles') : t('git.undo.description')}
        confirmLabel={t('git.undo.confirm')}
        onConfirm={() => {
          setAsking(false)
          undo
            .mutateAsync(last.id)
            .then(() => toast.success(t('git.undo.done', { label: last.label })))
            .catch((error: unknown) => toast.error(gitErrorText(error, t)))
        }}
      />
    </>
  )
}
