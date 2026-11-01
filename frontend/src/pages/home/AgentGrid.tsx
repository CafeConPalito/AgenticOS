import { Bot, ChevronDown, Pencil, Plus, Sparkles, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import type { HomeAgent, Team, TodayAgent } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useDialogs } from '@/stores/dialogs'
import { AgentCard } from './AgentCard'

const GRID = 'grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-3'

/** Drafts last, the rest in the order they come. */
const draftsLast = (agents: HomeAgent[]) =>
  [...agents].sort((a, b) => Number(a.state === 'draft') - Number(b.state === 'draft'))

/** The agents grouped by team (phase 10); one grid when there are no teams. */
export function AgentGrid({
  agents,
  teams,
  usage,
  highlighted,
  waitingRuns,
}: {
  agents: HomeAgent[]
  teams: Team[]
  usage: TodayAgent[]
  highlighted: string | null
  waitingRuns: Set<string>
}) {
  const { t } = useTranslation()
  const openNewAgent = useDialogs((s) => s.openNewAgent)
  const openTeam = useDialogs((s) => s.openTeam)
  const maxCost = Math.max(0, ...usage.map((u) => u.cost_usd))
  const known = new Set(teams.map((team) => team.id))
  // An agent whose team is gone (deleted meanwhile) reads as having none.
  const loose = draftsLast(agents.filter((a) => !a.team_id || !known.has(a.team_id)))

  const cards = (list: HomeAgent[]) =>
    list.map((agent) => (
      <AgentCard
        key={agent.id}
        agent={agent}
        highlighted={highlighted === agent.id}
        usage={usage.find((u) => u.id === agent.id)}
        maxCost={maxCost}
        waitingRuns={waitingRuns}
      />
    ))

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
          {teams.length > 0
            ? t('home.agents.countTeams', { teams: teams.length, agents: agents.length })
            : t('home.agents.count', { count: agents.length })}
        </span>
        {/* Phase 20: one «Nuevo» instead of three buttons; the empty state keeps its own. */}
        {(agents.length > 0 || teams.length > 0) && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="ml-auto flex h-[30px] items-center gap-1.5 rounded-full px-3 text-[12.5px] text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <Plus className="size-3.5" />
                {t('home.agents.newMenu')}
                <ChevronDown className="size-3.5" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => openNewAgent()}>
                <Bot />
                {t('home.agents.new')}
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link to="/agentes/arquitecto?nueva">
                  <Sparkles className="text-status-review" />
                  {t('agents.architect')}
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => openTeam()}>
                <Users />
                {t('teams.new')}
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link to="/agentes/arquitecto?equipo">
                  <Sparkles className="text-status-review" />
                  {t('teams.withArchitect')}
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      {agents.length === 0 && teams.length === 0 ? (
        <EmptyState
          icon={Bot}
          title={t('home.agents.empty.title')}
          description={t('home.agents.empty.description')}
        >
          <div className="flex flex-wrap justify-center gap-2">
            <Button asChild className="bg-primary-action text-white hover:bg-primary-action-hover">
              <Link to="/agentes/arquitecto?nueva">
                <Sparkles />
                {t('agents.architect')}
              </Link>
            </Button>
            <Button variant="outline" onClick={() => openNewAgent()}>
              <Plus />
              {t('home.agents.new')}
            </Button>
            {/* A team can come first and get its agents later (phase 21). */}
            <Button variant="outline" onClick={() => openTeam()}>
              <Users />
              {t('teams.new')}
            </Button>
            <Button variant="outline" asChild>
              <Link to="/agentes/arquitecto?equipo">
                <Sparkles />
                {t('teams.withArchitect')}
              </Link>
            </Button>
          </div>
        </EmptyState>
      ) : teams.length === 0 ? (
        <div className={GRID}>{cards(loose)}</div>
      ) : (
        <>
          {teams.map((team) => {
            const members = draftsLast(agents.filter((a) => a.team_id === team.id))
            const active = members.filter((a) => a.state === 'running' || a.state === 'waiting')
            return (
              <section key={team.id} aria-label={team.name} className="flex flex-col gap-2.5">
                <div className="flex items-center gap-3">
                  <h3 className="text-[13px] font-bold">{team.name}</h3>
                  <span className="text-xs whitespace-nowrap text-muted-foreground">
                    {t('home.agents.teamMeta', { count: members.length, active: active.length })}
                  </span>
                  <span
                    aria-hidden
                    className="h-px flex-1 bg-[linear-gradient(90deg,var(--sep),transparent)]"
                  />
                  <button
                    type="button"
                    onClick={() => openNewAgent({ teamId: team.id })}
                    aria-label={t('teams.addAgentTo', { team: team.name })}
                    className="flex h-7 items-center gap-1 rounded-full px-2.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                  >
                    <Plus className="size-3" />
                    {t('teams.addAgent')}
                  </button>
                  <button
                    type="button"
                    onClick={() => openTeam(team)}
                    aria-label={t('teams.editTeam', { team: team.name })}
                    className="grid size-7 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
                  >
                    <Pencil className="size-3.5" />
                  </button>
                </div>
                {members.length > 0 ? (
                  <div className={GRID}>{cards(members)}</div>
                ) : (
                  <p className="text-xs text-muted-foreground">{t('teams.emptyTeam')}</p>
                )}
              </section>
            )
          })}
          {loose.length > 0 && (
            <section aria-label={t('teams.none')} className="flex flex-col gap-2.5">
              <div className="flex items-center gap-3">
                <h3 className="text-[13px] font-bold">{t('teams.none')}</h3>
                <span className="text-xs whitespace-nowrap text-muted-foreground">
                  {t('home.agents.count', { count: loose.length })}
                </span>
                <span
                  aria-hidden
                  className="h-px flex-1 bg-[linear-gradient(90deg,var(--sep),transparent)]"
                />
              </div>
              <div className={GRID}>{cards(loose)}</div>
            </section>
          )}
        </>
      )}
    </section>
  )
}
