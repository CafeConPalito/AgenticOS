import { GitCompareArrows } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { type ChangesTarget, useChanges } from '@/api/changes'
import type { ChangesTotals } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { relativeTime } from '@/lib/time'
import { ChangesBadge } from './ChangesBadge'
import { ChangesViewer } from './ChangesViewer'

/** The diff in a wide side panel, with optional actions at the foot (a review's buttons). */
export function ChangesSheet({
  open,
  onOpenChange,
  title,
  target,
  footer,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  target: ChangesTarget
  footer?: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 sm:max-w-4xl">
        <SheetHeader className="border-b">
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{t('changes.sheetDescription')}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {target.kind === 'task' ? (
            <TaskChanges taskId={target.id} />
          ) : (
            <ChangesViewer target={target} />
          )}
        </div>
        {footer && <SheetFooter className="p-0">{footer}</SheetFooter>}
      </SheetContent>
    </Sheet>
  )
}

const WHOLE = 'task'

/** The diff of a task, with a selector to see only what one of its runs changed. */
export function TaskChanges({ taskId }: { taskId: string }) {
  const { t } = useTranslation()
  const whole = useChanges({ kind: 'task', id: taskId })
  const [picked, setPicked] = useState(WHOLE)
  const runs = whole.data?.runs ?? []
  const target: ChangesTarget =
    picked === WHOLE ? { kind: 'task', id: taskId } : { kind: 'run', id: picked }
  return (
    <div className="flex flex-col gap-3">
      {runs.length > 1 && (
        <div className="flex items-center gap-2">
          <span className="text-[12.5px] text-muted-foreground">{t('changes.show')}</span>
          <Select value={picked} onValueChange={setPicked}>
            <SelectTrigger aria-label={t('changes.show')} className="h-8 w-[320px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={WHOLE}>{t('changes.wholeTask')}</SelectItem>
              {runs.map((run) => (
                <SelectItem key={run.id} value={run.id}>
                  {t('changes.runOption', {
                    stage: run.stage_name ?? t('changes.run'),
                    attempt: run.attempt,
                    when: relativeTime(run.started_at ?? run.created_at),
                  })}
                  {run.totals ? ` · +${run.totals.additions} −${run.totals.deletions}` : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <ChangesViewer key={`${target.kind}-${target.id}`} target={target} />
    </div>
  )
}

/** «Ver cambios · 4 ficheros +120 −35»: opens the diff in a side panel. */
export function ChangesButton({
  target,
  title,
  totals,
  label,
  footer,
  className,
}: {
  target: ChangesTarget
  title: string
  totals?: ChangesTotals | null
  label?: string
  /** Actions at the foot of the panel; they receive a function that closes it. */
  footer?: (close: () => void) => React.ReactNode
  className?: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className={className}
        onClick={() => setOpen(true)}
      >
        <GitCompareArrows />
        {label ?? t('changes.view')}
        <ChangesBadge totals={totals} />
      </Button>
      {open && (
        <ChangesSheet
          open
          onOpenChange={setOpen}
          title={title}
          target={target}
          footer={footer?.(() => setOpen(false))}
        />
      )}
    </>
  )
}
