import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useProjects } from '@/api/projects'
import { isActive } from '@/api/runs'
import type { Run } from '@/api/types'
import { AgentAvatar, CliTag, ProjectChip } from '@/components/agentic/primitives'
import { ChangesBadge } from '@/components/changes/ChangesBadge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useNow } from '@/hooks/use-now'
import { formatTokens, formatUsd, totalTokens } from '@/lib/format'
import { formatDateTime, formatDuration } from '@/lib/time'
import { RunStatusBadge } from './RunStatusBadge'

/** Project colour for a run (runs keep a copy of the name, not of the colour). */
export function useProjectColor() {
  const projects = useProjects().data
  return (id: string | null) =>
    projects?.find((p) => p.id === id)?.color ?? 'var(--muted-foreground)'
}

export function RunsTable({ runs, showAgent = true }: { runs: Run[]; showAgent?: boolean }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const projectColor = useProjectColor()
  const now = useNow(runs.some(isActive) ? 1000 : null)

  return (
    <div className="overflow-hidden rounded-xl border border-sep shadow-card bg-card-grad">
      <Table>
        <TableHeader className="bg-subtle">
          <TableRow className="hover:bg-transparent">
            <TableHead className="px-4">{t('runs.columns.started')}</TableHead>
            {showAgent && <TableHead>{t('runs.columns.agent')}</TableHead>}
            <TableHead>{t('runs.columns.prompt')}</TableHead>
            <TableHead>{t('runs.columns.project')}</TableHead>
            <TableHead>{t('runs.columns.status')}</TableHead>
            <TableHead>{t('runs.columns.account')}</TableHead>
            <TableHead>{t('runs.columns.changes')}</TableHead>
            <TableHead className="text-right">{t('usage.columns.tokens')}</TableHead>
            <TableHead className="text-right">{t('usage.columns.cost')}</TableHead>
            <TableHead className="pr-4 text-right">{t('runs.columns.duration')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => {
            const open = () => navigate(`/ejecuciones/${run.id}`)
            return (
              <TableRow
                key={run.id}
                tabIndex={0}
                aria-label={t('runs.open', { name: run.agent_name, prompt: run.prompt })}
                onClick={open}
                onKeyDown={(e) => e.key === 'Enter' && open()}
                className="cursor-pointer"
              >
                <TableCell className="px-4 py-3 font-mono text-xs whitespace-nowrap text-muted-foreground">
                  {formatDateTime(run.started_at ?? run.created_at, now)}
                </TableCell>
                {showAgent && (
                  <TableCell>
                    <span className="inline-flex items-center gap-2 font-medium whitespace-nowrap">
                      <AgentAvatar name={run.agent_name} color={run.agent_color} size={20} />
                      {run.agent_name}
                    </span>
                  </TableCell>
                )}
                <TableCell className="max-w-[420px]">
                  <div className="flex items-center gap-2">
                    <CliTag cli={run.cli} label={t(`cli.${run.cli}`)} size={20} />
                    <div className="min-w-0">
                      <div className="truncate">{run.prompt}</div>
                      {run.last_status ? (
                        <div className="truncate text-[11.5px] text-muted-foreground">
                          {run.last_status}
                        </div>
                      ) : (
                        run.cli_session_id && (
                          <div className="truncate font-mono text-[11px] text-muted-foreground">
                            {run.cli_session_id}
                          </div>
                        )
                      )}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <ProjectChip name={run.project_name} color={projectColor(run.project_id)} />
                </TableCell>
                <TableCell>
                  <RunStatusBadge run={run} size="xs" />
                </TableCell>
                {/* Tertiary information (design v7): small and muted. */}
                <TableCell className="max-w-[160px] truncate text-xs text-muted-foreground">
                  {run.account_label || '—'}
                </TableCell>
                <TableCell>
                  {run.changes ? (
                    <ChangesBadge compact totals={run.changes} />
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right font-mono text-xs whitespace-nowrap text-muted-foreground">
                  {run.usage.status === 'unavailable' || run.usage.status === 'pending'
                    ? '—'
                    : formatTokens(totalTokens(run.usage, run.cli))}
                </TableCell>
                <TableCell className="text-right font-mono text-xs font-medium whitespace-nowrap">
                  {formatUsd(run.usage.cost_usd)}
                </TableCell>
                <TableCell className="pr-4 text-right font-mono text-xs text-muted-foreground">
                  {formatDuration(run.started_at, run.ended_at, now)}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
