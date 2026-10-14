import { ChevronDown } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { usePipeline } from '@/api/pipelines'
import { useProjects } from '@/api/projects'
import { useCreateTask } from '@/api/tasks'
import type { Priority } from '@/api/types'
import { Field } from '@/components/page'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import type { NewTaskInit } from '@/stores/dialogs'
import { useUiPrefs } from '@/stores/ui-prefs'

const PRIORITIES: Priority[] = ['high', 'normal', 'low']

/**
 * Creates a task: what to do, in which project, by which agent. The opener may preselect the
 * project or the agent; otherwise the last choice, then the first of each.
 */
export function NewTaskDialog({
  open,
  onOpenChange,
  init = {},
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  init?: NewTaskInit | null
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <NewTaskForm onClose={() => onOpenChange(false)} init={init ?? {}} />}
    </Dialog>
  )
}

function NewTaskForm({ onClose, init }: { onClose: () => void; init: NewTaskInit }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const projects = useProjects().data ?? []
  const agents = useAgents().data?.filter((a) => a.status !== 'draft') ?? []
  const last = useUiPrefs((s) => s.lastTaskTarget)
  const remember = useUiPrefs((s) => s.setLastTaskTarget)
  const create = useCreateTask()
  const titleRef = useRef<HTMLInputElement>(null)
  const [title, setTitle] = useState('')
  const [pickedProject, setProject] = useState(init.projectId ?? '')
  const [pickedAgent, setAgent] = useState(init.agentId ?? '')
  const [details, setDetails] = useState(false)
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<Priority>('normal')
  const [error, setError] = useState<string | null>(null)

  const known = (list: { id: string }[], id: string | undefined) =>
    id && list.some((item) => item.id === id) ? id : ''
  const project =
    known(projects, pickedProject) || known(projects, last?.projectId) || (projects[0]?.id ?? '')
  const pipeline = usePipeline(project, Boolean(project))
  const firstStage = project ? pipeline.data?.stages[0] : undefined
  // With a pipeline the first stage decides the agent; without one the person picks it.
  const needsAgent = Boolean(project) && pipeline.isSuccess && !firstStage
  const agent = known(agents, pickedAgent) || known(agents, last?.agentId) || (agents[0]?.id ?? '')
  const ready =
    Boolean(project && title.trim()) &&
    pipeline.isSuccess &&
    (!needsAgent || Boolean(agent)) &&
    !create.isPending

  const submitOnCtrlEnter = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      void submit(true)
    }
  }

  async function submit(enqueue: boolean) {
    if (!ready) return
    setError(null)
    try {
      const task = await create.mutateAsync({
        project_id: project,
        title: title.trim(),
        description: description.trim(),
        priority,
        agent_id: needsAgent ? agent : null,
        enqueue,
      })
      if (agent) remember({ projectId: project, agentId: agent })
      const owner = task.agent_name ?? agents.find((a) => a.id === agent)?.name ?? ''
      toast.success(
        enqueue
          ? t('tasks.new.queued', { code: task.code, agent: owner })
          : t('tasks.new.backlogged', { code: task.code }),
        {
          duration: 6000,
          action: {
            label: t('tasks.new.view'),
            onClick: () => void navigate(`/tablero/tareas/${task.id}`),
          },
        },
      )
      onClose()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <DialogContent
      className="gap-0 overflow-hidden p-0 sm:max-w-[520px]"
      onOpenAutoFocus={(e) => {
        e.preventDefault()
        titleRef.current?.focus()
      }}
    >
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          e.stopPropagation()
          void submit(true)
        }}
        className="flex flex-col"
      >
        <DialogHeader className="border-b border-sep px-4 py-3.5">
          <DialogTitle className="text-[15px] font-medium">{t('tasks.new.title')}</DialogTitle>
          <DialogDescription className="sr-only">{t('tasks.new.description')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 p-4">
          <Field label={t('tasks.new.what')} htmlFor="task-title">
            <Input
              id="task-title"
              ref={titleRef}
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={submitOnCtrlEnter}
              placeholder={t('tasks.new.titlePlaceholder')}
              className="h-9 rounded-[10px] bg-card"
            />
          </Field>
          <div className="grid grid-cols-2 gap-2.5">
            <Field label={t('tasks.new.project')} htmlFor="task-project">
              {/* Radix reports an empty value while its items are not mounted yet: ignore it. */}
              <Select value={project} onValueChange={(v) => v && setProject(v)}>
                <SelectTrigger id="task-project" className="h-9 w-full rounded-[10px] bg-card">
                  <SelectValue placeholder={t('tasks.new.pickProject')} />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      <span className="size-2 rounded-[2px]" style={{ background: p.color }} />
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label={t('tasks.new.agent')} htmlFor="task-agent">
              {firstStage ? (
                <div
                  id="task-agent"
                  className="flex h-9 items-center truncate rounded-[10px] border bg-subtle px-3 text-[13px] text-muted-foreground"
                  title={t('tasks.new.pipelineHint')}
                >
                  {firstStage.agent_name
                    ? t('tasks.new.pipelineNote', {
                        stage: firstStage.name,
                        agent: firstStage.agent_name,
                      })
                    : t('tasks.new.pipelineNoAgent', { stage: firstStage.name })}
                </div>
              ) : (
                <Select value={agent} onValueChange={(v) => v && setAgent(v)}>
                  <SelectTrigger id="task-agent" className="h-9 w-full rounded-[10px] bg-card">
                    <SelectValue placeholder={t('tasks.new.pickAgent')} />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((a) => (
                      <SelectItem key={a.id} value={a.id}>
                        {a.name}
                        {a.role && <span className="text-muted-foreground"> · {a.role}</span>}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </Field>
          </div>

          <button
            type="button"
            aria-expanded={details}
            onClick={() => setDetails((v) => !v)}
            className="flex w-fit items-center gap-1.5 text-[12.5px] text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn('size-3.5 transition-transform', details && 'rotate-180')} />
            {t('tasks.new.addDescription')}
          </button>
          {details && (
            <div className="flex flex-col gap-3">
              <Field label={t('tasks.new.descriptionField')} htmlFor="task-description">
                <Textarea
                  id="task-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  onKeyDown={submitOnCtrlEnter}
                  placeholder={t('tasks.new.descriptionPlaceholder')}
                  className="min-h-[100px]"
                />
              </Field>
              <Field label={t('tasks.new.priority')} htmlFor="task-priority" className="w-40">
                <Select value={priority} onValueChange={(v) => setPriority(v as Priority)}>
                  <SelectTrigger id="task-priority" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PRIORITIES.map((p) => (
                      <SelectItem key={p} value={p}>
                        {t(`tasks.priority.${p}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-status-failed">
              {error}
            </p>
          )}
        </div>

        <DialogFooter className="gap-2 border-t border-sep px-4 py-3">
          <Button
            type="button"
            variant="ghost"
            disabled={!ready}
            onClick={() => void submit(false)}
            className="h-8 rounded-[10px] sm:mr-auto"
          >
            {t('tasks.new.saveBacklog')}
          </Button>
          <Button
            type="submit"
            disabled={!ready}
            className="h-8 rounded-full bg-primary-action px-3.5 font-medium text-white hover:bg-primary-action-hover"
          >
            {create.isPending ? t('tasks.new.submitting') : t('tasks.new.submit')}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
