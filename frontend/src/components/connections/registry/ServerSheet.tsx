import { ShieldAlert, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import { type ServerOption, useInstallServer, useServerDetail } from '@/api/connections'
import { connectionError } from '@/components/connections/shared'
import { LevelSelect } from '@/components/skills/shared'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'

/** The form of one way to run the server: the exact command, what the machine lacks and the
 * values it asks for. Nothing runs until the person tests the connection that is created. */
function InstallForm({
  source,
  reference,
  option,
  name,
  onInstalled,
}: {
  source: string
  reference: string
  option: ServerOption
  name: string
  onInstalled: () => void
}) {
  const { t } = useTranslation()
  const install = useInstallServer()
  const [values, setValues] = useState<Record<string, string>>({})
  const [custom, setCustom] = useState('')
  const [login, setLogin] = useState(option.oauth)
  const [give, setGive] = useState(false)
  const [level, setLevel] = useState<KnowledgeLevel>({ scope: 'general' })
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      const created = await install.mutateAsync({
        source,
        ref: reference,
        option: option.index,
        name: custom.trim() || undefined,
        values,
        oauth: option.kind === 'remote' ? login : undefined,
        level: give ? level : undefined,
      })
      toast.success(t('connections.explore.installed', { name: created.name }))
      onInstalled()
    } catch (failed) {
      setError(connectionError(failed))
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <div className="grid gap-1.5">
        <h4 className="text-[12.5px] text-muted-foreground">{t('connections.explore.willRun')}</h4>
        <code className="rounded-lg bg-subtle p-2.5 font-mono text-[12.5px] break-all">
          {option.command}
        </code>
      </div>
      {option.missing.length > 0 && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg bg-status-waiting/10 p-2.5 text-[12.5px]"
        >
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-status-waiting" aria-hidden />
          {t('connections.explore.missing', { programs: option.missing.join(', ') })}
        </p>
      )}
      {option.fields.map((field) => (
        <div key={`${field.where}-${field.key}`} className="grid gap-1.5">
          <Label htmlFor={`install-${field.key}`}>
            {field.label}
            {field.required && ' *'}
          </Label>
          <Input
            id={`install-${field.key}`}
            type={field.secret ? 'password' : 'text'}
            autoComplete="off"
            placeholder={field.default}
            value={values[field.key] ?? ''}
            onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
            className="font-mono"
          />
          {field.description && (
            <p className="text-[12px] text-muted-foreground">{field.description}</p>
          )}
        </div>
      ))}
      {option.kind === 'remote' && (
        <label className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={login} onChange={(e) => setLogin(e.target.checked)} />
          {t('connections.explore.login')}
        </label>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor="install-name">{t('connections.explore.name')}</Label>
        <Input
          id="install-name"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          placeholder={name}
          className="w-[260px] font-mono"
        />
      </div>
      <div className="grid gap-2">
        <label className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={give} onChange={(e) => setGive(e.target.checked)} />
          {t('connections.explore.give')}
        </label>
        {give && (
          <LevelSelect
            value={level}
            onChange={setLevel}
            label={t('connections.explore.levelLabel')}
          />
        )}
      </div>
      {error && (
        <p role="alert" className="text-[13px] text-status-failed">
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <Button type="submit" disabled={install.isPending}>
          {t('connections.explore.install')}
        </Button>
      </div>
    </form>
  )
}

/** The ficha of a server from a registry, before installing it (spec G). */
export function ServerSheet({
  source,
  reference,
  onClose,
}: {
  source: string | null
  reference: string | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const detail = useServerDetail(source, reference)
  const [chosen, setChosen] = useState(0)
  const data = detail.data
  const option = data?.options[chosen] ?? data?.options[0]
  return (
    <Sheet open={source !== null} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        <SheetHeader className="border-b">
          <SheetTitle>{data?.card.name ?? reference ?? ''}</SheetTitle>
          <SheetDescription>{data?.card.description ?? ''}</SheetDescription>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
          <p className="flex items-start gap-2 rounded-lg bg-status-waiting/10 p-2.5 text-[12.5px]">
            <ShieldAlert className="mt-0.5 size-4 shrink-0 text-status-waiting" aria-hidden />
            {t('connections.explore.warning')}
          </p>
          {detail.isPending && source ? (
            <Skeleton aria-busy className="h-32 rounded-lg" />
          ) : detail.isError ? (
            <p role="alert" className="text-status-failed">
              {connectionError(detail.error)}
            </p>
          ) : data && option ? (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-[12.5px]">
                <dt className="text-muted-foreground">{t('connections.explore.author')}</dt>
                <dd>
                  {data.card.author}
                  {data.card.verified && (
                    <span className="bg-status-completed/15 text-status-completed ml-2 rounded px-1.5">
                      {t('connections.explore.verified')}
                    </span>
                  )}
                </dd>
                {data.license && (
                  <>
                    <dt className="text-muted-foreground">{t('connections.explore.license')}</dt>
                    <dd>{data.license}</dd>
                  </>
                )}
                {data.card.version && (
                  <>
                    <dt className="text-muted-foreground">{t('connections.explore.version')}</dt>
                    <dd>{data.card.version}</dd>
                  </>
                )}
                {data.repo_url && (
                  <>
                    <dt className="text-muted-foreground">{t('connections.explore.repo')}</dt>
                    <dd>
                      <a
                        href={data.repo_url}
                        target="_blank"
                        rel="noreferrer"
                        className="underline"
                      >
                        {data.repo_url}
                      </a>
                    </dd>
                  </>
                )}
              </dl>
              {data.note && <p className="text-[12.5px] text-muted-foreground">{data.note}</p>}
              {data.installed_as && (
                <p className="rounded-lg bg-subtle p-2.5 text-[12.5px]">
                  {t('connections.explore.alreadyInstalled', { name: data.installed_as })}
                </p>
              )}
              {data.options.length > 1 && (
                <fieldset className="flex flex-wrap gap-4">
                  <legend className="sr-only">{t('connections.explore.ways')}</legend>
                  {data.options.map((o) => (
                    <label key={o.index} className="flex items-center gap-1.5 text-[13px]">
                      <input
                        type="radio"
                        name="server-option"
                        checked={chosen === o.index}
                        onChange={() => setChosen(o.index)}
                      />
                      {o.label}
                    </label>
                  ))}
                </fieldset>
              )}
              <InstallForm
                key={`${data.card.ref}-${option.index}`}
                source={data.card.source}
                reference={data.card.ref}
                option={option}
                name={data.card.name}
                onInstalled={onClose}
              />
              {data.tools.length > 0 && (
                <section>
                  <h4 className="text-[12.5px] text-muted-foreground">
                    {t('connections.explore.declaredTools', { count: data.tools.length })}
                  </h4>
                  <ul className="mt-1 grid gap-1 text-[12.5px]">
                    {data.tools.map((tool) => (
                      <li key={tool.name}>
                        <span className="font-mono">{tool.name}</span>
                        {tool.description && (
                          <span className="ml-2 text-muted-foreground">{tool.description}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}
