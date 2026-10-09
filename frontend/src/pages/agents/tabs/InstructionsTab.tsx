import { Controller, useFormContext } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { MarkdownEditor } from '@/components/MarkdownEditor'
import { Field } from '@/components/page'
import type { AgentFormValues } from '../agent-form'

export function InstructionsTab() {
  const { t } = useTranslation()
  const { control } = useFormContext<AgentFormValues>()
  return (
    <div className="max-w-[1052px] px-6 pt-5 pb-8">
      <Field
        label={t('agents.fields.instructions')}
        htmlFor="agent-instructions"
        help={t('agents.fields.instructionsHelp')}
      >
        <Controller
          control={control}
          name="instructions"
          render={({ field }) => (
            <MarkdownEditor
              id="agent-instructions"
              value={field.value}
              onChange={field.onChange}
              minRows={22}
            />
          )}
        />
      </Field>
    </div>
  )
}
