import { GitCommitHorizontal, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { type HistoryFilters, useCommit, useHistory } from '@/api/git'
import { ChangesViewer } from '@/components/changes/ChangesViewer'
import { CommitGraph, ROW_HEIGHT } from '@/components/git/CommitGraph'
import { graphWidth, layoutGraph } from '@/components/git/graph'
import { EmptyState } from '@/components/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime, relativeTime } from '@/lib/time'
import { cn } from '@/lib/utils'

/** The history of a repository: its commits with the branch graph, filters, and the changes of
 * the commit that is picked. */
export function HistorySection({ repoId }: { repoId: string }) {
  const { t } = useTranslation()
  const [grep, setGrep] = useState('')
  const [author, setAuthor] = useState('')
  const [path, setPath] = useState('')
  const [allRefs, setAllRefs] = useState(true)
  const [picked, setPicked] = useState<string | null>(null)
  // The filters apply when the person stops typing: one request per search, not per key.
  const [applied, setApplied] = useState<HistoryFilters>({ allRefs: true })
  const history = useHistory(repoId, applied)

  const commits = useMemo(
    () => history.data?.pages.flatMap((page) => page.commits) ?? [],
    [history.data],
  )
  const { rows } = useMemo(() => layoutGraph(commits), [commits])
  const columns = graphWidth(rows)
  // A filter on the text or the file hides commits: their parents are not in the list, so the
  // graph would draw lines to nowhere.
  const filtered = Boolean(applied.grep || applied.author || applied.path || applied.search)

  function search(event: React.FormEvent) {
    event.preventDefault()
    setPicked(null)
    setApplied({
      allRefs,
      grep: grep.trim() || undefined,
      author: author.trim() || undefined,
      path: path.trim() || undefined,
    })
  }

  return (
    <div className="grid grid-cols-[minmax(380px,1fr)_minmax(0,1.2fr)] gap-4 px-6 py-4">
      <div className="flex min-w-0 flex-col gap-3">
        <form
          onSubmit={search}
          role="search"
          aria-label={t('git.history.filters')}
          className="flex flex-wrap items-center gap-2"
        >
          <Input
            value={grep}
            onChange={(e) => setGrep(e.target.value)}
            placeholder={t('git.history.message')}
            aria-label={t('git.history.message')}
            className="h-8 w-44"
          />
          <Input
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder={t('git.history.author')}
            aria-label={t('git.history.author')}
            className="h-8 w-32"
          />
          <Input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={t('git.history.file')}
            aria-label={t('git.history.file')}
            className="h-8 w-40 font-mono text-xs"
          />
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={allRefs}
              onChange={(e) => setAllRefs(e.target.checked)}
            />
            {t('git.history.allBranches')}
          </label>
          <Button type="submit" size="sm" variant="outline">
            <Search />
            {t('git.history.search')}
          </Button>
        </form>

        {history.isPending ? (
          <Skeleton aria-busy className="h-48 rounded-lg" />
        ) : history.isError ? (
          <p role="alert" className="text-[13px] text-status-failed">
            {t('git.history.error')}
          </p>
        ) : commits.length === 0 ? (
          <EmptyState icon={GitCommitHorizontal} title={t('git.history.empty')} />
        ) : (
          <>
            <ol
              aria-label={t('git.history.commits')}
              className="overflow-hidden rounded-lg border border-sep bg-card"
            >
              {commits.map((commit, index) => (
                <li key={commit.sha} className="border-b border-sep last:border-b-0">
                  <button
                    type="button"
                    onClick={() => setPicked(commit.sha)}
                    aria-current={picked === commit.sha || undefined}
                    style={{ height: ROW_HEIGHT }}
                    className={cn(
                      'flex w-full items-center gap-2 pr-3 text-left text-[13px] hover:bg-accent',
                      picked === commit.sha && 'bg-accent',
                    )}
                  >
                    {!filtered && <CommitGraph row={rows[index]} columns={columns} />}
                    <span className="min-w-0 flex-1 truncate">{commit.subject}</span>
                    {commit.refs.slice(0, 3).map((ref) => (
                      <Badge key={ref} variant="secondary" className="max-w-32 truncate font-mono">
                        {ref}
                      </Badge>
                    ))}
                    {commit.agent_name && <Badge variant="outline">{commit.agent_name}</Badge>}
                    <span className="hidden shrink-0 text-xs text-muted-foreground xl:inline">
                      {commit.author}
                    </span>
                    <span
                      className="shrink-0 text-xs text-muted-foreground"
                      title={formatDateTime(commit.date)}
                    >
                      {relativeTime(commit.date)}
                    </span>
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">
                      {commit.short}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
            {history.hasNextPage && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={history.isFetchingNextPage}
                onClick={() => void history.fetchNextPage()}
                className="self-center"
              >
                {t('git.history.more')}
              </Button>
            )}
          </>
        )}
      </div>

      <CommitPanel repoId={repoId} sha={picked} />
    </div>
  )
}

function CommitPanel({ repoId, sha }: { repoId: string; sha: string | null }) {
  const { t } = useTranslation()
  const commit = useCommit(repoId, sha)
  if (!sha)
    return (
      <p className="self-start rounded-lg border border-dashed border-sep p-6 text-center text-[13px] text-muted-foreground">
        {t('git.history.pick')}
      </p>
    )
  if (commit.isPending) return <Skeleton aria-busy className="h-40 rounded-lg" />
  if (commit.isError)
    return (
      <p role="alert" className="text-[13px] text-status-failed">
        {t('git.history.commitError')}
      </p>
    )
  const data = commit.data
  return (
    <section aria-label={data.short} className="flex min-w-0 flex-col gap-3">
      <header className="rounded-lg border border-sep bg-card p-3">
        <h3 className="text-[14px] font-medium">{data.subject}</h3>
        {data.body && (
          <p className="mt-1 text-[13px] whitespace-pre-wrap text-muted-foreground">{data.body}</p>
        )}
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="font-mono">{data.sha}</span>
          <span>
            {data.author} · {formatDateTime(data.date)}
          </span>
          {data.agent_name && (
            <Badge variant="outline">
              {data.agent_name}
              {data.task_code ? ` · ${data.task_code}` : ''}
            </Badge>
          )}
        </p>
      </header>
      <ChangesViewer
        key={data.sha}
        target={{ kind: 'repo', id: repoId, diff: { kind: 'commit', sha: data.sha } }}
      />
    </section>
  )
}
