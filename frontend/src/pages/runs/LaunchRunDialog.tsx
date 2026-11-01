import { Play } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useNavigate } from 'react-router'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { useLaunchRun } from '@/api/runs'
import { AgentAvatar, ProjectMark } from '@/components/agentic/primitives'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/form-errors'

/**
 * Launches an agent on a project with a prompt and opens the run page. Opened from the agent
 * (agent preselected), the project (project preselected) or the runs list.
 */
export function LaunchRunDialog({
  open,
  onOpenChange,
  agentId,
  projectId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  agentId?: string
  projectId?: string
}) {
  // The form is mounted only while open, so every opening starts clean.
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && (
        <LaunchRunForm
          onClose={() => onOpenChange(false)}
          agentId={agentId}
          projectId={projectId}
        />
      )}
    </Dialog>
  )
}

function LaunchRunForm({
  onClose,
  agentId,
  projectId,
}: {
  onClose: () => void
  agentId?: string
  projectId?: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const agents = useAgents().data?.filter((a) => a.status !== 'draft') ?? []
  const projects = useProjects().data ?? []
  const launch = useLaunchRun()
  const promptRef = useRef<HTMLTextAreaElement>(null)
  const [pickedAgent, setAgent] = useState(agentId ?? '')
  const [pickedProject, setProject] = useState(projectId ?? '')
  const [prompt, setPrompt] = useState('')
  const [error, setError] = useState<string | null>(null)
  // With a single choice there is nothing to pick.
  const agent = pickedAgent || (agents.length === 1 ? agents[0].id : '')
  const project = pickedProject || (projects.length === 1 ? projects[0].id : '')

  const ready = Boolean(agent && project && prompt.trim()) && !launch.isPending

  async function submit() {
    if (!ready) return
    setError(null)
    try {
      const run = await launch.mutateAsync({
        agent_id: agent,
        project_id: project,
        prompt: prompt.trim(),
      })
      onClose()
      // Over its CLI's daily limit (or out of quota) a manual run starts anyway: say so.
      if (run.warning) toast.warning(t(`usage.warning.${run.warning}`))
      navigate(`/ejecuciones/${run.id}`)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <DialogContent
      className="sm:max-w-[560px]"
      onOpenAutoFocus={(e) => {
        e.preventDefault()
        promptRef.current?.focus()
      }}
    >
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          e.stopPropagation() // the dialog can live inside the agent editor form
          void submit()
        }}
        className="flex flex-col gap-4"
      >
        <DialogHeader>
          <DialogTitle>{t('runs.launch.title')}</DialogTitle>
          <DialogDescription>{t('runs.launch.description')}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <Field
            label={t('runs.launch.agent')}
            htmlFor="launch-agent"
            help={agents.length === 0 ? t('runs.launch.noAgents') : undefined}
          >
            <Select value={agent} onValueChange={setAgent}>
              <SelectTrigger id="launch-agent" className="w-full">
                <SelectValue placeholder={t('runs.launch.pickAgent')} />
              </SelectTrigger>
              <SelectContent>
                {agents.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    <AgentAvatar name={a.name} color={a.color} agentId={a.id} size={16} />
                    {a.name}
                    {a.role && <span className="text-muted-foreground"> · {a.role}</span>}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field
            label={t('runs.launch.project')}
            htmlFor="launch-project"
            help={projects.length === 0 ? t('runs.launch.noProjects') : undefined}
          >
            <Select value={project} onValueChange={setProject}>
              <SelectTrigger id="launch-project" className="w-full">
                <SelectValue placeholder={t('runs.launch.pickProject')} />
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
          </Field>
        </div>
        <Field label={t('runs.launch.prompt')} htmlFor="launch-prompt" help={t('runs.launch.hint')}>
          <Textarea
            id="launch-prompt"
            dictation
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault()
                void submit()
              }
            }}
            placeholder={t('runs.launch.promptPlaceholder')}
            className="min-h-[140px] font-mono text-[12.5px]"
            ref={promptRef}
          />
        </Field>
        {error && (
          <p role="alert" className="text-sm text-status-failed">
            {error}
          </p>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={!ready}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <Play />
            {launch.isPending ? t('runs.launch.submitting') : t('runs.launch.submit')}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}

/** «Lanzar» button that opens the dialog; used in the agent and project headers. */
export function LaunchRunButton({
  agentId,
  projectId,
  disabled,
}: {
  agentId?: string
  projectId?: string
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button type="button" variant="outline" onClick={() => setOpen(true)} disabled={disabled}>
        <Play />
        {t('runs.launch.button')}
      </Button>
      <LaunchRunDialog open={open} onOpenChange={setOpen} agentId={agentId} projectId={projectId} />
    </>
  )
}
