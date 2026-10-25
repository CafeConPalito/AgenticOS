import { Download, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type Connection,
  fetchExport,
  useApplyUpdate,
  useConnections,
  useDeleteConnection,
  useUpdatePreview,
} from '@/api/connections'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { relativeTime } from '@/lib/time'
import { AssignmentsPanel } from './AssignmentsPanel'
import { ConnectionForm } from './ConnectionForm'
import { ConnectionTools } from './ConnectionTools'
import { OAuthPanel } from './OAuthPanel'
import { connectionError } from './shared'

/** What an update of an installed server changes, and the button that applies it. */
function UpdateBox({ connection }: { connection: Connection }) {
  const { t } = useTranslation()
  const available = connection.registry?.update_available ?? false
  const preview = useUpdatePreview(available ? connection.id : null)
  const apply = useApplyUpdate()
  const [error, setError] = useState<string | null>(null)
  if (!available || !preview.data) return null
  async function run() {
    setError(null)
    try {
      await apply.mutateAsync(connection.id)
      toast.success(t('connections.update.done'))
    } catch (failed) {
      setError(connectionError(failed))
    }
  }
  return (
    <section className="grid gap-2 rounded-lg border border-status-running/40 p-3 text-[13px]">
      <h3 className="font-medium">
        {t('connections.update.title', { from: preview.data.from, to: preview.data.to })}
      </h3>
      <ul className="grid gap-1 text-[12.5px]">
        {preview.data.changes.map((change) => (
          <li key={change.field}>
            <span className="text-muted-foreground">{change.label}: </span>
            <code className="break-all">{JSON.stringify(change.from)}</code>
            {' → '}
            <code className="break-all">{JSON.stringify(change.to)}</code>
          </li>
        ))}
      </ul>
      <p className="text-[12px] text-muted-foreground">{t('connections.update.never')}</p>
      {error && (
        <p role="alert" className="text-status-failed">
          {error}
        </p>
      )}
      <Button type="button" size="sm" className="w-fit" onClick={run} disabled={apply.isPending}>
        {t('connections.update.apply')}
      </Button>
    </section>
  )
}

function UsageTab({ connection, onDeleted }: { connection: Connection; onDeleted: () => void }) {
  const { t } = useTranslation()
  const remove = useDeleteConnection()
  const [confirm, setConfirm] = useState(false)
  const origin = connection.registry
  const usage = connection.usage

  async function exportJson() {
    const text = await fetchExport(connection.id)
    await navigator.clipboard.writeText(text)
    toast.success(t('connections.usage.exported'))
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4 text-[13px]">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
        <dt className="text-muted-foreground">{t('connections.usage.runs')}</dt>
        <dd>{usage.used_runs}</dd>
        <dt className="text-muted-foreground">{t('connections.usage.calls')}</dt>
        <dd>
          {usage.calls}
          {usage.failed_calls > 0 &&
            ` (${t('connections.usage.failed', { count: usage.failed_calls })})`}
        </dd>
        <dt className="text-muted-foreground">{t('connections.usage.last')}</dt>
        <dd>{usage.last_used ? relativeTime(usage.last_used) : '—'}</dd>
        <dt className="text-muted-foreground">{t('connections.usage.revision')}</dt>
        <dd>{connection.revision}</dd>
      </dl>
      {origin && (
        <section className="grid gap-1 text-[12.5px]">
          <h3 className="font-medium">{t('connections.usage.origin')}</h3>
          <p>
            {t('connections.usage.from', { source: origin.source, package: origin.package })}
            {origin.version ? ` @ ${origin.version}` : ''}
            {origin.official ? ` · ${t('connections.usage.official')}` : ''}
          </p>
          {origin.repo_url && (
            <a href={origin.repo_url} target="_blank" rel="noreferrer" className="underline">
              {origin.repo_url}
            </a>
          )}
        </section>
      )}
      <UpdateBox connection={connection} />
      <div className="mt-auto flex flex-wrap gap-2 border-t pt-3">
        <Button type="button" size="sm" variant="outline" onClick={exportJson}>
          <Download />
          {t('connections.usage.export')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="text-status-failed"
          onClick={() => setConfirm(true)}
        >
          <Trash2 />
          {t('common.delete')}
        </Button>
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={t('connections.delete.title', { name: connection.name })}
        description={t('connections.delete.description')}
        confirmLabel={t('common.delete')}
        destructive
        onConfirm={() =>
          void remove.mutateAsync(connection.id).then(() => {
            setConfirm(false)
            onDeleted()
          })
        }
      />
    </div>
  )
}

/** One connection in a sheet: its settings and secrets, its tools, where it is given, its use. */
export function ConnectionSheet({
  connectionId,
  onClose,
}: {
  connectionId: string | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const connections = useConnections()
  const connection = connections.data?.find((c) => c.id === connectionId)
  return (
    <Sheet open={connectionId !== null} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        <SheetHeader className="border-b">
          <SheetTitle className="font-mono">{connection?.name ?? ''}</SheetTitle>
          <SheetDescription>
            {connection?.description || t('connections.sheet.description')}
          </SheetDescription>
        </SheetHeader>
        {connection && (
          <Tabs defaultValue="config" className="flex min-h-0 flex-1 flex-col gap-0">
            <TabsList className="mx-4 mt-3">
              <TabsTrigger value="config">{t('connections.sheet.config')}</TabsTrigger>
              <TabsTrigger value="tools">{t('connections.sheet.tools')}</TabsTrigger>
              <TabsTrigger value="where">{t('connections.sheet.where')}</TabsTrigger>
              <TabsTrigger value="usage">{t('connections.sheet.usage')}</TabsTrigger>
            </TabsList>
            <TabsContent value="config" className="flex min-h-0 flex-1 flex-col">
              {connection.auth === 'oauth' && (
                <div className="px-4 pt-4">
                  <OAuthPanel connection={connection} />
                </div>
              )}
              <ConnectionForm
                key={`${connection.id}-${connection.revision}-${connection.updated_at}`}
                connection={connection}
                onDone={() => {}}
              />
            </TabsContent>
            <TabsContent value="tools" className="flex min-h-0 flex-1 flex-col">
              <ConnectionTools
                key={`${connection.id}-${connection.revision}`}
                connection={connection}
              />
            </TabsContent>
            <TabsContent value="where" className="flex min-h-0 flex-1 flex-col">
              <AssignmentsPanel connection={connection} />
            </TabsContent>
            <TabsContent value="usage" className="flex min-h-0 flex-1 flex-col">
              <UsageTab connection={connection} onDeleted={onClose} />
            </TabsContent>
          </Tabs>
        )}
      </SheetContent>
    </Sheet>
  )
}
