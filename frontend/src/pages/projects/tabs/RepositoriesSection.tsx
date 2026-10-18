import { FolderGit2, Link2, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  type ProjectRepo,
  type PullMode,
  useInitRepo,
  useLinkRepo,
  useRemoveRepo,
  useRepos,
  useScanRepos,
  useUpdateRepo,
} from '@/api/repos'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FolderPicker } from '@/components/FolderPicker'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { errorMessage } from '@/lib/form-errors'

const PULL_MODES: PullMode[] = ['ff_only', 'merge', 'rebase']

/** The repositories of a project: found in its folder or linked from outside, each with its own
 * base branch (phase 12). */
export function RepositoriesSection({ projectId }: { projectId: string }) {
  const { t } = useTranslation()
  const repos = useRepos(projectId)
  const scan = useScanRepos(projectId)
  const link = useLinkRepo(projectId)
  const init = useInitRepo(projectId)
  const [initBranch, setInitBranch] = useState('main')
  const update = useUpdateRepo(projectId)
  const remove = useRemoveRepo(projectId)
  const [linking, setLinking] = useState(false)
  const [path, setPath] = useState('')
  const [removing, setRemoving] = useState<ProjectRepo | null>(null)

  async function run(action: Promise<unknown>, done?: string) {
    try {
      await action
      if (done) toast.success(done)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onLink() {
    await run(link.mutateAsync({ path: path.trim() }), t('projects.repos.linked'))
    if (!link.isError) {
      setPath('')
      setLinking(false)
    }
  }

  return (
    <section aria-labelledby="repos-title" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 id="repos-title" className="font-medium">
            {t('projects.repos.title')}
          </h2>
          <p className="text-xs text-muted-foreground">{t('projects.repos.help')}</p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={scan.isPending}
            onClick={() => void run(scan.mutateAsync(), t('projects.repos.scanned'))}
          >
            <RefreshCw />
            {t('projects.repos.scan')}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => setLinking(!linking)}>
            <Link2 />
            {t('projects.repos.link')}
          </Button>
        </div>
      </div>

      {linking && (
        <div className="flex flex-col gap-2 rounded-lg border border-sep p-3">
          <label htmlFor="repo-path" className="text-xs text-muted-foreground">
            {t('projects.repos.linkHelp')}
          </label>
          <FolderPicker id="repo-path" value={path} onChange={setPath} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setLinking(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!path.trim() || link.isPending}
              onClick={() => void onLink()}
            >
              {t('projects.repos.linkConfirm')}
            </Button>
          </div>
        </div>
      )}

      {repos.isPending ? (
        <Skeleton className="h-16 rounded-lg" />
      ) : repos.isError ? (
        <p role="alert" className="text-[13px] text-status-failed">
          {t('projects.repos.error')}
        </p>
      ) : repos.data.length === 0 ? (
        <div className="flex flex-col gap-3 rounded-lg border border-dashed border-sep p-4 text-[13px]">
          <p className="text-muted-foreground">{t('projects.repos.none')}</p>
          <form
            aria-label={t('projects.repos.init')}
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              void run(
                init.mutateAsync({ branch: initBranch.trim() || 'main' }),
                t('projects.repos.initDone'),
              )
            }}
          >
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              {t('projects.repos.initBranch')}
              <Input
                value={initBranch}
                onChange={(e) => setInitBranch(e.target.value)}
                className="h-8 w-40 font-mono text-[12.5px]"
              />
            </label>
            <Button type="submit" size="sm" disabled={init.isPending}>
              <FolderGit2 />
              {t('projects.repos.init')}
            </Button>
          </form>
        </div>
      ) : (
        <ul className="overflow-hidden rounded-lg border border-sep bg-card">
          {repos.data.map((repo) => (
            <RepoRow
              key={repo.id}
              repo={repo}
              onChange={(body) => void run(update.mutateAsync({ id: repo.id, ...body }))}
              onRemove={() => setRemoving(repo)}
            />
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={t('projects.repos.removeTitle', { name: removing?.name ?? '' })}
        description={t('projects.repos.removeDescription')}
        confirmLabel={t('projects.repos.remove')}
        destructive
        onConfirm={() => {
          if (removing) void run(remove.mutateAsync(removing.id))
          setRemoving(null)
        }}
      />
    </section>
  )
}

function RepoRow({
  repo,
  onChange,
  onRemove,
}: {
  repo: ProjectRepo
  onChange: (body: {
    base_branch?: string
    participates?: boolean
    pull_mode?: PullMode
    forge?: 'github' | 'gitlab' | null
  }) => void
  onRemove: () => void
}) {
  const { t } = useTranslation()
  const [base, setBase] = useState(repo.base_branch ?? '')
  const where = repo.linked
    ? repo.path
    : repo.rel_path
      ? repo.rel_path
      : t('projects.repos.projectFolder')

  return (
    <li className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 border-b border-sep px-3 py-3 last:border-b-0">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <FolderGit2 className="size-4 text-muted-foreground" aria-hidden />
          <span className="font-medium">{repo.name}</span>
          {repo.linked && <Badge variant="secondary">{t('projects.repos.badgeLinked')}</Badge>}
          {repo.missing && <Badge variant="destructive">{t('projects.repos.badgeMissing')}</Badge>}
          {repo.git?.is_repo && repo.git.branch && (
            <span className="font-mono text-xs text-muted-foreground">{repo.git.branch}</span>
          )}
          {repo.git?.dirty && (
            <span className="text-xs text-muted-foreground">{t('projects.summary.dirty')}</span>
          )}
        </div>
        <span className="truncate font-mono text-xs text-muted-foreground" title={repo.path}>
          {where}
        </span>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={`${t('projects.repos.remove')} ${repo.name}`}
        onClick={onRemove}
      >
        <Trash2 />
      </Button>
      <div className="col-span-2 flex flex-wrap items-end gap-x-6 gap-y-2">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t('projects.repos.base')}
          <Input
            value={base}
            onChange={(e) => setBase(e.target.value)}
            onBlur={() => {
              const next = base.trim()
              if (next && next !== repo.base_branch) onChange({ base_branch: next })
              else setBase(repo.base_branch ?? '')
            }}
            aria-label={`${t('projects.repos.base')} ${repo.name}`}
            className="h-8 w-44 font-mono text-[12.5px]"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t('projects.repos.pull')}
          <select
            value={repo.pull_mode}
            onChange={(e) => onChange({ pull_mode: e.target.value as PullMode })}
            aria-label={`${t('projects.repos.pull')} ${repo.name}`}
            className="h-8 rounded-md border border-input bg-background px-2 text-[13px] text-foreground"
          >
            {PULL_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {t(`projects.repos.pullMode.${mode}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          {t('projects.repos.forge')}
          <select
            value={repo.forge ?? ''}
            onChange={(e) =>
              onChange({ forge: (e.target.value || null) as 'github' | 'gitlab' | null })
            }
            aria-label={`${t('projects.repos.forge')} ${repo.name}`}
            className="h-8 rounded-md border border-input bg-background px-2 text-[13px] text-foreground"
          >
            <option value="">{t('projects.repos.forgeAuto')}</option>
            <option value="github">{t('projects.repos.forges.github')}</option>
            <option value="gitlab">{t('projects.repos.forges.gitlab')}</option>
          </select>
        </label>
        <label className="flex items-center gap-2 pb-1 text-[13px]">
          <Switch
            size="sm"
            checked={repo.participates}
            onCheckedChange={(participates) => onChange({ participates })}
            aria-label={`${t('projects.repos.participates')} ${repo.name}`}
          />
          {t('projects.repos.participates')}
        </label>
      </div>
    </li>
  )
}
