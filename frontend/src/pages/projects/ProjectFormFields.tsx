import { Controller, useFormContext, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import type { WorkspaceMode } from '@/api/types'
import { FolderPicker } from '@/components/FolderPicker'
import { ColorPicker, Field } from '@/components/page'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { ProjectFormValues } from './project-form'

const MODES: WorkspaceMode[] = ['direct', 'worktree']

/** Fields shared by "Nuevo proyecto" and the project's Ajustes tab. */
export function ProjectFormFields({ pathAction }: { pathAction?: React.ReactNode }) {
  const { t } = useTranslation()
  const {
    register,
    control,
    formState: { errors },
  } = useFormContext<ProjectFormValues>()
  const mode = useWatch({ control, name: 'workspace_mode' })

  return (
    <div className="grid grid-cols-2 gap-x-5 gap-y-5">
      <Field label={t('projects.fields.name')} htmlFor="project-name" error={errors.name?.message}>
        <Input id="project-name" {...register('name')} aria-invalid={!!errors.name || undefined} />
      </Field>
      <Field label={t('projects.fields.color')}>
        <Controller
          control={control}
          name="color"
          render={({ field }) => (
            <ColorPicker
              value={field.value}
              onChange={field.onChange}
              colorLabel={(c) => t('agents.fields.color', { color: c })}
            />
          )}
        />
      </Field>
      <Field
        label={t('projects.fields.path')}
        htmlFor="project-path"
        error={errors.path?.message}
        className="col-span-2"
      >
        <Controller
          control={control}
          name="path"
          render={({ field }) => (
            <FolderPicker
              id="project-path"
              value={field.value}
              onChange={field.onChange}
              invalid={!!errors.path}
            />
          )}
        />
        {pathAction}
      </Field>
      <Field
        label={t('projects.fields.workspaceMode')}
        error={errors.workspace_mode?.message}
        className="col-span-2"
      >
        <Controller
          control={control}
          name="workspace_mode"
          render={({ field }) => (
            <div
              role="radiogroup"
              aria-label={t('projects.fields.workspaceMode')}
              className="grid grid-cols-2 gap-2"
            >
              {MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={field.value === mode}
                  onClick={() => field.onChange(mode)}
                  className={cn(
                    'rounded-lg border bg-card p-3 text-left hover:border-ring',
                    field.value === mode && 'border-ring bg-accent',
                  )}
                >
                  <span className="block font-medium">{t(`projects.mode.${mode}`)}</span>
                  <span className="block text-xs text-pretty text-muted-foreground">
                    {t(`projects.mode.${mode}Help`)}
                  </span>
                </button>
              ))}
            </div>
          )}
        />
      </Field>
      {mode === 'worktree' && (
        <Field
          label={t('projects.fields.baseBranch')}
          htmlFor="project-base-branch"
          help={t('projects.fields.baseBranchHelp')}
          error={errors.base_branch?.message}
          className="col-span-2"
        >
          <Input
            id="project-base-branch"
            {...register('base_branch')}
            placeholder="main"
            className="max-w-[280px] font-mono"
            aria-invalid={!!errors.base_branch || undefined}
          />
        </Field>
      )}
      <Field
        label={t('projects.fields.description')}
        htmlFor="project-description"
        className="col-span-2"
      >
        <Textarea
          id="project-description"
          rows={3}
          placeholder={t('projects.fields.descriptionPlaceholder')}
          {...register('description')}
        />
      </Field>
    </div>
  )
}
