import { ExternalLink, GitPullRequest } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useBranches } from '@/api/git'
import {
  type MergeMethod,
  type PullRequest,
  useCreatePull,
  useForgeInfo,
  useMergePull,
  usePull,
  usePullAction,
  usePulls,
  useSaveToken,
} from '@/api/forges'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/lib/api'
import { relativeTime } from '@/lib/time'
import { gitErrorText } from './git-errors'

type Filter = 'open' | 'closed' | 'all'

/** The pull requests of the repository's code host (GitHub or GitLab): the list, the detail of
 * one with its checks, reviews and comments, and the actions on it. */
export function PullsSection({ repoId, base }: { repoId: string; base: string | null }) {
  const { t } = useTranslation()
  const info = useForgeInfo(repoId)
  const [filter, setFilter] = useState<Filter>('open')
  const [picked, setPicked] = useState<number | null>(null)
  const ready = Boolean(info.data?.kind && info.data.has_token)
  const pulls = usePulls(repoId, filter, ready)

  if (info.isPending) return <Skeleton aria-busy className="m-6 h-40 rounded-lg" />
  const forge = info.data
  if (!forge?.kind)
    return (
      <div className="px-6 py-4">
        <EmptyState
          icon={GitPullRequest}
          title={t('git.pulls.noForgeTitle')}
          description={t('git.pulls.noForge')}
        />
      </div>
    )
  if (!forge.has_token) return <TokenPrompt host={forge.host ?? ''} />

  const failure = pulls.error instanceof ApiError ? pulls.error : null
  return (
    <div className="flex flex-col gap-3 px-6 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label={t('git.pulls.filter')} className="flex gap-1">
          {(['open', 'closed', 'all'] as const).map((value) => (
            <Button
              key={value}
              type="button"
              size="sm"
              variant={filter === value ? 'default' : 'outline'}
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {t(`git.pulls.filters.${value}`)}
            </Button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">
          {forge.kind === 'github' ? 'GitHub' : 'GitLab'} · {forge.host}
        </span>
      </div>

      <CreatePull repoId={repoId} base={base} onCreated={setPicked} />

      {pulls.isPending ? (
        <Skeleton aria-busy className="h-24 rounded-lg" />
      ) : failure ? (
        <p role="alert" className="text-[13px] text-status-failed">
          {gitErrorText(failure, t)}
        </p>
      ) : (pulls.data ?? []).length === 0 ? (
        <EmptyState icon={GitPullRequest} title={t('git.pulls.empty')} />
      ) : (
        <ul className="overflow-hidden rounded-lg border border-sep bg-card">
          {(pulls.data ?? []).map((pull) => (
            <PullRow
              key={pull.number}
              pull={pull}
              selected={picked === pull.number}
              onPick={() => setPicked(picked === pull.number ? null : pull.number)}
            />
          ))}
        </ul>
      )}
      {picked !== null && <PullDetailPanel repoId={repoId} number={picked} />}
    </div>
  )
}

function PullRow({
  pull,
  selected,
  onPick,
}: {
  pull: PullRequest
  selected: boolean
  onPick: () => void
}) {
  const { t } = useTranslation()
  return (
    <li className="border-b border-sep last:border-b-0">
      <button
        type="button"
        aria-pressed={selected}
        onClick={onPick}
        className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-left text-[13px] hover:bg-accent"
      >
        <span className="font-mono text-xs text-muted-foreground">#{pull.number}</span>
        <span className="min-w-0 flex-1 truncate">{pull.title}</span>
        {pull.draft && <Badge variant="outline">{t('git.pulls.draft')}</Badge>}
        <Badge variant={pull.state === 'open' ? 'secondary' : 'outline'}>
          {t(`git.pulls.state.${pull.state}`)}
        </Badge>
        <span className="font-mono text-xs text-muted-foreground">
          {pull.head} → {pull.base}
        </span>
        {pull.updated_at && (
          <span className="text-xs text-muted-foreground">{relativeTime(pull.updated_at)}</span>
        )}
      </button>
    </li>
  )
}

function PullDetailPanel({ repoId, number }: { repoId: string; number: number }) {
  const { t } = useTranslation()
  const detail = usePull(repoId, number)
  const merge = useMergePull(repoId)
  const act = usePullAction(repoId)
  const [method, setMethod] = useState<MergeMethod>('merge')
  const [confirming, setConfirming] = useState(false)

  async function run(action: Promise<unknown>, done: string) {
    try {
      await action
      toast.success(done)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  if (detail.isPending) return <Skeleton aria-busy className="h-32 rounded-lg" />
  const pull = detail.data
  if (!pull)
    return (
      <p role="alert" className="text-[13px] text-status-failed">
        {gitErrorText(detail.error, t)}
      </p>
    )

  return (
    <section
      aria-label={t('git.pulls.detail', { number })}
      className="flex flex-col gap-3 rounded-lg border border-sep bg-card p-3 text-[13px]"
    >
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium">
          #{pull.number} {pull.title}
        </h3>
        <a
          href={pull.url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 text-xs text-primary hover:underline"
        >
          <ExternalLink className="size-3" aria-hidden />
          {t('git.pulls.open')}
        </a>
      </header>
      {pull.body && <p className="whitespace-pre-wrap text-muted-foreground">{pull.body}</p>}
      {pull.mergeable === false && (
        <p className="text-xs text-status-failed">{t('git.pulls.notMergeable')}</p>
      )}

      <div>
        <h4 className="mb-1 text-xs font-medium text-muted-foreground">{t('git.pulls.checks')}</h4>
        {pull.checks.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('git.pulls.noChecks')}</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {pull.checks.map((check) => (
              <li key={check.name} className="flex items-center gap-2">
                <Badge variant={check.state === 'failure' ? 'destructive' : 'secondary'}>
                  {t(`git.pulls.checkState.${check.state}`)}
                </Badge>
                {check.name}
              </li>
            ))}
          </ul>
        )}
      </div>

      {pull.reviews.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-medium text-muted-foreground">
            {t('git.pulls.reviews')}
          </h4>
          <ul>
            {pull.reviews.map((review, index) => (
              <li key={`${review.author}-${index}`}>
                {review.author} · {t(`git.pulls.review.${review.state}`, review.state)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {pull.comments.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-medium text-muted-foreground">
            {t('git.pulls.comments')}
          </h4>
          <ul className="flex flex-col gap-1.5">
            {pull.comments.map((comment, index) => (
              <li key={index} className="rounded-md bg-subtle px-2 py-1">
                <span className="font-medium">{comment.author}</span>
                <p className="whitespace-pre-wrap">{comment.body}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {pull.state === 'open' ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-sep pt-3">
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value as MergeMethod)}
            aria-label={t('git.pulls.method')}
            className="h-8 rounded-md border border-input bg-background px-2 text-[12.5px]"
          >
            {(['merge', 'squash', 'rebase'] as const).map((value) => (
              <option key={value} value={value}>
                {t(`tasks.integration.modes.${value}`)}
              </option>
            ))}
          </select>
          <Button type="button" size="sm" onClick={() => setConfirming(true)}>
            {t('git.pulls.merge')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() =>
              void run(act.mutateAsync({ number, action: 'update-branch' }), t('git.pulls.updated'))
            }
          >
            {t('git.pulls.updateBranch')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() =>
              void run(act.mutateAsync({ number, action: 'close' }), t('git.pulls.closed'))
            }
          >
            {t('git.pulls.close')}
          </Button>
        </div>
      ) : pull.state === 'closed' ? (
        <div className="border-t border-sep pt-3">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() =>
              void run(act.mutateAsync({ number, action: 'reopen' }), t('git.pulls.reopened'))
            }
          >
            {t('git.pulls.reopen')}
          </Button>
        </div>
      ) : null}

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('git.pulls.mergeTitle', { number })}
        description={t('git.pulls.mergeDescription', {
          method: t(`tasks.integration.modes.${method}`),
        })}
        confirmLabel={t('git.pulls.merge')}
        onConfirm={() => {
          setConfirming(false)
          void run(merge.mutateAsync({ number, method }), t('git.pulls.merged'))
        }}
      />
    </section>
  )
}

function CreatePull({
  repoId,
  base,
  onCreated,
}: {
  repoId: string
  base: string | null
  onCreated: (number: number) => void
}) {
  const { t } = useTranslation()
  const branches = useBranches(repoId)
  const create = useCreatePull(repoId)
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [head, setHead] = useState('')
  const [target, setTarget] = useState(base ?? '')
  const [draft, setDraft] = useState(false)
  const locals = (branches.data ?? []).filter((b) => !b.remote)

  if (!open)
    return (
      <div>
        <Button type="button" size="sm" variant="outline" onClick={() => setOpen(true)}>
          <GitPullRequest />
          {t('git.pulls.create')}
        </Button>
      </div>
    )

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    try {
      const made = await create.mutateAsync({
        title: title.trim(),
        body,
        head,
        base: target.trim(),
        draft,
      })
      toast.success(t('git.pulls.created', { number: made.number }))
      setOpen(false)
      setTitle('')
      setBody('')
      onCreated(made.number)
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <form
      onSubmit={(event) => void onSubmit(event)}
      aria-label={t('git.pulls.create')}
      className="flex flex-col gap-2 rounded-lg border border-sep p-3"
    >
      <div className="flex flex-wrap gap-2">
        <select
          value={head}
          onChange={(e) => setHead(e.target.value)}
          aria-label={t('git.pulls.head')}
          className="h-8 rounded-md border border-input bg-background px-2 font-mono text-[12.5px]"
        >
          <option value="">{t('git.pulls.chooseBranch')}</option>
          {locals.map((branch) => (
            <option key={branch.name} value={branch.name}>
              {branch.name}
            </option>
          ))}
        </select>
        <span className="self-center text-xs text-muted-foreground">→</span>
        <Input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          aria-label={t('git.pulls.base')}
          className="h-8 w-40 font-mono text-xs"
        />
      </div>
      <Input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={t('git.pulls.title')}
        aria-label={t('git.pulls.title')}
        className="h-8 text-xs"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={t('git.pulls.body')}
        aria-label={t('git.pulls.body')}
        rows={3}
        className="rounded-md border border-input bg-background px-2 py-1 text-xs"
      />
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1.5 text-xs">
          <input type="checkbox" checked={draft} onChange={(e) => setDraft(e.target.checked)} />
          {t('git.pulls.asDraft')}
        </label>
        <Button
          type="submit"
          size="sm"
          disabled={!title.trim() || !head || !target.trim() || create.isPending}
        >
          {t('git.pulls.submit')}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
          {t('common.cancel')}
        </Button>
      </div>
    </form>
  )
}

/** git has no token for the host yet: the person can paste one (it goes into git's own store). */
function TokenPrompt({ host }: { host: string }) {
  const { t } = useTranslation()
  const save = useSaveToken()
  const [token, setToken] = useState('')
  return (
    <div className="flex flex-col gap-2 px-6 py-4">
      <p role="status" className="text-[13px]">
        {t('git.pulls.noToken', { host })}
      </p>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          void save
            .mutateAsync({ host, token })
            .then(() => {
              setToken('')
              toast.success(t('git.pulls.tokenSaved', { host }))
            })
            .catch((error: unknown) => toast.error(gitErrorText(error, t)))
        }}
      >
        <Input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder={t('git.pulls.token')}
          aria-label={t('git.pulls.token')}
          className="h-8 w-72 font-mono text-xs"
        />
        <Button type="submit" size="sm" disabled={!token.trim() || save.isPending}>
          {t('git.pulls.saveToken')}
        </Button>
      </form>
    </div>
  )
}
