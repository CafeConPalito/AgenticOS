import { GitCompareArrows } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { type AgentChangeRun, useAgentChanges } from '@/api/changes'
import { useProjects } from '@/api/projects'
import { ProjectChip } from '@/components/agentic/primitives'
import { ChangesBadge } from '@/components/changes/ChangesBadge'
import { ChangesSheet } from '@/components/changes/ChangesSheet'
import { EmptyState } from '@/components/EmptyState'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/time'

const ALL = 'all'

/** «Cambios» of an agent: the runs where it changed code, each opening its diff. */
export function ChangesTab({ agentId }: { agentId: string }) {
  const { t } = useTranslation()
  const projects = useProjects().data ?? []
  const [projectId, setProjectId] = useState(ALL)
  const runs = useAgentChanges(agentId, projectId === ALL ? undefined : projectId)
  const [open, setOpen] = useState<AgentChangeRun | null>(null)
  const projectColor = (id: string | null) =>
    projects.find((project) => project.id === id)?.color ?? 'var(--muted-foreground)'

  return (
    <section aria-label={t('agents.tabs.changes')} className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="text-[12.5px] text-muted-foreground">{t('changes.agent.project')}</span>
        <Select value={projectId} onValueChange={setProjectId}>
          <SelectTrigger aria-label={t('changes.agent.project')} className="h-8 w-[220px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('changes.agent.allProjects')}</SelectItem>
            {projects.map((project) => (
              <SelectItem key={project.id} value={project.id}>
                {project.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {runs.isPending ? (
        <Skeleton aria-busy className="h-24 rounded-lg" />
      ) : runs.data?.length ? (
        <ul className="overflow-hidden rounded-xl border border-sep shadow-card bg-card-grad">
          {runs.data.map((run) => {
            const label = run.task_code
              ? `${run.task_code} · ${run.task_title ?? ''}`
              : t('changes.agent.manual')
            return (
              <li key={run.run_id} className="border-b border-sep last:border-b-0">
                <button
                  type="button"
                  aria-label={t('changes.agent.open', { name: label })}
                  onClick={() => setOpen(run)}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-accent"
                >
                  <ProjectChip name={run.project_name} color={projectColor(run.project_id)} />
                  <span className="min-w-0 flex-1 truncate text-[13.5px]">{label}</span>
                  <time
                    className="shrink-0 text-xs text-muted-foreground"
                    dateTime={run.started_at ?? run.created_at}
                  >
                    {relativeTime(run.started_at ?? run.created_at)}
                  </time>
                  <ChangesBadge totals={run.totals} />
                </button>
              </li>
            )
          })}
        </ul>
      ) : (
        <EmptyState icon={GitCompareArrows} title={t('changes.agent.empty')} />
      )}
      {open && (
        <ChangesSheet
          open
          onOpenChange={(next) => !next && setOpen(null)}
          title={t('changes.titleRun')}
          target={{ kind: 'run', id: open.run_id }}
        />
      )}
    </section>
  )
}
