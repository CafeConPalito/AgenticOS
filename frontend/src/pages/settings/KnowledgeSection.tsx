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

type NumberKey =
  | 'max_file_mb'
  | 'context_budget'
  | 'small_doc_tokens'
  | 'concurrency'
  | 'threads'
  | 'proposals_per_run'
  | 'proposals_max_tokens'
  | 'graph_max_neighbors'
  | 'graph_expand'
interface NumberSpec {
  key: NumberKey
  min: number
  max: number
}
const LIBRARY: NumberSpec[] = [
  { key: 'max_file_mb', min: 1, max: 2048 },
  { key: 'context_budget', min: 500, max: 200_000 },
  { key: 'small_doc_tokens', min: 100, max: 50_000 },
  { key: 'concurrency', min: 1, max: 4 },
  { key: 'threads', min: 0, max: 64 },
]
const PROPOSALS: NumberSpec[] = [
  { key: 'proposals_per_run', min: 1, max: 20 },
  { key: 'proposals_max_tokens', min: 500, max: 100_000 },
]
const GRAPH: NumberSpec[] = [
  { key: 'graph_max_neighbors', min: 1, max: 30 },
  { key: 'graph_expand', min: 0, max: 10 },
]
const NUMBERS = [...LIBRARY, ...PROPOSALS, ...GRAPH]
const THRESHOLD = { min: 0.05, max: 0.9 }
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
    const threshold = draft.graph_threshold
    if (!(threshold >= THRESHOLD.min && threshold <= THRESHOLD.max))
      problems.graph_threshold = t('settings.knowledge.range', THRESHOLD)
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

  const numberFields = (specs: NumberSpec[]) => (
    <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
      {specs.map(({ key, min, max }) => (
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
  )

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      {numberFields(LIBRARY)}

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

      <div className="flex items-start justify-between gap-4 border-t border-sep pt-4">
        <div className="flex flex-col gap-0.5">
          <Label htmlFor="knowledge-proposals">{t('settings.knowledge.proposals')}</Label>
          <p className="text-xs text-muted-foreground">{t('settings.knowledge.proposalsHelp')}</p>
        </div>
        <Switch
          id="knowledge-proposals"
          checked={draft.proposals_enabled}
          onCheckedChange={(proposals_enabled) => setDraft((d) => ({ ...d, proposals_enabled }))}
          aria-label={t('settings.knowledge.proposals')}
        />
      </div>
      {draft.proposals_enabled && numberFields(PROPOSALS)}

      <h3 className="border-t border-sep pt-4 text-[13px] font-medium">
        {t('settings.knowledge.graphTitle')}
      </h3>
      {numberFields(GRAPH)}
      <Field
        label={t('settings.knowledge.fields.graph_threshold')}
        htmlFor="knowledge-graph_threshold"
        help={t('settings.knowledge.help.graph_threshold')}
        error={errors.graph_threshold}
      >
        <Input
          id="knowledge-graph_threshold"
          type="number"
          step={0.01}
          min={THRESHOLD.min}
          max={THRESHOLD.max}
          value={Number.isNaN(draft.graph_threshold) ? '' : draft.graph_threshold}
          onChange={(e) =>
            setDraft((d) => ({
              ...d,
              graph_threshold: e.target.value === '' ? Number.NaN : Number(e.target.value),
            }))
          }
          aria-invalid={errors.graph_threshold ? true : undefined}
        />
      </Field>

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
