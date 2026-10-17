import { FolderPlus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useClone } from '@/api/git-more'
import { useApplyPipelineTemplate } from '@/api/pipelines'
import { useCreateProject } from '@/api/projects'
import { FolderPicker } from '@/components/FolderPicker'
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
import { ApiError, api } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'

/** The six swatches the project can be marked with. */
const COLORS = ['#7C9CFF', '#4FD1C5', '#B5E061', '#FFA06B', '#F27FB2', '#C4A1FF']
type PipelineChoice = 'none' | 'web'
type Source = 'folder' | 'clone'

/** How often a running clone is asked for its progress. */
const CLONE_POLL_MS = 1000

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** The last folder of a path: the name that is proposed for the project. */
export function folderName(path: string): string {
  const parts = path
    .trim()
    .replace(/[\\/]+$/, '')
    .split(/[\\/]/)
  return parts[parts.length - 1] ?? ''
}

/** Registers a folder as a project, with an optional pipeline from a template. */
export function NewProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <NewProjectForm onClose={() => onOpenChange(false)} />}
    </Dialog>
  )
}

function NewProjectForm({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const create = useCreateProject()
  const applyTemplate = useApplyPipelineTemplate()
  const [path, setPath] = useState('')
  const [name, setName] = useState('')
  // Until the person types a name, it follows the folder.
  const [nameTouched, setNameTouched] = useState(false)
  const [color, setColor] = useState(COLORS[0])
  const [pipeline, setPipeline] = useState<PipelineChoice>('web')
  const [errors, setErrors] = useState<{ path?: string; name?: string; form?: string }>({})
  const [offerCreate, setOfferCreate] = useState(false)
  const [source, setSource] = useState<Source>('folder')
  const [url, setUrl] = useState('')
  const [parent, setParent] = useState('')
  const [cloning, setCloning] = useState<string | null>(null)
  const clone = useClone()
  const cloneName = folderName(url.replace(/\.git$/, '').replace(/[:]/g, '/'))
  const shownName = nameTouched ? name : source === 'clone' ? cloneName : folderName(path)

  /** Clones the repository and waits for it; returns the new folder, or null (and says why). */
  async function cloneRepository(): Promise<string | null> {
    if (!url.trim() || !parent.trim()) {
      setErrors({
        path: parent.trim() ? undefined : t('common.required'),
        form: url.trim() ? undefined : t('projects.new.urlRequired'),
      })
      return null
    }
    setErrors({})
    try {
      const started = await clone.mutateAsync({
        url: url.trim(),
        parent_folder: parent.trim(),
        name: cloneName || undefined,
      })
      let job = started.job
      while (job.status === 'running') {
        setCloning(job.percent === null ? job.phase : `${job.phase} ${Math.round(job.percent)}%`)
        await sleep(CLONE_POLL_MS)
        job = await api.get<typeof job>(`/api/git/jobs/${job.id}`)
      }
      setCloning(null)
      if (job.status !== 'succeeded') {
        setErrors({
          form: t(`git.errors.${job.error_code ?? 'git_failed'}`, { defaultValue: job.message }),
        })
        return null
      }
      return started.path
    } catch (error) {
      setCloning(null)
      setErrors({ form: errorMessage(error) })
      return null
    }
  }

  async function submit(createFolder: boolean) {
    let projectPath = path
    if (source === 'clone') {
      const cloned = await cloneRepository()
      if (!cloned) return
      projectPath = cloned
    }
    const projectName = shownName.trim()
    if (!projectPath.trim() || !projectName) {
      setErrors({
        path: projectPath.trim() ? undefined : t('common.required'),
        name: projectName ? undefined : t('errors.name_required'),
      })
      return
    }
    setErrors({})
    let project
    try {
      project = await create.mutateAsync({
        name: projectName,
        path: projectPath.trim(),
        color,
        description: '',
        workspace_mode: 'direct',
        base_branch: null,
        create_folder: createFolder,
      })
    } catch (error) {
      setOfferCreate(error instanceof ApiError && error.code === 'folder_not_found')
      const field = error instanceof ApiError ? error.field : undefined
      const message = errorMessage(error)
      setErrors(
        field === 'name'
          ? { name: message }
          : field === 'path'
            ? { path: message }
            : { form: message },
      )
      return
    }
    // The project exists from here on: a failing pipeline must not undo it.
    if (pipeline === 'web') {
      try {
        await applyTemplate.mutateAsync({ projectId: project.id, template: 'web' })
        toast.success(t('projects.new.created', { name: project.name }))
      } catch (error) {
        toast.error(
          t('projects.new.pipelineFailed', { name: project.name, error: errorMessage(error) }),
        )
      }
    } else {
      toast.success(t('projects.new.created', { name: project.name }))
    }
    onClose()
    void navigate(`/proyectos/${project.id}/summary`)
  }

  const busy = create.isPending || applyTemplate.isPending || clone.isPending || cloning !== null

  return (
    <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-[540px]">
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          e.stopPropagation()
          void submit(false)
        }}
        className="flex flex-col"
      >
        <DialogHeader className="border-b border-sep px-5 py-4">
          <DialogTitle className="text-[15px] font-medium">{t('projects.new.title')}</DialogTitle>
          <DialogDescription>{t('projects.new.subtitle')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 p-5">
          <div role="radiogroup" aria-label={t('projects.new.source')} className="flex gap-2">
            {(['folder', 'clone'] as const).map((id) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={source === id}
                onClick={() => {
                  setSource(id)
                  setErrors({})
                }}
                className={cn(
                  'flex-1 rounded-lg border bg-card px-3 py-2 text-left text-[13px] font-medium hover:border-ring',
                  source === id && 'border-ring bg-accent',
                )}
              >
                {t(`projects.new.sources.${id}`)}
              </button>
            ))}
          </div>
          {source === 'clone' && (
            <Field label={t('projects.new.url')} htmlFor="project-url">
              <Input
                id="project-url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/usuario/repositorio.git"
                className="font-mono text-xs"
              />
            </Field>
          )}
          <Field
            label={source === 'clone' ? t('projects.new.parent') : t('projects.fields.path')}
            htmlFor="project-path"
            error={errors.path}
          >
            <FolderPicker
              id="project-path"
              value={source === 'clone' ? parent : path}
              onChange={source === 'clone' ? setParent : setPath}
              invalid={Boolean(errors.path)}
            />
            {source === 'folder' && offerCreate && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="self-start"
                disabled={busy}
                onClick={() => void submit(true)}
              >
                <FolderPlus />
                {t('projects.new.createFolder')}
              </Button>
            )}
          </Field>
          <Field label={t('projects.fields.name')} htmlFor="project-name" error={errors.name}>
            <Input
              id="project-name"
              value={shownName}
              maxLength={80}
              onChange={(e) => {
                setNameTouched(true)
                setName(e.target.value)
              }}
              aria-invalid={Boolean(errors.name) || undefined}
            />
          </Field>

          <Field label={t('projects.new.pipeline')}>
            <div
              role="radiogroup"
              aria-label={t('projects.new.pipeline')}
              className="grid grid-cols-2 gap-2"
            >
              {(
                [
                  ['web', t('projects.new.webPipeline'), t('projects.new.webPipelineHelp')],
                  ['none', t('projects.new.noPipeline'), t('projects.new.noPipelineHelp')],
                ] as const
              ).map(([id, label, help]) => (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={pipeline === id}
                  onClick={() => setPipeline(id)}
                  className={cn(
                    'flex flex-col gap-0.5 rounded-lg border bg-card p-3 text-left hover:border-ring',
                    pipeline === id && 'border-ring bg-accent',
                  )}
                >
                  <span className="font-medium">{label}</span>
                  <span className="text-xs text-muted-foreground">{help}</span>
                </button>
              ))}
            </div>
          </Field>

          <Field label={t('projects.fields.color')}>
            <div role="radiogroup" aria-label={t('projects.fields.color')} className="flex gap-2">
              {COLORS.map((swatch) => (
                <button
                  key={swatch}
                  type="button"
                  role="radio"
                  aria-checked={color === swatch}
                  aria-label={t('agents.fields.color', { color: swatch })}
                  onClick={() => setColor(swatch)}
                  className={cn(
                    'size-7 rounded-md border-2 border-transparent outline-offset-2',
                    color === swatch && 'border-foreground',
                  )}
                  style={{ background: swatch }}
                />
              ))}
            </div>
          </Field>

          {cloning !== null && (
            <p role="status" className="text-sm text-muted-foreground">
              {t('projects.new.cloning', { progress: cloning })}
            </p>
          )}
          {errors.form && (
            <p role="alert" className="text-sm text-status-failed">
              {errors.form}
            </p>
          )}
        </div>

        <DialogFooter className="gap-2 border-t border-sep px-5 py-3">
          <Button type="button" variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            disabled={busy}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {busy
              ? t('common.creating')
              : source === 'clone'
                ? t('projects.new.cloneSubmit')
                : t('projects.new.submit')}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  )
}
