import { ArrowLeft, ArrowRight, CornerUpLeft, Plus, Workflow, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import {
  useDeletePipeline,
  usePipeline,
  usePipelineFromTemplate,
  useSavePipeline,
} from '@/api/pipelines'
import type { Pipeline, Project } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'

const NONE = '__none__'

/** A stage being edited. `key` is stable while editing; `rejectTo` points at another key. */
interface DraftStage {
  key: string
  id: string | null
  name: string
  agentId: string | null
  requiresReview: boolean
  rejectTo: string | null
  activeTasks: number
}

interface Draft {
  name: string
  maxRejections: number
  stages: DraftStage[]
}

let draftSeq = 0
const newKey = () => `new-${++draftSeq}`

function toDraft(pipeline: Pipeline): Draft {
  return {
    name: pipeline.name,
    maxRejections: pipeline.max_rejections,
    stages: pipeline.stages.map((s) => ({
      key: s.id,
      id: s.id,
      name: s.name,
      agentId: s.agent_id,
      requiresReview: s.requires_review,
      rejectTo: s.reject_to_stage_id,
      activeTasks: s.active_tasks,
    })),
  }
}

/** A rejection may only point at an earlier stage: moves can break that, so it is dropped. */
function normalize(stages: DraftStage[]): DraftStage[] {
  return stages.map((stage, i) => {
    const target = stages.findIndex((s) => s.key === stage.rejectTo)
    return target >= 0 && target < i ? stage : { ...stage, rejectTo: null }
  })
}

export function PipelineTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const pipeline = usePipeline(project.id)
  const fromTemplate = usePipelineFromTemplate(project.id)
  const [blank, setBlank] = useState(false)

  if (pipeline.isPending) return null
  if (!pipeline.data && !blank)
    return (
      <div className="px-6 pt-5 pb-8">
        <EmptyState
          icon={Workflow}
          title={t('pipeline.emptyTitle')}
          description={t('pipeline.emptyDescription')}
        >
          <div className="flex gap-2">
            <Button
              onClick={() =>
                fromTemplate.mutate('web', { onError: (e) => toast.error(errorMessage(e)) })
              }
              disabled={fromTemplate.isPending}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {t('pipeline.useTemplate')}
            </Button>
            <Button variant="outline" onClick={() => setBlank(true)}>
              {t('pipeline.startBlank')}
            </Button>
          </div>
        </EmptyState>
      </div>
    )
  return (
    <PipelineEditor
      key={pipeline.data?.id ?? 'new'}
      project={project}
      pipeline={pipeline.data ?? null}
    />
  )
}

