import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAccounts } from '@/api/accounts'
import { useClis } from '@/api/clis'
import { useHome } from '@/api/home'
import { useInbox } from '@/api/inbox'
import { useTeams } from '@/api/teams'
import { useUsageToday } from '@/api/usage'
import { Skeleton } from '@/components/ui/skeleton'
import { useHealth } from '@/hooks/useHealth'
import { cn } from '@/lib/utils'
import { useUiPrefs } from '@/stores/ui-prefs'
import { AgentGrid } from './AgentGrid'
import { buildCliAlerts, SYSTEM_KINDS, sortRequests } from './alerts'
import { Greeting } from './Greeting'
import { HomeShortcuts } from './HomeShortcuts'
import { NeedsYouPanel } from './NeedsYouPanel'
import { SummaryAside } from './SummaryAside'

/** Inicio: what needs the person, what each agent is doing, and the summary column. */
export default function HomePage() {
  const { t } = useTranslation()
  const home = useHome()
  const pendingData = useInbox('pending').data
  // A stand-in backend (or an older one) may answer something else: show nothing, not a crash.
  const pending = useMemo(() => (Array.isArray(pendingData) ? pendingData : []), [pendingData])
  const clis = useClis().data
  const accounts = useAccounts().data
  const teams = useTeams().data
  const todayQuery = useUsageToday()
  const today =
    todayQuery.data && Array.isArray(todayQuery.data.agents) ? todayQuery.data : undefined
  const snoozed = useUiPrefs((s) => s.snoozedAlerts)
  const offline = useHealth().state !== 'connected'
  const [highlighted, setHighlighted] = useState<string | null>(null)

  const requests = useMemo(
    () => sortRequests(pending.filter((item) => !SYSTEM_KINDS.includes(item.kind))),
    [pending],
  )
  const alerts = useMemo(
    () => buildCliAlerts({ pending, clis, accounts, today, snoozed, t }),
    [pending, clis, accounts, today, snoozed, t],
  )
  const waitingRuns = useMemo(
    () => new Set(pending.flatMap((item) => (item.run_id ? [item.run_id] : []))),
    [pending],
  )

  if (!home.data || !Array.isArray(home.data.agents))
    return (
      <div
        aria-busy
        className="mx-auto grid max-w-[1520px] grid-cols-[minmax(0,1fr)_300px] gap-12 px-8 pt-7 max-xl:grid-cols-1"
      >
        <div className="flex flex-col gap-8">
          <Skeleton className="h-28 rounded-2xl" />
          <Skeleton className="h-40 rounded-2xl" />
          <div className="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-28 rounded-2xl" />
            ))}
          </div>
        </div>
        <Skeleton className="h-96 rounded-2xl" />
      </div>
    )

  const { agents, projects, counts } = home.data
  return (
    <div
      className={cn(
        'mx-auto grid max-w-[1520px] grid-cols-[minmax(0,1fr)_300px] items-start gap-12 px-8 pt-7 pb-14 max-xl:grid-cols-1',
        offline && 'opacity-60',
      )}
    >
      <div className="flex min-w-0 flex-col gap-8">
        <Greeting
          sessions={counts.sessions}
          working={counts.agents_working}
          waiting={requests.length + alerts.length}
          cost={today?.cost_usd ?? 0}
          tokens={today?.tokens ?? 0}
        />
        <HomeShortcuts />
        <NeedsYouPanel requests={requests} alerts={alerts} onHoverAgent={setHighlighted} />
        <AgentGrid
          agents={agents}
          teams={Array.isArray(teams) ? teams : []}
          usage={today?.agents ?? []}
          highlighted={highlighted}
          waitingRuns={waitingRuns}
        />
      </div>
      <SummaryAside
        agents={agents}
        projects={projects}
        today={today}
        clis={Array.isArray(clis) ? clis : []}
        accounts={Array.isArray(accounts) ? accounts : []}
      />
    </div>
  )
}
