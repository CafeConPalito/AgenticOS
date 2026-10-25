import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import type { KnowledgeLevel } from '@/api/knowledge'
import { type Connection, useCreateConnections, useParseJson } from '@/api/connections'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ConnectionForm } from './ConnectionForm'
import { connectionError } from './shared'

/** Pasting the `mcpServers` block a server's README gives: review it, then create. */
function PasteJson({
  level,
  onDone,
}: {
  level?: KnowledgeLevel
  onDone: (created: Connection[]) => void
}) {
  const { t } = useTranslation()
  const parse = useParseJson()
  const create = useCreateConnections()
  const [text, setText] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const servers = parse.data?.servers ?? []

  async function preview() {
    setError(null)
    try {
      await parse.mutateAsync({ text, name })
    } catch (failure) {
      parse.reset()
      setError(connectionError(failure))
    }
  }

  async function confirm() {
    setError(null)
    try {
      const created = await create.mutateAsync({ jsonText: text, name, level })
      toast.success(t('connections.paste.created', { count: created.length }))
      onDone(created)
    } catch (failure) {
      setError(connectionError(failure))
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4">
      <p className="text-[12.5px] text-muted-foreground">{t('connections.paste.hint')}</p>
      <div className="grid gap-1.5">
        <Label htmlFor="paste-json">{t('connections.paste.label')}</Label>
        <Textarea
          id="paste-json"
          value={text}
          rows={10}
          onChange={(e) => {
            setText(e.target.value)
            parse.reset()
          }}
          placeholder={'{ "mcpServers": { "github": { "command": "npx", "args": ["-y", "…"] } } }'}
          className="font-mono text-[12.5px]"
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="paste-name">{t('connections.paste.name')}</Label>
        <Input
          id="paste-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-[260px] font-mono"
        />
      </div>
      {servers.length > 0 && (
        <ul aria-label={t('connections.paste.preview')} className="grid gap-2">
          {servers.map((server) => (
            <li key={server.name} className="rounded-lg border p-2.5 text-[12.5px]">
              <span className="font-mono font-medium">{server.name}</span>
              <span className="ml-2 text-muted-foreground">
                {t(`connections.transport.${server.transport}`)} ·{' '}
                {server.transport === 'stdio'
                  ? [server.command, ...server.args].join(' ')
                  : server.url}
              </span>
              {server.secret_keys.length > 0 && (
                <p className="mt-1">
                  {t('connections.paste.secrets', { keys: server.secret_keys.join(', ') })}
                </p>
              )}
              {server.ignored.length > 0 && (
                <p className="mt-1 text-muted-foreground">
                  {t('connections.paste.ignored', { fields: server.ignored.join(', ') })}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p role="alert" className="text-[13px] text-status-failed">
          {error}
        </p>
      )}
      <div className="mt-auto flex justify-end gap-2 border-t pt-3">
        <Button type="button" variant="outline" disabled={!text.trim()} onClick={preview}>
          {t('connections.paste.review')}
        </Button>
        <Button type="button" disabled={servers.length === 0 || create.isPending} onClick={confirm}>
          {t('connections.paste.create', { count: servers.length || 1 })}
        </Button>
      </div>
    </div>
  )
}

/** A new connection: the form, or a pasted JSON block. */
export function ConnectionEditor({
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
  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-3xl">
        <SheetHeader className="border-b">
          <SheetTitle>{t('connections.editor.titleNew')}</SheetTitle>
          <SheetDescription>{t('connections.editor.description')}</SheetDescription>
        </SheetHeader>
        <Tabs defaultValue="form" className="flex min-h-0 flex-1 flex-col gap-0">
          <TabsList className="mx-4 mt-3">
            <TabsTrigger value="form">{t('connections.editor.tabForm')}</TabsTrigger>
            <TabsTrigger value="json">{t('connections.editor.tabJson')}</TabsTrigger>
          </TabsList>
          <TabsContent value="form" className="flex min-h-0 flex-1 flex-col">
            <ConnectionForm
              level={level}
              onDone={(saved) => {
                if (saved) onCreated?.(saved)
                onClose()
              }}
            />
          </TabsContent>
          <TabsContent value="json" className="flex min-h-0 flex-1 flex-col">
            <PasteJson
              level={level}
              onDone={(created) => {
                if (created[0]) onCreated?.(created[0])
                onClose()
              }}
            />
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  )
}
