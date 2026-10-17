import { GitMerge } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { RepoStatus } from '@/api/git'
import { useProceed } from '@/api/git-integration'
import { ConflictEditor } from '@/components/git/ConflictEditor'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { gitErrorText } from './git-errors'

/** A merge, rebase, cherry-pick or revert that stopped: its conflicts, and the three ways out
 * (continue, skip, abort). */
export function OperationBar({ repoId, status }: { repoId: string; status: RepoStatus }) {
  const { t } = useTranslation()
  const proceed = useProceed(repoId)
  const [editing, setEditing] = useState<string | null>(null)
  const [aborting, setAborting] = useState(false)
  const operation = status.operation
  if (!operation || operation === 'bisect') return null

  async function go(action: 'continue' | 'skip' | 'abort') {
    try {
      const result = await proceed.mutateAsync(action)
      if (result.status === 'conflicts') toast.warning(t('git.conflicts.more'))
      else if (action === 'continue') toast.success(t('git.operationDone'))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  const unresolved = status.conflicts
  return (
    <section
      role="status"
      aria-label={t(`git.operation.${operation}`)}
      className="mx-6 mt-3 flex flex-col gap-2 rounded-lg border border-status-waiting/40 bg-status-waiting/10 px-3 py-2.5 text-[13px]"
    >
      <div className="flex flex-wrap items-center gap-2">
        <GitMerge className="size-4" aria-hidden />
        <span className="font-medium">{t(`git.operation.${operation}`)}</span>
        <span className="ml-auto flex gap-2">
          <Button
            type="button"
            size="sm"
            disabled={unresolved.length > 0 || proceed.isPending}
            onClick={() => void go('continue')}
          >
            {t('git.operations.continue')}
          </Button>
          {operation !== 'merge' && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={proceed.isPending}
              onClick={() => void go('skip')}
            >
              {t('git.operations.skip')}
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={proceed.isPending}
            onClick={() => setAborting(true)}
          >
            {t('git.operations.abort')}
          </Button>
        </span>
      </div>
      {unresolved.length > 0 && (
        <ul aria-label={t('git.conflicts.title')} className="flex flex-col gap-1">
          {unresolved.map((file) => (
            <li key={file.path} className="flex items-center gap-2">
              <span className="font-mono text-xs">{file.path}</span>
              <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(file.path)}>
                {t('git.conflicts.resolve')}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {unresolved.length === 0 && (
        <p className="text-xs text-muted-foreground">{t('git.conflicts.allResolved')}</p>
      )}

      <Sheet open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <SheetContent className="w-full gap-0 sm:max-w-5xl">
          <SheetHeader className="border-b">
            <SheetTitle>{t('git.conflicts.editorTitle', { path: editing ?? '' })}</SheetTitle>
            <SheetDescription>{t('git.conflicts.editorDescription')}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-auto p-4">
            {editing && (
              <ConflictEditor repoId={repoId} path={editing} onDone={() => setEditing(null)} />
            )}
          </div>
        </SheetContent>
      </Sheet>
      <ConfirmDialog
        open={aborting}
        onOpenChange={setAborting}
        title={t('git.operations.abortTitle')}
        description={t('git.operations.abortDescription')}
        confirmLabel={t('git.operations.abort')}
        destructive
        onConfirm={() => {
          setAborting(false)
          void go('abort')
        }}
      />
    </section>
  )
}
