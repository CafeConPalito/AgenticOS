import { Controller, useFormContext, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { AgentAvatar } from '@/components/agentic/primitives'
import { ColorPicker, Field } from '@/components/page'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { AgentFormValues } from '../agent-form'
import { TeamSelect } from '../AgentLinks'

export function GeneralTab() {
  const { t } = useTranslation()
  const {
    register,
    control,
    formState: { errors },
  } = useFormContext<AgentFormValues>()
  const [name, color] = useWatch<AgentFormValues, ['name', 'color']>({ name: ['name', 'color'] })

  return (
    <div className="grid max-w-[1052px] grid-cols-2 gap-x-5 gap-y-5 px-6 pt-5 pb-8">
      <Field label={t('agents.fields.name')} htmlFor="agent-name" error={errors.name?.message}>
        <Input id="agent-name" {...register('name')} aria-invalid={!!errors.name || undefined} />
      </Field>
      <Field label={t('agents.fields.role')} htmlFor="agent-role" error={errors.role?.message}>
        <Input id="agent-role" {...register('role')} />
      </Field>
      <Field label={t('agents.fields.team')} htmlFor="agent-team">
        <Controller
          control={control}
          name="team_id"
          render={({ field }) => (
            <TeamSelect id="agent-team" value={field.value} onChange={field.onChange} />
          )}
        />
      </Field>
      <Field
        label={t('agents.fields.avatar')}
        help={t('agents.fields.colorHelp')}
        className="col-span-2"
      >
        <div className="flex items-center gap-4">
          <AgentAvatar name={name || '?'} color={color} size={56} />
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
        </div>
      </Field>
      <Field
        label={t('agents.fields.description')}
        htmlFor="agent-description"
        className="col-span-2"
      >
        <Textarea
          id="agent-description"
          dictation
          rows={3}
          placeholder={t('agents.fields.descriptionPlaceholder')}
          {...register('description')}
        />
      </Field>
    </div>
  )
}
