import { CheckCircle2, Minus, Plus, Undo2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { type ChangesTarget, type FileChange, useChanges } from '@/api/changes'
import {
  type LineRef,
  useApplyLines,
  useCommitStaged,
  useDiscard,
  useRepoStatus,
  useStage,
  useUnstage,
} from '@/api/git'
import { ChangesBadge } from '@/components/changes/ChangesBadge'
import { FileDiffView, StatusLetter } from '@/components/changes/FileDiffView'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { gitErrorText } from './git-errors'

interface Picked {
  path: string
  staged: boolean
}

const target = (repoId: string, staged: boolean): ChangesTarget => ({
  kind: 'repo',
  id: repoId,
  diff: { kind: 'worktree', staged },
})

/** Lines the person ticked, as the backend wants them. */
function toRefs(keys: ReadonlySet<string>): LineRef[] {
  return [...keys].map((key) => {
    const [kind, no] = key.split(':')
    return { kind: kind as LineRef['kind'], no: Number(no) }
  })
}

/** The uncommitted changes of a repository: what is staged and what is not, the diff of a file
 * with a checkbox on every line, and the commit form. */
export function ChangesSection({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const status = useRepoStatus(repoId)
  const unstaged = useChanges(target(repoId, false))
  const staged = useChanges(target(repoId, true))
  const stage = useStage(repoId)
  const unstage = useUnstage(repoId)
  const discard = useDiscard(repoId)
  const apply = useApplyLines(repoId)
  const [picked, setPicked] = useState<Picked | null>(null)
  const [lines, setLines] = useState<ReadonlySet<string>>(new Set())
  const [confirm, setConfirm] = useState<{ paths: string[]; lines?: LineRef[] } | null>(null)

  const unstagedFiles = useMemo(() => unstaged.data?.repos[0]?.files ?? [], [unstaged.data])
  const stagedFiles = useMemo(() => staged.data?.repos[0]?.files ?? [], [staged.data])
  const current = useMemo(() => {
    if (!picked) return null
    const list = picked.staged ? stagedFiles : unstagedFiles
    return list.find((file) => file.path === picked.path) ?? null
  }, [picked, stagedFiles, unstagedFiles])

  async function run(action: Promise<unknown>) {
    try {
      await action
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  function choose(file: FileChange, isStaged: boolean) {
    setPicked({ path: file.path, staged: isStaged })
    setLines(new Set())
  }

  const toggle = (keys: string[], on: boolean) =>
    setLines((previous) => {
      const next = new Set(previous)
      for (const key of keys) {
        if (on) next.add(key)
        else next.delete(key)
      }
      return next
    })

  async function applyLines(action: 'stage' | 'unstage') {
    if (!current) return
    await run(apply.mutateAsync({ action, path: current.path, lines: toRefs(lines) }))
    setLines(new Set())
  }

  if (unstaged.isPending || staged.isPending || status.isPending)
    return <Skeleton aria-busy className="m-6 h-40 rounded-lg" />

  const conflicts = status.data?.conflicts ?? []
  const nothing = unstagedFiles.length === 0 && stagedFiles.length === 0 && conflicts.length === 0
  // Lines can be picked in files that exist on both sides: not in new, deleted or renamed ones.
  const selectable = current?.status === 'modified' && !current.binary

  return (
    <div className="grid grid-cols-[minmax(280px,360px)_1fr] gap-4 px-6 py-4">
      <div className="flex min-w-0 flex-col gap-4">
        {conflicts.length > 0 && (
          <section
            aria-label={t('git.changes.conflicts')}
            className="rounded-lg border border-status-failed/40 bg-status-failed/10 p-3 text-[13px]"
          >
            <h3 className="font-medium">{t('git.changes.conflicts')}</h3>
            <ul className="mt-1 font-mono text-xs">
              {conflicts.map((file) => (
                <li key={file.path}>{file.path}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">{t('git.changes.conflictsHelp')}</p>
          </section>
        )}
        <FileList
          title={t('git.changes.staged')}
          files={stagedFiles}
          picked={picked?.staged ? picked.path : null}
          onPick={(file) => choose(file, true)}
          empty={t('git.changes.noStaged')}
          headerAction={
            stagedFiles.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void run(unstage.mutateAsync(stagedFiles.map((f) => f.path)))}
              >
                <Minus />
                {t('git.changes.unstageAll')}
              </Button>
            )
          }
          rowAction={(file) => (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`${t('git.changes.unstage')} ${file.path}`}
              onClick={() => void run(unstage.mutateAsync([file.path]))}
            >
              <Minus />
            </Button>
          )}
        />
        <FileList
          title={t('git.changes.unstaged')}
          files={unstagedFiles}
          picked={picked && !picked.staged ? picked.path : null}
          onPick={(file) => choose(file, false)}
          empty={nothing ? t('git.changes.clean') : t('git.changes.noUnstaged')}
          headerAction={
            unstagedFiles.length > 0 && (
              <div className="flex gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void run(stage.mutateAsync(unstagedFiles.map((f) => f.path)))}
                >
                  <Plus />
                  {t('git.changes.stageAll')}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setConfirm({ paths: unstagedFiles.map((f) => f.path) })}
                >
                  <Undo2 />
                  {t('git.changes.discardAll')}
                </Button>
              </div>
            )
          }
          rowAction={(file) => (
            <>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`${t('git.changes.stage')} ${file.path}`}
                onClick={() => void run(stage.mutateAsync([file.path]))}
              >
                <Plus />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`${t('git.changes.discard')} ${file.path}`}
                onClick={() => setConfirm({ paths: [file.path] })}
              >
                <Undo2 />
              </Button>
            </>
          )}
        />
        <CommitForm repoId={repoId} stagedCount={stagedFiles.length} />
      </div>

      <div className="min-w-0">
        {nothing ? (
          <EmptyState
            icon={CheckCircle2}
            title={t('git.changes.clean')}
            description={t('git.changes.cleanHelp')}
          />
        ) : !current || !picked ? (
          <p className="rounded-lg border border-dashed border-sep p-6 text-center text-[13px] text-muted-foreground">
            {t('git.changes.pickAFile')}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {selectable && (
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="text-muted-foreground">
                  {t('git.changes.linesPicked', { count: lines.size })}
                </span>
                {picked.staged ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={lines.size === 0 || apply.isPending}
                    onClick={() => void applyLines('unstage')}
                  >
                    {t('git.changes.unstageLines')}
                  </Button>
                ) : (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={lines.size === 0 || apply.isPending}
                      onClick={() => void applyLines('stage')}
                    >
                      {t('git.changes.stageLines')}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={lines.size === 0 || apply.isPending}
                      onClick={() => setConfirm({ paths: [current.path], lines: toRefs(lines) })}
                    >
                      {t('git.changes.discardLines')}
                    </Button>
                  </>
                )}
              </div>
            )}
            {!selectable && !current.binary && (
              <p className="text-xs text-muted-foreground">{t('git.changes.wholeFileOnly')}</p>
            )}
            <FileDiffView
              key={`${picked.staged}:${current.path}`}
              target={target(repoId, picked.staged)}
              file={current}
              id="git-file"
              jump={null}
              selection={selectable ? { picked: lines, toggle } : undefined}
            />
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={t('git.changes.discardTitle')}
        description={
          confirm?.lines
            ? t('git.changes.discardLinesDescription', { count: confirm.lines.length })
            : t('git.changes.discardDescription', { count: confirm?.paths.length ?? 0 })
        }
        confirmLabel={t('git.changes.discardConfirm')}
        destructive
        onConfirm={() => {
          const request = confirm
          setConfirm(null)
          if (!request) return
          if (request.lines && current)
            void run(
              apply.mutateAsync({ action: 'discard', path: current.path, lines: request.lines }),
            ).then(() => setLines(new Set()))
          else void run(discard.mutateAsync(request.paths))
        }}
      />
    </div>
  )
}

function FileList({
  title,
  files,
  picked,
  onPick,
  empty,
  headerAction,
  rowAction,
}: {
  title: string
  files: FileChange[]
  picked: string | null
  onPick: (file: FileChange) => void
  empty: string
  headerAction: React.ReactNode
  rowAction: (file: FileChange) => React.ReactNode
}) {
  return (
    <section aria-label={title} className="overflow-hidden rounded-lg border border-sep bg-card">
      <header className="flex items-center justify-between gap-2 border-b border-sep bg-subtle px-3 py-1.5">
        <h3 className="text-[13px] font-medium">
          {title} <span className="text-muted-foreground">({files.length})</span>
        </h3>
        {headerAction}
      </header>
      {files.length === 0 ? (
        <p className="px-3 py-3 text-xs text-muted-foreground">{empty}</p>
      ) : (
        <ul>
          {files.map((file) => (
            <li
              key={file.path}
              className={
                'flex items-center gap-1 border-b border-sep pr-1 last:border-b-0 ' +
                (picked === file.path ? 'bg-accent' : '')
              }
            >
              <button
                type="button"
                onClick={() => onPick(file)}
                aria-current={picked === file.path || undefined}
                className="flex min-w-0 flex-1 items-center gap-2 px-3 py-1.5 text-left hover:bg-accent"
              >
                <StatusLetter status={file.status} />
                <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]" title={file.path}>
                  {file.old_path ? `${file.old_path} → ${file.path}` : file.path}
                </span>
                {!file.binary && (
                  <ChangesBadge
                    compact
                    totals={{ files: 1, additions: file.additions, deletions: file.deletions }}
                  />
                )}
              </button>
              {rowAction(file)}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function CommitForm({ repoId, stagedCount }: { repoId: string; stagedCount: number }) {
  const { t } = useTranslation()
  const commit = useCommitStaged(repoId)
  const [summary, setSummary] = useState('')
  const [body, setBody] = useState('')
  const [amend, setAmend] = useState(false)
  const [noVerify, setNoVerify] = useState(false)
  const message = body.trim() ? `${summary.trim()}\n\n${body.trim()}` : summary.trim()
  const ready = amend ? true : stagedCount > 0 && summary.trim() !== ''

  async function onCommit() {
    try {
      const done = await commit.mutateAsync({ message, amend, no_verify: noVerify })
      toast.success(t('git.changes.committed', { sha: done.short }))
      setSummary('')
      setBody('')
      setAmend(false)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <section
      aria-label={t('git.changes.commit')}
      className="flex flex-col gap-2 rounded-lg border border-sep bg-card p-3"
    >
      <Input
        value={summary}
        onChange={(event) => setSummary(event.target.value)}
        placeholder={amend ? t('git.changes.keepMessage') : t('git.changes.summary')}
        aria-label={t('git.changes.summary')}
        maxLength={200}
      />
      <Textarea
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder={t('git.changes.body')}
        aria-label={t('git.changes.body')}
        rows={3}
      />
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={amend} onChange={(e) => setAmend(e.target.checked)} />
          {t('git.changes.amend')}
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={noVerify}
            onChange={(e) => setNoVerify(e.target.checked)}
          />
          {t('git.changes.noVerify')}
        </label>
      </div>
      <Button
        type="button"
        disabled={!ready || commit.isPending}
        onClick={() => void onCommit()}
        className="bg-primary-action text-white hover:bg-primary-action-hover"
      >
        {amend
          ? t('git.changes.amendConfirm')
          : t('git.changes.commitConfirm', { count: stagedCount })}
      </Button>
    </section>
  )
}
