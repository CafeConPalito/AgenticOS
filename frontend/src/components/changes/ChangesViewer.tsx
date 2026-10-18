import type { TFunction } from 'i18next'
import { AlertTriangle, GitCompareArrows } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  type Changes,
  type ChangesTarget,
  type RefLabel,
  type RepoChanges,
  useChanges,
} from '@/api/changes'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { ChangesBadge } from './ChangesBadge'
import { FileDiffView, StatusLetter } from './FileDiffView'

function refText(ref: RefLabel | null, t: TFunction): string {
  return ref ? t(`changes.ref.${ref.kind}`, { name: ref.name }) : ''
}

/** The diff of a run or a task: header, and for each repository its list of files and the diff
 * of each one. */
export function ChangesViewer({ target }: { target: ChangesTarget }) {
  const { t } = useTranslation()
  const changes = useChanges(target)

  if (changes.isPending)
    return (
      <div aria-busy className="flex flex-col gap-2">
        <Skeleton className="h-6 w-1/2" />
        <Skeleton className="h-24 rounded-lg" />
        <Skeleton className="h-24 rounded-lg" />
      </div>
    )
  if (changes.isError)
    return (
      <div role="alert" className="flex items-center gap-3 text-[13px] text-status-failed">
        {t('changes.error')}
        <Button variant="outline" size="sm" onClick={() => void changes.refetch()}>
          {t('changes.retry')}
        </Button>
      </div>
    )

  const data = changes.data
  if (data.state !== 'ok' || data.repos.length === 0)
    return (
      <EmptyState
        icon={GitCompareArrows}
        title={t(`changes.empty.${data.state === 'ok' ? 'no_snapshots' : data.state}.title`)}
        description={t(
          `changes.empty.${data.state === 'ok' ? 'no_snapshots' : data.state}.description`,
        )}
      />
    )

  const several = data.repos.length > 1
  return (
    <div className="flex flex-col gap-4">
      <Header data={data} single={several ? null : data.repos[0]} />
      {data.repos.map((part) => (
        <RepoSection
          key={part.key}
          target={{ ...target, repo: part.key }}
          part={part}
          showName={several}
        />
      ))}
    </div>
  )
}

/** One repository: its comparison, its files and the diff of each. */
function RepoSection({
  target,
  part,
  showName,
}: {
  target: ChangesTarget
  part: RepoChanges
  showName: boolean
}) {
  const { t } = useTranslation()
  const [jump, setJump] = useState<{ path: string; n: number } | null>(null)

  if (part.state !== 'ok')
    return (
      <section aria-label={part.name} className="flex flex-col gap-2">
        <h3 className="text-[13px] font-semibold">{part.name}</h3>
        <Notice>{t(`changes.empty.${part.state}.title`)}</Notice>
      </section>
    )

  return (
    <section aria-label={part.name || undefined} className="flex flex-col gap-3">
      {showName && (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-[13px] font-semibold">{part.name}</h3>
          <ChangesBadge totals={part.totals} className="text-[12.5px]" />
          {part.from_ref && part.to_ref && (
            <span className="text-[12.5px] text-muted-foreground">
              {t('changes.compare', {
                from: refText(part.from_ref, t),
                to: refText(part.to_ref, t),
              })}
            </span>
          )}
          {part.skipped_large > 0 && (
            <span className="text-[12.5px] text-muted-foreground">
              {t('changes.skippedLarge', { count: part.skipped_large })}
            </span>
          )}
        </div>
      )}
      {part.files.length === 0 ? (
        <EmptyState icon={GitCompareArrows} title={t('changes.empty.none')} />
      ) : (
        <>
          <ul
            aria-label={t('changes.fileList')}
            className="overflow-hidden rounded-lg border border-sep bg-card"
          >
            {part.files.map((file) => {
              const total = file.additions + file.deletions
              return (
                <li key={file.path} className="border-b border-sep last:border-b-0">
                  <button
                    type="button"
                    onClick={() => setJump({ path: file.path, n: (jump?.n ?? 0) + 1 })}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-accent"
                  >
                    <StatusLetter status={file.status} />
                    <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]">
                      {file.old_path ? `${file.old_path} → ${file.path}` : file.path}
                    </span>
                    {!file.binary && (
                      <>
                        <ChangesBadge
                          compact
                          totals={{
                            files: 1,
                            additions: file.additions,
                            deletions: file.deletions,
                          }}
                        />
                        <Proportion added={file.additions} deleted={file.deletions} total={total} />
                      </>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
          {part.truncated_files > 0 && (
            <Notice>{t('changes.truncated', { count: part.truncated_files })}</Notice>
          )}
          <div className="flex flex-col gap-3">
            {part.files.map((file, index) => (
              <FileDiffView
                key={file.path}
                target={target}
                file={file}
                id={`change-file-${part.key}-${index}`}
                jump={jump}
                live={part.live}
              />
            ))}
          </div>
        </>
      )}
    </section>
  )
}

/** The totals of everything, and what is true of the whole diff. With a single repository, the
 * comparison goes here too. */
function Header({ data, single }: { data: Changes; single: RepoChanges | null }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <ChangesBadge totals={data.totals} className="text-[13px]" />
        {single?.from_ref && single.to_ref && (
          <span className="text-[12.5px] text-muted-foreground">
            {t('changes.compare', {
              from: refText(single.from_ref, t),
              to: refText(single.to_ref, t),
            })}
          </span>
        )}
      </div>
      {data.live && <Notice>{t('changes.live')}</Notice>}
      {data.partial && <Notice>{t('changes.partial')}</Notice>}
      {data.direct_folder && <Notice>{t('changes.directFolder')}</Notice>}
      {single && single.skipped_large > 0 && (
        <Notice>{t('changes.skippedLarge', { count: single.skipped_large })}</Notice>
      )}
    </div>
  )
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="note"
      className="flex items-start gap-2 rounded-md border border-status-waiting/40 bg-status-waiting/10 px-2.5 py-1.5 text-[12.5px]"
    >
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-status-waiting" />
      {children}
    </p>
  )
}

/** A bar split between what was added and what was deleted. */
function Proportion({ added, deleted, total }: { added: number; deleted: number; total: number }) {
  if (total === 0) return null
  const BLOCKS = 5
  const green = Math.round((added / total) * BLOCKS)
  return (
    <span aria-hidden className="inline-flex gap-px">
      {Array.from({ length: BLOCKS }, (_, index) => (
        <span
          key={index}
          className={cn(
            'h-2.5 w-2 rounded-[1px]',
            index < green ? 'bg-[var(--diff-add-fg)]' : 'bg-[var(--diff-del-fg)]',
            deleted === 0 && 'bg-[var(--diff-add-fg)]',
            added === 0 && 'bg-[var(--diff-del-fg)]',
          )}
        />
      ))}
    </span>
  )
}
