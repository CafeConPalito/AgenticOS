import { zodResolver } from '@hookform/resolvers/zod'
import { Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useDeleteProject, useUpdateProject } from '@/api/projects'
import type { Project } from '@/api/types'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { Button } from '@/components/ui/button'
import { applyApiError, errorMessage } from '@/lib/form-errors'
import {
  PROJECT_FORM_FIELDS,
  type ProjectFormValues,
  projectSchema,
  toApiValues,
} from '../project-form'
import { ProjectFormFields } from '../ProjectFormFields'
import { RepositoriesSection } from './RepositoriesSection'

function toValues(project: Project): ProjectFormValues {
  return {
    name: project.name,
    path: project.path,
    color: project.color,
    description: project.description,
    workspace_mode: project.workspace_mode,
    base_branch: project.base_branch ?? '',
  }
}

export function SettingsTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const update = useUpdateProject(project.id)
  const remove = useDeleteProject()
  const leaving = useRef(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const schema = useMemo(() => projectSchema(), [])
  const form = useForm<ProjectFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toValues(project),
  })

  useEffect(() => {
    if (!form.formState.isDirty) form.reset(toValues(project))
  }, [project, form])

  const save = form.handleSubmit(async (values) => {
    const dirty = form.formState.dirtyFields
    const changes = Object.fromEntries(
      PROJECT_FORM_FIELDS.filter((f) => dirty[f]).map((f) => [f, values[f]]),
    )
    try {
      const saved = await update.mutateAsync(toApiValues(changes))
      form.reset(toValues(saved))
      toast.success(t('common.saved'))
    } catch (error) {
      applyApiError(error, form.setError, PROJECT_FORM_FIELDS)
    }
  })

  async function onDelete() {
    try {
      await remove.mutateAsync(project.id)
      leaving.current = true
      toast.success(t('projects.delete.done', { name: project.name }))
      navigate('/proyectos')
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div className="flex max-w-[1052px] flex-col gap-8 px-6 pt-5 pb-8">
      <FormProvider {...form}>
        <form onSubmit={save} noValidate className="flex flex-col gap-4">
          <UnsavedChangesGuard when={form.formState.isDirty} allowRef={leaving} />
          <ProjectFormFields />
          <Button
            type="submit"
            disabled={!form.formState.isDirty || update.isPending}
            className="self-end bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {update.isPending ? t('common.saving') : t('common.save')}
          </Button>
        </form>
      </FormProvider>
      <RepositoriesSection projectId={project.id} />
      <section className="flex items-center justify-between gap-4 rounded-lg border border-[color-mix(in_oklch,var(--status-failed)_40%,transparent)] p-4">
        <div>
          <h2 className="font-medium">{t('projects.danger')}</h2>
          <p className="text-xs text-muted-foreground">{t('projects.deleteHelp')}</p>
        </div>
        <Button
          variant="outline"
          className="text-status-failed"
          onClick={() => setConfirmDelete(true)}
        >
          <Trash2 />
          {t('projects.delete.confirm')}
        </Button>
      </section>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('projects.delete.title', { name: project.name })}
        description={t('projects.delete.description')}
        confirmLabel={t('projects.delete.confirm')}
        destructive
        onConfirm={() => void onDelete()}
      />
    </div>
  )
}
