import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  useKnowledgeSettings,
  useSaveKnowledgeSettings,
  type KnowledgeSettings,
} from '@/api/knowledge'
import { Field } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { ApiError } from '@/lib/api'
import { errorMessage } from '@/lib/form-errors'

type NumberKey = 'max_file_mb' | 'context_budget' | 'small_doc_tokens' | 'concurrency' | 'threads'
const NUMBERS: { key: NumberKey; min: number; max: number }[] = [
  { key: 'max_file_mb', min: 1, max: 2048 },
  { key: 'context_budget', min: 500, max: 200_000 },
  { key: 'small_doc_tokens', min: 100, max: 50_000 },
  { key: 'concurrency', min: 1, max: 4 },
  { key: 'threads', min: 0, max: 64 },
]
const CLI_CHOICES = ['', 'claude', 'agy'] as const

function Form({ initial }: { initial: KnowledgeSettings }) {
  const { t } = useTranslation()
  const save = useSaveKnowledgeSettings()
  const [draft, setDraft] = useState<KnowledgeSettings>(initial)
  const [errors, setErrors] = useState<Partial<Record<keyof KnowledgeSettings, string>>>({})
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)

  function setNumber(key: NumberKey, raw: string) {
    setDraft((d) => ({ ...d, [key]: raw === '' ? Number.NaN : Number(raw) }))
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const problems: typeof errors = {}
    for (const { key, min, max } of NUMBERS) {
      const value = draft[key]
      if (!Number.isInteger(value) || value < min || value > max)
        problems[key] = t('settings.knowledge.range', { min, max })
    }
    setErrors(problems)
    if (Object.keys(problems).length > 0) return
    try {
      await save.mutateAsync(draft)
      toast.success(t('common.saved'))
    } catch (error) {
      if (error instanceof ApiError && error.field)
        setErrors({ [error.field]: error.message } as typeof errors)
      else toast.error(errorMessage(error))
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
        {NUMBERS.map(({ key, min, max }) => (
          <Field
            key={key}
            label={t(`settings.knowledge.fields.${key}`)}
            htmlFor={`knowledge-${key}`}
            help={t(`settings.knowledge.help.${key}`)}
            error={errors[key]}
          >
            <Input
              id={`knowledge-${key}`}
              type="number"
              min={min}
              max={max}
              value={Number.isNaN(draft[key]) ? '' : draft[key]}
              onChange={(e) => setNumber(key, e.target.value)}
              aria-invalid={errors[key] ? true : undefined}
            />
          </Field>
        ))}
      </div>

      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <Label htmlFor="knowledge-describe">{t('settings.knowledge.describe')}</Label>
          <p className="text-xs text-muted-foreground">{t('settings.knowledge.describeHelp')}</p>
        </div>
        <Switch
          id="knowledge-describe"
          checked={draft.describe_images}
          onCheckedChange={(describe_images) => setDraft((d) => ({ ...d, describe_images }))}
          aria-label={t('settings.knowledge.describe')}
        />
      </div>

      {draft.describe_images && (
        <div className="flex flex-col gap-4 rounded-lg border bg-subtle p-3">
          <Field label={t('settings.knowledge.describer')} htmlFor="knowledge-describer">
            <Select
              value={draft.describer}
              onValueChange={(describer) =>
                setDraft((d) => ({ ...d, describer: describer as KnowledgeSettings['describer'] }))
              }
            >
              <SelectTrigger id="knowledge-describer" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(['cli', 'local'] as const).map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(`settings.knowledge.describers.${value}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          {draft.describer === 'cli' ? (
            <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
              <Field label={t('settings.knowledge.cli')} htmlFor="knowledge-cli">
                <Select
                  value={draft.describer_cli || 'auto'}
                  onValueChange={(value) =>
                    setDraft((d) => ({
                      ...d,
                      describer_cli: (value === 'auto'
                        ? ''
                        : value) as KnowledgeSettings['describer_cli'],
                    }))
                  }
                >
                  <SelectTrigger id="knowledge-cli" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CLI_CHOICES.map((value) => (
                      <SelectItem key={value || 'auto'} value={value || 'auto'}>
                        {t(`settings.knowledge.clis.${value || 'auto'}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field
                label={t('settings.knowledge.model')}
                htmlFor="knowledge-model"
                help={t('settings.knowledge.modelHelp')}
              >
                <Input
                  id="knowledge-model"
                  value={draft.describer_model}
                  maxLength={80}
                  onChange={(e) => setDraft((d) => ({ ...d, describer_model: e.target.value }))}
                />
              </Field>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{t('settings.knowledge.localHelp')}</p>
          )}
        </div>
      )}

      <div>
        <Button
          type="submit"
          disabled={!dirty || save.isPending}
          className="bg-primary-action text-white hover:bg-primary-action-hover"
        >
          {save.isPending ? t('common.saving') : t('common.save')}
        </Button>
      </div>
    </form>
  )
}

/** «Conocimiento»: limits of the library and the optional description of pictures with AI. */
export function KnowledgeSection() {
  const { t } = useTranslation()
  const { data } = useKnowledgeSettings()
  return (
    <section
      aria-labelledby="knowledge-title"
      className="flex flex-col gap-4 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="knowledge-title" className="text-[15px] font-medium">
        {t('settings.knowledge.title')}
      </h2>
      {data ? <Form initial={data} /> : <Skeleton aria-busy className="h-40 rounded-lg" />}
    </section>
  )
}
