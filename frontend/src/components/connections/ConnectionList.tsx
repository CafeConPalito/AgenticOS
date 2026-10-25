import { Compass, Download, LayoutTemplate, Plug, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { KnowledgeLevel } from '@/api/knowledge'
import { type Connection, useAddAssignment, useConnections } from '@/api/connections'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { ConnectionCard } from './ConnectionCard'
import { ConnectionEditor } from './ConnectionEditor'
import { ConnectionImportDialog } from './ConnectionImportDialog'
import { ConnectionSheet } from './ConnectionSheet'
import { TemplatePicker } from './TemplatePicker'

/**
 * The catalog of connections: the cards with their switch, whether they work and their use;
 * creating one (form, pasted JSON or a template) and importing the ones the CLIs already have.
 * `onlyLevel` shows the ones given to that level (a project's tab).
 */
export function ConnectionList({
  onlyLevel,
  explore = false,
  initialOpen = null,
}: {
  onlyLevel?: KnowledgeLevel
  /** Shows the link to the explorer (the page has it as a tab). */
  explore?: boolean
  /** A connection to open at once (a link from the Inbox). */
  initialOpen?: string | null
}) {
  const { t } = useTranslation()
  const connections = useConnections()
  const [opened, setOpened] = useState<string | null>(initialOpen)
  const [creating, setCreating] = useState(false)
  const [templates, setTemplates] = useState(false)
  const [importing, setImporting] = useState(false)
  const all: Connection[] = connections.data ?? []
  const shown = onlyLevel
    ? all.filter((c) =>
        c.assignments.some(
          (a) =>
            a.scope === onlyLevel.scope &&
            (onlyLevel.scope !== 'project' || a.project_id === onlyLevel.projectId) &&
            (onlyLevel.scope !== 'agent' || a.agent_id === onlyLevel.agentId),
        ),
      )
    : all
  const active = all.filter((c) => c.enabled).length
  const give = useAddAssignment()
  const [pick, setPick] = useState('')
  const notHere = all.filter((c) => !shown.some((s) => s.id === c.id))

  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-8">
      <p className="max-w-[760px] text-[13px] text-muted-foreground">{t('connections.intro')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={() => setCreating(true)}>
          <Plus />
          {t('connections.actions.new')}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setTemplates(true)}>
          <LayoutTemplate />
          {t('connections.actions.fromTemplate')}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setImporting(true)}>
          <Download />
          {t('connections.actions.import')}
        </Button>
        {explore && (
          <Button asChild size="sm" variant="outline">
            <Link to="/conexiones?vista=explorar">
              <Compass />
              {t('connections.actions.explore')}
            </Link>
          </Button>
        )}
        {onlyLevel && notHere.length > 0 && (
          <span className="flex items-center gap-2">
            <Select value={pick} onValueChange={setPick}>
              <SelectTrigger
                aria-label={t('connections.actions.giveExisting')}
                className="h-8 w-[220px]"
              >
                <SelectValue placeholder={t('connections.actions.giveExisting')} />
              </SelectTrigger>
              <SelectContent>
                {notHere.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!pick || give.isPending}
              onClick={() =>
                give.mutate({ id: pick, level: onlyLevel }, { onSuccess: () => setPick('') })
              }
            >
              {t('connections.actions.give')}
            </Button>
          </span>
        )}
        {all.length > 0 && (
          <span className="ml-auto text-[12.5px] text-muted-foreground">
            {t('connections.count', { active, total: all.length })}
          </span>
        )}
      </div>
      {connections.isPending ? (
        <Skeleton aria-busy className="h-24 rounded-lg" />
      ) : connections.isError ? (
        <p role="alert" className="text-status-failed">
          {t('connections.loadFailed')}
        </p>
      ) : shown.length === 0 ? (
        <EmptyState
          icon={Plug}
          title={t('connections.empty.title')}
          description={t('connections.empty.description')}
        />
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
          {shown.map((connection) => (
            <ConnectionCard key={connection.id} connection={connection} onOpen={setOpened} />
          ))}
        </div>
      )}
      <ConnectionSheet connectionId={opened} onClose={() => setOpened(null)} />
      {creating && (
        <ConnectionEditor
          open
          level={onlyLevel}
          onClose={() => setCreating(false)}
          onCreated={(created) => setOpened(created.id)}
        />
      )}
      {templates && (
        <TemplatePicker
          open
          level={onlyLevel}
          onClose={() => setTemplates(false)}
          onCreated={(created) => setOpened(created.id)}
        />
      )}
      <ConnectionImportDialog open={importing} onClose={() => setImporting(false)} />
    </div>
  )
}
