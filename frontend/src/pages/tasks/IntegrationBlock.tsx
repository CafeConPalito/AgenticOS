import { GitMerge, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { type RepoPull, useTaskPulls } from '@/api/forges'
import {
  type IntegrationMode,
  type RepoCheck,
  type Resolution,
  useFinishResolution,
  useIntegrate,
  useIntegration,
  useResolveConflicts,
  useStartResolution,
  useUndoIntegration,
} from '@/api/integration'
import type { Task } from '@/api/types'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { gitErrorText } from '@/pages/projects/tabs/git/git-errors'

const PROBLEMS = ['conflicts', 'blocked', 'failed', 'missing']

/** The branches a finished task left, one per repository, and what bringing them into their
 * bases would do: the check, the integration (merge, squash or rebase, optionally pushing) and,
 * when something conflicts, resolving it here or handing it to an agent. */
export function IntegrationBlock({ task }: { task: Task }) {
  const { t } = useTranslation()
  const check = useIntegration(task.id)
  const integrate = useIntegrate(task.id)
  const undo = useUndoIntegration(task.id)
  const pulls = useTaskPulls(task.id)
  const [opened, setOpened] = useState<RepoPull[]>([])
  const [asDraft, setAsDraft] = useState(false)
  const [mode, setMode] = useState<IntegrationMode | ''>('')
  const [push, setPush] = useState(false)
  const [removeBranches, setRemoveBranches] = useState(false)
  const [confirmUndo, setConfirmUndo] = useState(false)

  const repos = check.data?.repos ?? []
  // Nothing to show for a task that left no branches or whose work is all in its bases already.
  if (!check.data || repos.length === 0) return null
  const anyIntegrated = repos.some((r) => r.state === 'integrated')
  if (check.data.pending === 0 && !anyIntegrated) return null
  const conflicting = repos.filter((r) => r.state === 'conflicts')

  async function onIntegrate() {
    try {
      const result = await integrate.mutateAsync({
        mode: mode || undefined,
        push,
        delete_branches: removeBranches,
      })
      const problem = result.repos.find((r) => PROBLEMS.includes(r.status))
      if (problem)
        toast.warning(
          t('tasks.integration.stopped', { name: problem.name, count: result.integrated }),
        )
      else toast.success(t('tasks.integration.done', { count: result.integrated }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onPulls() {
    try {
      const results = await pulls.mutateAsync({ draft: asDraft })
      setOpened(results)
      const failed = results.filter((r) => r.status === 'failed')
      if (failed.length) toast.warning(t('tasks.integration.pullsFailed', { count: failed.length }))
      else toast.success(t('tasks.integration.pullsOpened'))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onUndo() {
    try {
      await undo.mutateAsync()
      toast.success(t('tasks.integration.undone'))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <section
      aria-labelledby="integration-title"
      className="rounded-[10px] border bg-subtle px-3.5 py-3"
    >
      <h2
        id="integration-title"
        className="mb-2 flex items-center gap-1.5 text-[12.5px] font-medium"
      >
        <GitMerge className="size-3.5" aria-hidden />
        {t('tasks.integration.title')}
      </h2>
      <ul className="mb-3 flex flex-col gap-1.5 text-[13px]">
        {repos.map((repo) => (
          <RepoRow key={repo.repo_id} repo={repo} />
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-xs">
          {t('tasks.integration.mode')}
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as IntegrationMode | '')}
            className="h-8 rounded-md border border-input bg-background px-2 text-[12.5px]"
          >
            <option value="">{t('tasks.integration.modes.project')}</option>
            {(['merge', 'squash', 'rebase'] as const).map((value) => (
              <option key={value} value={value}>
                {t(`tasks.integration.modes.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs">
          <input type="checkbox" checked={push} onChange={(e) => setPush(e.target.checked)} />
          {t('tasks.integration.push')}
        </label>
        <label className="flex items-center gap-1.5 text-xs">
          <input
            type="checkbox"
            checked={removeBranches}
            onChange={(e) => setRemoveBranches(e.target.checked)}
          />
          {t('tasks.integration.deleteBranches')}
        </label>
        <Button
          type="button"
          size="sm"
          disabled={!check.data.can_integrate || integrate.isPending}
          onClick={() => void onIntegrate()}
        >
          {t('tasks.integration.integrate')}
        </Button>
        <label className="flex items-center gap-1.5 text-xs">
          <input type="checkbox" checked={asDraft} onChange={(e) => setAsDraft(e.target.checked)} />
          {t('git.pulls.asDraft')}
        </label>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={check.data.pending === 0 || pulls.isPending}
          onClick={() => void onPulls()}
        >
          {t('tasks.integration.openPull')}
        </Button>
        {anyIntegrated && (
          <Button type="button" size="sm" variant="outline" onClick={() => setConfirmUndo(true)}>
            <Undo2 />
            {t('tasks.integration.undo')}
          </Button>
        )}
      </div>
      {opened.length > 0 && (
        <ul aria-label={t('tasks.integration.pulls')} className="mt-3 flex flex-col gap-1 text-xs">
          {opened.map((item) => (
            <li key={item.repo_id}>
              {item.pull ? (
                <a
                  href={item.pull.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline"
                >
                  {t('tasks.integration.pullLink', { name: item.name, number: item.pull.number })}
                </a>
              ) : item.status === 'failed' ? (
                <span className="text-status-failed">
                  {item.name}: {t(`git.errors.${item.error_code ?? 'git_failed'}`, item.message)}
                </span>
              ) : (
                <span className="text-muted-foreground">
                  {item.name}: {t('tasks.integration.state.nothing')}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {conflicting.length > 0 && <ConflictHelp task={task} repos={conflicting} />}
      <ConfirmDialog
        open={confirmUndo}
        onOpenChange={setConfirmUndo}
        title={t('tasks.integration.undoTitle', { code: task.code })}
        description={t('tasks.integration.undoDescription')}
        confirmLabel={t('tasks.integration.undo')}
        destructive
        onConfirm={() => {
          setConfirmUndo(false)
          void onUndo()
        }}
      />
    </section>
  )
}

function RepoRow({ repo }: { repo: RepoCheck }) {
  const { t } = useTranslation()
  return (
    <li className="flex flex-col gap-0.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{repo.name}</span>
        <span className="font-mono text-xs text-muted-foreground">
          {repo.branch} → {repo.base ?? '?'}
        </span>
        <Badge variant={repo.state === 'clean' ? 'secondary' : 'outline'}>
          {t(`tasks.integration.state.${repo.state}`)}
        </Badge>
        {repo.ahead > 0 && repo.state !== 'integrated' && (
          <span className="text-xs text-muted-foreground">
            {t('tasks.integration.ahead', { count: repo.ahead })}
          </span>
        )}
      </div>
      {repo.state === 'conflicts' && (
        <p className="text-xs text-status-failed">
          {t('tasks.integration.conflictsIn', { count: repo.conflicts.length })}
          {': '}
          <span className="font-mono">{repo.conflicts.join(', ')}</span>
        </p>
      )}
      {repo.state === 'blocked' && (
        <p className="text-xs text-status-failed">
          {t('tasks.integration.blockedBy', { folder: repo.active_in ?? '' })}
          {': '}
          <span className="font-mono">{repo.dirty.join(', ')}</span>
        </p>
      )}
    </li>
  )
}

/** The ways out of a conflict: resolve it in a folder of its own, or ask an agent. */
function ConflictHelp({ task, repos }: { task: Task; repos: RepoCheck[] }) {
  const { t } = useTranslation()
  const agents = useAgents()
  const start = useStartResolution(task.id)
  const finish = useFinishResolution(task.id)
  const resolve = useResolveConflicts(task.id)
  const [open, setOpen] = useState<Record<string, Resolution>>({})
  const [agentId, setAgentId] = useState('')
  const [created, setCreated] = useState<{ id: string; code: string } | null>(null)

  async function onStart(repo: RepoCheck) {
    try {
      const resolution = await start.mutateAsync(repo.repo_id)
      if (resolution.path) setOpen((current) => ({ ...current, [repo.repo_id]: resolution }))
      else toast.success(t('tasks.integration.mergedClean', { name: repo.name }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onFinish(repo: RepoCheck) {
    try {
      await finish.mutateAsync(repo.repo_id)
      setOpen((current) =>
        Object.fromEntries(Object.entries(current).filter(([id]) => id !== repo.repo_id)),
      )
      toast.success(t('tasks.integration.resolved', { name: repo.name }))
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  async function onAgent() {
    try {
      const made = await resolve.mutateAsync(agentId)
      setCreated({ id: made.id, code: made.code })
    } catch (error) {
      toast.error(gitErrorText(error, t))
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-sep pt-3">
      <p className="text-xs text-muted-foreground">{t('tasks.integration.conflictHelp')}</p>
      {repos.map((repo) => (
        <div key={repo.repo_id} className="flex flex-col gap-1">
          {open[repo.repo_id] ? (
            <>
              <p className="text-xs">
                {t('tasks.integration.resolveIn', { name: repo.name })}{' '}
                <span className="font-mono">{open[repo.repo_id].path}</span>
              </p>
              <ul className="font-mono text-xs">
                {open[repo.repo_id].conflicts.map((file) => (
                  <li key={file}>{file}</li>
                ))}
              </ul>
              <div>
                <Button type="button" size="sm" onClick={() => void onFinish(repo)}>
                  {t('tasks.integration.markResolved')}
                </Button>
              </div>
            </>
          ) : (
            <div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                aria-label={`${t('tasks.integration.resolveHere')} ${repo.name}`}
                onClick={() => void onStart(repo)}
              >
                {t('tasks.integration.resolveHere')} · {repo.name}
              </Button>
            </div>
          )}
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label={t('tasks.integration.agent')}
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2 text-[12.5px]"
        >
          <option value="">{t('tasks.integration.chooseAgent')}</option>
          {(agents.data ?? []).map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!agentId || resolve.isPending}
          onClick={() => void onAgent()}
        >
          {t('tasks.integration.handToAgent')}
        </Button>
        {created && (
          <Link
            to={`/tablero/tareas/${created.id}`}
            className="text-xs text-primary hover:underline"
          >
            {t('tasks.integration.createdTask', { code: created.code })}
          </Link>
        )}
      </div>
    </div>
  )
}
