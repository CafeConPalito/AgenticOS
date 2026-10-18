import { Check, Minus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePreviewDecision } from '@/api/pipelines'
import type { PreviewResult } from '@/api/types'
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
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'
import { linksFrom, type Draft } from './model'

/** «Probar»: asks the decider which branches of a fork it would take for an example task. */
export function TryDecisionDialog({
  open,
  onOpenChange,
  projectId,
  draft,
  fork,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId: string
  draft: Draft
  /** Key of the stage whose branches are tried. */
  fork: string
}) {
  const { t } = useTranslation()
  const preview = usePreviewDecision(projectId)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [result, setResult] = useState<PreviewResult | null>(null)
  const stage = draft.stages.find((s) => s.key === fork)
  const branches = linksFrom(draft, fork)

  function run() {
    setResult(null)
    preview.mutate(
      {
        title: title.trim(),
        description,
        branches: branches.map((b) => ({
          name: b.name || draft.stages.find((s) => s.key === b.target)?.name || '?',
          condition: b.always ? t('pipeline.alwaysCondition') : b.condition,
        })),
        decider_cli: draft.deciderCli,
        decider_account_id: draft.deciderAccountId,
        decider_model: draft.deciderModel.trim() || null,
      },
      { onSuccess: setResult },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('pipeline.tryTitle', { name: stage?.name ?? '' })}</DialogTitle>
          <DialogDescription>{t('pipeline.tryHelp')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <label className="grid gap-1 text-[13px]">
            {t('pipeline.tryTask')}
            <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="grid gap-1 text-[13px]">
            {t('pipeline.tryDescription')}
            <Textarea
              value={description}
              rows={3}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          {preview.isError && (
            <p role="alert" className="text-[13px] text-status-failed">
              {errorMessage(preview.error)}
            </p>
          )}
          {result?.error && (
            <p role="alert" className="text-[13px] text-status-failed">
              {result.error}
            </p>
          )}
          {result && !result.error && (
            <>
              <ul aria-label={t('pipeline.tryResult')} className="grid gap-2">
                {result.branches.map((b) => (
                  <li key={b.name} className="flex gap-2 text-[13px]">
                    {b.take ? (
                      <Check
                        aria-label={t('pipeline.taken')}
                        className="mt-0.5 size-4 shrink-0 text-status-done"
                      />
                    ) : (
                      <Minus
                        aria-label={t('pipeline.notTaken')}
                        className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      />
                    )}
                    <span>
                      <strong>{b.name}</strong>
                      {b.reason && <span className="text-muted-foreground"> — {b.reason}</span>}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-[12px] text-muted-foreground">
                {t('pipeline.tryCost', {
                  model: result.model ?? '',
                  seconds: result.seconds,
                  cost: result.cost_usd === null ? '—' : `$${result.cost_usd.toFixed(4)}`,
                })}
              </p>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('pipeline.tryClose')}
          </Button>
          <Button
            disabled={!title.trim() || preview.isPending}
            onClick={run}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {preview.isPending ? t('pipeline.trying') : t('pipeline.tryRun')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
