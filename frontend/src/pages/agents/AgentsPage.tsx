import { Bot, ChevronRight, FileUp, LayoutTemplate, Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useAgents } from '@/api/agents'
import { useTeams } from '@/api/teams'
import { useMonthBreakdown } from '@/api/usage'
import { formatTokens, formatUsd } from '@/lib/format'
import type { Agent, Team } from '@/api/types'
import { AgentAvatar, CliTag, StatusBadge } from '@/components/agentic/primitives'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import { useDialogs } from '@/stores/dialogs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ImportAgentDialog, TemplatesDialog } from './AgentFileDialogs'
import { TemplatePicker } from './TemplatePicker'

const ALL = '__all__' // Radix Select cannot use "" as an item value
const NO_TEAM = '__none__'

export default function AgentsPage() {
  const { t } = useTranslation()
  const { data: agents, isPending } = useAgents()
  const openNewAgent = useDialogs((s) => s.openNewAgent)
  const [importing, setImporting] = useState(false)
  const [templates, setTemplates] = useState(false)

  return (
    <PageContainer>
      <PageHeader
        title={t('agents.title')}
        subtitle={t('agents.subtitle')}
        actions={
          <>
            <Button variant="ghost" onClick={() => setTemplates(true)}>
              <LayoutTemplate />
              {t('agentTemplates.title')}
            </Button>
            <Button variant="outline" onClick={() => setImporting(true)}>
              <FileUp />
              {t('agentTemplates.import.button')}
            </Button>
            <Button variant="outline" asChild>
              <Link to="/agentes/arquitecto?nueva">
                <Sparkles className="text-status-review" />
                {t('agents.architect')}
              </Link>
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
        <AgentsList agents={agents} />
      ) : (
        <EmptyState
          icon={Bot}
          title={t('pages.agents.emptyTitle')}
          description={t('pages.agents.emptyDescription')}
        >
          <TemplatePicker compact />
        </EmptyState>
      )}
      <ImportAgentDialog open={importing} onOpenChange={setImporting} />
      <TemplatesDialog open={templates} onOpenChange={setTemplates} />
    </PageContainer>
  )
}

/** The agents, filterable by team once there is any (`?equipo=<id>` or `?equipo=sin`). */
function AgentsList({ agents }: { agents: Agent[] }) {
  const { t } = useTranslation()
  const teams = useTeams().data ?? []
  const [params, setParams] = useSearchParams()
  const wanted = params.get('equipo')
  const filter = wanted === 'sin' ? NO_TEAM : teams.some((x) => x.id === wanted) ? wanted : null
  const shown = agents.filter((a) =>
    filter === null ? true : filter === NO_TEAM ? !a.team_id : a.team_id === filter,
  )
  return (
    <>
      {teams.length > 0 && (
        <div className="flex justify-end">
          <Select
            value={filter ?? ALL}
            onValueChange={(value) => {
              if (!value) return
              const next = new URLSearchParams(params)
              if (value === ALL) next.delete('equipo')
              else next.set('equipo', value === NO_TEAM ? 'sin' : value)
              setParams(next, { replace: true })
            }}
          >
            <SelectTrigger aria-label={t('agents.fields.team')} className="w-[220px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t('agents.allTeams')}</SelectItem>
              <SelectItem value={NO_TEAM}>{t('teams.none')}</SelectItem>
              {teams.map((team) => (
                <SelectItem key={team.id} value={team.id}>
                  {team.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      <AgentsTable agents={shown} teams={teams} />
    </>
  )
}

function AgentsTable({ agents, teams }: { agents: Agent[]; teams: Team[] }) {
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
    <div className="overflow-hidden rounded-xl border border-sep shadow-card bg-card-grad">
      <Table>
        <TableHeader className="bg-subtle">
          <TableRow className="hover:bg-transparent">
            <TableHead className="px-4">{t('agents.columns.agent')}</TableHead>
            {teams.length > 0 && <TableHead>{t('agents.columns.team')}</TableHead>}
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
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{agent.name}</span>
                        {agent.status === 'draft' && agent.proposal_id && (
                          // Phase 19, design §2: a draft that waits for the person.
                          <span className="flex h-5 items-center gap-1 rounded-full border border-dashed border-status-review px-1.5 text-[11px] whitespace-nowrap text-status-review">
                            <Sparkles className="size-3" aria-hidden />
                            {agent.proposed_by && agent.proposed_by !== 'architect'
                              ? t('proposals.chipAgent', { name: agent.proposed_by })
                              : t('proposals.chip')}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">{agent.role}</div>
                    </div>
                  </div>
                </TableCell>
                {teams.length > 0 && (
                  <TableCell className="text-[13px] text-muted-foreground">
                    {teams.find((x) => x.id === agent.team_id)?.name ?? t('teams.none')}
                  </TableCell>
                )}
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
