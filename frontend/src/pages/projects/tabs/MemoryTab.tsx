import { Controller, useForm } from 'react-hook-form'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useUpdateProject } from '@/api/projects'
import type { Project } from '@/api/types'
import { MarkdownEditor } from '@/components/MarkdownEditor'
import { Field } from '@/components/page'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'

export function MemoryTab({ project }: { project: Project }) {
  const { t } = useTranslation()
  const update = useUpdateProject(project.id)
  const form = useForm<{ memory: string }>({ defaultValues: { memory: project.memory } })

  useEffect(() => {
    if (!form.formState.isDirty) form.reset({ memory: project.memory })
  }, [project.memory, form])

  const save = form.handleSubmit(async ({ memory }) => {
    try {
      const saved = await update.mutateAsync({ memory })
      form.reset({ memory: saved.memory })
      toast.success(t('common.saved'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  })

  return (
    <form onSubmit={save} className="flex max-w-[1052px] flex-col gap-3 px-6 pt-5 pb-8">
      <UnsavedChangesGuard when={form.formState.isDirty} />
      <Field
        label={t('projects.fields.memory')}
        htmlFor="project-memory"
        help={t('projects.fields.memoryHelp')}
      >
        <Controller
          control={form.control}
          name="memory"
          render={({ field }) => (
            <MarkdownEditor
              id="project-memory"
              value={field.value}
              onChange={field.onChange}
              placeholder={t('projects.fields.memoryPlaceholder')}
              minRows={20}
            />
          )}
        />
      </Field>
      <Button
        type="submit"
        disabled={!form.formState.isDirty || update.isPending}
        className="self-end bg-primary-action text-white hover:bg-primary-action-hover"
      >
        {update.isPending ? t('common.saving') : t('common.save')}
      </Button>
    </form>
  )
}
