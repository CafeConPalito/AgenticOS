import { AlertTriangle, FileText, Globe, Image as ImageIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { KnowledgeDoc } from '@/api/knowledge'
import { Badge } from '@/components/ui/badge'
import { formatBytes } from '@/lib/format'
import { isPending, progressPercent } from './status'

function ProgressBar({ doc }: { doc: KnowledgeDoc }) {
  const { t } = useTranslation()
  const percent = progressPercent(doc)
  return (
    <div className="flex items-center gap-2">
      <div
        role="progressbar"
        aria-label={t('knowledge.row.progress', { title: doc.title })}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent ?? undefined}
        className="relative h-1.5 w-40 overflow-hidden rounded-full bg-muted"
      >
        <div
          className={
            percent === null
              ? 'absolute inset-y-0 w-1/3 animate-pulse rounded-full bg-primary-action'
              : 'absolute inset-y-0 left-0 bg-primary-action'
          }
          style={percent === null ? undefined : { width: `${percent}%` }}
        />
      </div>
      {doc.progress_total > 0 && (
        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
          {doc.progress_done}/{doc.progress_total}
        </span>
      )}
    </div>
  )
}

function DocIcon({ doc }: { doc: KnowledgeDoc }) {
  const Icon =
    doc.source_kind === 'url' ? Globe : doc.source_kind === 'image' ? ImageIcon : FileText
  return <Icon aria-hidden className="size-5 shrink-0 text-muted-foreground" />
}

export function DocRow({ doc, onOpen }: { doc: KnowledgeDoc; onOpen: (id: string) => void }) {
  const { t } = useTranslation()
  const meta = [
    doc.file_name ?? doc.url,
    doc.size !== null ? formatBytes(doc.size) : null,
    doc.status === 'ready' ? t('knowledge.row.tokens', { count: doc.md_tokens }) : null,
  ].filter(Boolean)
  return (
    <li>
      <button
        type="button"
        aria-label={t('knowledge.row.open', { title: doc.title })}
        onClick={() => onOpen(doc.id)}
        className="flex w-full items-center gap-3 rounded-lg border bg-card px-3.5 py-3 text-left transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <DocIcon doc={doc} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[13.5px] font-medium">{doc.title}</span>
            {doc.mode !== 'auto' && (
              <Badge variant="outline">{t(`knowledge.modes.${doc.mode}`)}</Badge>
            )}
          </div>
          <div className="truncate font-mono text-[11.5px] text-muted-foreground">
            {meta.join(' · ')}
          </div>
          {isPending(doc) && doc.status !== 'queued' && <ProgressBar doc={doc} />}
          {doc.status === 'failed' && (
            <div className="text-[12px] text-status-failed">
              {t(`knowledge.errors.${doc.error_code ?? 'unknown'}`, {
                defaultValue: doc.error_message ?? t('knowledge.errors.unknown'),
              })}
            </div>
          )}
        </div>
        {doc.presence !== 'ok' && (
          <Badge variant="outline" className="border-status-failed text-status-failed">
            <AlertTriangle />
            {t(`knowledge.presence.${doc.presence}`)}
          </Badge>
        )}
        {doc.notice && (
          <Badge
            variant="outline"
            title={t(`knowledge.notices.${doc.notice}`, { defaultValue: doc.notice })}
          >
            <AlertTriangle />
            {t('knowledge.row.notice')}
          </Badge>
        )}
        <Badge variant={doc.status === 'failed' ? 'destructive' : 'secondary'}>
          {t(`knowledge.status.${doc.status}`)}
        </Badge>
      </button>
    </li>
  )
}

export function DocList({ docs, onOpen }: { docs: KnowledgeDoc[]; onOpen: (id: string) => void }) {
  return (
    <ul className="flex flex-col gap-2">
      {docs.map((doc) => (
        <DocRow key={doc.id} doc={doc} onOpen={onOpen} />
      ))}
    </ul>
  )
}
