import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useCopyPipeline, usePipeline } from '@/api/pipelines'
import { useProjects } from '@/api/projects'
import { ProjectMark } from '@/components/agentic/primitives'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { errorMessage } from '@/lib/form-errors'

/**
 * Phase 24: copies the pipeline of another project — stages, branches, exits, reviews and the
 * skills and connections of each stage, with the same agents; no tasks nor history. A stage
 * whose agent is archived or a draft is left without one, and the person is told.
 */
export function CopyPipelineDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId: string
}) {
  const { t } = useTranslation()
  const c = 'pipeline.copy'
  const projects = (useProjects().data ?? []).filter((p) => p.id !== projectId)
  const [from, setFrom] = useState('')
  const source = usePipeline(from, Boolean(from))
  const copy = useCopyPipeline(projectId)

  async function onCopy() {
    try {
      const copied = await copy.mutateAsync(from)
      for (const w of copied.warnings)
        toast.warning(t(`${c}.warning`, { stage: w.stage, agent: w.agent }))
      toast.success(t(`${c}.done`))
      onOpenChange(false)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t(`${c}.title`)}</DialogTitle>
          <DialogDescription>{t(`${c}.description`)}</DialogDescription>
        </DialogHeader>
        <label className="grid gap-1 text-[13px]">
          {t(`${c}.from`)}
          <Select value={from} onValueChange={setFrom}>
            <SelectTrigger aria-label={t(`${c}.from`)}>
              <SelectValue placeholder={t(`${c}.pick`)} />
            </SelectTrigger>
            <SelectContent>
              {projects.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  <ProjectMark name={p.name} color={p.color} avatar={p.avatar} />
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        {from && source.data === null && (
          <p role="note" className="text-[13px] text-muted-foreground">
            {t(`${c}.none`)}
          </p>
        )}
        {source.data && (
          <ol aria-label={t(`${c}.preview`)} className="grid gap-1 text-[13px]">
            {source.data.stages.map((s) => (
              <li key={s.id} className="flex gap-2">
                <span className="font-medium">{s.name}</span>
                <span className="text-muted-foreground">{s.agent_name ?? '—'}</span>
                {s.exit_condition && (
                  <span className="text-muted-foreground">· {t('pipeline.exit.badge')}</span>
                )}
              </li>
            ))}
          </ol>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={!source.data || copy.isPending}
            onClick={() => void onCopy()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t(`${c}.submit`)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
