import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useAgents } from '@/api/agents'
import { type Conversation, useConversationActions, useProposal } from '@/api/architect'
import { AgentAvatar } from '@/components/agentic/primitives'
import { TeamProposalReview } from '@/components/proposals/TeamProposalReview'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { errorMessage } from '@/lib/form-errors'
import { cn } from '@/lib/utils'
import { PipelinePreview } from './PipelinePreview'

/** The sheet of a team conversation (design §11): the team, its agents and the pipeline, each
 * in its tab, filled in as the Architect works. */
export function TeamSheet({ conversation }: { conversation: Conversation }) {
  const { t } = useTranslation()
  const actions = useConversationActions(conversation.id)
  const existing = useAgents().data ?? []
  const [reviewing, setReviewing] = useState(false)
  const { data: proposal } = useProposal(conversation.proposal_id)
  const { sheet, issues, progress, ready, pipeline_layout } = conversation.sheet
  const improving = conversation.mode !== 'team'
  const refs = Object.keys(sheet.agents)
  const names: Record<string, string> = Object.fromEntries(existing.map((a) => [a.id, a.name]))
  for (const ref of refs) names[`ref:${ref}`] = sheet.agents[ref]?.name || ref
  const percent = refs.length
    ? Math.round(refs.reduce((sum, ref) => sum + (progress[ref] ?? 0), 0) / refs.length)
    : 0
  const errors = issues.filter((i) => i.level === 'error')
  const warnings = issues.filter((i) => i.level === 'warning')
  const team = sheet.team
  const pending = proposal?.status === 'pending'

  async function propose() {
    try {
      await actions.propose.mutateAsync()
      toast.success(t('architect.teamProposed'))
      setReviewing(true)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <aside className="flex min-h-0 flex-col bg-subtle" aria-label={t('architect.teamSheet')}>
      <div className="border-b border-sep px-5 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-medium">
            {t(improving ? 'architect.teamSheetImprove' : 'architect.teamSheet')}
          </h2>
          <span className="text-[12.5px] text-muted-foreground">
            {t('architect.progress', { percent })}
          </span>
        </div>
      </div>

      <Tabs defaultValue="team" className="flex min-h-0 flex-1 flex-col gap-0">
        <TabsList className="mx-5 mt-3">
          <TabsTrigger value="team">{t('architect.tabs.team')}</TabsTrigger>
          <TabsTrigger value="agents">{t('architect.tabs.agents')}</TabsTrigger>
          <TabsTrigger value="pipeline">{t('architect.tabs.pipeline')}</TabsTrigger>
        </TabsList>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <TabsContent value="team" className="space-y-3">
            <div className="space-y-3 rounded-lg border border-sep bg-card p-4">
              <Field label={t('architect.fields.name')} value={team.name} />
              <Field label={t('architect.fields.description')} value={team.description} />
            </div>
          </TabsContent>
          <TabsContent value="agents" className="space-y-2">
            {refs.length === 0 && sheet.existing_agents.length === 0 && (
              <div
                aria-hidden
                className="h-14 animate-pulse rounded-md border border-dashed border-sep bg-muted/40"
              />
            )}
            <ul className="space-y-2">
              {refs.map((ref) => {
                const agent = sheet.agents[ref]
                return (
                  <li
                    key={ref}
                    className="flex items-center gap-3 rounded-lg border border-sep bg-card p-3"
                  >
                    <AgentAvatar
                      name={agent?.name || '?'}
                      color={agent?.color || '#B39CFF'}
                      size={32}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{agent?.name || ref}</p>
                      <p className="truncate text-[12.5px] text-muted-foreground">
                        {agent?.role}
                        {agent?.cli ? ` · ${t(`cli.${agent.cli}`)}` : ''}
                      </p>
                    </div>
                    <span className="text-[12px] text-muted-foreground">
                      {t('architect.newAgent')} · {progress[ref] ?? 0} %
                    </span>
                  </li>
                )
              })}
              {sheet.existing_agents.map((id) => (
                <li
                  key={id}
                  className="flex items-center gap-3 rounded-lg border border-sep bg-card p-3"
                >
                  <AgentAvatar name={names[id] ?? '?'} color="#B39CFF" size={32} />
                  <p className="min-w-0 flex-1 truncate font-medium">{names[id] ?? id}</p>
                  <span className="text-[12px] text-muted-foreground">
                    {t('architect.existingAgent')}
                  </span>
                </li>
              ))}
            </ul>
          </TabsContent>
          <TabsContent value="pipeline" className="space-y-2">
            {sheet.pipeline ? (
              <>
                <p className="text-[12.5px] text-muted-foreground">
                  {t('architect.pipelineOf', { project: sheet.pipeline.project_name })}
                </p>
                <PipelinePreview
                  pipeline={sheet.pipeline}
                  layout={pipeline_layout}
                  agentNames={names}
                />
              </>
            ) : (
              <p className="text-[12.5px] text-muted-foreground">{t('architect.noPipeline')}</p>
            )}
          </TabsContent>
          {(errors.length > 0 || warnings.length > 0) && (
            <ul className="mt-3 space-y-1 text-[12.5px]" aria-label={t('architect.issues')}>
              {[...errors, ...warnings].map((issue) => (
                <li key={`${issue.field}-${issue.code}`} className="flex gap-1.5">
                  <AlertTriangle
                    className={cn(
                      'mt-0.5 size-3.5 shrink-0',
                      issue.level === 'error' ? 'text-status-failed' : 'text-status-waiting',
                    )}
                    aria-hidden
                  />
                  <span>{issue.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Tabs>

      <div className="border-t border-sep px-5 py-3">
        {conversation.status === 'open' ? (
          <Button
            onClick={() => void propose()}
            disabled={!ready || actions.propose.isPending}
            className="w-full bg-primary-action text-white hover:bg-primary-action-hover disabled:opacity-45"
          >
            {t('architect.proposeTeam')}
          </Button>
        ) : pending ? (
          <Button
            onClick={() => setReviewing(true)}
            className="w-full bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('proposals.reviewTeam')}
          </Button>
        ) : (
          <p className="text-center text-[12.5px] text-muted-foreground">
            {t(`architect.done.${conversation.status}`)}
          </p>
        )}
        <p className="mt-1.5 text-center text-[11.5px] text-muted-foreground">
          {t('architect.teamNote')}
        </p>
      </div>
      {reviewing && proposal && (
        <TeamProposalReview proposal={proposal} onClose={() => setReviewing(false)} />
      )}
    </aside>
  )
}

function Field({ label, value }: { label: string; value?: string }) {
  return (
    <section>
      <h3 className="mb-1 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </h3>
      {value ? (
        <p className="whitespace-pre-wrap">{value}</p>
      ) : (
        <div
          aria-hidden
          className="h-8 animate-pulse rounded-md border border-dashed border-sep bg-muted/40"
        />
      )}
    </section>
  )
}
