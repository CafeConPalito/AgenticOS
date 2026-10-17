import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useConflictFile, useResolveConflict, useTakeSide } from '@/api/git-integration'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { gitErrorText } from '@/pages/projects/tabs/git/git-errors'
import {
  type Choice,
  type Segment,
  applyChoices,
  conflictCount,
  hasMarkers,
  newlineOf,
  parseConflicts,
} from './conflict-parse'

/** Resolving one file that did not merge: each conflict shows both sides and takes one of them,
 * both, or text written by hand; the result is a text that can be edited freely. */
export function ConflictEditor({
  repoId,
  path,
  onDone,
}: {
  repoId: string
  path: string
  onDone: () => void
}) {
  const { t } = useTranslation()
  const file = useConflictFile(repoId, path)
  const resolve = useResolveConflict(repoId)
  const take = useTakeSide(repoId)

  if (file.isPending) return <Skeleton aria-busy className="h-40 rounded-lg" />
  if (file.isError)
    return (
      <p role="alert" className="text-[13px] text-status-failed">
        {t('git.conflicts.error')}
      </p>
    )

  async function run(action: Promise<unknown>) {
    try {
      await action
      toast.success(t('git.conflicts.resolved', { path }))
      onDone()
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  const data = file.data
  const whole = (
    <div className="flex flex-wrap gap-2">
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={take.isPending}
        onClick={() => void run(take.mutateAsync({ path, side: 'ours' }))}
      >
        {t('git.conflicts.keepOurs', { name: data.ours_label })}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={take.isPending}
        onClick={() => void run(take.mutateAsync({ path, side: 'theirs' }))}
      >
        {t('git.conflicts.keepTheirs', { name: data.theirs_label })}
      </Button>
    </div>
  )

  if (data.binary || data.merged === null || data.ours === null || data.theirs === null)
    return (
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-muted-foreground">
          {data.binary
            ? t('git.conflicts.binary')
            : data.ours === null
              ? t('git.conflicts.deletedHere', { name: data.ours_label })
              : t('git.conflicts.deletedThere', { name: data.theirs_label })}
        </p>
        {whole}
      </div>
    )

  return (
    <Editor
      key={path}
      merged={data.merged}
      oursLabel={data.ours_label}
      theirsLabel={data.theirs_label}
      busy={resolve.isPending}
      whole={whole}
      onSave={(content) => void run(resolve.mutateAsync({ path, content }))}
    />
  )
}

function Editor({
  merged,
  oursLabel,
  theirsLabel,
  busy,
  whole,
  onSave,
}: {
  merged: string
  oursLabel: string
  theirsLabel: string
  busy: boolean
  whole: React.ReactNode
  onSave: (content: string) => void
}) {
  const { t } = useTranslation()
  const segments = useMemo(() => parseConflicts(merged), [merged])
  const newline = newlineOf(merged)
  const [choices, setChoices] = useState<Record<number, Choice | undefined>>({})
  // Once the result is edited by hand it stops following the choices.
  const [manual, setManual] = useState<string | null>(null)
  const computed = applyChoices(segments, choices, newline)
  const result = manual ?? computed
  const total = conflictCount(segments)
  const settled = Object.values(choices).filter((choice) => choice !== undefined).length

  const blocks = segments.filter(
    (segment): segment is Extract<Segment, { type: 'conflict' }> => segment.type === 'conflict',
  )
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] text-muted-foreground">
          {t('git.conflicts.progress', { settled, total })}
        </p>
        {whole}
      </div>

      {blocks.map((segment, position) => {
        const choice = choices[position]
        const pick = (next: Choice) => {
          setManual(null)
          setChoices((previous) => ({ ...previous, [position]: next }))
        }
        return (
          <section
            key={position}
            aria-label={t('git.conflicts.block', { number: position + 1 })}
            className={cn(
              'overflow-hidden rounded-lg border bg-card',
              choice ? 'border-sep' : 'border-status-failed/50',
            )}
          >
            <header className="flex flex-wrap items-center justify-between gap-2 border-b border-sep bg-subtle px-3 py-1.5">
              <h4 className="text-[13px] font-medium">
                {t('git.conflicts.block', { number: position + 1 })}
              </h4>
              <div className="flex gap-1">
                <Button type="button" size="sm" variant="outline" onClick={() => pick('ours')}>
                  {t('git.conflicts.acceptOurs')}
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => pick('theirs')}>
                  {t('git.conflicts.acceptTheirs')}
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => pick('both')}>
                  {t('git.conflicts.acceptBoth')}
                </Button>
              </div>
            </header>
            <div className="grid grid-cols-2 divide-x divide-sep font-mono text-[12px] leading-5">
              <Side
                title={t('git.conflicts.ours', { name: segment.oursLabel || oursLabel })}
                lines={segment.ours}
                chosen={choice === 'ours' || choice === 'both'}
              />
              <Side
                title={t('git.conflicts.theirs', { name: segment.theirsLabel || theirsLabel })}
                lines={segment.theirs}
                chosen={choice === 'theirs' || choice === 'both'}
              />
            </div>
            {segment.base && (
              <details className="border-t border-sep px-3 py-1.5 text-xs text-muted-foreground">
                <summary>{t('git.conflicts.base')}</summary>
                <pre className="mt-1 font-mono whitespace-pre-wrap">{segment.base.join('\n')}</pre>
              </details>
            )}
          </section>
        )
      })}

      <section aria-label={t('git.conflicts.result')} className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h4 className="text-[13px] font-medium">{t('git.conflicts.result')}</h4>
          {manual !== null && (
            <Button type="button" size="sm" variant="ghost" onClick={() => setManual(null)}>
              {t('git.conflicts.backToChoices')}
            </Button>
          )}
        </div>
        <Textarea
          value={result}
          onChange={(event) => setManual(event.target.value)}
          aria-label={t('git.conflicts.result')}
          rows={Math.min(24, Math.max(8, result.split('\n').length + 1))}
          spellCheck={false}
          className="font-mono text-[12px]"
        />
        {hasMarkers(result) && (
          <p role="note" className="text-xs text-status-failed">
            {t('git.conflicts.markersLeft')}
          </p>
        )}
        <Button
          type="button"
          disabled={hasMarkers(result) || busy}
          onClick={() => onSave(result)}
          className="self-end bg-primary-action text-white hover:bg-primary-action-hover"
        >
          {t('git.conflicts.markResolved')}
        </Button>
      </section>
    </div>
  )
}

function Side({ title, lines, chosen }: { title: string; lines: string[]; chosen: boolean }) {
  return (
    <div className={cn('min-w-0', chosen && 'bg-[var(--diff-add-bg)]')}>
      <div className="border-b border-sep px-3 py-1 font-sans text-xs text-muted-foreground">
        {title}
      </div>
      <pre className="overflow-x-auto px-3 py-1.5 whitespace-pre-wrap">
        {lines.length === 0 ? ' ' : lines.join('\n')}
      </pre>
    </div>
  )
}
