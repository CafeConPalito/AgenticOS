import { zodResolver } from '@hookform/resolvers/zod'
import { FolderPlus } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { useCreateProject } from '@/api/projects'
import { PageContainer, PageHeader, PALETTE } from '@/components/page'
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'
import { applyApiError } from '@/lib/form-errors'
import { PROJECT_FORM_FIELDS, type ProjectFormValues, projectSchema } from './project-form'
import { ProjectFormFields } from './ProjectFormFields'

export default function NewProjectPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const create = useCreateProject()
  const leaving = useRef(false)
  const [offerCreate, setOfferCreate] = useState(false)

  const schema = useMemo(() => projectSchema(), [])
  const form = useForm<ProjectFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      path: '',
      color: PALETTE[4],
      description: '',
      workspace_mode: 'direct',
    },
  })

  const submit = (createFolder: boolean) =>
    form.handleSubmit(async (values) => {
      try {
        const project = await create.mutateAsync({ ...values, create_folder: createFolder })
        leaving.current = true
        toast.success(t('projects.new.created', { name: project.name }))
        navigate(`/proyectos/${project.id}/summary`)
      } catch (error) {
        setOfferCreate(error instanceof ApiError && error.code === 'folder_not_found')
        applyApiError(error, form.setError, PROJECT_FORM_FIELDS)
      }
    })

  return (
    <PageContainer narrow>
      <PageHeader title={t('projects.new.title')} subtitle={t('projects.new.subtitle')} />
      <FormProvider {...form}>
        <form onSubmit={(e) => void submit(false)(e)} noValidate className="flex flex-col gap-6">
          <UnsavedChangesGuard when={form.formState.isDirty} allowRef={leaving} />
          <ProjectFormFields
            pathAction={
              offerCreate && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="self-start"
                  disabled={create.isPending}
                  onClick={() => void submit(true)()}
                >
                  <FolderPlus />
                  {t('projects.new.createFolder')}
                </Button>
              )
            }
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => navigate('/proyectos')}>
              {t('common.cancel')}
            </Button>
            <Button
              type="submit"
              disabled={create.isPending}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              {create.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </div>
        </form>
      </FormProvider>
    </PageContainer>
  )
}
