import { LoaderCircle, Play, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type Connection,
  type McpTool,
  cancelTest,
  useStartTest,
  useTest,
  useUpdateConnection,
} from '@/api/connections'
import { Button } from '@/components/ui/button'
import { relativeTime } from '@/lib/time'
import { TestErrorBox, connectionError } from './shared'

function ToolRow({
  tool,
  selecting,
  allowed,
  preapproved,
  onAllow,
  onPreapprove,
}: {
  tool: McpTool
  selecting: boolean
  allowed: boolean
  preapproved: boolean
  onAllow: (on: boolean) => void
  onPreapprove: (on: boolean) => void
}) {
  const { t } = useTranslation()
  return (
    <li className="flex items-start gap-3 rounded-lg border p-2.5">
      {selecting && (
        <input
          type="checkbox"
          className="mt-1"
          checked={allowed}
          aria-label={t('connections.tools.allow', { name: tool.name })}
          onChange={(e) => onAllow(e.target.checked)}
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[13px] font-medium">{tool.name}</span>
          {tool.read_only && (
            <span className="rounded bg-subtle px-1.5 text-[11px]">
              {t('connections.tools.readOnly')}
            </span>
          )}
          {tool.destructive && (
            <span className="rounded bg-status-failed/15 px-1.5 text-[11px] text-status-failed">
              {t('connections.tools.destructive')}
            </span>
          )}
        </div>
        {tool.description && (
          <p className="line-clamp-2 text-[12.5px] text-muted-foreground">{tool.description}</p>
        )}
      </div>
      <label className="flex items-center gap-1 text-[12px] whitespace-nowrap">
        <input
          type="checkbox"
          checked={preapproved}
          disabled={selecting && !allowed}
          aria-label={t('connections.tools.preapprove', { name: tool.name })}
          onChange={(e) => onPreapprove(e.target.checked)}
        />
        <ShieldCheck className="size-3.5" aria-hidden />
        {t('connections.tools.noAsk')}
      </label>
    </li>
  )
}

/**
 * Tests the connection (start the server, list what it offers) and chooses which of its tools
 * the agents get and which need no permission (CA4, CA7).
 */
export function ConnectionTools({ connection }: { connection: Connection }) {
  const { t } = useTranslation()
  const start = useStartTest()
  const update = useUpdateConnection()
  const [testId, setTestId] = useState<string | null>(null)
  const test = useTest(testId)
  const [mode, setMode] = useState(connection.tool_mode)
  const [allowed, setAllowed] = useState<string[]>(connection.allowed_tools)
  const [preapproved, setPreapproved] = useState<string[]>(connection.preapproved_tools)
  const [error, setError] = useState<string | null>(null)
  const running = test.data?.state === 'running' || start.isPending
  const selecting = mode === 'selected'
  const result = test.data?.result ?? null
  const failure = result ? result.error : connection.test_error
  const toggle = (list: string[], name: string, on: boolean) =>
    on ? [...new Set([...list, name])] : list.filter((n) => n !== name)

  async function run() {
    setError(null)
    try {
      const started = await start.mutateAsync(connection.id)
      setTestId(started.id)
    } catch (failed) {
      setError(connectionError(failed))
    }
  }

  async function save() {
    setError(null)
    try {
      await update.mutateAsync({
        id: connection.id,
        tool_mode: mode,
        allowed_tools: allowed,
        preapproved_tools: preapproved.filter((n) => mode === 'all' || allowed.includes(n)),
      })
      toast.success(t('connections.tools.saved'))
    } catch (failed) {
      setError(connectionError(failed))
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" disabled={running} onClick={run}>
          {running ? <LoaderCircle className="animate-spin" /> : <Play />}
          {running ? t('connections.tools.testing') : t('connections.tools.test')}
        </Button>
        {running && testId && (
          <Button type="button" size="sm" variant="outline" onClick={() => void cancelTest(testId)}>
            {t('common.cancel')}
          </Button>
        )}
        {result?.ok && (
          <span role="status" className="text-status-completed text-[12.5px]">
            {t('connections.tools.works', {
              tools: result.tools.length,
              seconds: result.seconds,
            })}
          </span>
        )}
        {!result && connection.tested_at && !connection.test_error && (
          <span className="text-[12.5px] text-muted-foreground">
            {t('connections.tools.lastTest', { when: relativeTime(connection.tested_at) })}
          </span>
        )}
      </div>
      {error && (
        <p role="alert" className="text-[13px] text-status-failed">
          {error}
        </p>
      )}
      {failure && !running && <TestErrorBox error={failure} />}
      {connection.tools_changed && (
        <div className="flex items-center gap-3 rounded-lg bg-status-running/10 p-2.5 text-[12.5px]">
          <span className="flex-1">{t('connections.tools.changed')}</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => update.mutate({ id: connection.id, tools_changed: false })}
          >
            {t('connections.tools.seen')}
          </Button>
        </div>
      )}
      {connection.tools.length === 0 ? (
        <p className="text-[13px] text-muted-foreground">{t('connections.tools.none')}</p>
      ) : (
        <>
          <fieldset className="flex flex-wrap items-center gap-4">
            <legend className="sr-only">{t('connections.tools.mode')}</legend>
            {(['all', 'selected'] as const).map((value) => (
              <label key={value} className="flex items-center gap-1.5 text-[13px]">
                <input
                  type="radio"
                  name={`mode-${connection.id}`}
                  checked={mode === value}
                  onChange={() => setMode(value)}
                />
                {t(`connections.tools.mode_${value}`)}
              </label>
            ))}
            <span className="ml-auto text-[12px] text-muted-foreground">
              {t('connections.tools.count', { count: connection.tools.length })}
            </span>
          </fieldset>
          <ul className="grid gap-2">
            {connection.tools.map((tool) => (
              <ToolRow
                key={tool.name}
                tool={tool}
                selecting={selecting}
                allowed={allowed.includes(tool.name)}
                preapproved={preapproved.includes(tool.name)}
                onAllow={(on) => setAllowed(toggle(allowed, tool.name, on))}
                onPreapprove={(on) => setPreapproved(toggle(preapproved, tool.name, on))}
              />
            ))}
          </ul>
          <p className="text-[12px] text-muted-foreground">{t('connections.tools.noAskHint')}</p>
          <div className="flex justify-end">
            <Button type="button" onClick={save} disabled={update.isPending}>
              {t('connections.tools.save')}
            </Button>
          </div>
        </>
      )}
      {connection.resources.length > 0 && (
        <section>
          <h3 className="text-[12.5px] text-muted-foreground">
            {t('connections.tools.resources')}
          </h3>
          <ul className="mt-1 text-[12.5px]">
            {connection.resources.map((r) => (
              <li key={r.uri} className="font-mono">
                {r.name}
              </li>
            ))}
          </ul>
        </section>
      )}
      {connection.prompts.length > 0 && (
        <section>
          <h3 className="text-[12.5px] text-muted-foreground">{t('connections.tools.prompts')}</h3>
          <ul className="mt-1 text-[12.5px]">
            {connection.prompts.map((p) => (
              <li key={p.name} className="font-mono">
                {p.name}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
