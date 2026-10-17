import type { TFunction } from 'i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  type ChangesTarget,
  type DiffLine,
  type FileChange,
  type Hunk,
  fetchContextLines,
  useChangesFile,
} from '@/api/changes'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { formatBytes } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ChangesBadge } from './ChangesBadge'
import { CONTEXT_STEP, LARGE_DIFF, hunkBounds, offsetAfter, offsetBefore } from './diff'

const STATUS_LETTER = { added: 'A', modified: 'M', deleted: 'D', renamed: 'R' } as const

/** Lines revealed with «Mostrar más»: above the first hunk, between hunks and after the last. */
interface Extra {
  top: DiffLine[]
  gaps: Record<number, DiffLine[]>
  bottom: DiffLine[]
  bottomDone: boolean
}

const NO_EXTRA: Extra = { top: [], gaps: {}, bottom: [], bottomDone: false }

export function StatusLetter({ status }: { status: FileChange['status'] }) {
  const { t } = useTranslation()
  return (
    <span
      title={t(`changes.status.${status}`)}
      aria-label={t(`changes.status.${status}`)}
      className={cn(
        'inline-grid size-[18px] shrink-0 place-items-center rounded font-mono text-[10.5px] font-semibold',
        status === 'added' && 'bg-[var(--diff-add-bg)] text-[var(--diff-add-fg)]',
        status === 'deleted' && 'bg-[var(--diff-del-bg)] text-[var(--diff-del-fg)]',
        (status === 'modified' || status === 'renamed') && 'bg-accent text-muted-foreground',
      )}
    >
      {STATUS_LETTER[status]}
    </span>
  )
}

/** One file of a diff: folded or open, with its hunks and the buttons that widen the context. */
export function FileDiffView({
  target,
  file,
  id,
  jump,
  live = false,
}: {
  target: ChangesTarget
  file: FileChange
  id: string
  /** The run is going: the diff is read again every few seconds. */
  live?: boolean
  /** The file list asked to show this file. */
  jump: { path: string; n: number } | null
}) {
  const { t } = useTranslation()
  const changed = file.additions + file.deletions
  const large = changed > LARGE_DIFF
  const folded = file.generated || large
  const [open, setOpen] = useState(!folded)
  const root = useRef<HTMLElement>(null)
  const diff = useChangesFile(target, file, open && !file.binary, live)
  const [extra, setExtra] = useState<Extra>(NO_EXTRA)

  // The file list asked for this file: open it (adjusting state while rendering, not in an
  // effect) and bring it into view.
  const jumped = jump?.path === file.path ? jump.n : 0
  const [seenJump, setSeenJump] = useState(jumped)
  if (jumped !== seenJump) {
    setSeenJump(jumped)
    if (jumped > 0) setOpen(true)
  }
  useEffect(() => {
    if (jumped > 0) root.current?.scrollIntoView?.({ block: 'start' })
  }, [jumped])

  // A live run changes its files: what was revealed no longer lines up.
  const hunksKey = diff.data?.hunks.map((h) => `${h.new_start}:${h.new_lines}`).join('|')
  const [extraKey, setExtraKey] = useState(hunksKey)
  if (extraKey !== hunksKey) {
    setExtraKey(hunksKey)
    setExtra(NO_EXTRA)
  }

  const widenable = file.status !== 'added' && file.status !== 'deleted'
  const title = file.old_path ? `${file.old_path} → ${file.path}` : file.path

  return (
    <section
      ref={root}
      id={id}
      aria-label={file.path}
      className="overflow-hidden rounded-lg border border-sep bg-card"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 border-b border-sep bg-subtle px-3 py-2 text-left"
      >
        {open ? (
          <ChevronDown className="size-4 shrink-0" />
        ) : (
          <ChevronRight className="size-4 shrink-0" />
        )}
        <StatusLetter status={file.status} />
        <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]" title={title}>
          {title}
        </span>
        {!open && folded && (
          <span className="shrink-0 text-xs text-muted-foreground">
            {file.generated
              ? t('changes.foldedGenerated')
              : t('changes.foldedLarge', { count: changed })}
          </span>
        )}
        {!file.binary && (
          <ChangesBadge
            compact
            totals={{ files: 1, additions: file.additions, deletions: file.deletions }}
          />
        )}
      </button>
      {open && (
        <div className="overflow-x-auto">
          {file.binary ? (
            <Note>{binaryText(file, t)}</Note>
          ) : diff.isPending ? (
            <div aria-busy className="flex flex-col gap-1.5 p-3">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : diff.isError ? (
            <p role="alert" className="px-3 py-2.5 text-[12.5px] text-status-failed">
              {t('changes.fileError')}
            </p>
          ) : diff.data.binary ? (
            <Note>{binaryText(file, t)}</Note>
          ) : diff.data.too_large ? (
            <Note>{t('changes.tooLarge')}</Note>
          ) : diff.data.hunks.length === 0 ? (
            <Note>{t('changes.noLines')}</Note>
          ) : (
            <Hunks
              target={target}
              path={file.path}
              hunks={diff.data.hunks}
              extra={extra}
              setExtra={setExtra}
              widenable={widenable}
            />
          )}
        </div>
      )}
    </section>
  )
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="px-3 py-2.5 text-[12.5px] text-muted-foreground">{children}</p>
}

function binaryText(file: FileChange, t: TFunction): string {
  const { old_size: before, new_size: after } = file
  if (before === null && after === null) return t('changes.binary')
  const sizes =
    before !== null && after !== null
      ? `${formatBytes(before)} → ${formatBytes(after)}`
      : formatBytes((after ?? before) as number)
  return t('changes.binarySize', { sizes })
}