function PipelineEditor({ project, pipeline }: { project: Project; pipeline: Pipeline | null }) {
  const { t } = useTranslation()
  const agents = (useAgents().data ?? []).filter((a) => a.status !== 'draft')
  const save = useSavePipeline(project.id)
  const remove = useDeletePipeline(project.id)
  const initial = useMemo<Draft>(
    () =>
      pipeline
        ? toDraft(pipeline)
        : {
            name: '',
            maxRejections: 3,
            stages: [
              {
                key: newKey(),
                id: null,
                name: t('pipeline.newStage'),
                agentId: null,
                requiresReview: false,
                rejectTo: null,
                activeTasks: 0,
              },
            ],
          },
    [pipeline, t],
  )
  const [draft, setDraft] = useState<Draft>(initial)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const saved = pipeline ? toDraft(pipeline) : null
  const dirty = !saved || JSON.stringify(draft) !== JSON.stringify(saved)

  const setStages = (update: (stages: DraftStage[]) => DraftStage[]) =>
    setDraft((d) => ({ ...d, stages: normalize(update(d.stages)) }))
  const patch = (key: string, values: Partial<DraftStage>) =>
    setStages((stages) => stages.map((s) => (s.key === key ? { ...s, ...values } : s)))
  const move = (index: number, by: -1 | 1) =>
    setStages((stages) => {
      const next = [...stages]
      ;[next[index], next[index + by]] = [next[index + by], next[index]]
      return next
    })

  async function onSave() {
    const stages = draft.stages
    try {
      const result = await save.mutateAsync({
        name: draft.name,
        max_rejections: draft.maxRejections,
        stages: stages.map((s) => ({
          id: s.id,
          name: s.name.trim(),
          agent_id: s.agentId,
          requires_review: s.requiresReview,
          reject_to: s.rejectTo ? stages.findIndex((x) => x.key === s.rejectTo) : null,
        })),
      })
      setDraft(toDraft(result))
      toast.success(t('pipeline.saved'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const name = (key: string | null) => draft.stages.find((s) => s.key === key)?.name ?? ''

  return (
    <div className="flex flex-col gap-3 px-6 pt-5 pb-8">
      <UnsavedChangesGuard when={dirty && Boolean(pipeline)} />
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[15px] font-medium">{t('pipeline.title')}</h2>
          <p className="text-xs text-muted-foreground">{t('pipeline.help')}</p>
        </div>
        <Button
          variant="outline"
          className="border-dashed"
          onClick={() =>
            setStages((stages) => [
              ...stages,
              {
                key: newKey(),
                id: null,
                name: t('pipeline.newStage'),
                agentId: null,
                requiresReview: false,
                rejectTo: null,
                activeTasks: 0,
              },
            ])
          }
        >
          <Plus />
          {t('pipeline.addStage')}
        </Button>
      </div>
      <div
        className="overflow-x-auto rounded-xl border bg-subtle p-7"
        style={{
          backgroundImage: 'radial-gradient(var(--border) 1px, transparent 1px)',
          backgroundSize: '16px 16px',
        }}
      >
        <ol className="flex items-stretch gap-0">
          {draft.stages.map((stage, index) => (
            <li key={stage.key} className="flex items-stretch">
              {index > 0 && (
                <span aria-hidden className="flex w-11 items-center justify-center self-center">
                  <span className="h-0.5 w-8 bg-ring" />
                  <ArrowRight className="-ml-1 size-3 text-ring" />
                </span>
              )}
              <article
                aria-label={t('pipeline.stage', { n: index + 1 })}
                className="flex w-[300px] flex-col gap-2.5 rounded-xl border bg-card p-3"
              >
                <div className="flex items-center gap-1">
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {t('pipeline.stage', { n: index + 1 }).toUpperCase()}
                  </span>
                  <span className="ml-auto flex">
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label={t('pipeline.moveLeft')}
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                    >
                      <ArrowLeft />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label={t('pipeline.moveRight')}
                      disabled={index === draft.stages.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      <ArrowRight />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label={t('pipeline.remove')}
                      title={
                        stage.activeTasks
                          ? t('pipeline.inUse', { count: stage.activeTasks })
                          : undefined
                      }
                      disabled={draft.stages.length === 1 || stage.activeTasks > 0}
                      onClick={() =>
                        setStages((stages) => stages.filter((s) => s.key !== stage.key))
                      }
                    >
                      <X />
                    </Button>
                  </span>
                </div>
                <Input
                  aria-label={t('pipeline.stageName', { n: index + 1 })}
                  value={stage.name}
                  maxLength={80}
                  onChange={(e) => patch(stage.key, { name: e.target.value })}
                  className="h-8 border-transparent bg-transparent px-1 text-[15px] font-medium"
                />
                <Select
                  value={stage.agentId ?? NONE}
                  onValueChange={(v) => patch(stage.key, { agentId: v === NONE ? null : v })}
                >
                  <SelectTrigger
                    aria-label={t('pipeline.agent', { n: index + 1 })}
                    className="h-11 w-full"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>{t('pipeline.noAgent')}</SelectItem>
                    {agents.map((a) => (
                      <SelectItem key={a.id} value={a.id}>
                        <AgentAvatar name={a.name} color={a.color} size={20} />
                        <span>
                          {a.name}
                          {a.role && <span className="text-muted-foreground"> · {a.role}</span>}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <label className="flex items-center gap-2 text-[12.5px]">
                  <Switch
                    checked={stage.requiresReview}
                    onCheckedChange={(v) => patch(stage.key, { requiresReview: v })}
                  />
                  {t('pipeline.requiresReview')}
                </label>
                {index > 0 && (
                  <div className="flex items-center gap-2 text-[12.5px]">
                    <span className="shrink-0 text-muted-foreground">{t('pipeline.rejectTo')}</span>
                    <Select
                      value={stage.rejectTo ?? NONE}
                      onValueChange={(v) => patch(stage.key, { rejectTo: v === NONE ? null : v })}
                    >
                      <SelectTrigger
                        aria-label={`${t('pipeline.rejectTo')} (${stage.name})`}
                        className="h-7 min-w-0 flex-1 text-[12.5px]"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE}>{t('pipeline.noReject')}</SelectItem>
                        {draft.stages.slice(0, index).map((s) => (
                          <SelectItem key={s.key} value={s.key}>
                            {s.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {stage.rejectTo && (
                  <span className="inline-flex items-center gap-1.5 text-[12px] text-status-failed">
                    <span className="size-1.5 rounded-full bg-current" />
                    {t('pipeline.canReject')}
                  </span>
                )}
              </article>
            </li>
          ))}
        </ol>
        <ul className="mt-4 flex flex-wrap gap-2">
          {draft.stages
            .filter((s) => s.rejectTo)
            .map((s) => (
              <li
                key={s.key}
                className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-status-failed px-2.5 py-0.5 text-[12px] text-status-failed"
              >
                <CornerUpLeft className="size-3" />
                {t('pipeline.rejectLabel', { from: s.name, to: name(s.rejectTo) })}
              </li>
            ))}
        </ul>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-[13px]">
          {t('pipeline.maxRejections')}
          <Input
            type="number"
            min={1}
            max={10}
            value={draft.maxRejections}
            onChange={(e) =>
              setDraft((d) => ({
                ...d,
                maxRejections: Math.min(10, Math.max(1, Number(e.target.value) || 1)),
              }))
            }
            className="h-8 w-16"
          />
        </label>
        <div className="ml-auto flex gap-2">
          {pipeline && (
            <Button variant="outline" onClick={() => setConfirmDelete(true)}>
              {t('pipeline.delete')}
            </Button>
          )}
          <Button
            disabled={!dirty || save.isPending || draft.stages.some((s) => !s.name.trim())}
            onClick={() => void onSave()}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {save.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </div>
      </div>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('pipeline.deleteTitle')}
        description={t('pipeline.deleteDescription')}
        confirmLabel={t('pipeline.delete')}
        destructive
        onConfirm={() => remove.mutate(undefined, { onError: (e) => toast.error(errorMessage(e)) })}
      />
    </div>
  )
}
