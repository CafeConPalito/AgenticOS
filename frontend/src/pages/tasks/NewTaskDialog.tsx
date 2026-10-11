import { Plus } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { usePipeline } from '@/api/pipelines'
import { useProjects } from '@/api/projects'
import { useCreateTask } from '@/api/tasks'
import type { Priority } from '@/api/types'
import { AgentAvatar } from '@/components/agentic/primitives'
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
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'

const PRIORITIES: Priority[] = ['high', 'normal', 'low']

/** Creates a task: queued at once (default) or left in the backlog. */
export function NewTaskDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId?: string
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <NewTaskForm onClose={() => onOpenChange(false)} projectId={projectId} />}
    </Dialog>
  )
}

function NewTaskForm({ onClose, projectId }: { onClose: () => void; projectId?: string }) {
  const { t } = useTranslation()
  const projects = useProjects().data ?? []
  const agents = useAgents().data?.filter((a) => a.status !== 'draft') ?? []
  const create = useCreateTask()
  const titleRef = useRef<HTMLInputElement>(null)
  const [pickedProject, setProject] = useState(projectId ?? '')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<Priority>('normal')
  const [pickedAgent, setAgent] = useState('')
  const [backlog, setBacklog] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const project = pickedProject || (projects.length === 1 ? projects[0].id : '')
  const pipeline = usePipeline(project, Boolean(project))
  const firstStage = project ? pipeline.data?.stages[0] : undefined
  const needsAgent = Boolean(project) && pipeline.isSuccess && !firstStage
  const agent = pickedAgent || (agents.length === 1 ? agents[0].id : '')
  const ready =
    Boolean(project && title.trim()) &&
    pipeline.isSuccess &&
    (!needsAgent || Boolean(agent)) &&
    !create.isPending

  const submitOnCtrlEnter = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      void submit()
    }
  }

  async function submit() {
    if (!ready) return
    setError(null)
    try {
      const task = await create.mutateAsync({
        project_id: project,
        title: title.trim(),
        description: description.trim(),
        priority,
        agent_id: needsAgent ? agent : null,
        enqueue: !backlog,
      })
      toast.success(t('tasks.new.created', { code: task.code }))
      onClose()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <DialogContent
      className="sm:max-w-[600px]"
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
          void submit()
        }}
        className="flex flex-col gap-4"
      >
        <DialogHeader>
          <DialogTitle>{t('tasks.new.title')}</DialogTitle>
          <DialogDescription>{t('tasks.new.description')}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-[minmax(0,1fr)_150px] gap-3">
          <Field label={t('tasks.new.project')} htmlFor="task-project">
            <Select value={project} onValueChange={setProject}>
              <SelectTrigger id="task-project" className="w-full">
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
          <Field label={t('tasks.new.priority')} htmlFor="task-priority">
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
        <Field label={t('tasks.new.titleField')} htmlFor="task-title">
          <Input
            id="task-title"
            ref={titleRef}
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('tasks.new.titlePlaceholder')}
          />
        </Field>
        <Field label={t('tasks.new.descriptionField')} htmlFor="task-description">
          <Textarea
            id="task-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={submitOnCtrlEnter}
            placeholder={t('tasks.new.descriptionPlaceholder')}
            className="min-h-[120px]"
          />
        </Field>
        {needsAgent && (
          <Field label={t('tasks.new.agent')} htmlFor="task-agent">
            <Select value={agent} onValueChange={setAgent}>
              <SelectTrigger id="task-agent" className="w-full">
                <SelectValue placeholder={t('tasks.new.pickAgent')} />
              </SelectTrigger>
              <SelectContent>
                {agents.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    <AgentAvatar name={a.name} color={a.color} size={16} />
                    {a.name}
                    {a.role && <span className="text-muted-foreground"> · {a.role}</span>}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        )}
        {firstStage && (
          <p className="text-[12.5px] text-muted-foreground">
            {firstStage.agent_name
              ? t('tasks.new.pipelineNote', {
                  stage: firstStage.name,
                  agent: firstStage.agent_name,
                })
              : t('tasks.new.pipelineNoAgent', { stage: firstStage.name })}
          </p>
        )}
        <label className="flex items-center gap-2.5 text-[13px]">
          <Switch checked={backlog} onCheckedChange={setBacklog} />
          {t('tasks.new.backlog')}
        </label>
        {error && (
          <p role="alert" className="text-sm text-status-failed">
            {error}
          </p>
        )}
        <DialogFooter>
          <span className="mr-auto self-center text-xs text-muted-foreground">
            {t('tasks.new.hint')}
          </span>
          <Button type="button" variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={!ready}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <Plus />
            {create.isPending ? t('tasks.new.submitting') : t('tasks.new.submit')}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
