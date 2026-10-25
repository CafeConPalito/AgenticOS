import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type ConnectionSettings,
  useConnectionSettings,
  useRegistrySources,
  useRequirements,
  useSaveConnectionSettings,
} from '@/api/connections'
import { Field } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'

type NumberKey = 'probe_timeout' | 'startup_timeout' | 'agy_grace' | 'oauth_port'
type LabelKey = 'probeTimeout' | 'startupTimeout' | 'agyGrace' | 'oauthPort'
const NUMBERS: { key: NumberKey; label: LabelKey; min: number; max: number }[] = [
  { key: 'probe_timeout', label: 'probeTimeout', min: 5, max: 600 },
  { key: 'startup_timeout', label: 'startupTimeout', min: 5, max: 600 },
  { key: 'agy_grace', label: 'agyGrace', min: 0, max: 120 },
  { key: 'oauth_port', label: 'oauthPort', min: 1024, max: 65535 },
]

function Form({ initial }: { initial: ConnectionSettings }) {
  const { t } = useTranslation()
  const save = useSaveConnectionSettings()
  const sources = (useRegistrySources().data ?? []).filter((s) => s.switchable)
  const requirements = useRequirements().data ?? []
  const [draft, setDraft] = useState(initial)
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      await save.mutateAsync(draft)
      toast.success(t('connections.settings.saved'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
        {NUMBERS.map((spec) => (
          <Field
            key={spec.key}
            label={t(`connections.settings.${spec.label}`)}
            htmlFor={`connections-${spec.key}`}
            help={t(`connections.settings.${spec.label}Hint`)}
          >
            <Input
              id={`connections-${spec.key}`}
              type="number"
              min={spec.min}
              max={spec.max}
              value={draft[spec.key]}
              onChange={(e) => setDraft((d) => ({ ...d, [spec.key]: Number(e.target.value) }))}
            />
          </Field>
        ))}
      </div>
      <h3 className="border-t border-sep pt-4 text-[13px] font-medium">
        {t('connections.settings.registries')}
      </h3>
      <p className="text-xs text-muted-foreground">{t('connections.settings.registriesHint')}</p>
      <ul className="flex flex-col gap-2">
        {sources.map((source) => (
          <li key={source.id} className="flex items-center justify-between gap-4">
            <Label htmlFor={`mcp-registry-${source.id}`}>{source.title}</Label>
            <Switch
              id={`mcp-registry-${source.id}`}
              checked={draft.registries[source.id] ?? source.enabled}
              onCheckedChange={(on) =>
                setDraft((d) => ({ ...d, registries: { ...d.registries, [source.id]: on } }))
              }
            />
          </li>
        ))}
      </ul>
      <h3 className="border-t border-sep pt-4 text-[13px] font-medium">
        {t('connections.settings.programs')}
      </h3>
      <p className="text-xs text-muted-foreground">{t('connections.settings.programsHint')}</p>
      <ul className="flex flex-wrap gap-2 text-[12.5px]">
        {requirements.map((r) => (
          <li
            key={r.program}
            className={
              r.found
                ? 'bg-status-completed/15 text-status-completed rounded px-2 py-0.5'
                : 'rounded bg-subtle px-2 py-0.5 text-muted-foreground'
            }
          >
            {r.program} ·{' '}
            {r.found ? t('connections.settings.found') : t('connections.settings.missing')}
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">{t('connections.settings.store')}</p>
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

/** «Conexiones MCP»: the timeouts, the login's return port and the registries. */
export function ConnectionsSection() {
  const { t } = useTranslation()
  const { data } = useConnectionSettings()
  return (
    <section
      aria-labelledby="connections-title"
      className="flex flex-col gap-4 rounded-xl border border-sep p-4 shadow-card bg-card-grad"
    >
      <h2 id="connections-title" className="text-[15px] font-medium">
        {t('connections.settings.title')}
      </h2>
      {data ? <Form initial={data} /> : <Skeleton aria-busy className="h-40 rounded-lg" />}
    </section>
  )
}
