import { AlertTriangle, LayoutGrid, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { useDeletePipeline, useSavePipeline } from '@/api/pipelines'
import type { Pipeline, Project } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import {
  autoLayout,
  emptyDraft,
  graphOf,
  linksFrom,
  newLink,
  newStage,
  tidy,
  toDraft,
  toWrite,
  withoutStage,
  type Draft,
} from './model'
import { PipelineCanvas, type Selection } from './PipelineCanvas'
import { BranchPanel, SettingsPanel, StagePanel } from './Panels'
import { TryDecisionDialog } from './TryDecisionDialog'
import { validateGraph } from './validate'

export function PipelineEditor({
  project,
  pipeline,
}: {
  project: Project
  pipeline: Pipeline | null
}) {
  const { t } = useTranslation()
  const agents = (useAgents().data ?? []).filter((a) => a.status !== 'draft')
  const save = useSavePipeline(project.id)
  const remove = useDeletePipeline(project.id)
  const initial = useMemo<Draft>(
    () => (pipeline ? toDraft(pipeline) : emptyDraft(t('pipeline.newStage'))),
    [pipeline, t],
  )
  const [draft, setDraft] = useState<Draft>(initial)
  const [selection, setSelection] = useState<Selection>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [trying, setTrying] = useState<string | null>(null)
  const dirty = !pipeline || JSON.stringify(draft) !== JSON.stringify(toDraft(pipeline))

  const issues = useMemo(() => validateGraph(graphOf(draft)), [draft])
  const emptyNames = draft.stages.some((s) => !s.name.trim())
  const forks = draft.stages.filter((s) => linksFrom(draft, s.key).length > 1)

  const change = (update: (d: Draft) => Draft) => setDraft((d) => tidy(update(d)))
  const removeStage = (key: string) => {
    change((d) => withoutStage(d, key))
    setSelection(null)
  }

  function addStage() {
    const last = draft.stages[draft.stages.length - 1]
    const stage = newStage(t('pipeline.newStage'), (last?.x ?? -300) + 300, last ? last.y : 0)
    change((d) => ({
      ...d,
      stages: [...d.stages, stage],
      // A new stage follows the last one so the pipeline stays in one piece.
      links: last ? [...d.links, newLink(last.key, stage.key, stage.name)] : d.links,
    }))
    setSelection({ kind: 'stage', key: stage.key })
  }

  async function onSave() {
    try {
      const result = await save.mutateAsync(toWrite(draft))
      setDraft(toDraft(result))
      setSelection(null)
      toast.success(t('pipeline.saved'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const stageName = (key?: string) => draft.stages.find((s) => s.key === key)?.name ?? ''
  const selectedStage =
    selection?.kind === 'stage' ? draft.stages.find((s) => s.key === selection.key) : undefined
  const selectedLink =
    selection?.kind === 'link' ? draft.links.find((l) => l.key === selection.key) : undefined

  return (
    <div className="flex flex-col gap-3 px-6 pt-5 pb-8">
      <UnsavedChangesGuard when={dirty && Boolean(pipeline)} />
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[15px] font-medium">{t('pipeline.title')}</h2>
          <p className="text-xs text-muted-foreground">{t('pipeline.help')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => change((d) => autoLayout(d))}>
            <LayoutGrid />
            {t('pipeline.arrange')}
          </Button>
          <Button variant="outline" className="border-dashed" onClick={addStage}>
            <Plus />
            {t('pipeline.addStage')}
          </Button>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
        <PipelineCanvas
          draft={draft}
          agents={agents}
          issues={issues}
          selection={selection}
          onSelect={setSelection}
          onChange={change}
          onRemoveStage={removeStage}
        />
        <aside className="flex flex-col gap-3 rounded-xl border bg-card p-3">
          <nav aria-label={t('pipeline.stages')}>
            <ol className="grid gap-1">
              {draft.stages.map((stage, index) => {
                const agent = agents.find((a) => a.id === stage.agentId)
                const bad = issues.some((i) => i.stage === stage.key)
                return (
                  <li key={stage.key}>
                    <button
                      type="button"
                      aria-current={
                        selection?.kind === 'stage' && selection.key === stage.key
                          ? 'true'
                          : undefined
                      }
                      onClick={() => setSelection({ kind: 'stage', key: stage.key })}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-lg border border-transparent px-2 py-1.5 text-left text-[13px] hover:bg-subtle',
                        selection?.kind === 'stage' &&
                          selection.key === stage.key &&
                          'border-ring bg-subtle',
                      )}
                    >
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {index + 1}
                      </span>
                      {agent && <AgentAvatar name={agent.name} color={agent.color} size={18} />}
                      <span className="min-w-0 flex-1 truncate">{stage.name}</span>
                      {bad && (
                        <AlertTriangle
                          aria-label={t('pipeline.hasProblem')}
                          className="size-3.5 text-status-failed"
                        />
                      )}
                    </button>
                  </li>
                )
              })}
            </ol>
          </nav>
          <hr />
          {selectedStage ? (
            <StagePanel
              stage={selectedStage}
              draft={draft}
              agents={agents}
              onChange={change}
              onSelectLink={(key) => setSelection({ kind: 'link', key })}
              onRemove={() => removeStage(selectedStage.key)}
            />
          ) : selectedLink ? (
            <BranchPanel link={selectedLink} draft={draft} onChange={change} />
          ) : (
            <SettingsPanel
              draft={draft}
              onChange={change}
              forks={forks.map((s) => ({ key: s.key, name: s.name }))}
              direct={project.workspace_mode === 'direct'}
              onTry={setTrying}
            />
          )}
        </aside>
      </div>

      {issues.length > 0 && (
        <ul
          aria-label={t('pipeline.problems')}
          className="grid gap-1 text-[13px] text-status-failed"
        >
          {issues.map((issue, i) => (
            <li key={`${issue.code}-${issue.stage ?? ''}-${issue.link ?? ''}-${i}`}>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 hover:underline"
                onClick={() =>
                  setSelection(
                    issue.link
                      ? { kind: 'link', key: issue.link }
                      : issue.stage
                        ? { kind: 'stage', key: issue.stage }
                        : null,
                  )
                }
              >
                <AlertTriangle className="size-3.5" />
                {t(`pipeline.issues.${issue.code}`, { stage: stageName(issue.stage) })}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="ml-auto flex gap-2">
          {pipeline && (
            <Button variant="outline" onClick={() => setConfirmDelete(true)}>
              {t('pipeline.delete')}
            </Button>
          )}
          <Button
            disabled={!dirty || save.isPending || emptyNames || issues.length > 0}
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
      {trying && (
        <TryDecisionDialog
          open
          onOpenChange={(open) => !open && setTrying(null)}
          projectId={project.id}
          draft={draft}
          fork={trying}
        />
      )}
    </div>
  )
}
