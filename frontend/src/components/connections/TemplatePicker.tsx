import { Plug } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import {
  type Connection,
  type ConnectionTemplate,
  useFromTemplate,
  useRequirements,
  useTemplates,
} from '@/api/connections'
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
import { connectionError } from './shared'

/** The form of one template: only what the server asks for. Nothing is installed or run. */
function TemplateForm({
  template,
  level,
  onBack,
  onDone,
}: {
  template: ConnectionTemplate
  level?: KnowledgeLevel
  onBack: () => void
  onDone: (created: Connection) => void
}) {
  const { t } = useTranslation()
  const make = useFromTemplate()
  const requirements = useRequirements()
  const [values, setValues] = useState<Record<string, string>>({})
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const missing = template.requires.filter((program) =>
    (requirements.data ?? []).some((r) => r.program === program && !r.found),
  )

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      const created = await make.mutateAsync({
        template: template.id,
        name: name.trim() || undefined,
        values,
        level,
      })
      toast.success(t('connections.form.created', { name: created.name }))
      onDone(created)
    } catch (failure) {
      setError(connectionError(failure))
    }
  }

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
      <div>
        <h3 className="text-[15px] font-medium">{template.name}</h3>
        <p className="text-[12.5px] text-muted-foreground">{template.description}</p>
        <p className="mt-1 font-mono text-[12px] text-muted-foreground">
          {template.command || template.url}
        </p>
      </div>
      {missing.length > 0 && (
        <p role="alert" className="rounded-lg bg-status-waiting/10 p-2.5 text-[12.5px]">
          {t('connections.templates.missing', { programs: missing.join(', ') })}
        </p>
      )}
      {template.fields.map((field) => (
        <div key={field.key} className="grid gap-1.5">
          <Label htmlFor={`field-${field.key}`}>{field.label}</Label>
          <Input
            id={`field-${field.key}`}
            type={field.secret ? 'password' : 'text'}
            autoComplete="off"
            value={values[field.key] ?? ''}
            onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
            className={field.secret || field.kind === 'path' ? 'font-mono' : undefined}
          />
          {field.help && <p className="text-[12px] text-muted-foreground">{field.help}</p>}
          {field.help_url && (
            <a
              href={field.help_url}
              target="_blank"
              rel="noreferrer"
              className="w-fit text-[12px] underline"
            >
              {t('connections.templates.help')}
            </a>
          )}
        </div>
      ))}
      {template.auth === 'oauth' && (
        <p className="text-[12.5px] text-muted-foreground">{t('connections.templates.oauth')}</p>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor="template-name">{t('connections.templates.name')}</Label>
        <Input
          id="template-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={template.id}
          className="w-[260px] font-mono"
        />
      </div>
      {error && (
        <p role="alert" className="text-[13px] text-status-failed">
          {error}
        </p>
      )}
      <div className="mt-auto flex justify-end gap-2 border-t pt-3">
        <Button type="button" variant="outline" onClick={onBack}>
          {t('common.back')}
        </Button>
        <Button type="submit" disabled={make.isPending}>
          {t('connections.templates.create')}
        </Button>
      </div>
    </form>
  )
}

/** «Nueva desde plantilla»: the servers people use most, one click away. */
export function TemplatePicker({
  open,
  onClose,
  level,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  level?: KnowledgeLevel
  onCreated?: (created: Connection) => void
}) {
  const { t } = useTranslation()
  const templates = useTemplates()
  const [chosen, setChosen] = useState<ConnectionTemplate | null>(null)
  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-2xl">
        <SheetHeader className="border-b">
          <SheetTitle>{t('connections.templates.title')}</SheetTitle>
          <SheetDescription>{t('connections.templates.description')}</SheetDescription>
        </SheetHeader>
        {chosen ? (
          <TemplateForm
            template={chosen}
            level={level}
            onBack={() => setChosen(null)}
            onDone={(created) => {
              onCreated?.(created)
              onClose()
            }}
          />
        ) : (
          <div className="grid min-h-0 flex-1 gap-2 overflow-auto p-4 sm:grid-cols-2">
            {(templates.data ?? []).map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => setChosen(template)}
                className="flex items-start gap-2.5 rounded-xl border p-3 text-left hover:bg-accent"
              >
                <Plug className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium">{template.name}</span>
                  <span className="line-clamp-2 text-[12.5px] text-muted-foreground">
                    {template.description}
                  </span>
                  <span className="mt-1 block text-[11.5px] text-muted-foreground">
                    {t(`connections.transport.${template.transport}`)}
                    {template.auth === 'oauth' ? ` · ${t('connections.templates.account')}` : ''}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
