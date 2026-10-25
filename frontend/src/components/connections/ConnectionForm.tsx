import { Plus, Trash2, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import {
  type Connection,
  type Transport,
  useCreateConnections,
  useUpdateConnection,
} from '@/api/connections'
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
import { Textarea } from '@/components/ui/textarea'
import { connectionError, placeholder, secretKeyFor, secretKeysIn } from './shared'

interface Row {
  id: number
  name: string
  value: string
}

let rowId = 0
const rowsOf = (values: Record<string, string>): Row[] =>
  Object.entries(values).map(([name, value]) => ({ id: ++rowId, name, value }))
const objectOf = (rows: Row[]): Record<string, string> =>
  Object.fromEntries(rows.filter((r) => r.name.trim()).map((r) => [r.name.trim(), r.value]))

/** Rows of `name = value` (variables or headers); a row can hold a secret instead of a value. */
function Rows({
  label,
  rows,
  onChange,
  nameLabel,
}: {
  label: string
  rows: Row[]
  onChange: (rows: Row[]) => void
  nameLabel: string
}) {
  const { t } = useTranslation()
  const update = (id: number, patch: Partial<Row>) =>
    onChange(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-1 text-[12.5px] text-muted-foreground">{label}</legend>
      {rows.map((row) => {
        const secret = /\$\{secret:/.test(row.value)
        return (
          <div key={row.id} className="flex items-center gap-2">
            <Input
              aria-label={`${nameLabel} ${row.name || row.id}`}
              value={row.name}
              onChange={(e) => update(row.id, { name: e.target.value })}
              className="h-8 w-[200px] font-mono text-[12.5px]"
            />
            <Input
              aria-label={t('connections.form.valueOf', { name: row.name || row.id })}
              value={row.value}
              onChange={(e) => update(row.id, { value: e.target.value })}
              className="h-8 min-w-0 flex-1 font-mono text-[12.5px]"
            />
            <label className="flex items-center gap-1 text-[12px] whitespace-nowrap">
              <input
                type="checkbox"
                checked={secret}
                aria-label={t('connections.form.secretOf', { name: row.name || row.id })}
                onChange={(e) =>
                  update(row.id, {
                    value: e.target.checked ? placeholder(secretKeyFor(row.name)) : '',
                  })
                }
              />
              {t('connections.form.secret')}
            </label>
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label={t('connections.form.removeRow', { name: row.name || row.id })}
              onClick={() => onChange(rows.filter((r) => r.id !== row.id))}
            >
              <Trash2 />
            </Button>
          </div>
        )
      })}
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="w-fit"
        onClick={() => onChange([...rows, { id: ++rowId, name: '', value: '' }])}
      >
        <Plus />
        {t('connections.form.addRow')}
      </Button>
    </fieldset>
  )
}

/**
 * Creates a connection (at `level`, if given) or edits `connection`: the server (a command or a
 * URL), its variables and headers, and the values of the secrets they mention. A secret value
 * is sent to the credential store and never read back (CA3).
 */
export function ConnectionForm({
  connection,
  level,
  onDone,
}: {
  connection?: Connection
  level?: KnowledgeLevel
  onDone: (saved?: Connection) => void
}) {
  const { t } = useTranslation()
  const create = useCreateConnections()
  const update = useUpdateConnection()
  const [name, setName] = useState(connection?.name ?? '')
  const [description, setDescription] = useState(connection?.description ?? '')
  const [transport, setTransport] = useState<Transport>(connection?.transport ?? 'stdio')
  const [command, setCommand] = useState(connection?.command ?? '')
  const [args, setArgs] = useState((connection?.args ?? []).join('\n'))
  const [url, setUrl] = useState(connection?.url ?? '')
  const [env, setEnv] = useState<Row[]>(() => rowsOf(connection?.env ?? {}))
  const [headers, setHeaders] = useState<Row[]>(() => rowsOf(connection?.headers ?? {}))
  const [oauth, setOauth] = useState(connection?.auth === 'oauth')
  const [typed, setTyped] = useState<Record<string, string>>({})
  const [cleared, setCleared] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const local = transport === 'stdio'
  const argList = args.split('\n').filter((a) => a.trim() !== '')
  const keys = [
    ...new Set([
      ...secretKeysIn(
        command,
        url,
        ...argList,
        ...env.map((r) => r.value),
        ...headers.map((r) => r.value),
      ),
      ...(connection?.secrets.map((s) => s.key) ?? []),
    ]),
  ]
  const isSet = (key: string) =>
    !cleared.includes(key) && (connection?.secrets.find((s) => s.key === key)?.set ?? false)
  const busy = create.isPending || update.isPending

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    const values = Object.fromEntries(
      Object.entries(typed).filter(([key, value]) => value !== '' && keys.includes(key)),
    )
    const config = {
      description,
      transport,
      command: local ? command.trim() : '',
      args: local ? argList : [],
      url: local ? '' : url.trim(),
      env: local ? objectOf(env) : {},
      headers: local ? {} : objectOf(headers),
      auth: !local && oauth ? ('oauth' as const) : ('none' as const),
    }
    try {
      if (connection) {
        const saved = await update.mutateAsync({
          id: connection.id,
          name: name.trim(),
          ...config,
          secrets: values,
          remove_secrets: cleared.filter((key) => !(key in values)),
        })
        toast.success(t('connections.form.saved', { name: saved.name }))
        onDone(saved)
      } else {
        const [created] = await create.mutateAsync({
          name: name.trim(),
          ...config,
          secrets: values,
          level,
        })
        toast.success(t('connections.form.created', { name: created.name }))
        onDone(created)
      }
    } catch (failure) {
      setError(connectionError(failure))
    }
  }

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
      <div className="grid gap-1.5">
        <Label htmlFor="connection-name">{t('connections.form.name')}</Label>
        <Input
          id="connection-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="github"
          className="font-mono"
          required
        />
        <p className="text-[12px] text-muted-foreground">{t('connections.form.nameHint')}</p>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="connection-description">{t('connections.form.description')}</Label>
        <Input
          id="connection-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="connection-transport">{t('connections.form.transport')}</Label>
        <Select value={transport} onValueChange={(v) => setTransport(v as Transport)}>
          <SelectTrigger id="connection-transport" className="h-8 w-[260px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(['stdio', 'http', 'sse'] as const).map((value) => (
              <SelectItem key={value} value={value}>
                {t(`connections.transport.${value}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {local ? (
        <>
          <p className="flex items-start gap-2 rounded-lg bg-status-waiting/10 p-2.5 text-[12.5px]">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-status-waiting" aria-hidden />
            {t('connections.form.stdioWarning')}
          </p>
          <div className="grid gap-1.5">
            <Label htmlFor="connection-command">{t('connections.form.command')}</Label>
            <Input
              id="connection-command"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="npx"
              className="font-mono"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="connection-args">{t('connections.form.args')}</Label>
            <Textarea
              id="connection-args"
              value={args}
              onChange={(e) => setArgs(e.target.value)}
              rows={3}
              className="font-mono text-[12.5px]"
            />
            <p className="text-[12px] text-muted-foreground">{t('connections.form.argsHint')}</p>
          </div>
          <Rows
            label={t('connections.form.env')}
            nameLabel={t('connections.form.variable')}
            rows={env}
            onChange={setEnv}
          />
        </>
      ) : (
        <>
          <div className="grid gap-1.5">
            <Label htmlFor="connection-url">{t('connections.form.url')}</Label>
            <Input
              id="connection-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://mcp.example.com/mcp"
              className="font-mono"
            />
          </div>
          <Rows
            label={t('connections.form.headers')}
            nameLabel={t('connections.form.header')}
            rows={headers}
            onChange={setHeaders}
          />
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={oauth} onChange={(e) => setOauth(e.target.checked)} />
            {t('connections.form.oauth')}
          </label>
        </>
      )}
      {keys.length > 0 && (
        <fieldset className="grid gap-2 rounded-lg border p-3">
          <legend className="px-1 text-[12.5px] text-muted-foreground">
            {t('connections.form.secrets')}
          </legend>
          <p className="text-[12px] text-muted-foreground">{t('connections.form.secretsHint')}</p>
          {keys.map((key) => (
            <div key={key} className="flex items-center gap-2">
              <span className="w-[200px] truncate font-mono text-[12.5px]">{key}</span>
              <Input
                type="password"
                autoComplete="off"
                aria-label={t('connections.form.secretValue', { key })}
                placeholder={
                  isSet(key)
                    ? t('connections.form.secretKept')
                    : t('connections.form.secretMissing')
                }
                value={typed[key] ?? ''}
                onChange={(e) => setTyped({ ...typed, [key]: e.target.value })}
                className="h-8 min-w-0 flex-1"
              />
              {isSet(key) && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setCleared([...cleared, key])}
                >
                  {t('connections.form.secretClear')}
                </Button>
              )}
            </div>
          ))}
        </fieldset>
      )}
      {error && (
        <p role="alert" className="text-[13px] text-status-failed">
          {error}
        </p>
      )}
      <div className="mt-auto flex justify-end gap-2 border-t pt-3">
        <Button type="button" variant="outline" onClick={() => onDone()}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" disabled={busy || !name.trim()}>
          {t('connections.actions.save')}
        </Button>
      </div>
    </form>
  )
}
