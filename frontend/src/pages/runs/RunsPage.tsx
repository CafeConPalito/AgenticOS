import { SquareTerminal } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { useAgents } from '@/api/agents'
import { useProjects } from '@/api/projects'
import { useRuns } from '@/api/runs'
import { EmptyState } from '@/components/EmptyState'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { LaunchRunDialog } from './LaunchRunDialog'
import { RunsTable } from './RunsTable'

const ALL = '__all__' // Radix Select cannot use "" as an item value

export default function RunsPage() {
  const { t } = useTranslation()
  // Filters live in the URL so the list can be linked and survives a reload.
  const [params, setParams] = useSearchParams()
  const agentId = params.get('agente') ?? undefined
  const projectId = params.get('proyecto') ?? undefined
  const activeOnly = params.get('activas') === '1'
  const { data: runs, isPending } = useRuns({
    agentId,
    projectId,
    active: activeOnly ? true : undefined,
  })
  const agents = useAgents().data ?? []
  const projects = useProjects().data ?? []
  const [launching, setLaunching] = useState(false)
  const filtered = Boolean(agentId || projectId || activeOnly)

  function setFilter(key: string, value: string | undefined) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: true },
    )
  }

  return (
    <PageContainer>
      <PageHeader title={t('runs.title')} subtitle={t('runs.subtitle')} />
      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={agentId ?? ALL}
          onValueChange={(v) => setFilter('agente', v === ALL ? undefined : v)}
        >
          <SelectTrigger aria-label={t('runs.filters.agent')} className="w-[220px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('runs.filters.allAgents')}</SelectItem>
            {agents.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                {a.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={projectId ?? ALL}
          onValueChange={(v) => setFilter('proyecto', v === ALL ? undefined : v)}
        >
          <SelectTrigger aria-label={t('runs.filters.project')} className="w-[220px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('runs.filters.allProjects')}</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2">
          <Switch
            id="runs-active"
            checked={activeOnly}
            onCheckedChange={(on) => setFilter('activas', on ? '1' : undefined)}
          />
          <Label htmlFor="runs-active" className="font-normal">
            {t('runs.filters.activeOnly')}
          </Label>
        </div>
      </div>
      {isPending ? (
        <div aria-busy className="flex flex-col gap-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : runs && runs.length > 0 ? (
        <RunsTable runs={runs} />
      ) : filtered ? (
        <EmptyState icon={SquareTerminal} title={t('runs.emptyFiltered')} />
      ) : (
        <EmptyState
          icon={SquareTerminal}
          title={t('runs.emptyTitle')}
          description={t('runs.emptyDescription')}
        >
          <Button
            onClick={() => setLaunching(true)}
            className="bg-primary-action text-white hover:bg-primary-action-hover"
          >
            {t('header.primary.launchRun')}
          </Button>
        </EmptyState>
      )}
      <LaunchRunDialog open={launching} onOpenChange={setLaunching} />
    </PageContainer>
  )
}
