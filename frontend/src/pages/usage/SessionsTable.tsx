import { ArrowDown, ArrowUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import type { SessionSort } from '@/api/usage'
import type { SessionRow } from '@/api/types'
import { AgentAvatar, ProjectChip } from '@/components/agentic/primitives'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatSeconds, formatTokens, formatUsd } from '@/lib/format'
import { formatDateTime } from '@/lib/time'
import { cn } from '@/lib/utils'
import { useProjectColor } from '@/pages/runs/RunsTable'

const COLUMNS: { id: SessionSort; numeric?: boolean }[] = [
  { id: 'started_at' },
  { id: 'agent' },
  { id: 'project' },
  { id: 'task' },
  { id: 'model' },
  { id: 'tokens', numeric: true },
  { id: 'cost', numeric: true },
  { id: 'duration', numeric: true },
]

/** «Sesiones de CLI»: sortable by any column (clicking the active one flips the order). */
export function SessionsTable({
  rows,
  sort,
  dir,
  onSort,
}: {
  rows: SessionRow[]
  sort: SessionSort
  dir: 'asc' | 'desc'
  onSort: (sort: SessionSort, dir: 'asc' | 'desc') => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const projectColor = useProjectColor()
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          {COLUMNS.map((column, i) => {
            const active = sort === column.id
            const Arrow = dir === 'asc' ? ArrowUp : ArrowDown
            return (
              <TableHead
                key={column.id}
                aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                className={cn(
                  column.numeric && 'text-right',
                  i === 0 && 'pl-4',
                  i === COLUMNS.length - 1 && 'pr-4',
                )}
              >
                <button
                  type="button"
                  onClick={() =>
                    onSort(
                      column.id,
                      active ? (dir === 'asc' ? 'desc' : 'asc') : column.numeric ? 'desc' : 'asc',
                    )
                  }
                  className={cn(
                    'inline-flex items-center gap-1 text-[12.5px] hover:text-foreground',
                    active ? 'font-medium text-foreground' : 'text-muted-foreground',
                  )}
                >
                  {t(`usage.sessions.columns.${column.id}`)}
                  {active && <Arrow aria-hidden className="size-3" />}
                </button>
              </TableHead>
            )
          })}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const open = () => navigate(`/ejecuciones/${row.run_id}`)
          const partial = row.usage_status === 'partial'
          return (
            <TableRow
              key={row.run_id}
              tabIndex={0}
              aria-label={t('usage.sessions.open', { name: row.agent_name })}
              onClick={open}
              onKeyDown={(e) => e.key === 'Enter' && open()}
              className="cursor-pointer"
            >
              <TableCell className="py-2.5 pl-4 font-mono text-xs whitespace-nowrap text-muted-foreground">
                {row.started_at ? formatDateTime(row.started_at) : '—'}
              </TableCell>
              <TableCell>
                <span className="inline-flex items-center gap-2 font-medium whitespace-nowrap">
                  <AgentAvatar
                    name={row.agent_name}
                    color={row.agent_color}
                    agentId={row.agent_id}
                    size={20}
                  />
                  {row.agent_name}
                </span>
              </TableCell>
              <TableCell className="whitespace-nowrap">
                <ProjectChip
                  name={row.project_name}
                  color={projectColor(row.project_id)}
                  variant="dot"
                />
              </TableCell>
              <TableCell className="max-w-[320px] truncate">
                {row.task_code ? (
                  `${row.task_title ?? ''}`
                ) : (
                  <span className="text-muted-foreground">{t('usage.sessions.manual')}</span>
                )}
              </TableCell>
              <TableCell className="font-mono text-xs whitespace-nowrap text-muted-foreground">
                {row.model || '—'}
              </TableCell>
              <TableCell className="text-right font-mono text-[13px] whitespace-nowrap">
                {row.usage_status === 'unavailable' ? '—' : formatTokens(row.tokens)}
              </TableCell>
              <TableCell
                className="text-right font-mono text-[13px] whitespace-nowrap"
                title={partial ? t('usage.partialHint') : undefined}
              >
                {formatUsd(row.cost_usd)}
                {partial && (
                  <span className="ml-1 text-[10.5px] text-muted-foreground">
                    {t('usage.sessions.partial')}
                  </span>
                )}
              </TableCell>
              <TableCell className="pr-4 text-right font-mono text-[13px] whitespace-nowrap">
                {formatSeconds(row.duration_seconds)}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