function Hunks({
  target,
  path,
  hunks,
  extra,
  setExtra,
  widenable,
}: {
  target: ChangesTarget
  path: string
  hunks: Hunk[]
  extra: Extra
  setExtra: React.Dispatch<React.SetStateAction<Extra>>
  widenable: boolean
}) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  async function load(start: number, end: number, apply: (lines: DiffLine[]) => void) {
    setBusy(true)
    setFailed(false)
    try {
      apply(await fetchContextLines(target, path, start, end))
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  // The backend gives the new numbers; the old ones follow from the hunk next to the lines.
  const withOld = (lines: DiffLine[], offset: number): DiffLine[] =>
    lines.map((line) => ({ ...line, old_no: (line.new_no ?? 0) + offset }))

  const first = hunkBounds(hunks[0])
  const last = hunks[hunks.length - 1]
  const lastBounds = hunkBounds(last)
  const topRemaining = first.newFirst - 1 - extra.top.length

  function expandTop() {
    const end = first.newFirst - 1 - extra.top.length
    const start = Math.max(1, end - CONTEXT_STEP + 1)
    void load(start, end, (lines) =>
      setExtra((current) => ({
        ...current,
        top: [...withOld(lines, offsetBefore(hunks[0])), ...current.top],
      })),
    )
  }

  function expandGap(index: number) {
    const previous = hunkBounds(hunks[index - 1])
    const shown = extra.gaps[index] ?? []
    const start = previous.newAfter + shown.length
    const end = Math.min(hunkBounds(hunks[index]).newFirst - 1, start + CONTEXT_STEP - 1)
    void load(start, end, (lines) =>
      setExtra((current) => ({
        ...current,
        gaps: {
          ...current.gaps,
          [index]: [...shown, ...withOld(lines, offsetAfter(hunks[index - 1]))],
        },
      })),
    )
  }

  function expandBottom() {
    const start = lastBounds.newAfter + extra.bottom.length
    void load(start, start + CONTEXT_STEP - 1, (lines) =>
      setExtra((current) => ({
        ...current,
        bottom: [...current.bottom, ...withOld(lines, offsetAfter(last))],
        bottomDone: lines.length < CONTEXT_STEP,
      })),
    )
  }

  const expandRow = (key: string, label: string, onClick: () => void) => (
    <tr key={key}>
      <td colSpan={4} className="bg-subtle px-3 py-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={onClick}
          className="h-6 px-2 text-xs text-muted-foreground"
        >
          {label}
        </Button>
      </td>
    </tr>
  )

  return (
    <table className="w-full border-collapse font-mono text-[12px] leading-5">
      <tbody>
        {widenable &&
          topRemaining > 0 &&
          expandRow(
            'top',
            t('changes.showMore', { count: Math.min(CONTEXT_STEP, topRemaining) }),
            expandTop,
          )}
        {extra.top.map((line) => (
          <LineRow key={`t${line.new_no}`} line={line} />
        ))}
        {hunks.map((hunk, index) => {
          const gapStart = index > 0 ? hunkBounds(hunks[index - 1]).newAfter : 0
          const gapEnd = hunkBounds(hunk).newFirst - 1
          const shown = extra.gaps[index] ?? []
          const remaining = gapEnd - gapStart + 1 - shown.length
          return (
            <Fragment key={`${hunk.old_start}-${hunk.new_start}`}>
              {index > 0 && (
                <>
                  {shown.map((line) => (
                    <LineRow key={`g${index}-${line.new_no}`} line={line} />
                  ))}
                  {widenable &&
                    remaining > 0 &&
                    expandRow(
                      `gap${index}`,
                      t('changes.showMore', { count: Math.min(CONTEXT_STEP, remaining) }),
                      () => expandGap(index),
                    )}
                </>
              )}
              <tr>
                <td colSpan={4} className="bg-accent/50 px-3 py-0.5 text-muted-foreground">
                  {`@@ -${hunk.old_start},${hunk.old_lines} +${hunk.new_start},${hunk.new_lines} @@`}
                  {hunk.header && <span className="ml-2">{hunk.header}</span>}
                </td>
              </tr>
              {hunk.lines.map((line, position) => (
                <LineRow key={position} line={line} />
              ))}
            </Fragment>
          )
        })}
        {extra.bottom.map((line) => (
          <LineRow key={`b${line.new_no}`} line={line} />
        ))}
        {widenable &&
          !extra.bottomDone &&
          expandRow('bottom', t('changes.showMoreAfter'), expandBottom)}
        {failed && (
          <tr>
            <td colSpan={4} className="px-3 py-1">
              <p role="alert" className="text-xs text-status-failed">
                {t('changes.fileError')}
              </p>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  )
}

function LineRow({ line }: { line: DiffLine }) {
  const marker = line.kind === 'add' ? '+' : line.kind === 'del' ? '−' : ' '
  return (
    <tr
      className={cn(
        line.kind === 'add' && 'bg-[var(--diff-add-bg)]',
        line.kind === 'del' && 'bg-[var(--diff-del-bg)]',
      )}
    >
      <td className="w-10 min-w-10 px-2 text-right text-muted-foreground/70 select-none">
        {line.old_no ?? ''}
      </td>
      <td className="w-10 min-w-10 px-2 text-right text-muted-foreground/70 select-none">
        {line.new_no ?? ''}
      </td>
      <td
        aria-hidden
        className={cn(
          'w-4 text-center select-none',
          line.kind === 'add' && 'text-[var(--diff-add-fg)]',
          line.kind === 'del' && 'text-[var(--diff-del-fg)]',
        )}
      >
        {marker}
      </td>
      <td className="pr-3 break-all whitespace-pre-wrap">{line.text}</td>
    </tr>
  )
}
