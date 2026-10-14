import { Bot, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { HomeAgent, TodayAgent } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { useDialogs } from '@/stores/dialogs'
import { AgentCard } from './AgentCard'

/** All the agents in one grid; drafts last. */
export function AgentGrid({
  agents,
  usage,
  highlighted,
  waitingRuns,
}: {
  agents: HomeAgent[]
  usage: TodayAgent[]
  highlighted: string | null
  waitingRuns: Set<string>
}) {
  const { t } = useTranslation()
  const openNewAgent = useDialogs((s) => s.openNewAgent)
  const ordered = [...agents].sort(
    (a, b) => Number(a.state === 'draft') - Number(b.state === 'draft'),
  )
  const maxCost = Math.max(0, ...usage.map((u) => u.cost_usd))

  return (
    <section
      aria-labelledby="agents-title"
      className="flex min-w-0 animate-rise-in flex-col gap-3.5 [animation-delay:160ms]"
    >
      <div className="flex items-center gap-2.5">
        <h2 id="agents-title" className="text-lg font-bold tracking-[-0.02em]">
          {t('home.agents.title')}
        </h2>
        <span className="text-xs text-muted-foreground">
          {t('home.agents.count', { count: agents.length })}
        </span>
        {agents.length > 0 && (
          <button
            type="button"
            onClick={openNewAgent}
            className="ml-auto flex h-[30px] items-center gap-1.5 rounded-full px-3 text-[12.5px] text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Plus className="size-3.5" />
            {t('home.agents.new')}
          </button>
        )}
      </div>
      {agents.length === 0 ? (
        <EmptyState
          icon={Bot}
          title={t('home.agents.empty.title')}
          description={t('home.agents.empty.description')}
        >
          <Button
            onClick={openNewAgent}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            <Plus />
            {t('home.agents.new')}
          </Button>
        </EmptyState>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-3">
          {ordered.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              highlighted={highlighted === agent.id}
              usage={usage.find((u) => u.id === agent.id)}
              maxCost={maxCost}
              waitingRuns={waitingRuns}
            />
          ))}
        </div>
      )}
    </section>
  )
}
