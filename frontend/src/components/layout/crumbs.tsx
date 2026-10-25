import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { Params } from 'react-router'
import { useAgent } from '@/api/agents'
import { useTeams } from '@/api/teams'
import { useProject } from '@/api/projects'
import { useRun } from '@/api/runs'
import { useTask } from '@/api/tasks'
import { runTitle } from '@/pages/runs/RunPage'

/** Route `handle`: how a route contributes to the header breadcrumb. */
export interface CrumbHandle {
  crumb: (params: Params) => ReactNode
}

export function TextCrumb({
  i18nKey,
}: {
  i18nKey:
    | 'nav.agents'
    | 'nav.projects'
    | 'nav.runs'
    | 'nav.board'
    | 'nav.inbox'
    | 'nav.usage'
    | 'nav.settings'
    | 'nav.clis'
    | 'nav.knowledge'
    | 'nav.connections'
}) {
  const { t } = useTranslation()
  return <>{t(i18nKey)}</>
}

export function AgentCrumb({ id }: { id?: string }) {
  const { data } = useAgent(id)
  const teams = useTeams().data
  if (!data) return <>…</>
  // Inicio › Equipo / Agente (phase 10): the team is part of where the agent lives.
  const team = teams?.find((x) => x.id === data.team_id)
  return (
    <>
      {team ? `${team.name} / ` : ''}
      {data.name}
      {data.role ? ` · ${data.role}` : ''}
    </>
  )
}

export function ProjectCrumb({ id }: { id?: string }) {
  const { data } = useProject(id)
  return <>{data?.name ?? '…'}</>
}

export function RunCrumb({ id }: { id?: string }) {
  const { data } = useRun(id)
  if (!data) return <>…</>
  return (
    <>
      {data.agent_name} · {runTitle(data, 48)}
    </>
  )
}

export function TaskCrumb({ id }: { id?: string }) {
  const { data } = useTask(id)
  if (!data) return <>…</>
  const title = data.title.length > 48 ? `${data.title.slice(0, 47)}…` : data.title
  return (
    <>
      {data.project_name} / {data.code} · {title}
    </>
  )
}
