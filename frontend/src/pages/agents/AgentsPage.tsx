import { Bot, ChevronRight, Plus, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { useAgents } from '@/api/agents'
import { useMonthBreakdown } from '@/api/usage'
import { formatTokens, formatUsd } from '@/lib/format'
import type { Agent } from '@/api/types'
import { AgentAvatar, CliTag, StatusBadge } from '@/components/agentic/primitives'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import { useDialogs } from '@/stores/dialogs'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { TemplatePicker } from './TemplatePicker'

export default function AgentsPage() {
  const { t } = useTranslation()
  const { data: agents, isPending } = useAgents()
  const openNewAgent = useDialogs((s) => s.openNewAgent)

  return (
    <PageContainer>
      <PageHeader
        title={t('agents.title')}
        subtitle={t('agents.subtitle')}
        actions={
          <>
            <Button variant="outline" disabled title={t('common.comingSoonPhase')}>
              <Sparkles className="text-status-review" />
              {t('agents.architect')}
            </Button>
            <Button
              onClick={() => openNewAgent()}
              className="bg-primary-action text-white hover:bg-primary-action-hover"
            >
              <Plus />
              {t('header.primary.newAgent')}
            </Button>
          </>
        }
      />
      {isPending ? (
        <div aria-busy className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : agents && agents.length > 0 ? (
        <AgentsTable agents={agents} />
      ) : (
        <EmptyState
          icon={Bot}
          title={t('pages.agents.emptyTitle')}
          description={t('pages.agents.emptyDescription')}
        >
          <TemplatePicker compact />
        </EmptyState>
      )}
    </PageContainer>
  )
}

function AgentsTable({ agents }: { agents: Agent[] }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const month = useMonthBreakdown('agent').data
  // «Consumo del mes»: the cost, or the tokens for an agent whose CLI records no cost (agy).
  const monthUsage = (id: string) => {
    const row = month?.rows.find((r) => r.id === id)
    if (!row) return t('common.none')
    return row.cost_usd > 0 ? formatUsd(row.cost_usd) : formatTokens(row.tokens)
  }
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader className="bg-subtle">
          <TableRow className="hover:bg-transparent">
            <TableHead className="px-4">{t('agents.columns.agent')}</TableHead>
            <TableHead>{t('agents.columns.cli')}</TableHead>
            <TableHead>{t('agents.columns.model')}</TableHead>
            <TableHead>{t('agents.columns.status')}</TableHead>
            <TableHead className="text-right">{t('agents.columns.queue')}</TableHead>
            <TableHead className="text-right">{t('agents.columns.usage')}</TableHead>
            <TableHead className="w-8" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {agents.map((agent) => {
            const open = () => navigate(`/agentes/${agent.id}`)
            return (
              <TableRow
                key={agent.id}
                tabIndex={0}
                aria-label={t('agents.open', { name: agent.name })}
                onClick={open}
                onKeyDown={(e) => e.key === 'Enter' && open()}
                className="cursor-pointer"
              >
                <TableCell className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <AgentAvatar name={agent.name} color={agent.color} size={32} />
                    <div className="min-w-0">
                      <div className="font-medium">{agent.name}</div>
                      <div className="text-xs text-muted-foreground">{agent.role}</div>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <CliTag cli={agent.cli} label={t(`cli.${agent.cli}`)} />
                    <span className="font-medium">{t(`cli.${agent.cli}`)}</span>
                  </div>
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {agent.model || t('cli.defaultModel')}
                </TableCell>
                <TableCell>
                  <StatusBadge
                    tone={agent.status === 'draft' ? 'review' : 'queued'}
                    label={t(`agents.status.${agent.status}`)}
                    size="sm"
                  />
                </TableCell>
                <TableCell className="text-right font-mono">
                  {agent.queued_count + agent.running_count > 0
                    ? `${agent.running_count} · ${agent.queued_count}`
                    : t('common.none')}
                </TableCell>
                <TableCell className="text-right font-mono">{monthUsage(agent.id)}</TableCell>
                <TableCell>
                  <ChevronRight className="size-4 text-muted-foreground" />
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
