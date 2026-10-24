import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type SkillSettings,
  useRegistries,
  useSaveSkillSettings,
  useSkillSettings,
} from '@/api/skills'
import { Field } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'

type NumberKey = 'candidates' | 'index_tokens' | 'always_tokens' | 'proposals_per_run'
type LabelKey = 'candidates' | 'indexTokens' | 'alwaysTokens' | 'perRun'
const NUMBERS: { key: NumberKey; label: LabelKey; min: number; max: number }[] = [
  { key: 'candidates', label: 'candidates', min: 0, max: 20 },
  { key: 'index_tokens', label: 'indexTokens', min: 100, max: 5_000 },
  { key: 'always_tokens', label: 'alwaysTokens', min: 0, max: 50_000 },
]

function Form({ initial }: { initial: SkillSettings }) {
  const { t } = useTranslation()
  const save = useSaveSkillSettings()
  const registries = (useRegistries().data ?? []).filter((r) => r.switchable)
  const [draft, setDraft] = useState(initial)
  const [key, setKey] = useState('')
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial) || key !== ''

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      const values: Partial<SkillSettings> = { ...draft }
      delete values.skillsmp_key_set
      await save.mutateAsync({ ...values, ...(key ? { skillsmp_key: key } : {}) })
      setKey('')
      toast.success(t('skills.settings.saved'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const number = (spec: (typeof NUMBERS)[number]) => (
    <Field key={spec.key} label={t(`skills.settings.${spec.label}`)} htmlFor={`skills-${spec.key}`}>
      <Input
        id={`skills-${spec.key}`}
        type="number"
        min={spec.min}
        max={spec.max}
        value={draft[spec.key]}
        onChange={(e) => setDraft((d) => ({ ...d, [spec.key]: Number(e.target.value) }))}
      />
    </Field>
  )

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      <h3 className="text-[13px] font-medium">{t('skills.settings.selection')}</h3>
      <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">{NUMBERS.map(number)}</div>

      <div className="flex items-start justify-between gap-4 border-t border-sep pt-4">
        <Label htmlFor="skills-proposals">{t('skills.settings.proposalsEnabled')}</Label>
        <Switch
          id="skills-proposals"
          checked={draft.proposals_enabled}
          onCheckedChange={(proposals_enabled) => setDraft((d) => ({ ...d, proposals_enabled }))}
        />
      </div>
      {draft.proposals_enabled &&
        number({ key: 'proposals_per_run', label: 'perRun', min: 1, max: 10 })}

      <h3 className="border-t border-sep pt-4 text-[13px] font-medium">
        {t('skills.settings.registries')}
      </h3>
      <p className="text-xs text-muted-foreground">{t('skills.settings.registriesHint')}</p>
      <ul className="flex flex-col gap-2">
        {registries.map((registry) => (
          <li key={registry.id} className="flex items-center justify-between gap-4">
            <Label htmlFor={`registry-${registry.id}`}>
              {t(`skills.explore.sources.${registry.id}`, { defaultValue: registry.title })}
            </Label>
            <Switch
              id={`registry-${registry.id}`}
              checked={draft.registries[registry.id] ?? registry.default_enabled}
              onCheckedChange={(on) =>
                setDraft((d) => ({ ...d, registries: { ...d.registries, [registry.id]: on } }))
              }
            />
          </li>
        ))}
      </ul>
      <Field
        label={t('skills.settings.skillsmpKey')}
        htmlFor="skills-skillsmp-key"
        help={draft.skillsmp_key_set ? t('skills.settings.keySet') : undefined}
      >
        <Input
          id="skills-skillsmp-key"
          type="password"
          autoComplete="off"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </Field>
      <p className="text-xs text-muted-foreground">{t('skills.settings.githubToken')}</p>
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

/** «Skills»: how many are offered per run, the proposals of the agents and the registries. */
export function SkillsSection() {
  const { t } = useTranslation()
  const { data } = useSkillSettings()
  return (
    <section
      aria-labelledby="skills-title"
      className="flex flex-col gap-4 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="skills-title" className="text-[15px] font-medium">
        {t('skills.settings.title')}
      </h2>
      {data ? <Form initial={data} /> : <Skeleton aria-busy className="h-40 rounded-lg" />}
    </section>
  )
}
