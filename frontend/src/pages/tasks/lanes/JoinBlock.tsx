import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import {
  type JoinResolution,
  useFinishJoinEditor,
  useJoin,
  useJoinAgent,
  useStartJoinEditor,
} from '@/api/tasks'
import type { Task } from '@/api/types'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/form-errors'

/** The lanes’ branches clash where they meet: resolve here or hand it to an agent. */
export function JoinBlock({ task }: { task: Task }) {
  const { t } = useTranslation()
  const waiting = task.status === 'waiting_human' && task.waiting_reason === 'join_conflict'
  const clashes = useJoin(task.id, waiting).data ?? []
  const agents = useAgents().data ?? []
  const start = useStartJoinEditor(task.id)
  const finish = useFinishJoinEditor(task.id)
  const handOver = useJoinAgent(task.id)
  const [open, setOpen] = useState<JoinResolution[]>([])
  const [agentId, setAgentId] = useState('')
  const [created, setCreated] = useState<{ id: string; code: string } | null>(null)
  if (!waiting) return null

  async function onStart() {
    try {
      const found = await start.mutateAsync()
      setOpen(found)
      if (found.length === 0) toast.success(t('tasks.lanes.mergedClean'))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onFinish(repo: JoinResolution) {
    try {
      const result = await finish.mutateAsync(repo.repo_id)
      setOpen((current) => current.filter((r) => r.repo_id !== repo.repo_id))
      if (result.conflicts.length)
        setOpen((current) => [...current, { ...repo, conflicts: result.conflicts }])
      else toast.success(t('tasks.lanes.resolved', { name: repo.name }))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onAgent() {
    try {
      const made = await handOver.mutateAsync(agentId)
      setCreated({ id: made.id, code: made.code })
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <section
      aria-labelledby="join-title"
      className="flex flex-col gap-2 rounded-[10px] border border-status-waiting/40 bg-status-waiting/10 px-3 py-2.5"
    >
      <h2 id="join-title" className="text-[12.5px] font-medium">
        {t('tasks.lanes.joinTitle')}
      </h2>
      <p className="text-xs text-muted-foreground">{t('tasks.lanes.joinHelp')}</p>
      <ul className="grid gap-1 text-xs">
        {clashes.map((c) => (
          <li key={`${c.repo_id}-${c.lane}`}>
            <span className="font-medium">
              {c.name} · {c.lane}
            </span>
            <span className="block font-mono break-words text-muted-foreground">
              {c.files.join(', ')}
            </span>
          </li>
        ))}
      </ul>
      {open.map((repo) => (
        <div key={repo.repo_id} className="flex flex-col gap-1">
          <p className="text-xs">
            {t('tasks.lanes.resolveIn', { name: repo.name })}{' '}
            <span className="font-mono break-all">{repo.path}</span>
          </p>
          <ul className="font-mono text-xs">
            {repo.conflicts.map((file) => (
              <li key={file}>{file}</li>
            ))}
          </ul>
          <div>
            <Button size="sm" onClick={() => void onFinish(repo)}>
              {t('tasks.lanes.markResolved')}
            </Button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={start.isPending || open.length > 0}
          onClick={() => void onStart()}
        >
          {t('tasks.lanes.resolveHere')}
        </Button>
        <select
          aria-label={t('tasks.lanes.agent')}
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2 text-[12.5px]"
        >
          <option value="">{t('tasks.lanes.chooseAgent')}</option>
          {agents
            .filter((a) => a.status !== 'draft')
            .map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
        </select>
        <Button
          size="sm"
          variant="outline"
          disabled={!agentId || handOver.isPending}
          onClick={() => void onAgent()}
        >
          {t('tasks.lanes.handToAgent')}
        </Button>
        {created && (
          <Link
            to={`/tablero/tareas/${created.id}`}
            className="text-xs text-primary hover:underline"
          >
            {t('tasks.lanes.createdTask', { code: created.code })}
          </Link>
        )}
      </div>
    </section>
  )
}
