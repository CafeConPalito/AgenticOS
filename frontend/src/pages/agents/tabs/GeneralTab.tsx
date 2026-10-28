import { Controller, useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Field } from '@/components/page'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { AgentFormValues } from '../agent-form'
import { TeamSelect } from '../AgentLinks'
import { AvatarField } from './AvatarField'

export function GeneralTab() {
  const { t } = useTranslation()
  const {
    register,
    control,
    formState: { errors },
  } = useFormContext<AgentFormValues>()

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
        <AvatarField />
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
