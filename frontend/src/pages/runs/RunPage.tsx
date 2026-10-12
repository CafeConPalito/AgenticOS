import { FolderOpen, SquareTerminal, Square } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { useOpenProjectFolder } from '@/api/projects'
import { isActive, useRun, useStopRun } from '@/api/runs'
import type { Run } from '@/api/types'
import { AgentAvatar, ProjectChip } from '@/components/agentic/primitives'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer } from '@/components/page'
import { TerminalPanel } from '@/components/terminal/TerminalPanel'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useNow } from '@/hooks/use-now'
import { errorMessage } from '@/lib/form-errors'
import { formatDateTime, formatDuration } from '@/lib/time'
import { SessionUsage } from '@/components/usage/SessionUsage'
import { RunEventsPanel } from './RunEventsPanel'
import { RunStatusBadge } from './RunStatusBadge'
import { useProjectColor } from './RunsTable'

/** First line of the prompt, as the run's title. */
export function runTitle(run: Pick<Run, 'prompt'>, max = 80): string {
  const line = run.prompt.split('\n', 1)[0].trim()
  return line.length > max ? `${line.slice(0, max - 1)}…` : line
}

export default function RunPage() {
  const { runId = '' } = useParams()
  const { t } = useTranslation()
  const { data: run, isPending, isError } = useRun(runId)

  if (isPending)
    return (
      <PageContainer>
        <Skeleton aria-busy className="h-24 rounded-lg" />
      </PageContainer>
    )
  if (isError || !run)
    return (
      <PageContainer>
        <EmptyState icon={SquareTerminal} title={t('runs.notFound')} />
      </PageContainer>
    )
  return <RunDetail key={run.id} run={run} />
}

function RunDetail({ run }: { run: Run }) {
  const { t } = useTranslation()
  const stop = useStopRun()
  const openFolder = useOpenProjectFolder()
  const projectColor = useProjectColor()
  const [confirmStop, setConfirmStop] = useState(false)
  const active = isActive(run)

  async function onStop() {
    try {
      await stop.mutateAsync(run.id)
      toast.success(t('runs.stop.done', { name: run.agent_name }))
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  async function onOpenFolder() {
    if (!run.project_id) return
    try {
      await openFolder.mutateAsync(run.project_id)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <div className="flex h-full min-h-[560px] flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b px-5 py-3">
        <h1 className="min-w-0 truncate text-[17px] font-medium" title={run.prompt}>
          {runTitle(run)}
        </h1>
        <RunStatusBadge run={run} />
        <ProjectChip name={run.project_name} color={projectColor(run.project_id)} />
        <span className="inline-flex items-center gap-2 text-[12.5px] text-muted-foreground">
          <AgentAvatar name={run.agent_name} color={run.agent_color} size={18} />
          {run.agent_name}
        </span>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void onOpenFolder()}
            disabled={!run.project_id || openFolder.isPending}
          >
            <FolderOpen />
            {t('runs.openFolder')}
          </Button>
          {active && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmStop(true)}
              disabled={stop.isPending}
              className="border-status-failed/50 text-status-failed hover:bg-status-failed/10 hover:text-status-failed"
            >
              <Square />
              {t('runs.stop.button')}
            </Button>
          )}
        </div>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_316px] grid-rows-[minmax(0,1fr)]">
        <RunSidePanel run={run} />
        <div className="flex min-h-0 flex-col gap-2 p-3.5">
          <TerminalPanel run={run} />
          <div className="flex gap-4 px-0.5 font-mono text-[11.5px] text-muted-foreground">
            <span>{t('runs.terminalInfo', { cols: run.cols, rows: run.rows })}</span>
            <span>{t(`cli.${run.cli}`)}</span>
            <span className="truncate">{run.cwd}</span>
          </div>
        </div>
        <aside className="flex min-h-0 flex-col overflow-auto border-l p-4">
          <RunEventsPanel runId={run.id} />
          <SessionUsage run={run} />
        </aside>
      </div>
      <ConfirmDialog
        open={confirmStop}
        onOpenChange={setConfirmStop}
        title={t('runs.stop.title', { name: run.agent_name })}
        description={t('runs.stop.description')}
        confirmLabel={t('runs.stop.confirm')}
        destructive
        onConfirm={() => void onStop()}
      />
    </div>
  )
}

function RunSidePanel({ run }: { run: Run }) {
  const { t } = useTranslation()
  const now = useNow(isActive(run) ? 1000 : null)
  const rows: [string, React.ReactNode][] = [
    [
      t('runs.details.agent'),
      run.agent_id ? (
        <Link to={`/agentes/${run.agent_id}/general`}>{run.agent_name}</Link>
      ) : (
        run.agent_name
      ),
    ],
    [
      t('runs.details.project'),
      run.project_id ? (
        <Link to={`/proyectos/${run.project_id}/summary`}>{run.project_name}</Link>
      ) : (
        run.project_name
      ),
    ],
    [t('runs.details.cli'), t(`cli.${run.cli}`)],
    [
      t('runs.details.model'),
      <span className="font-mono">{run.model || t('cli.defaultModel')}</span>,
    ],
    [
      t('runs.details.started'),
      run.started_at ? formatDateTime(run.started_at, now) : t('common.none'),
    ],
    [
      t('runs.details.duration'),
      <span className="font-mono">{formatDuration(run.started_at, run.ended_at, now)}</span>,
    ],
    [
      t('runs.details.session'),
      <span className="font-mono text-[11.5px] break-all">
        {run.cli_session_id ?? t('common.none')}
      </span>,
    ],
  ]
  if (run.exit_code !== null)
    rows.push([t('runs.details.exitCode'), <span className="font-mono">{run.exit_code}</span>])
  if (isActive(run)) rows.push([t('runs.details.viewers'), run.viewers])

  return (
    <aside className="flex min-h-0 flex-col gap-[18px] overflow-auto border-r p-4">
      <section>
        <h2 className="mb-1.5 text-[12.5px] text-muted-foreground">{t('runs.details.prompt')}</h2>
        <p className="text-[13.5px] whitespace-pre-wrap">{run.prompt}</p>
      </section>
      {run.last_status && !run.summary && (
        <section>
          <h2 className="mb-1.5 text-[12.5px] text-muted-foreground">
            {t('runs.details.lastStatus')}
          </h2>
          <p className="text-[13px]">{run.last_status}</p>
        </section>
      )}
      {run.summary && (
        <section className="rounded-[10px] border bg-subtle px-3.5 py-3">
          <h2 className="mb-1.5 text-[12.5px] text-muted-foreground">{t('runs.summary')}</h2>
          <p className="text-[13.5px] whitespace-pre-wrap">{run.summary}</p>
        </section>
      )}
      {run.error && (
        <section>
          <h2 className="mb-1.5 text-[12.5px] text-muted-foreground">{t('runs.details.error')}</h2>
          <p role="alert" className="font-mono text-xs break-words text-status-failed">
            {run.error}
          </p>
        </section>
      )}
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[13px] [&_a]:underline-offset-2 [&_a:hover]:underline">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0">{value}</dd>
          </div>
        ))}
      </dl>
      <section>
        <h2 className="mb-1.5 text-[12.5px] text-muted-foreground">{t('runs.details.folder')}</h2>
        <p className="font-mono text-xs break-all">{run.cwd}</p>
      </section>
    </aside>
  )
}
